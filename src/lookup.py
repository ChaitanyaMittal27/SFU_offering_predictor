"""
src/lookup.py  —  Input Conversion & Feature Building

Takes validated user inputs (dept, course_num, semester, year) and builds
the complete feature dict that model.py expects.

Entry point:
    build_features(dept, course_num, semester, year) -> dict

All historical features are computed using only offerings PRIOR to the
target term — the same no-leakage guarantee used during training.

DB usage:
    sfu_clean.db  — single source: offerings table contains all needed fields
                    (dept_code, course_level, degree_level, units, prereq_count
                     were joined in during cleaning)

Encoders:
    le_dept_code.pkl, le_degree_level.pkl — loaded from data/processed/
"""

import sqlite3
import numpy as np
import joblib
from contextlib import contextmanager
from paths import DATA_PROCESSED

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_SEMESTERS   = {"spring", "summer", "fall"}
SEMESTER_TO_ORDER = {"spring": 1, "summer": 2, "fall": 3}
HIGH_FILL_THRESHOLD = 0.9
COLD_START_TERMS_SINCE = 19   # sentinel for "never offered before"

# ---------------------------------------------------------------------------
# Load encoders once at import time
# ---------------------------------------------------------------------------
_le_dept   = joblib.load(DATA_PROCESSED / "le_dept_code.pkl")
_le_degree = joblib.load(DATA_PROCESSED / "le_degree_level.pkl")


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------
@contextmanager
def _db():
    conn = sqlite3.connect(DATA_PROCESSED / "sfu_clean.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _term_idx(year: int, term_order: int) -> int:
    """Sequential term index. 2020 Spring=0, 2020 Summer=1, 2020 Fall=2, ..."""
    return (year - 2020) * 3 + (term_order - 1)


def _encode_dept(dept_code: str) -> int:
    try:
        return int(_le_dept.transform([dept_code])[0])
    except ValueError:
        return 0   # unseen department → default to 0


def _encode_degree(degree_level: str) -> int:
    try:
        return int(_le_degree.transform([degree_level])[0])
    except ValueError:
        return int(_le_degree.transform(["UGRD"])[0])   # default to UGRD


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _validate(dept: str, course_num: str, semester: str, year: int):
    if semester not in VALID_SEMESTERS:
        raise ValueError(
            f"semester must be one of {sorted(VALID_SEMESTERS)}, got: {semester!r}"
        )
    if not isinstance(year, int) or not (2020 <= year <= 2040):
        raise ValueError(
            f"year must be an integer between 2020 and 2040, got: {year!r}"
        )


# ---------------------------------------------------------------------------
# Feature group helpers
# ---------------------------------------------------------------------------
def _get_course(dept: str, course_num: str) -> dict:
    """
    Static per-course fields from sfu_clean.db offerings table.
    Raises ValueError if course not found.
    """
    with _db() as conn:
        row = conn.execute(
            """
            SELECT DISTINCT
                ml_course_id, dept_code, course_level,
                degree_level, units, prereq_count
            FROM offerings
            WHERE dept_code = ? AND course_number = ?
            LIMIT 1
            """,
            (dept, course_num),
        ).fetchone()

    if row is None:
        raise ValueError(f"Course not found: {dept} {course_num}. Check dept and course number.")

    return {
        "ml_course_id":     int(row["ml_course_id"]),
        "dept_code_enc":    _encode_dept(row["dept_code"] or "UNKNOWN"),
        "degree_level_enc": _encode_degree(row["degree_level"] or "UGRD"),
        "course_level":     int(row["course_level"]),
        "units":            int(row["units"] or 3),
        "prereq_count":     int(row["prereq_count"] or 0),
    }


def _get_term(year: int, term_order: int) -> dict:
    """
    Term-level features. is_covid_affected looked up from DB if term exists,
    otherwise defaults to 0 (all future terms are post-COVID).
    """
    with _db() as conn:
        row = conn.execute(
            """
            SELECT DISTINCT is_covid_affected
            FROM offerings
            WHERE year = ? AND term_order = ?
            LIMIT 1
            """,
            (year, term_order),
        ).fetchone()

    return {
        "term_order":        term_order,
        "is_covid_affected": int(row["is_covid_affected"]) if row else 0,
    }


def _get_history(
    ml_course_id: int,
    dept_code: str,
    target_year: int,
    target_term_order: int,
    target_idx: int,
) -> dict:
    """
    Compute all historical features using only offerings prior to the target term.

    Mirrors the feature engineering logic exactly:
    - Aggregate sections to course-term level (sum capacity/enrolled, count sections)
    - Compute averages, previous values, trends, and streak from those aggregates
    - Cold-start (no prior history) → filled with dept-level averages
    """
    with _db() as conn:
        # All course-term aggregates strictly prior to target term
        rows = conn.execute(
            """
            SELECT
                year,
                term_order,
                SUM(capacity) AS total_capacity,
                SUM(enrolled) AS total_enrolled,
                COUNT(*)      AS n_sections
            FROM offerings
            WHERE ml_course_id = ?
              AND (year < ? OR (year = ? AND term_order < ?))
            GROUP BY year, term_order
            ORDER BY year, term_order
            """,
            (ml_course_id, target_year, target_year, target_term_order),
        ).fetchall()

    if not rows:
        # Cold start — no prior history at all
        return _cold_start(dept_code, target_idx)

    # Build list of offering dicts with computed fill_rate and term_idx
    offerings = []
    for r in rows:
        cap = int(r["total_capacity"] or 0)
        enr = int(r["total_enrolled"] or 0)
        offerings.append({
            "year":           r["year"],
            "term_order":     r["term_order"],
            "term_idx":       _term_idx(r["year"], r["term_order"]),
            "total_capacity": cap,
            "total_enrolled": enr,
            "n_sections":     r["n_sections"],
            "fill_rate":      enr / cap if cap > 0 else 0.0,
        })

    # Same-semester offerings only
    same_sem = [o for o in offerings if o["term_order"] == target_term_order]

    # ── Offering counts ──────────────────────────────────────────────────────
    hist_n_offerings          = len(offerings)
    hist_n_this_semester      = len(same_sem)
    n_distinct_sems           = len(set(o["term_order"] for o in offerings))

    # Total same-semester term slots in the grid prior to target
    # (one slot per year from first_offering onwards where same semester occurs)
    first_year  = offerings[0]["year"]
    first_order = offerings[0]["term_order"]
    deduct = 1 if target_term_order < first_order else 0
    total_same_sem_prior = max(0, target_year - first_year - deduct)

    same_semester_offer_ratio = (
        hist_n_this_semester / total_same_sem_prior
        if total_same_sem_prior > 0 else 0.0
    )

    # ── Averages ─────────────────────────────────────────────────────────────
    hist_avg_capacity   = float(np.mean([o["total_capacity"] for o in offerings]))
    hist_avg_enrollment = float(np.mean([o["total_enrolled"] for o in offerings]))
    hist_avg_sections   = float(np.mean([o["n_sections"]     for o in offerings]))

    hist_avg_cap_this_sem = (
        float(np.mean([o["total_capacity"] for o in same_sem]))
        if same_sem else None
    )
    hist_avg_enr_this_sem = (
        float(np.mean([o["total_enrolled"] for o in same_sem]))
        if same_sem else None
    )

    # ── Ratios ───────────────────────────────────────────────────────────────
    same_sem_cap_ratio = (
        hist_avg_cap_this_sem / hist_avg_capacity
        if hist_avg_cap_this_sem is not None and hist_avg_capacity > 0
        else 0.0
    )
    same_sem_enr_ratio = (
        hist_avg_enr_this_sem / hist_avg_enrollment
        if hist_avg_enr_this_sem is not None and hist_avg_enrollment > 0
        else 0.0
    )

    # ── Previous term values ─────────────────────────────────────────────────
    prev_cap = float(offerings[-1]["total_capacity"])
    prev_enr = float(offerings[-1]["total_enrolled"])
    prev_same_sem_cap = float(same_sem[-1]["total_capacity"]) if same_sem else None
    prev_same_sem_enr = float(same_sem[-1]["total_enrolled"]) if same_sem else None

    # ── Trends (linear slope over all prior offerings) ───────────────────────
    if len(offerings) >= 2:
        x = np.arange(len(offerings))
        cap_trend = float(np.polyfit(x, [o["total_capacity"] for o in offerings], 1)[0])
        enr_trend = float(np.polyfit(x, [o["total_enrolled"] for o in offerings], 1)[0])
    else:
        cap_trend = 0.0
        enr_trend = 0.0

    # ── n_terms_since_last_offered ───────────────────────────────────────────
    last_offering_idx    = offerings[-1]["term_idx"]
    n_terms_since        = float(target_idx - last_offering_idx)

    # ── n_consecutive_same_semester_streak ───────────────────────────────────
    # Walk backwards through same-semester years.
    # Stop at first year the course did NOT run (not in same_sem).
    streak = 0
    if same_sem:
        offered_years = set(o["year"] for o in same_sem)
        y = max(offered_years)
        while True:
            # Check if (y, target_term_order) is in the grid at all
            if _term_idx(y, target_term_order) < _term_idx(first_year, first_order):
                break   # before grid start
            if y in offered_years:
                streak += 1
                y -= 1
            else:
                break   # gap in offerings → streak ends

    # ── high_fill_rate_frequency ─────────────────────────────────────────────
    high_fill_freq = float(
        np.mean([1.0 if o["fill_rate"] >= HIGH_FILL_THRESHOLD else 0.0 for o in offerings])
    )

    # ── course_age_terms ─────────────────────────────────────────────────────
    # How many term slots from first offering to target term (inclusive)
    first_idx    = offerings[0]["term_idx"]
    course_age   = float(target_idx - first_idx + 1)

    def _or_zero(v):
        return v if v is not None else 0.0

    return {
        # offered features
        "hist_n_offerings":                   hist_n_offerings,
        "hist_n_this_semester_offerings":     hist_n_this_semester,
        "same_semester_offer_ratio":          same_semester_offer_ratio,
        "n_distinct_semesters_offered":       n_distinct_sems,
        "n_terms_since_last_offered":         n_terms_since,
        "n_consecutive_same_semester_streak": streak,
        # capacity features
        "hist_avg_capacity_per_offering":     hist_avg_capacity,
        "hist_avg_capacity_this_semester":    _or_zero(hist_avg_cap_this_sem),
        "same_semester_capacity_ratio":       same_sem_cap_ratio,
        "previous_term_capacity":             prev_cap,
        "previous_same_semester_capacity":    _or_zero(prev_same_sem_cap),
        "capacity_trend":                     cap_trend,
        "hist_avg_sections_per_offering":     hist_avg_sections,
        "hist_avg_enrollment_per_offering":   hist_avg_enrollment,
        # enrollment features
        "hist_avg_enrollment_this_semester":  _or_zero(hist_avg_enr_this_sem),
        "same_semester_enrollment_ratio":     same_sem_enr_ratio,
        "previous_same_semester_enrollment":  _or_zero(prev_same_sem_enr),
        "previous_term_enrollment":           prev_enr,
        "enrollment_trend":                   enr_trend,
        "high_fill_rate_frequency":           high_fill_freq,
        "course_age_terms":                   course_age,
    }


def _cold_start(dept_code: str, target_idx: int) -> dict:
    """
    Fallback features for a course with no prior history.
    Capacity/enrollment features filled with dept-level averages from clean DB.
    Offering features default to zeros/sentinels.
    """
    with _db() as conn:
        row = conn.execute(
            """
            SELECT
                AVG(capacity) AS avg_cap,
                AVG(enrolled) AS avg_enr,
                AVG(CAST(enrolled AS REAL) / NULLIF(capacity, 0)) AS avg_fill
            FROM offerings
            WHERE dept_code = ?
            """,
            (dept_code,),
        ).fetchone()

    avg_cap  = float(row["avg_cap"]  or 30.0)
    avg_enr  = float(row["avg_enr"]  or 20.0)
    avg_fill = float(row["avg_fill"] or 0.5)

    return {
        "hist_n_offerings":                   0,
        "hist_n_this_semester_offerings":     0,
        "same_semester_offer_ratio":          0.0,
        "n_distinct_semesters_offered":       0,
        "n_terms_since_last_offered":         float(COLD_START_TERMS_SINCE),
        "n_consecutive_same_semester_streak": 0,
        "hist_avg_capacity_per_offering":     avg_cap,
        "hist_avg_capacity_this_semester":    avg_cap,
        "same_semester_capacity_ratio":       1.0,
        "previous_term_capacity":             avg_cap,
        "previous_same_semester_capacity":    avg_cap,
        "capacity_trend":                     0.0,
        "hist_avg_sections_per_offering":     1.0,
        "hist_avg_enrollment_per_offering":   avg_enr,
        "hist_avg_enrollment_this_semester":  avg_enr,
        "same_semester_enrollment_ratio":     1.0,
        "previous_same_semester_enrollment":  avg_enr,
        "previous_term_enrollment":           avg_enr,
        "enrollment_trend":                   0.0,
        "high_fill_rate_frequency":           avg_fill,
        "course_age_terms":                   float(target_idx + 1),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def build_features(dept: str, course_num: str, semester: str, year: int) -> dict:
    """
    Validate inputs and build the complete feature dict.

    Parameters
    ----------
    dept       : e.g. "CMPT", "cmpt", "Cmpt"   (normalised to upper internally)
    course_num : e.g. "225", "360W"             (normalised to upper internally)
    semester   : "spring" | "summer" | "fall"   (case-insensitive)
    year       : e.g. 2027

    Returns
    -------
    dict  — all keys expected by model.py

    Raises
    ------
    ValueError — bad inputs or course not found
    """
    semester   = semester.lower().strip()
    dept       = dept.upper().strip()
    course_num = course_num.upper().strip()

    _validate(dept, course_num, semester, year)

    term_order = SEMESTER_TO_ORDER[semester]
    target_idx = _term_idx(year, term_order)

    course = _get_course(dept, course_num)
    term   = _get_term(year, term_order)
    hist   = _get_history(
        course["ml_course_id"],
        dept,
        target_year=year,
        target_term_order=term_order,
        target_idx=target_idx,
    )

    return {**course, **term, **hist}
