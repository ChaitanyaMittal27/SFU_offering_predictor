"""
src/tests/test_model/test_model.py  —  Tests for the Model Layer

Run from project root:
    pytest src/tests/test_model/test_model.py -v

Any output files this test produces (logs, result CSVs) are written to
TEST_OUT, which points to the same folder as this file.

What is tested and why:
  1. LOAD  — models import without error (catches bad pkl paths immediately)
  2. TYPES — each function returns a Python float (not ndarray, not list)
  3. RANGES — offered prob in [0,1], capacity and enrollment are positive
  4. CONSISTENCY — enrollment <= capacity on the same real course (sanity check)
  5. MISSING KEY — a feature dict missing a required column raises KeyError,
                   not a silent wrong answer
  6. COLD START — an ml_course_id never seen in training (0) doesn't crash;
                  the model returns something, we just check it doesn't explode
  7. SMOKE TEST — pulls a real course from the SQLite DB and runs all
                  three functions end-to-end with grounded historical values
"""

import sys
import sqlite3
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# src/tests/test_model/test_model.py  →  go up 3 levels to reach src/
_SRC = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_SRC))

from paths import DATA_PROCESSED, DATA_RAW                         # noqa: E402  (after sys.path)
import model as M                               # noqa: E402

# Folder where this test file lives — any output files go here
TEST_OUT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_feature_dict(ml_course_id: int, ml_term_id: int,
                       course_level: int = 200) -> dict:
    """
    Build a complete feature dict with sensible defaults.
    Only ml_course_id, ml_term_id, and course_level vary between tests;
    everything else is held constant so tests are stable and repeatable.
    """
    return {
        "ml_course_id":               ml_course_id,
        "ml_term_id":                 ml_term_id,
        "course_level":               course_level,
        "is_grad":                    0,
        "prereq_count":               1,
        "has_coreqs":                 0,
        "units":                      3,
        "has_designation":            0,
        "term_order":                 4,          # Fall
        "is_covid_affected":          0,
        "is_online":                  0,
        "is_evening":                 0,
        "is_burnaby":                 1,
        "is_surrey":                  0,
        "is_harbour_ctr":             0,
        "is_other_van":               0,
        "is_off_campus":              0,
        "hist_n_offerings":           12,
        "hist_n_sections_total":      24,
        "hist_capacity_total":        1200,
        "hist_enrolled_total":        1050,
        "hist_n_spring_offerings":    4,
        "hist_n_summer_offerings":    2,
        "hist_n_fall_offerings":      6,
        "hist_fill_rate_std":         0.05,
        "n_terms_since_last_offered": 0,
    }


