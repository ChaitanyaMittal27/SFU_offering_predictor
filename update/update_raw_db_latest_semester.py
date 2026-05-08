"""
update/update_raw_db_latest_semester.py
-----------------------------------------
Adds ONE new semester's section offerings to sfu_ml.db.

Fully self-contained — no imports from the rest of the project.

Usage:
    python update/update_raw_db_latest_semester.py            # uses today's date
    python update/update_raw_db_latest_semester.py 2026-09-01 # explicit date

Semester boundaries (SFU):
    Spring  Jan – Apr   term_order = 1
    Summer  May – Aug   term_order = 2
    Fall    Sep – Dec   term_order = 3

semester_code formula (SFU Coursys):
    1200 + (year - 2020) * 10 + offset
    where offset: spring=1, summer=4, fall=7
    e.g. Spring 2026 = 1200 + 60 + 1 = 1261
"""

import requests
import sqlite3
import time
import re
import sys
import os
from datetime import datetime, date

# ── config ────────────────────────────────────────────────────────────────────
DB_PATH    = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "sfu_ml.db")
BASE_URL   = "https://coursys.sfu.ca/browse/"
RATE_LIMIT = 1.2   # seconds between API calls


# ── semester derivation ───────────────────────────────────────────────────────
_SEMESTER_MAP = {
    1: ("spring", 1, 1),   # month range start, term_order, code_offset
    2: ("spring", 1, 1),
    3: ("spring", 1, 1),
    4: ("spring", 1, 1),
    5: ("summer", 2, 4),
    6: ("summer", 2, 4),
    7: ("summer", 2, 4),
    8: ("summer", 2, 4),
    9: ("fall",   3, 7),
    10: ("fall",  3, 7),
    11: ("fall",  3, 7),
    12: ("fall",  3, 7),
}


def derive_semester(d: date) -> tuple:
    """
    Returns (year, term_name, term_order, semester_code) for a given date.
    e.g. date(2026, 3, 15) -> (2026, 'spring', 1, 1261)
    """
    term_name, term_order, code_offset = _SEMESTER_MAP[d.month]
    year          = d.year
    semester_code = 1200 + (year - 2020) * 10 + code_offset
    return year, term_name, term_order, semester_code


# ── parsers (copied logic from 02_collect_offerings.py) ──────────────────────
def _parse_section_link(raw_html: str):
    match = re.search(r">([^<]+)</a>", raw_html)
    if not match:
        return None, None, None
    parts = match.group(1).strip().split()
    if len(parts) < 3:
        return None, None, None
    return parts[0], parts[1], parts[2]


def _parse_enrollment(raw: str):
    raw = str(raw).strip()
    m = re.match(r"^(\d+)/(\d+)\s*\(\+(\d+)\)$", raw)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r"^(\d+)/(\d+)$", raw)
    if m:
        return int(m.group(1)), int(m.group(2)), 0
    m = re.match(r"^\?/(\d+)$", raw)
    if m:
        return None, int(m.group(1)), None
    return None, None, None


# ── API ───────────────────────────────────────────────────────────────────────
def _fetch(dept: str, semester_code: int):
    url = (f"{BASE_URL}?subject[]={dept}"
           f"&semester[]={semester_code}"
           f"&tabledata=yes&length=-1")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("result") != "ok":
            return None, f"result={data.get('result')}"
        return data.get("data", []), None
    except Exception as e:
        return None, str(e)


