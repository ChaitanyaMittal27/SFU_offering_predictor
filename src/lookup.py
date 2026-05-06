"""
src/lookup.py  —  Input Conversion & Feature Building

Takes validated user inputs (dept, course_num, semester, year) and builds
the complete feature dict that model.py expects.

Entry point:
    build_features(dept, course_num, semester, year) -> dict

Four internal helpers, one per feature group:
    _get_course_features()     — static per-course fields
    _get_term_features()       — term fields (or synthesized for future terms)
    _get_historical_features() — aggregated past offering stats
    _get_delivery_features()   — campus/modality flags from past sections

DB usage:
    sfu_clean.db  — primary source (offerings table, fully denormalized)
    sfu_ml.db     — only for prereq_count, has_coreqs, units, designation
                    (not present in clean DB)
"""

import statistics
import sqlite3
from contextlib import contextmanager
from paths import DATA_RAW, DATA_PROCESSED

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SEMESTERS = {"spring", "summer", "fall"}

SEMESTER_TO_ORDER = {"spring": 1, "summer": 2, "fall": 3}

# Last known term in the DB — update if you collect more terms
_LAST_TERM_ID    = 18     # 2025 Fall
_LAST_TERM_YEAR  = 2025
_LAST_TERM_ORDER = 3      # Fall

# Primary section prefixes (established during feature engineering)
_PRIMARY_PREFIXES = ("D", "E", "O", "C", "J", "G", "N")
_PRIMARY_FILTER   = " OR ".join(
    f"section_code LIKE '{p}%'" for p in _PRIMARY_PREFIXES
)