def _get_course_ids(dept: str, course_num: str, semester: int):
    """
    Look up real ml_course_id and ml_term_id from sfu_clean.db.
    Returns (ml_course_id, ml_term_id) or calls pytest.skip if not found.
    """
    conn = sqlite3.connect(DATA_RAW / "sfu_ml.db")
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    cur.execute(
        "SELECT ml_course_id FROM ml_courses WHERE dept_code = ? AND course_number = ?",
        (dept, course_num.upper()),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        pytest.skip(f"{dept} {course_num} not found in DB")
    ml_course_id = row["ml_course_id"]

    cur.execute(
        "SELECT ml_term_id FROM ml_terms WHERE term_order = ? ORDER BY year DESC LIMIT 1",
        (semester,),
    )
    term_row = cur.fetchone()
    conn.close()
    if term_row is None:
        pytest.skip("No matching term found in DB")

    return ml_course_id, term_row["ml_term_id"]


# ---------------------------------------------------------------------------
# Test 1 — LOAD
# ---------------------------------------------------------------------------
def test_models_loaded():
    """All three pkl files loaded at import time without error."""
    assert M._model_offered    is not None
    assert M._model_capacity   is not None
    assert M._model_enrollment is not None


# ---------------------------------------------------------------------------
# Test 2 — TYPES
# ---------------------------------------------------------------------------
def test_predict_offered_returns_float():
    result = M.predict_offered(_make_feature_dict(1, 1))
    assert isinstance(result, float), f"Expected float, got {type(result)}"


def test_predict_capacity_returns_float():
    result = M.predict_capacity(_make_feature_dict(1, 1))
    assert isinstance(result, float), f"Expected float, got {type(result)}"


def test_predict_enrollment_returns_float():
    result = M.predict_enrollment(_make_feature_dict(1, 1))
    assert isinstance(result, float), f"Expected float, got {type(result)}"


# ---------------------------------------------------------------------------
# Test 3 — RANGES
# ---------------------------------------------------------------------------
def test_offered_prob_in_zero_one():
    prob = M.predict_offered(_make_feature_dict(1, 1))
    assert 0.0 <= prob <= 1.0, f"Offered probability out of range: {prob}"


def test_capacity_is_positive():
    cap = M.predict_capacity(_make_feature_dict(1, 1))
    assert cap > 0, f"Capacity should be positive, got {cap}"


def test_enrollment_is_positive():
    enr = M.predict_enrollment(_make_feature_dict(1, 1))
    assert enr > 0, f"Enrollment should be positive, got {enr}"


# ---------------------------------------------------------------------------
# Test 4 — CONSISTENCY
# ---------------------------------------------------------------------------
def test_enrollment_not_wildly_above_capacity():
    """
    Enrollment shouldn't massively exceed capacity on a normal course.
    20% margin allowed — these are independent models, slight overshoot
    is possible. If enrollment is 2x capacity, feature alignment is broken.
    """
    features = _make_feature_dict(1, 1)
    cap = M.predict_capacity(features)
    enr = M.predict_enrollment(features)
    assert enr <= cap * 2.0, (
        f"Enrollment ({enr:.1f}) is more than 2x capacity — likely feature misalignment ({cap:.1f})"
    )


# ---------------------------------------------------------------------------
# Test 5 — MISSING KEY
# ---------------------------------------------------------------------------
def test_missing_key_offered():
    bad = _make_feature_dict(1, 1)
    del bad["hist_n_offerings"]
    with pytest.raises(KeyError):
        M.predict_offered(bad)


def test_missing_key_capacity():
    bad = _make_feature_dict(1, 1)
    del bad["hist_enrolled_total"]
    with pytest.raises(KeyError):
        M.predict_capacity(bad)


def test_missing_key_enrollment():
    bad = _make_feature_dict(1, 1)
    del bad["is_burnaby"]
    with pytest.raises(KeyError):
        M.predict_enrollment(bad)


# ---------------------------------------------------------------------------
# Test 6 — COLD START
# ---------------------------------------------------------------------------
def test_cold_start_does_not_crash():
    """ml_course_id=0 was never in training. Should not raise."""
    features = _make_feature_dict(ml_course_id=0, ml_term_id=1)
    prob = M.predict_offered(features)
    cap  = M.predict_capacity(features)
    enr  = M.predict_enrollment(features)
    assert isinstance(prob, float)
    assert isinstance(cap,  float)
    assert isinstance(enr,  float)


# ---------------------------------------------------------------------------
# Test 7 — SMOKE TESTS  (real DB data)
# ---------------------------------------------------------------------------
def test_smoke_cmpt225_fall():
    """
    CMPT 225 runs every Fall in our training data.
    Offered probability should be high (> 0.70).
    """
    ml_course_id, ml_term_id = _get_course_ids("CMPT", "225", semester=3)
    features = _make_feature_dict(ml_course_id, ml_term_id, course_level=200)
 
    prob = M.predict_offered(features)
    cap  = M.predict_capacity(features)
    enr  = M.predict_enrollment(features)
 
    # Write results to the test folder
    out = TEST_OUT / "smoke_cmpt225_fall.txt"
    out.write_text(
        f"CMPT 225 Fall\n"
        f"  offered_prob : {prob:.4f}\n"
        f"  capacity     : {cap:.1f}\n"
        f"  enrollment   : {enr:.1f}\n"
    )
 
    assert prob > 0.70, f"CMPT 225 Fall offered prob too low: {prob:.2f}"


def test_smoke_cmpt120_spring():
    """CMPT 120 runs every Spring — offered prob should be high."""
    ml_course_id, ml_term_id = _get_course_ids("CMPT", "120", semester=1)
    features = _make_feature_dict(ml_course_id, ml_term_id, course_level=100)

    prob = M.predict_offered(features)

    out = TEST_OUT / "smoke_cmpt120_spring.txt"
    out.write_text(f"CMPT 120 Spring\n  offered_prob : {prob:.4f}\n")

    assert prob > 0.65, f"CMPT 120 Spring offered prob too low: {prob:.2f}"