# ── DB helpers ────────────────────────────────────────────────────────────────
def _get_or_create_term(cursor, year: int, term_name: str,
                         term_order: int, semester_code: int) -> int:
    """
    Returns ml_term_id for this semester. Creates the row in ml_terms if absent.
    New terms are always is_covid_affected=0.
    """
    row = cursor.execute(
        "SELECT ml_term_id FROM ml_terms WHERE semester_code = ?",
        (semester_code,)
    ).fetchone()

    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO ml_terms (year, term, term_order, semester_code, is_covid_affected)
        VALUES (?, ?, ?, ?, 0)
        """,
        (year, term_name, term_order, semester_code)
    )
    print(f"  Created new ml_terms row: {term_name} {year} (code={semester_code})")
    return cursor.lastrowid


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    # ── 1. parse date arg ────────────────────────────────────────────────────
    if len(sys.argv) > 1:
        try:
            run_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            print(f"ERROR: date must be YYYY-MM-DD, got: {sys.argv[1]!r}")
            sys.exit(1)
    else:
        run_date = date.today()

    year, term_name, term_order, semester_code = derive_semester(run_date)

    print(f"\n{'='*60}")
    print(f"  update_raw_db_latest_semester.py")
    print(f"  Run date:  {run_date}")
    print(f"  Semester:  {term_name.capitalize()} {year}  (code={semester_code})")
    print(f"{'='*60}\n")

    # ── 2. connect ───────────────────────────────────────────────────────────
    db_path = os.path.normpath(DB_PATH)
    if not os.path.exists(db_path):
        print(f"ERROR: DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()

    # ── 3. check for existing data ───────────────────────────────────────────
    existing_term = cursor.execute(
        "SELECT ml_term_id FROM ml_terms WHERE semester_code = ?",
        (semester_code,)
    ).fetchone()

    if existing_term:
        existing_rows = cursor.execute(
            "SELECT COUNT(*) FROM ml_section_offerings WHERE ml_term_id = ?",
            (existing_term[0],)
        ).fetchone()[0]
        if existing_rows > 0:
            print(f"  {term_name.capitalize()} {year} already has {existing_rows:,} rows in DB.")
            print(f"  INSERT OR IGNORE will skip duplicates — proceeding to catch any new rows.\n")

    # ── 4. get or create term row ─────────────────────────────────────────────
    ml_term_id = _get_or_create_term(cursor, year, term_name, term_order, semester_code)
    conn.commit()
    print(f"  ml_term_id: {ml_term_id}")

    # ── 5. load course lookup and dept list ───────────────────────────────────
    course_lookup = {}
    for dept_code, course_number, ml_course_id in cursor.execute(
        "SELECT dept_code, course_number, ml_course_id FROM ml_courses"
    ):
        course_lookup[(dept_code.upper(), str(course_number))] = ml_course_id

    depts = [row[0].upper() for row in cursor.execute(
        "SELECT DISTINCT dept_code FROM ml_courses ORDER BY dept_code"
    )]

    if not depts:
        print("ERROR: ml_courses is empty.")
        conn.close()
        sys.exit(1)

    print(f"  Departments to collect: {len(depts)}")
    print(f"  Estimated time: ~{int(len(depts) * RATE_LIMIT / 60)} minutes\n")

    # ── 6. collect ────────────────────────────────────────────────────────────
    inserted   = 0
    ignored    = 0
    errors     = 0
    parse_fail = 0

    for d_idx, dept in enumerate(depts, 1):
        raw_rows, error = _fetch(dept, semester_code)

        if error:
            print(f"  [{d_idx:>3}/{len(depts)}] {dept:<10} ERROR: {error}")
            errors += 1
            time.sleep(RATE_LIMIT)
            continue

        if not raw_rows:
            time.sleep(RATE_LIMIT)
            continue

        for row in raw_rows:
            if len(row) < 6:
                parse_fail += 1
                continue

            _, section_html, _, enroll_str, instructor, campus = (
                row[0], row[1], row[2], row[3], row[4], row[5]
            )

            api_dept, course_number, section_code = _parse_section_link(section_html)
            if not course_number or not section_code:
                parse_fail += 1
                continue

            enrolled, capacity, waitlist = _parse_enrollment(enroll_str)
            ml_course_id = course_lookup.get((api_dept or dept, str(course_number)))

            cursor.execute(
                """
                INSERT OR IGNORE INTO ml_section_offerings (
                    ml_course_id, ml_term_id,
                    dept_code, course_number, section_code,
                    instructor, campus,
                    capacity, enrolled, waitlist
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ml_course_id,
                    ml_term_id,
                    api_dept or dept,
                    str(course_number),
                    str(section_code),
                    str(instructor).strip() if instructor else None,
                    str(campus).strip()     if campus     else None,
                    capacity,
                    enrolled,
                    waitlist,
                ),
            )

            if cursor.rowcount == 1:
                inserted += 1
            else:
                ignored += 1

        conn.commit()

        if d_idx % 20 == 0 or d_idx == len(depts):
            print(f"  [{d_idx:>3}/{len(depts)}] {inserted} inserted so far...")

        time.sleep(RATE_LIMIT)

    # ── 7. summary ────────────────────────────────────────────────────────────
    conn.close()

    total = inserted + ignored
    print(f"\n{'='*60}")
    print(f"  DONE — {term_name.capitalize()} {year}")
    print(f"  Inserted:   {inserted:,}")
    print(f"  Duplicates: {ignored:,}")
    print(f"  API errors: {errors:,}")
    print(f"  Parse fail: {parse_fail:,}")
    print(f"  Total rows: {total:,}")
    print(f"{'='*60}\n")

    if errors > 0:
        print(f"WARNING: {errors} API errors occurred. Rerun to retry failed depts.")
        sys.exit(1)


if __name__ == "__main__":
    main()