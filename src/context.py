"""
src/context.py  —  Valid Context for Gemini

Reads from sfu_clean.db and returns valid values for each field.
Used by the controller to build Gemini's system prompt context.

Each function is independent and returns one piece of context.
get_all_context() calls them all and returns a single JSON-ready dict.
"""

import sqlite3
from contextlib import contextmanager
from paths import DATA_PROCESSED

# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------

@contextmanager
def _clean_db():
    conn = sqlite3.connect(DATA_PROCESSED / "sfu_clean.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Individual context functions
# ---------------------------------------------------------------------------

def get_valid_semesters() -> list[str]:
    """
    Valid semester strings the controller accepts.
    Hardcoded — these never change.
    """
    return ["spring", "summer", "fall"]


def get_valid_year_range() -> dict:
    """
    Min year is one ahead of the last collected term.
    Max year is a reasonable planning horizon.
    """
    with _clean_db() as conn:
        row = conn.execute("SELECT MAX(year) AS last_year FROM offerings").fetchone()

    last_year = row["last_year"] if row and row["last_year"] else 2025

    return {
        "min": last_year + 1,
        "max": last_year + 10,
    }


def get_valid_depts() -> list[str]:
    """
    All distinct department codes that appear in the offerings table.
    Sorted alphabetically.
    """
    with _clean_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT dept_code FROM offerings ORDER BY dept_code"
        ).fetchall()

    return [r["dept_code"] for r in rows if r["dept_code"]]


def get_valid_course_pairs() -> list[dict]:
    """
    All distinct (dept, course_num, title) combinations in the offerings table.
    Title included so Gemini can match on course name e.g. "Data Structures".
    If no title exists for a course, title is an empty string.
    Each entry is unique by (dept, course_num).
    """
    with _clean_db() as conn:
        rows = conn.execute(
            """
            SELECT
                dept_code,
                course_number,
                MAX(title) AS title
            FROM offerings
            WHERE dept_code    IS NOT NULL
              AND course_number IS NOT NULL
            GROUP BY dept_code, course_number
            ORDER BY dept_code, course_number
            """
        ).fetchall()

    return [
        {
            "dept":       r["dept_code"],
            "course_num": r["course_number"],
            "title":      r["title"] or "",
        }
        for r in rows
    ]


def get_semester_examples() -> list[dict]:
    """
    Concrete examples of how semester + year map to real terms.
    Helps Gemini understand the expected format.
    """
    with _clean_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT year, term, term_order
            FROM offerings
            ORDER BY year DESC, term_order
            LIMIT 9
            """
        ).fetchall()

    return [
        {
            "year":     r["year"],
            "semester": r["term"],
            "order":    r["term_order"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Master function
# ---------------------------------------------------------------------------

def get_all_context() -> dict:
    """
    Returns a single JSON-ready dict with all valid context.
    Called once at app startup by the controller.

    Structure:
    {
        "semesters":        ["spring", "summer", "fall"],
        "year_range":       {"min": 2026, "max": 2035},
        "depts":            ["BUS", "CA", "CMPT", ...],
        "course_pairs":     [{"dept": "CMPT", "course_num": "225"}, ...],
        "course_examples":  [{"dept": "CMPT", "course_num": "225",
                              "title": "Data Structures"}, ...],
        "semester_examples":[{"year": 2025, "semester": "fall",
                              "order": 3}, ...],
    }
    """
    return {
        "semesters":         get_valid_semesters(),
        "year_range":        get_valid_year_range(),
        "depts":             get_valid_depts(),
        "course_pairs":      get_valid_course_pairs(),
        "semester_examples": get_semester_examples(),
    }