"""
src/collect/01_init_db.py
--------------------------
One-time script. Reads courses.csv and departments.csv from data/raw/,
joins them, derives ML-ready columns, and inserts into ml_courses in SQLite.

Run from project root:
    python src/collect/01_init_db.py

After this runs successfully, Supabase is never needed again.
"""

import sqlite3
import pandas as pd
import os
import re

# ============================================================
# CONFIG
# ============================================================
DB_PATH           = "data/raw/sfu_ml.db"
COURSES_CSV       = "data/raw/courses.csv"
DEPARTMENTS_CSV   = "data/raw/departments.csv"


# ============================================================
# HELPERS
# ============================================================

def derive_course_level(course_number: str) -> int | None:
    """
    Extract the level from a course number.
    '225' -> 200, '120' -> 100, '801' -> 800
    Returns None if the number doesn't start with a digit.
    """
    if not course_number:
        return None
    first = str(course_number).strip()[0]
    if first.isdigit():
        return int(first) * 100
    return None


def derive_prereq_count(prereqs: str) -> int:
    """
    Count the number of prerequisites by counting comma-separated items.
    Empty or null -> 0.
    'CMPT 120, CMPT 125' -> 2
    """
    if not prereqs or str(prereqs).strip() == "" or str(prereqs) == "nan":
        return 0
    # Split on semicolons too — SFU sometimes uses both
    parts = re.split(r"[;,]", str(prereqs))
    return len([p for p in parts if p.strip()])


def has_coreqs(coreqs: str) -> int:
    """Returns 1 if corequisites field has content, else 0."""
    if not coreqs or str(coreqs).strip() == "" or str(coreqs) == "nan":
        return 0
    return 1


# ============================================================
# MAIN
# ============================================================

def main():
    # --------------------------------------------------------
    # 1. Check files exist
    # --------------------------------------------------------
    for path in [COURSES_CSV, DEPARTMENTS_CSV, DB_PATH]:
        if not os.path.exists(path):
            print(f"ERROR: File not found: {path}")
            print("Make sure you exported courses.csv and departments.csv")
            print("to data/raw/ and have already run sql/run_setup.py")
            return

    # --------------------------------------------------------
    # 2. Load CSVs
    # --------------------------------------------------------
    print("Loading CSVs...")
    courses = pd.read_csv(COURSES_CSV)
    departments = pd.read_csv(DEPARTMENTS_CSV)

    print(f"  courses.csv:     {len(courses)} rows")
    print(f"  departments.csv: {len(departments)} rows")

    # --------------------------------------------------------
    # 3. Clean departments
    # --------------------------------------------------------
    departments = departments[["dept_id", "dept_code", "name"]].copy()
    departments["dept_code"] = departments["dept_code"].str.upper().str.strip()
    departments["name"] = departments["name"].str.strip()

    # --------------------------------------------------------
    # 4. Join courses + departments
    # --------------------------------------------------------
    df = courses.merge(departments, on="dept_id", how="left")

    missing_dept = df["dept_code"].isna().sum()
    if missing_dept > 0:
        print(f"  WARNING: {missing_dept} courses have no matching department")

    # --------------------------------------------------------
    # 5. Derive ML columns
    # --------------------------------------------------------
    df["course_level"]  = df["course_number"].astype(str).apply(derive_course_level)
    df["prereq_count"]  = df["prerequisites"].apply(derive_prereq_count)
    df["has_coreqs"]    = df["corequisites"].apply(has_coreqs)

    # Normalise nullable text fields
    for col in ["prerequisites", "corequisites", "description", "designation", "title"]:
        df[col] = df[col].where(df[col].notna(), None)

    # --------------------------------------------------------
    # 6. Select only the columns ml_courses needs
    # --------------------------------------------------------
    ml_courses = df[[
        "course_id",       # -> source_course_id
        "dept_code",
        "name",            # -> dept_name
        "course_number",
        "course_level",
        "title",
        "units",
        "degree_level",
        "prereq_count",
        "has_coreqs",
        "designation",
    ]].copy()

    ml_courses = ml_courses.rename(columns={
        "course_id": "source_course_id",
        "name":      "dept_name",
    })

    # --------------------------------------------------------
    # 7. Insert into SQLite
    # --------------------------------------------------------
    print("\nConnecting to SQLite...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # Confirm ml_courses table exists and is empty
    cursor.execute("SELECT COUNT(*) FROM ml_courses")
    existing = cursor.fetchone()[0]
    if existing > 0:
        print(f"  ml_courses already has {existing} rows.")
        answer = input("  Overwrite? This will delete existing rows. (yes/no): ").strip().lower()
        if answer != "yes":
            print("  Aborted.")
            conn.close()
            return
        cursor.execute("DELETE FROM ml_courses")
        conn.commit()
        print("  Cleared existing rows.")

    print(f"Inserting {len(ml_courses)} courses...")

    inserted = 0
    skipped  = 0

    for _, row in ml_courses.iterrows():
        try:
            cursor.execute("""
                INSERT INTO ml_courses (
                    source_course_id, dept_code, dept_name,
                    course_number, course_level, title, units,
                    degree_level, prereq_count, has_coreqs, designation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(row["source_course_id"]),
                row["dept_code"],
                row["dept_name"],
                str(row["course_number"]).upper(),  # Coursys returns uppercase e.g. 360W not 360w
                int(row["course_level"]) if row["course_level"] else None,
                row["title"],
                int(row["units"]) if pd.notna(row["units"]) else None,
                row["degree_level"],
                int(row["prereq_count"]),
                int(row["has_coreqs"]),
                row["designation"],
            ))
            inserted += 1
        except Exception as e:
            print(f"  SKIPPED course_id={row['source_course_id']}: {e}")
            skipped += 1

    conn.commit()

    # --------------------------------------------------------
    # 8. Verify
    # --------------------------------------------------------
    print(f"\n  Inserted: {inserted}")
    print(f"  Skipped:  {skipped}")

    print("\nVerification — row counts by department (top 10):")
    cursor.execute("""
        SELECT dept_code, COUNT(*) as n
        FROM ml_courses
        GROUP BY dept_code
        ORDER BY n DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    for dept, count in rows:
        print(f"  {dept:<10} {count} courses")

    print("\nVerification — course level breakdown:")
    cursor.execute("""
        SELECT course_level, COUNT(*) as n
        FROM ml_courses
        GROUP BY course_level
        ORDER BY course_level
    """)
    rows = cursor.fetchall()
    for level, count in rows:
        print(f"  {str(level)+'-level' if level else 'unknown':<12} {count} courses")

    print("\nSample rows:")
    cursor.execute("""
        SELECT source_course_id, dept_code, course_number,
               course_level, prereq_count, has_coreqs
        FROM ml_courses LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"  {'src_id':<8} {'dept':<8} {'num':<6} {'level':<8} {'prereqs':<8} {'coreqs'}")
    print(f"  {'-'*50}")
    for row in rows:
        print(f"  {row[0]:<8} {row[1]:<8} {row[2]:<6} {str(row[3]):<8} {row[4]:<8} {row[5]}")

    conn.close()
    print(f"\nDone. ml_courses is populated in {DB_PATH}")

if __name__ == "__main__":
    main()