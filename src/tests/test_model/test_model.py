"""
src/tests/test_model/test_model.py  —  Tests for the Model Layer

Run from project root:
    pytest src/tests/test_model/test_model.py -v

What is tested:
  1. LOAD     — models import without error
  2. TYPES    — each function returns a Python float
  3. RANGES   — offered prob in [0,1], capacity and enrollment positive
  4. INVERSE  — capacity and enrollment are in real units (not log scale)
  5. MISSING  — missing feature key raises KeyError immediately
  6. COLD     — unseen ml_course_id (0) doesn't crash
  7. SMOKE    — real course from DB, sensible output values
"""

import sys
import sqlite3
import pytest
from pathlib import Path

_SRC = Path(__file__).parent.parent.parent   # test_model/ → tests/ → src/
sys.path.insert(0, str(_SRC))

from paths import DATA_PROCESSED
import model as M

TEST_OUT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_features(**overrides) -> dict:
    """
    Build a complete feature dict with sensible defaults.
    All keys required by all three models are included.
    """
    base = {
        # static course features
        "ml_course_id":                    523,   # real CMPT 225 id
        "dept_code_enc":                   10,
        "degree_level_enc":                1,
        "course_level":                    200,
        "units":                           3,
        "prereq_count":                    1,
        # term features
        "term_order":                      3,     # fall
        "is_covid_affected":               0,
        # offered historical features
        "hist_n_offerings":                12,
        "hist_n_this_semester_offerings":  5,
        "same_semester_offer_ratio":       1.0,
        "n_distinct_semesters_offered":    3,
        "n_terms_since_last_offered":      1.0,
        "n_consecutive_same_semester_streak": 5,
        # capacity historical features
        "hist_avg_capacity_per_offering":  380.0,
        "hist_avg_capacity_this_semester": 400.0,
        "same_semester_capacity_ratio":    1.05,
        "previous_term_capacity":          400.0,
        "previous_same_semester_capacity": 400.0,
        "capacity_trend":                  2.0,
        "hist_avg_sections_per_offering":  3.0,
        "hist_avg_enrollment_per_offering": 280.0,
        # enrollment historical features
        "hist_avg_enrollment_this_semester": 290.0,
        "same_semester_enrollment_ratio":  1.04,
        "previous_same_semester_enrollment": 300.0,
        "previous_term_enrollment":        280.0,
        "enrollment_trend":                1.5,
        "high_fill_rate_frequency":        0.7,
        "course_age_terms":                19.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 1 — LOAD
# ---------------------------------------------------------------------------
def test_models_loaded():
    assert M._model_offered    is not None
    assert M._model_capacity   is not None
    assert M._model_enrollment is not None


# ---------------------------------------------------------------------------
# Test 2 — TYPES
# ---------------------------------------------------------------------------
def test_predict_offered_returns_float():
    result = M.predict_offered(_make_features())
    assert isinstance(result, float), f"Expected float, got {type(result)}"


def test_predict_capacity_returns_float():
    result = M.predict_capacity(_make_features())
    assert isinstance(result, float), f"Expected float, got {type(result)}"


def test_predict_enrollment_returns_float():
    result = M.predict_enrollment(_make_features())
    assert isinstance(result, float), f"Expected float, got {type(result)}"


# ---------------------------------------------------------------------------
# Test 3 — RANGES
# ---------------------------------------------------------------------------
def test_offered_prob_in_zero_one():
    prob = M.predict_offered(_make_features())
    assert 0.0 <= prob <= 1.0, f"Offered probability out of range: {prob}"


def test_capacity_is_positive():
    cap = M.predict_capacity(_make_features())
    assert cap > 0, f"Capacity should be positive, got {cap}"


def test_enrollment_is_positive():
    enr = M.predict_enrollment(_make_features())
    assert enr > 0, f"Enrollment should be positive, got {enr}"


# ---------------------------------------------------------------------------
# Test 4 — INVERSE TRANSFORM
# ---------------------------------------------------------------------------
def test_capacity_is_real_seats_not_log():
    """
    Models trained on log_capacity. expm1 applied in model.py.
    Result should be in real seats (> 1), not log space (~3-6).
    """
    cap = M.predict_capacity(_make_features())
    assert cap > 1.0, f"Capacity looks like log scale: {cap}"


def test_enrollment_is_real_students_not_log():
    enr = M.predict_enrollment(_make_features())
    assert enr > 1.0, f"Enrollment looks like log scale: {enr}"


# ---------------------------------------------------------------------------
# Test 5 — MISSING KEY
# ---------------------------------------------------------------------------
def test_missing_key_offered_raises():
    bad = _make_features()
    del bad["hist_n_offerings"]
    with pytest.raises(KeyError):
        M.predict_offered(bad)


def test_missing_key_capacity_raises():
    bad = _make_features()
    del bad["hist_avg_capacity_per_offering"]
    with pytest.raises(KeyError):
        M.predict_capacity(bad)


def test_missing_key_enrollment_raises():
    bad = _make_features()
    del bad["high_fill_rate_frequency"]
    with pytest.raises(KeyError):
        M.predict_enrollment(bad)


# ---------------------------------------------------------------------------
# Test 6 — COLD START
# ---------------------------------------------------------------------------
def test_cold_start_does_not_crash():
    """ml_course_id=0 was never in training. Should not raise."""
    features = _make_features(
        ml_course_id=0,
        hist_n_offerings=0,
        hist_n_this_semester_offerings=0,
        same_semester_offer_ratio=0.0,
        n_distinct_semesters_offered=0,
        n_terms_since_last_offered=19.0,
        n_consecutive_same_semester_streak=0,
    )
    prob = M.predict_offered(features)
    cap  = M.predict_capacity(features)
    enr  = M.predict_enrollment(features)
    assert isinstance(prob, float)
    assert isinstance(cap,  float)
    assert isinstance(enr,  float)


# ---------------------------------------------------------------------------
# Test 7 — SMOKE (real DB values)
# ---------------------------------------------------------------------------
def test_smoke_cmpt225_fall():
    """
    CMPT 225 runs every Fall. Offered prob should be high (> 0.70).
    Uses the real ml_course_id from the DB.
    """
    conn = sqlite3.connect(DATA_PROCESSED / "sfu_clean.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT DISTINCT ml_course_id FROM offerings "
        "WHERE dept_code='CMPT' AND course_number='225' LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        pytest.skip("CMPT 225 not found in clean DB")

    features = _make_features(
        ml_course_id=int(row["ml_course_id"]),
        term_order=3,  # fall
    )

    prob = M.predict_offered(features)
    cap  = M.predict_capacity(features)
    enr  = M.predict_enrollment(features)

    out = TEST_OUT / "smoke_cmpt225_fall.txt"
    out.write_text(
        f"CMPT 225 Fall\n"
        f"  offered_prob : {prob:.4f}\n"
        f"  capacity     : {cap:.1f} seats\n"
        f"  enrollment   : {enr:.1f} students\n"
    )

    assert prob > 0.70, f"CMPT 225 Fall offered prob too low: {prob:.2f}"
    assert cap > 0,     f"CMPT 225 Fall capacity non-positive: {cap:.1f}"
    assert enr > 0,     f"CMPT 225 Fall enrollment non-positive: {enr:.1f}"
