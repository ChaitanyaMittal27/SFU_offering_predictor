"""
sql/run_setup.py
----------------
Runs both SQL setup scripts against sfu_ml.db.
"""

import sqlite3
import os

DB_PATH  = "data/raw/sfu_ml.db"
SQL_DIR  = "sql"
SCRIPTS  = ["01_create_tables.sql", "02_seed_terms.sql"]


def run():
    os.makedirs("data/raw", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    for script in SCRIPTS:
        path = os.path.join(SQL_DIR, script)
        print(f"Running {script}...")
        with open(path, "r") as f:
            sql = f.read()
        cursor.executescript(sql)
        conn.commit()
        print(f"  done.")

    # Verify
    print("\nVerification:")
    for table in ["ml_terms", "ml_courses", "ml_section_offerings"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  {table}: {count} rows")

    print("\nml_terms contents:")
    cursor.execute("""
        SELECT ml_term_id, year, term, semester_code, is_covid_affected
        FROM ml_terms ORDER BY year, term_order
    """)
    rows = cursor.fetchall()
    print(f"  {'ID':<4} {'Year':<6} {'Term':<8} {'Code':<6} {'COVID'}")
    print(f"  {'-'*38}")
    for row in rows:
        covid = "YES" if row[4] else ""
        print(f"  {row[0]:<4} {row[1]:<6} {row[2]:<8} {row[3]:<6} {covid}")

    conn.close()
    print(f"\nDatabase ready at: {DB_PATH}")


if __name__ == "__main__":
    run()