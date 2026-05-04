"""
src/collect/02_collect_offerings.py
-------------------------------------
Collects all SFU course section offerings from Coursys and stores
raw data in ml_section_offerings.

PURE COLLECTION — no filtering, no classification, no cleaning.
Every row the API returns gets inserted exactly as received.
All interpretation happens later in EDA notebooks.

The only unavoidable transforms:
  - HTML link parsed to extract dept, course number, section code
  - Enrollment string split into capacity / enrolled / waitlist integers
  These are just reading the API format, not processing decisions.

Resume safe: INSERT OR IGNORE skips rows already in DB.
Re-run the script at any time — it picks up where it left off.

Run from project root:
    python src/collect/02_collect_offerings.py
"""

import requests
import sqlite3
import time
import re
import os
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================
DB_PATH    = "data/raw/sfu_ml.db"
BASE_URL   = "https://coursys.sfu.ca/browse/"
RATE_LIMIT = 1.2
LOG_FILE   = "data/raw/collection_log.txt"


# ============================================================
# MINIMAL PARSERS
# Only parses what is needed to read the API response format.
# No decisions, no interpretation.
# ============================================================

def parse_section_link(raw_html):
    """
    Extract dept, course number, section code from Coursys HTML link.
    '<a href="/browse/info/2025fa-cmpt-276-d1">CMPT 276 D100</a>'
    -> ('CMPT', '276', 'D100')
    Returns (None, None, None) if the HTML can't be parsed.
    This is unavoidable — the API returns HTML, not plain text.
    """
    match = re.search(r">([^<]+)</a>", raw_html)
    if not match:
        return None, None, None
    parts = match.group(1).strip().split()
    if len(parts) < 3:
        return None, None, None
    return parts[0], parts[1], parts[2]


def parse_enrollment(raw):
    """
    Split enrollment string into (enrolled, capacity, waitlist).
    This is unavoidable — the API returns a formatted string, not integers.

    Confirmed formats from test data:
      "96/100"          -> (96,   100,  0)
      "138/150 (+33)"   -> (138,  150,  33)
      "?/20"            -> (None, 20,   None)
      "?/?"             -> (None, None, None)
      "0/50"            -> (0,    50,   0)    zero enrolled is valid

    Over-enrolled e.g. "104/100" stored as-is — real demand signal.
    """
    raw = str(raw).strip()

    # "N/N (+W)"
    m = re.match(r"^(\d+)/(\d+)\s*\(\+(\d+)\)$", raw)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    # "N/N"
    m = re.match(r"^(\d+)/(\d+)$", raw)
    if m:
        return int(m.group(1)), int(m.group(2)), 0

    # "?/N"
    m = re.match(r"^\?/(\d+)$", raw)
    if m:
        return None, int(m.group(1)), None

    # "?/?" or anything unrecognised
    return None, None, None


# ============================================================
# API
# ============================================================

def fetch(dept, semester_code):
    """
    Fetch all sections for one dept + term from Coursys.
    length=-1 returns all rows (no pagination).
    Returns (rows, error_message).
    """
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


# ============================================================
# MAIN
# ============================================================