# Campus string → feature flag name
_CAMPUS_MAP = {
    "burnaby":            "is_burnaby",
    "surrey":             "is_surrey",
    "harbour ctr":        "is_harbour_ctr",
    "other vancouver":    "is_other_van",
    "off-campus":         "is_off_campus",
    "great northern way": "is_off_campus",   # merged with off-campus
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@contextmanager
def _clean_db():
    """sfu_clean.db — primary source."""
    conn = sqlite3.connect(DATA_PROCESSED / "sfu_clean.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _raw_db():
    """sfu_ml.db — only for columns absent from clean DB."""
    conn = sqlite3.connect(DATA_RAW / "sfu_ml.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(dept: str, course_num: str, semester: str, year: int):
    if not isinstance(dept, str) or not dept.strip():
        raise ValueError(f"dept must be a non-empty string, got: {dept!r}")
    if not isinstance(course_num, str) or not course_num.strip():
        raise ValueError(f"course_num must be a non-empty string, got: {course_num!r}")
    if semester not in VALID_SEMESTERS:
        raise ValueError(
            f"semester must be one of {sorted(VALID_SEMESTERS)}, got: {semester!r}"
        )
    if not isinstance(year, int) or not (2020 <= year <= 2035):
        raise ValueError(
            f"year must be an integer between 2020 and 2035, got: {year!r}"
        )


# ---------------------------------------------------------------------------
# Feature group helpers
# ---------------------------------------------------------------------------

def _get_course_features(dept: str, course_num: str) -> dict:
    """
    Static per-course fields.

    course_level, degree_level  → sfu_clean.db offerings (first matching row)
    prereq_count, has_coreqs,
    units, designation          → sfu_ml.db ml_courses

    Raises ValueError if the course doesn't exist in sfu_clean.db.
    """
    # Pull ml_course_id + static fields from clean DB
    with _clean_db() as conn:
        row = conn.execute(
            """
            SELECT DISTINCT
                ml_course_id,
                course_level,
                degree_level
            FROM offerings
            WHERE dept_code    = ?
              AND course_number = ?
            LIMIT 1
            """,
            (dept.upper(), course_num.upper()),
        ).fetchone()

    if row is None:
        raise ValueError(
            f"Course not found: {dept.upper()} {course_num.upper()}. "
            "Check dept_code and course_number."
        )

    ml_course_id = row["ml_course_id"]
    course_level = row["course_level"]
    is_grad      = 1 if row["degree_level"] == "GRAD" else 0

    # Pull the four missing columns from raw DB
    with _raw_db() as conn:
        raw = conn.execute(
            """
            SELECT prereq_count, has_coreqs, units, designation
            FROM ml_courses
            WHERE ml_course_id = ?
            """,
            (ml_course_id,),
        ).fetchone()

    if raw:
        prereq_count    = raw["prereq_count"]  or 0
        has_coreqs      = raw["has_coreqs"]    or 0
        units           = raw["units"]         or 3
        has_designation = 0 if raw["designation"] is None else 1
    else:
        prereq_count    = 0
        has_coreqs      = 0
        units           = 3
        has_designation = 0

    return {
        "ml_course_id":    ml_course_id,
        "course_level":    course_level,
        "is_grad":         is_grad,
        "prereq_count":    prereq_count,
        "has_coreqs":      has_coreqs,
        "units":           units,
        "has_designation": has_designation,
    }


def _get_term_features(year: int, semester: str) -> dict:
    """
    Term fields from sfu_clean.db offerings table.
    If the term doesn't exist yet, synthesize it (is_covid_affected=0).

    Returns: ml_term_id, term_order, is_covid_affected
    """
    order = SEMESTER_TO_ORDER[semester]

    with _clean_db() as conn:
        row = conn.execute(
            """
            SELECT DISTINCT ml_term_id, term_order, is_covid_affected
            FROM offerings
            WHERE year = ? AND term_order = ?
            LIMIT 1
            """,
            (year, order),
        ).fetchone()

    if row is not None:
        return {
            "ml_term_id":        row["ml_term_id"],
            "term_order":        row["term_order"],
            "is_covid_affected": row["is_covid_affected"],
        }

    # Synthesize future term ID
    years_ahead  = year - _LAST_TERM_YEAR
    orders_ahead = order - _LAST_TERM_ORDER
    offset       = years_ahead * 3 + orders_ahead

    return {
        "ml_term_id":        _LAST_TERM_ID + offset,
        "term_order":        order,
        "is_covid_affected": 0,
    }


def _get_historical_features(ml_course_id: int, target_term_order: int) -> dict:
    """
    Aggregate past offering stats from sfu_clean.db offerings table.
    Only primary sections counted. Cold-start → all zeros.

    Returns: hist_n_offerings, hist_n_sections_total, hist_capacity_total,
             hist_enrolled_total, hist_n_spring_offerings,
             hist_n_summer_offerings, hist_n_fall_offerings,
             hist_fill_rate_std, n_terms_since_last_offered
    """
    with _clean_db() as conn:
        rows = conn.execute(
            f"""
            SELECT ml_term_id, term_order, capacity, enrolled
            FROM offerings
            WHERE ml_course_id = ?
              AND ({_PRIMARY_FILTER})
            """,
            (ml_course_id,),
        ).fetchall()

    zeros = {
        "hist_n_offerings":           0,
        "hist_n_sections_total":      0,
        "hist_capacity_total":        0,
        "hist_enrolled_total":        0,
        "hist_n_spring_offerings":    0,
        "hist_n_summer_offerings":    0,
        "hist_n_fall_offerings":      0,
        "hist_fill_rate_std":         0.0,
        "n_terms_since_last_offered": 0,
    }

    if not rows:
        return zeros

    terms_seen     = {}   # ml_term_id → term_order
    sections_total = 0
    cap_total      = 0
    enr_total      = 0
    fill_rates     = []
    last_term_id   = 0

    for r in rows:
        tid   = r["ml_term_id"]
        order = r["term_order"]
        cap   = r["capacity"] or 0
        enr   = r["enrolled"] or 0

        sections_total += 1
        cap_total      += cap
        enr_total      += enr

        if cap > 0:
            fill_rates.append(enr / cap)

        terms_seen[tid] = order
        if tid > last_term_id:
            last_term_id = tid

    spring = sum(1 for o in terms_seen.values() if o == 1)
    summer = sum(1 for o in terms_seen.values() if o == 2)
    fall   = sum(1 for o in terms_seen.values() if o == 3)

    # Most recent term with this order in DB — use as "current" reference
    with _clean_db() as conn:
        ref = conn.execute(
            """
            SELECT ml_term_id FROM offerings
            WHERE term_order = ?
            ORDER BY ml_term_id DESC LIMIT 1
            """,
            (target_term_order,),
        ).fetchone()

    n_terms_since = max(0, (ref["ml_term_id"] - last_term_id)) if ref else 0

    return {
        "hist_n_offerings":           len(terms_seen),
        "hist_n_sections_total":      sections_total,
        "hist_capacity_total":        cap_total,
        "hist_enrolled_total":        enr_total,
        "hist_n_spring_offerings":    spring,
        "hist_n_summer_offerings":    summer,
        "hist_n_fall_offerings":      fall,
        "hist_fill_rate_std":         round(statistics.stdev(fill_rates), 4)
                                      if len(fill_rates) > 1 else 0.0,
        "n_terms_since_last_offered": n_terms_since,
    }


def _get_delivery_features(ml_course_id: int) -> dict:
    """
    Infer delivery mode and campus from historical sections in sfu_clean.db.
    Uses the dominant (most common) campus and >50% threshold for online/evening.
    Cold-start defaults to is_burnaby=1.

    Returns: is_online, is_evening, is_burnaby, is_surrey,
             is_harbour_ctr, is_other_van, is_off_campus
    """
    default = {
        "is_online":      0,
        "is_evening":     0,
        "is_burnaby":     1,
        "is_surrey":      0,
        "is_harbour_ctr": 0,
        "is_other_van":   0,
        "is_off_campus":  0,
    }

    with _clean_db() as conn:
        rows = conn.execute(
            f"""
            SELECT section_code, campus
            FROM offerings
            WHERE ml_course_id = ?
              AND ({_PRIMARY_FILTER})
            """,
            (ml_course_id,),
        ).fetchall()

    if not rows:
        return default

    total         = len(rows)
    campus_counts: dict[str, int] = {}
    online_count  = 0
    evening_count = 0

    for r in rows:
        code   = (r["section_code"] or "").upper()
        campus = (r["campus"]       or "").lower().strip()

        if code.startswith("O"):
            online_count  += 1
        if code.startswith("E"):
            evening_count += 1

        campus_counts[campus] = campus_counts.get(campus, 0) + 1

    dominant  = max(campus_counts, key=campus_counts.get)
    flag      = _CAMPUS_MAP.get(dominant, "is_burnaby")

    result = {k: 0 for k in default}
    result[flag]           = 1
    result["is_online"]    = 1 if online_count  / total > 0.5 else 0
    result["is_evening"]   = 1 if evening_count / total > 0.5 else 0

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_features(dept: str, course_num: str, semester: str, year: int) -> dict:
    """
    Validate inputs and build the complete 26-key feature dict.

    Parameters
    ----------
    dept       : e.g. "CMPT", "MATH"
    course_num : e.g. "225", "360W"
    semester   : "spring" | "summer" | "fall"
    year       : e.g. 2027

    Returns
    -------
    dict  — all keys expected by model.py

    Raises
    ------
    ValueError — bad inputs or course not found
    """
    semester = semester.lower()
    _validate(dept, course_num, semester, year)

    course_feats   = _get_course_features(dept, course_num)
    term_feats     = _get_term_features(year, semester)
    hist_feats     = _get_historical_features(
                         course_feats["ml_course_id"],
                         term_feats["term_order"],
                     )
    delivery_feats = _get_delivery_features(course_feats["ml_course_id"])

    return {
        **course_feats,
        **term_feats,
        **hist_feats,
        **delivery_feats,
    }