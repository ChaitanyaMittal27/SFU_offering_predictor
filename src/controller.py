"""
src/controller.py  —  Controller Layer

Single public function: predict(dept, course_num, semester, year)

Flow:
    1. build_features() via lookup  — validates inputs, hits DB, builds features
    2. predict_*()      via model   — runs the three pkl models
    3. package result               — clean dict, always same shape

The result dict shape is always identical whether ok or error.
Callers check result["status"] first.
"""

import lookup
import model
from context import get_all_context


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_UNLIKELY_THRESHOLD = 0.30   # offered_prob below this → is_unlikely = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _ok(dept, course_num, semester, year,
        offered_prob, capacity, enrollment,
        is_cold_start, is_unlikely) -> dict:
    return {
        "status":        "ok",
        "dept":          dept.upper(),
        "course_num":    course_num.upper(),
        "semester":      semester.lower(),
        "year":          year,
        "offered_prob":  round(offered_prob, 4),
        "capacity":      int(round(capacity)),
        "enrollment":    int(round(enrollment)),
        "is_cold_start": is_cold_start,
        "is_unlikely":   is_unlikely,
        "error":         None,
    }


def _error(dept, course_num, semester, year, message: str) -> dict:
    return {
        "status":        "error",
        "dept":          dept,
        "course_num":    course_num,
        "semester":      semester,
        "year":          year,
        "offered_prob":  None,
        "capacity":      None,
        "enrollment":    None,
        "is_cold_start": None,
        "is_unlikely":   None,
        "error":         message,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def predict(dept: str, course_num: str, semester: str, year: int) -> dict:
    """
    Run all three models for the given course + semester + year.

    Parameters
    ----------
    dept       : e.g. "CMPT", "cmpt", "Cmpt"   (normalised internally)
    course_num : e.g. "225", "360W"             (normalised internally)
    semester   : "spring" | "summer" | "fall"   (case-insensitive)
    year       : e.g. 2027

    Returns
    -------
    dict — always the same shape, check result["status"] first.

    Ok result:
        {
            "status":        "ok",
            "dept":          "CMPT",
            "course_num":    "225",
            "semester":      "fall",
            "year":          2027,
            "offered_prob":  0.9329,
            "capacity":      399,
            "enrollment":    307,
            "is_cold_start": False,
            "is_unlikely":   False,
            "error":         None,
        }

    Error result:
        {
            "status":        "error",
            "dept":          "CMPT",
            "course_num":    "999",
            ...all prediction fields None...
            "error":         "Course not found: CMPT 999",
        }
    """
    try:
        # 1. Build features (validates inputs, queries DB)
        features = lookup.build_features(dept, course_num, semester, year)

        # 2. Run the three models
        offered_prob = model.predict_offered(features)
        capacity     = model.predict_capacity(features)
        enrollment   = model.predict_enrollment(features)

        # 3. Derive flags
        is_cold_start = (features["hist_n_offerings"] == 0)
        is_unlikely   = (offered_prob < _UNLIKELY_THRESHOLD)

        return _ok(
            dept, course_num, semester, year,
            offered_prob, capacity, enrollment,
            is_cold_start, is_unlikely,
        )

    except ValueError as e:
        return _error(dept, course_num, semester, year, str(e))


def get_context() -> dict:
    """
    Return valid input context for Gemini's system prompt.
    Call once at app startup, not on every request.
    """
    return get_all_context()
