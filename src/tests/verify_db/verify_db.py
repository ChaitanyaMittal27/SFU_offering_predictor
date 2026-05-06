"""
src/test/verify_db.py
----------------------
Validates sfu_ml.db after collection.
Runs SQL checks and prints a clear report.
Writes output to src/test/verify_db_output.txt as well.

Run from project root:
    python src/test/verify_db.py
"""

import sqlite3
import os
from datetime import datetime

DB_PATH    = "data/raw/sfu_ml.db"
OUTPUT_FILE = "src/test/verify_db_output.txt"

lines = []

def w(line=""):
    print(line)
    lines.append(line)

def section(title):
    w()
    w(f"{'='*60}")
    w(f"  {title}")
    w(f"{'='*60}")

def check(label, value, expected=None, warn_if_zero=False):
    """Print a check with PASS/WARN indicator."""
    if expected is not None:
        status = "PASS" if value == expected else "WARN"
    elif warn_if_zero:
        status = "WARN" if value == 0 else "PASS"
    else:
        status = "INFO"
    w(f"  [{status}] {label}: {value}")


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found.")
        return

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    w(f"  SFU ML Database Verification")
    w(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w(f"  DB:  {DB_PATH}")

    # --------------------------------------------------------
    section("1. TABLE ROW COUNTS")
    # --------------------------------------------------------
    for table in ["ml_terms", "ml_courses", "ml_section_offerings"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        n = cursor.fetchone()[0]
        check(table, n, warn_if_zero=True)

    # --------------------------------------------------------
    section("2. ml_terms — all 18 semesters present")
    # --------------------------------------------------------
    cursor.execute("SELECT COUNT(*) FROM ml_terms")
    check("Total terms", cursor.fetchone()[0], expected=18)

    cursor.execute("SELECT COUNT(*) FROM ml_terms WHERE is_covid_affected = 1")
    check("COVID-affected terms", cursor.fetchone()[0], expected=6)

    cursor.execute("""
        SELECT year, term, semester_code, is_covid_affected
        FROM ml_terms ORDER BY year, term_order
    """)
    w()
    w(f"  {'Year':<6} {'Term':<8} {'Code':<6} COVID")
    w(f"  {'-'*30}")
    for year, term, code, covid in cursor.fetchall():
        flag = "YES" if covid else ""
        w(f"  {year:<6} {term:<8} {code:<6} {flag}")

    # --------------------------------------------------------
    section("3. ml_courses — dept and level breakdown")
    # --------------------------------------------------------
    cursor.execute("SELECT COUNT(*) FROM ml_courses")
    check("Total courses", cursor.fetchone()[0], warn_if_zero=True)

    cursor.execute("SELECT COUNT(DISTINCT dept_code) FROM ml_courses")
    check("Distinct departments", cursor.fetchone()[0], warn_if_zero=True)

    cursor.execute("""
        SELECT COUNT(*) FROM ml_courses WHERE course_level IS NULL
    """)
    check("Courses with NULL course_level (non-numeric codes)", cursor.fetchone()[0])

    w()
    w("  Top 10 departments by course count:")
    cursor.execute("""
        SELECT dept_code, COUNT(*) as n
        FROM ml_courses GROUP BY dept_code
        ORDER BY n DESC LIMIT 10
    """)
    for dept, n in cursor.fetchall():
        w(f"    {dept:<10} {n} courses")

    w()
    w("  Course level breakdown:")
    cursor.execute("""
        SELECT course_level, COUNT(*) as n
        FROM ml_courses
        GROUP BY course_level ORDER BY course_level
    """)
    for level, n in cursor.fetchall():
        label = f"{level}-level" if level else "unknown"
        w(f"    {label:<12} {n} courses")

    # --------------------------------------------------------
    section("4. ml_section_offerings — row counts per term")
    # --------------------------------------------------------
    cursor.execute("SELECT COUNT(*) FROM ml_section_offerings")
    check("Total rows", cursor.fetchone()[0], warn_if_zero=True)

    w()
    w(f"  {'Year':<6} {'Term':<8} {'Rows':>6}  {'Avg/dept':>8}  COVID")
    w(f"  {'-'*40}")
    cursor.execute("""
        SELECT t.year, t.term, t.is_covid_affected, COUNT(*) as n
        FROM ml_section_offerings o
        JOIN ml_terms t ON o.ml_term_id = t.ml_term_id
        GROUP BY t.year, t.term, t.is_covid_affected
        ORDER BY t.year, t.term_order
    """)
    rows = cursor.fetchall()
    counts = [r[3] for r in rows]
    avg    = sum(counts) / len(counts) if counts else 0
    for year, term, covid, n in rows:
        flag    = "[COVID]" if covid else ""
        pct_avg = f"{n/avg*100:.0f}% of avg" if avg else ""
        w(f"  {year:<6} {term:<8} {n:>6}  {pct_avg:>8}  {flag}")

    # --------------------------------------------------------
    section("5. MATCHED vs UNMATCHED COURSES")
    # --------------------------------------------------------
    cursor.execute("""
        SELECT
            SUM(CASE WHEN ml_course_id IS NOT NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN ml_course_id IS NULL     THEN 1 ELSE 0 END)
        FROM ml_section_offerings
    """)
    matched, unmatched = cursor.fetchone()
    total = matched + unmatched
    check("Matched rows (ml_course_id set)", matched)
    check("Unmatched rows (ml_course_id NULL)", unmatched)
    w(f"  [INFO] Match rate: {matched/total*100:.1f}%")

    w()
    w("  Top unmatched courses (in Coursys, not in ml_courses):")
    cursor.execute("""
        SELECT dept_code, course_number, COUNT(*) as appearances
        FROM ml_section_offerings
        WHERE ml_course_id IS NULL
        GROUP BY dept_code, course_number
        ORDER BY appearances DESC
        LIMIT 20
    """)
    for dept, num, n in cursor.fetchall():
        w(f"    {dept} {num:<10} appeared in {n} terms")

    # --------------------------------------------------------
    section("6. ENROLLMENT DATA QUALITY")
    # --------------------------------------------------------
    cursor.execute("""
        SELECT
            COUNT(*)                                                        as total,
            SUM(CASE WHEN enrolled IS NOT NULL
                      AND capacity IS NOT NULL THEN 1 ELSE 0 END)          as full_data,
            SUM(CASE WHEN enrolled IS NULL
                      AND capacity IS NOT NULL THEN 1 ELSE 0 END)          as cap_only,
            SUM(CASE WHEN capacity IS NULL THEN 1 ELSE 0 END)              as no_data,
            SUM(CASE WHEN enrolled = 0 AND capacity = 0 THEN 1 ELSE 0 END) as zero_both,
            SUM(CASE WHEN waitlist > 0 THEN 1 ELSE 0 END)                  as has_waitlist,
            SUM(CASE WHEN enrolled IS NOT NULL
                      AND capacity IS NOT NULL
                      AND capacity > 0
                      AND enrolled > capacity THEN 1 ELSE 0 END)           as over_enrolled
        FROM ml_section_offerings
    """)
    total, full, cap_only, no_data, zero_both, wl, over = cursor.fetchone()
    w(f"  Full data (N/N):          {full:>6}  ({full/total*100:.1f}%)")
    w(f"  Capacity only (?/N):      {cap_only:>6}  ({cap_only/total*100:.1f}%)")
    w(f"  No data (?/?):            {no_data:>6}  ({no_data/total*100:.1f}%)")
    w(f"  Zero enrolled + capacity: {zero_both:>6}  ({zero_both/total*100:.1f}%) — placeholder/thesis")
    w(f"  Has waitlist (+N):        {wl:>6}  ({wl/total*100:.1f}%)")
    w(f"  Over-enrolled:            {over:>6}  ({over/total*100:.1f}%)")

    # --------------------------------------------------------
    section("7. SECTION CODE DIVERSITY")
    # --------------------------------------------------------
    w("  Unique section code prefixes (first character):")
    cursor.execute("""
        SELECT UPPER(SUBSTR(section_code, 1, 1)) as prefix,
               COUNT(*) as n
        FROM ml_section_offerings
        GROUP BY prefix ORDER BY n DESC
    """)
    for prefix, n in cursor.fetchall():
        w(f"    {prefix}xxx   {n:>6} rows")

    w()
    w("  Most common section codes:")
    cursor.execute("""
        SELECT section_code, COUNT(*) as n
        FROM ml_section_offerings
        GROUP BY section_code ORDER BY n DESC LIMIT 15
    """)
    for code, n in cursor.fetchall():
        w(f"    {code:<10} {n:>6} rows")

    # --------------------------------------------------------
    section("8. SPOT CHECKS — known courses")
    # --------------------------------------------------------
    spot_checks = [
        ("CMPT", "120"),
        ("CMPT", "276"),
        ("MATH", "150"),
        ("BUS",  "201"),
    ]
    for dept, num in spot_checks:
        cursor.execute("""
            SELECT COUNT(DISTINCT o.ml_term_id), MIN(enrolled), MAX(enrolled),
                   MIN(capacity), MAX(capacity)
            FROM ml_section_offerings o
            JOIN ml_courses c ON o.ml_course_id = c.ml_course_id
            WHERE c.dept_code = ? AND c.course_number = ?
        """, (dept, num))
        terms_found, min_enr, max_enr, min_cap, max_cap = cursor.fetchone()
        w(f"  {dept} {num}: found in {terms_found}/18 terms  "
          f"enrolled {min_enr}-{max_enr}  capacity {min_cap}-{max_cap}")

    # --------------------------------------------------------
    section("9. INSTRUCTOR COVERAGE")
    # --------------------------------------------------------
    cursor.execute("""
        SELECT
            COUNT(*)                                          as total,
            SUM(CASE WHEN instructor IS NOT NULL
                      AND instructor != '' THEN 1 ELSE 0 END) as has_instructor
        FROM ml_section_offerings
    """)
    total, has_inst = cursor.fetchone()
    missing = total - has_inst
    w(f"  Has instructor:     {has_inst}  ({has_inst/total*100:.1f}%)")
    w(f"  Missing instructor: {missing}  ({missing/total*100:.1f}%)")

    # --------------------------------------------------------
    section("10. OVERALL VERDICT")
    # --------------------------------------------------------
    issues = []
    cursor.execute("SELECT COUNT(*) FROM ml_section_offerings")
    if cursor.fetchone()[0] < 40000:
        issues.append("Total rows below 40k — possible collection gap")
    cursor.execute("SELECT COUNT(*) FROM ml_terms")
    if cursor.fetchone()[0] != 18:
        issues.append("ml_terms does not have 18 rows")
    cursor.execute("SELECT COUNT(*) FROM ml_courses")
    if cursor.fetchone()[0] == 0:
        issues.append("ml_courses is empty")

    if not issues:
        w("  ALL CHECKS PASSED — data stage complete")
    else:
        w("  ISSUES FOUND:")
        for issue in issues:
            w(f"    - {issue}")

    # Write output file
    os.makedirs("src/test", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    w()
    w(f"  Output written to: {OUTPUT_FILE}")

    conn.close()


if __name__ == "__main__":
    main()