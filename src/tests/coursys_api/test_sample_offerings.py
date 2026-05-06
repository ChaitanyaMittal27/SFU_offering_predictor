"""
src/test/coursys_api/test_sample_offerings.py
----------------------------------------------
Final validated version. All known SFU section types classified.
Enrollment parser handles all 3 formats (?/?, ?/N, N/N).
Over-enrolled stored as-is — real signal, not an anomaly.

Run from project root:
    python src/test/coursys_api/test_sample_offerings.py

Output: src/test/coursys_api/output/
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
OUTPUT_DIR = "src/test/coursys_api/output"
BASE_URL   = "https://coursys.sfu.ca/browse/"
RATE_LIMIT = 1.2

TEST_CASES = [
    {
        "label":       "CMPT_fall_2025",
        "description": "Popular dept, current term",
        "dept":        "CMPT",
        "semester":    1257,
        "term_label":  "Fall 2025",
    },
    {
        "label":       "CMPT_summer_2025",
        "description": "Summer — sparser offerings",
        "dept":        "CMPT",
        "semester":    1254,
        "term_label":  "Summer 2025",
    },
    {
        "label":       "CMPT_fall_2020",
        "description": "COVID term — confirms historical data",
        "dept":        "CMPT",
        "semester":    1207,
        "term_label":  "Fall 2020",
    },
    {
        "label":       "MATH_fall_2025",
        "description": "Second dept — parsing sanity check",
        "dept":        "MATH",
        "semester":    1257,
        "term_label":  "Fall 2025",
    },
    {
        "label":       "BUS_fall_2025",
        "description": "Biggest dept — stress test",
        "dept":        "BUS",
        "semester":    1257,
        "term_label":  "Fall 2025",
    },
    {
        "label":       "CA_fall_2025",
        "description": "Mixed section types — G, E, OL",
        "dept":        "CA",
        "semester":    1257,
        "term_label":  "Fall 2025",
    },
]


# ============================================================
# PARSING — final production versions
# These exact functions will be copied into 02_collect_offerings.py
# ============================================================

def parse_section_link(raw_html: str):
    """
    '<a href="...">CMPT 276 D100</a>' -> ('CMPT', '276', 'D100')
    Returns (None, None, None) if parsing fails.
    """
    match = re.search(r">([^<]+)</a>", raw_html)
    if not match:
        return None, None, None
    full  = match.group(1).strip()
    parts = full.split()
    if len(parts) < 3:
        return None, None, None
    return parts[0], parts[1], parts[2]


def parse_section_type(section_code: str):
    """
    Classify SFU section codes -> (section_type, is_primary).

    PRIMARY (is_primary=True):
      Standalone lectures with their own enrollment + capacity.
      These are the only rows used in ML capacity/enrollment models.

      D  — standard in-person lecture (D100, D200...)
      E  — evening lecture, standalone (E100, E200...)
      O  — online lecture (O100, OL01, OP01...)
      C  — old distance education (C100, C200...)
      J  — Nights or Weekends cohort lecture
      G  — grad / alternate campus lecture (G100, G200...)
      N  — night section variant

    NON-PRIMARY (is_primary=False):
      Sub-sections tied to a lecture. Enrollment overlaps — must not
      be double-counted with the primary section.

      I  — individual/directed study (I100, I200...) — grad sub-section
      L  — laboratory (L100, LA01, LB01, LAB1...)
      T  — tutorial
      S  — seminar sub-section
      P  — practicum
      W  — workshop
      R  — recitation / lab rotation
      B  — blended/hybrid sub-section
    """
    code = section_code.upper().strip()

    # PRIMARY
    if code.startswith("D"): return "LEC",    True
    if code.startswith("E"): return "LEC",    True   # evening — standalone
    if code.startswith("O"): return "ONLINE", True   # O100, OL01, OP01...
    if code.startswith("C"): return "DIST",   True   # old distance C100/C200
    if code.startswith("J"): return "LEC",    True   # NoW cohort
    if code.startswith("G"): return "LEC",    True   # grad / alt campus
    if code.startswith("N"): return "LEC",    True   # night section

    # NON-PRIMARY
    if code.startswith("I"):                  return "IND",  False  # individual/directed
    if code.startswith("L") or "LAB" in code: return "LAB",  False
    if code.startswith("T") or "TUT" in code: return "TUT",  False
    if code.startswith("S") or "SEM" in code: return "SEM",  False
    if code.startswith("P") or "PRA" in code: return "PRA",  False
    if code.startswith("W") or "WKS" in code: return "WKS",  False
    if code.startswith("R"):                  return "REC",  False
    if code.startswith("B"):                  return "BLD",  False  # blended

    return "OTHER", False


def parse_enrollment(raw: str):
    """
    Parse the enrollment/capacity string from Coursys.

    Three formats exist in the wild:
      "96/100"  -> enrolled=96,   capacity=100,  fill_rate=96.0
      "?/20"    -> enrolled=None, capacity=20,   fill_rate=None
      "?/?"     -> enrolled=None, capacity=None, fill_rate=None

    Over-enrolled (enrolled > capacity) is stored as-is.
    It is real signal — a course that consistently goes over capacity
    tells the model something important about demand.

    Returns (enrolled, capacity, fill_rate).
    """
    raw = str(raw).strip()

    # Try full "number/number" parse first
    full_match = re.match(r"^(\d+)/(\d+)$", raw)
    if full_match:
        enrolled = int(full_match.group(1))
        capacity = int(full_match.group(2))
        fill_rate = round(enrolled / capacity * 100, 2) if capacity > 0 else None
        return enrolled, capacity, fill_rate

    # Try "?/number" — capacity known, enrollment not public
    partial_match = re.match(r"^\?/(\d+)$", raw)
    if partial_match:
        capacity = int(partial_match.group(1))
        return None, capacity, None

    # "?/?" or anything else — nothing known
    return None, None, None


def fetch(dept: str, semester_code: int):
    """Hit Coursys API with length=-1 to get all rows."""
    url = (f"{BASE_URL}?subject[]={dept}"
           f"&semester[]={semester_code}&tabledata=yes&length=-1")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("result") != "ok":
            return None, f"API result: {data.get('result')}"
        return data.get("data", []), None
    except Exception as e:
        return None, str(e)


def lookup_courses(conn, dept_code: str):
    """Load all courses for a dept from ml_courses."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT course_number, ml_course_id FROM ml_courses WHERE dept_code = ?",
        (dept_code.upper(),)
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