def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found.")
        print("Run sql/run_setup.py first.")
        return

    conn   = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()

    # Load terms
    cursor.execute("""
        SELECT ml_term_id, year, term, semester_code, is_covid_affected
        FROM ml_terms ORDER BY year, term_order
    """)
    terms = cursor.fetchall()

    # Load course lookup: (dept_code, course_number) -> ml_course_id
    # Used to set ml_course_id where we can match, NULL where we can't
    cursor.execute("SELECT dept_code, course_number, ml_course_id FROM ml_courses")
    course_lookup = {}
    for dept_code, course_number, ml_course_id in cursor.fetchall():
        course_lookup[(dept_code.upper(), str(course_number))] = ml_course_id

    # Get all dept codes from ml_courses
    cursor.execute("SELECT DISTINCT dept_code FROM ml_courses ORDER BY dept_code")
    depts = [row[0].upper() for row in cursor.fetchall()]

    if not depts:
        print("ERROR: ml_courses is empty. Run src/collect/01_init_db.py first.")
        conn.close()
        return

    total_calls = len(terms) * len(depts)
    print(f"\n{'='*60}")
    print(f"  SFU Offerings Collection — Raw Data")
    print(f"  Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Terms:    {len(terms)}")
    print(f"  Depts:    {len(depts)}")
    print(f"  Est time: ~{int(total_calls * RATE_LIMIT / 60)} minutes")
    print(f"{'='*60}\n")

    log_lines   = []
    grand_total = {"inserted": 0, "ignored": 0, "errors": 0, "parse_fail": 0}

    for t_idx, (ml_term_id, year, term, sem_code, is_covid) in enumerate(terms, 1):
        label      = f"{year} {term.capitalize()}"
        covid_note = " [COVID]" if is_covid else ""
        t_inserted = 0

        print(f"[{t_idx:>2}/{len(terms)}] {label}{covid_note} (code={sem_code})")

        for d_idx, dept in enumerate(depts, 1):
            raw_rows, error = fetch(dept, sem_code)

            if error:
                msg = f"  ERROR {dept}: {error}"
                print(msg)
                log_lines.append(f"{label} {dept}: ERROR {error}")
                grand_total["errors"] += 1
                time.sleep(RATE_LIMIT)
                continue

            if not raw_rows:
                # No offerings this dept+term — normal, not an error
                time.sleep(RATE_LIMIT)
                continue

            for row in raw_rows:
                if len(row) < 6:
                    grand_total["parse_fail"] += 1
                    continue

                _, section_html, _, enroll_str, instructor, campus = (
                    row[0], row[1], row[2], row[3], row[4], row[5]
                )

                api_dept, course_number, section_code = parse_section_link(section_html)
                if not course_number or not section_code:
                    grand_total["parse_fail"] += 1
                    continue

                enrolled, capacity, waitlist = parse_enrollment(enroll_str)

                # Look up ml_course_id — NULL if not in our courses table
                # We still insert the row, just without the foreign key
                ml_course_id = course_lookup.get(
                    (api_dept or dept, str(course_number))
                )

                cursor.execute("""
                    INSERT OR IGNORE INTO ml_section_offerings (
                        ml_course_id, ml_term_id,
                        dept_code, course_number, section_code,
                        instructor, campus,
                        capacity, enrolled, waitlist
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ml_course_id,         # None if unmatched — stored as NULL
                    ml_term_id,
                    api_dept or dept,
                    str(course_number),
                    str(section_code),
                    str(instructor).strip() if instructor else None,
                    str(campus).strip() if campus else None,
                    capacity,
                    enrolled,
                    waitlist,
                ))

                if cursor.rowcount == 1:
                    t_inserted += 1
                    grand_total["inserted"] += 1
                else:
                    grand_total["ignored"] += 1

            conn.commit()

            if d_idx % 20 == 0:
                print(f"    {d_idx}/{len(depts)} depts, {t_inserted} rows so far...")

            time.sleep(RATE_LIMIT)

        print(f"    done — {t_inserted} rows inserted\n")
        log_lines.append(f"{label}: {t_inserted} rows inserted")

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  COLLECTION COMPLETE")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    print(f"  Inserted:      {grand_total['inserted']}")
    print(f"  Already existed (ignored): {grand_total['ignored']}")
    print(f"  API errors:    {grand_total['errors']}")
    print(f"  Parse failures:{grand_total['parse_fail']}")

    print(f"\n  Rows per term:")
    cursor.execute("""
        SELECT t.year, t.term, COUNT(*) as n
        FROM ml_section_offerings o
        JOIN ml_terms t ON o.ml_term_id = t.ml_term_id
        GROUP BY t.year, t.term
        ORDER BY t.year, t.term_order
    """)
    for year, term, n in cursor.fetchall():
        print(f"    {year} {term.capitalize():<8}  {n:>6} rows")

    print(f"\n  Matched vs unmatched courses:")
    cursor.execute("""
        SELECT
            SUM(CASE WHEN ml_course_id IS NOT NULL THEN 1 ELSE 0 END) as matched,
            SUM(CASE WHEN ml_course_id IS NULL     THEN 1 ELSE 0 END) as unmatched
        FROM ml_section_offerings
    """)
    matched, unmatched = cursor.fetchone()
    print(f"    Matched (ml_course_id set):   {matched}")
    print(f"    Unmatched (ml_course_id NULL): {unmatched}")

    print(f"\n  Enrollment data coverage (all rows):")
    cursor.execute("""
        SELECT
            COUNT(*)                                                    as total,
            SUM(CASE WHEN enrolled IS NOT NULL
                      AND capacity IS NOT NULL THEN 1 ELSE 0 END)      as full_data,
            SUM(CASE WHEN enrolled IS NULL
                      AND capacity IS NOT NULL THEN 1 ELSE 0 END)      as cap_only,
            SUM(CASE WHEN capacity IS NULL THEN 1 ELSE 0 END)          as no_data,
            SUM(CASE WHEN waitlist > 0 THEN 1 ELSE 0 END)              as has_waitlist
        FROM ml_section_offerings
    """)
    total, full, cap_only, no_data, wl = cursor.fetchone()
    print(f"    Total rows:          {total}")
    print(f"    Full (N/N):          {full}  ({full/total*100:.1f}%)")
    print(f"    Capacity only (?/N): {cap_only}  ({cap_only/total*100:.1f}%)")
    print(f"    No data (?/?):       {no_data}  ({no_data/total*100:.1f}%)")
    print(f"    Has waitlist:        {wl}  ({wl/total*100:.1f}%)")

    os.makedirs("data/raw", exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Inserted: {grand_total['inserted']}\n")
        f.write(f"Errors:   {grand_total['errors']}\n\n")
        f.write("\n".join(log_lines))
    print(f"\n  Log: {LOG_FILE}")
    print(f"{'='*60}\n")

    conn.close()


if __name__ == "__main__":
    main()