# ============================================================
# SINGLE TEST RUNNER
# ============================================================

def run_test(case: dict, conn) -> dict:
    dept  = case["dept"]
    sem   = case["semester"]
    label = case["label"]
    lines = []

    def w(line=""): lines.append(line)

    w(f"{'='*70}")
    w(f"  Test: {label}")
    w(f"  {case['description']}")
    w(f"  Dept: {dept}   Semester: {sem}  ({case['term_label']})")
    w(f"  Run:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w(f"{'='*70}")
    w()

    raw_rows, error = fetch(dept, sem)

    if error:
        w(f"  ERROR: {error}")
        w("  VERDICT: FAIL")
        result = {"label": label, "status": "ERROR", "total": 0,
                  "primary": 0, "unmatched": 0, "unknown_types": set(), "anomalies": []}
        _write(label, lines)
        return result

    total_rows = len(raw_rows)
    w(f"  API returned {total_rows} rows")
    w()

    if total_rows == 0:
        w("  VERDICT: EMPTY — zero rows (dept code mismatch or no offerings)")
        result = {"label": label, "status": "EMPTY", "total": 0,
                  "primary": 0, "unmatched": 0, "unknown_types": set(), "anomalies": []}
        _write(label, lines)
        return result

    course_map    = lookup_courses(conn, dept)
    type_counts   = {}
    anomalies     = []
    unknown_types = set()
    unmatched     = []
    primary_rows  = []
    parsed_rows   = []

    for row in raw_rows:
        if len(row) < 6:
            anomalies.append(f"Short row ({len(row)} fields): {row}")
            continue

        _, section_html, _, enroll_str, instructor, campus = (
            row[0], row[1], row[2], row[3], row[4], row[5]
        )

        api_dept, number, section_code = parse_section_link(section_html)
        if not section_code:
            anomalies.append(f"Unparseable link: {section_html}")
            continue

        stype, is_primary   = parse_section_type(section_code)
        enrolled, capacity, fill_rate = parse_enrollment(enroll_str)

        type_counts[stype] = type_counts.get(stype, 0) + 1
        if stype == "OTHER":
            unknown_types.add(section_code)

        ml_id   = course_map.get(str(number))
        matched = ml_id is not None
        if not matched:
            unmatched.append(f"{api_dept} {number}")

        # Anomalies: only things that indicate a data problem
        # NOT over-enrolled — that's real signal and stored as-is
        notes = []
        if enrolled is None and capacity is None:
            notes.append("no enrollment data (?/?)")
        if capacity == 0:
            notes.append("zero capacity")
        if not instructor or str(instructor).strip() == "":
            notes.append("no instructor")
        if stype == "OTHER":
            notes.append(f"unknown section type")
        if notes:
            anomalies.append(
                f"{api_dept} {number} {section_code}: {', '.join(notes)}"
            )

        parsed_rows.append({
            "dept": api_dept, "number": number, "section": section_code,
            "type": stype, "primary": is_primary,
            "enrolled": enrolled, "capacity": capacity,
            "fill_rate": fill_rate, "instructor": instructor,
            "campus": campus, "matched": matched,
            "raw_enroll": enroll_str,
        })
        if is_primary:
            primary_rows.append(parsed_rows[-1])

    # ---- Table output ----
    w(f"  {'COURSE':<12} {'SEC':<8} {'TYPE':<7} {'PRI':<5} "
      f"{'RAW':<10} {'FILL%':>6}  {'MATCH':<6}  INSTRUCTOR")
    w("  " + "-"*90)
    for r in parsed_rows:
        enr = str(r["enrolled"]) if r["enrolled"] is not None else "?"
        cap = str(r["capacity"]) if r["capacity"] is not None else "?"
        fil = f"{r['fill_rate']:.1f}" if r["fill_rate"] is not None else "?"
        mtc = "YES" if r["matched"] else "NO"
        pri = "YES" if r["primary"] else "no"
        raw = r["raw_enroll"].strip()
        w(f"  {r['dept']+' '+r['number']:<12} {r['section']:<8} "
          f"{r['type']:<7} {pri:<5} {raw:<10} {fil:>6}%  {mtc:<6}  {r['instructor']}")

    # ---- Stats ----
    w()
    w(f"  Section type breakdown:")
    primary_types = {"LEC", "ONLINE", "DIST"}
    for t, n in sorted(type_counts.items()):
        flag = "(primary)" if t in primary_types else "(non-primary)"
        w(f"    {t:<10} {n:>4} sections  {flag}")

    # Enrollment coverage for primary sections only
    w()
    w(f"  Enrollment data coverage (primary sections only):")
    p_full     = sum(1 for r in primary_rows if r["enrolled"] is not None and r["capacity"] is not None)
    p_cap_only = sum(1 for r in primary_rows if r["enrolled"] is None and r["capacity"] is not None)
    p_none     = sum(1 for r in primary_rows if r["capacity"] is None)
    p_over     = sum(1 for r in primary_rows if r["enrolled"] and r["capacity"] and r["enrolled"] > r["capacity"])
    w(f"    Full (enrolled + capacity):  {p_full}")
    w(f"    Capacity only (?/N):         {p_cap_only}")
    w(f"    No data (?/?):               {p_none}")
    w(f"    Over-enrolled (stored raw):  {p_over}")

    w()
    w(f"  Course matching:")
    w(f"    Total rows:    {total_rows}")
    w(f"    Primary only:  {len(primary_rows)}")
    w(f"    Matched:       {total_rows - len(unmatched)}")
    w(f"    Unmatched:     {len(unmatched)}")
    if unmatched:
        seen = set()
        w(f"    (courses in Coursys but not in ml_courses — will be skipped)")
        for u in unmatched:
            if u not in seen:
                w(f"      {u}")
                seen.add(u)

    w()
    w(f"  Anomalies ({len(anomalies)} total):")
    if anomalies:
        for a in anomalies[:30]:
            w(f"    {a}")
        if len(anomalies) > 30:
            w(f"    ... and {len(anomalies)-30} more")
    else:
        w(f"    None")

    if unknown_types:
        w()
        w(f"  *** UNKNOWN section types — add to parse_section_type: ***")
        for u in sorted(unknown_types):
            w(f"    {u}")

    # Verdict
    issues = []
    if total_rows <= 10:   issues.append(f"only {total_rows} rows — pagination?")
    if unknown_types:      issues.append(f"unknown types: {unknown_types}")

    w()
    w(f"{'='*70}")
    if not issues:
        w(f"  VERDICT: PASS")
    else:
        w(f"  VERDICT: REVIEW — {', '.join(issues)}")

    _write(label, lines)

    return {
        "label":         label,
        "status":        "PASS" if not issues else "REVIEW",
        "total":         total_rows,
        "primary":       len(primary_rows),
        "unmatched":     len(unmatched),
        "unknown_types": unknown_types,
        "anomalies":     anomalies,
        "p_full":        p_full,
        "p_cap_only":    p_cap_only,
        "p_none":        p_none,
        "p_over":        p_over,
    }


def _write(label: str, lines: list):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{label}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Written: {path}")


# ============================================================
# SUMMARY
# ============================================================

def write_summary(results: list):
    lines = []
    lines.append("=" * 70)
    lines.append("  COURSYS API — FINAL VALIDATION SUMMARY")
    lines.append(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)
    lines.append("")

    all_unknown = set()
    any_fail    = False

    lines.append(
        f"  {'TEST CASE':<25} {'STATUS':<8} {'ROWS':<6} {'PRIMARY':<8} "
        f"{'UNMATCHED':<10} {'FULL ENR':<9} {'CAP ONLY':<9} {'NO DATA':<8} OVER"
    )
    lines.append("  " + "-"*95)

    for r in results:
        if r["status"] in ("ERROR", "REVIEW", "EMPTY"):
            any_fail = True
        all_unknown |= r.get("unknown_types", set())
        lines.append(
            f"  {r['label']:<25} {r['status']:<8} {r['total']:<6} "
            f"{r['primary']:<8} {r['unmatched']:<10} "
            f"{r.get('p_full',0):<9} {r.get('p_cap_only',0):<9} "
            f"{r.get('p_none',0):<8} {r.get('p_over',0)}"
        )

    lines.append("")

    lines.append("  Pagination check:")
    paginated = [r for r in results if r["total"] <= 10 and r["status"] != "EMPTY"]
    if paginated:
        lines.append("  WARNING — these returned <=10 rows (pagination still active):")
        for r in paginated:
            lines.append(f"    {r['label']}: {r['total']} rows")
    else:
        lines.append("  OK — all tests returned >10 rows")

    lines.append("")

    if all_unknown:
        lines.append("  *** STILL UNKNOWN section types — fix before collection: ***")
        for u in sorted(all_unknown):
            lines.append(f"    {u}")
        lines.append("")

    lines.append("  Enrollment note:")
    lines.append("  - FULL rows:     enrolled + capacity stored, fill_rate computed")
    lines.append("  - CAP ONLY rows: capacity stored, enrolled=NULL, fill_rate=NULL")
    lines.append("  - NO DATA rows:  both NULL — thesis/directed study registrations")
    lines.append("  - OVER rows:     stored as-is. Real signal — do not cap or filter.")
    lines.append("")

    lines.append("  Overall verdict:")
    if not any_fail and not all_unknown:
        lines.append("  ALL PASS — ready to write 02_collect_offerings.py")
    else:
        lines.append("  REVIEW — fix issues above before proceeding")

    lines.append("=" * 70)

    path = os.path.join(OUTPUT_DIR, "summary.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print()
    print("\n".join(lines))


# ============================================================
# MAIN
# ============================================================

def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found.")
        print("Run sql/run_setup.py and src/collect/01_init_db.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    results = []

    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] {case['label']} — {case['description']}")
        result = run_test(case, conn)
        results.append(result)
        if i < len(TEST_CASES):
            time.sleep(RATE_LIMIT)

    conn.close()
    write_summary(results)


if __name__ == "__main__":
    main()