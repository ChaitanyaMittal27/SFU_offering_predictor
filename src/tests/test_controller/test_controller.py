"""
src/tests/test_controller/test_controller.py  —  Tests for the Controller Layer

Run from project root:
    python -m pytest src/tests/test_controller/test_controller.py -v

Output files written to the same folder as this test file (TEST_OUT).
"""

import sys
import json
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SRC = Path(__file__).parent.parent.parent   # src/tests/test_controller → src/
sys.path.insert(0, str(_SRC))

from controller import predict, get_context   # noqa: E402

TEST_OUT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save(filename: str, data: dict):
    """Write result dict as formatted JSON to TEST_OUT folder."""
    (TEST_OUT / filename).write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Test 1 — SCHEMA: ok result always has all keys
# ---------------------------------------------------------------------------
def test_ok_schema():
    result = predict("CMPT", "225", "fall", 2027)
    required = {
        "status", "dept", "course_num", "semester", "year",
        "offered_prob", "capacity", "enrollment",
        "is_cold_start", "is_unlikely", "error",
    }
    assert required == set(result.keys()), (
        f"Missing keys: {required - set(result.keys())}"
    )


def test_error_schema():
    result = predict("CMPT", "999", "fall", 2027)
    required = {
        "status", "dept", "course_num", "semester", "year",
        "offered_prob", "capacity", "enrollment",
        "is_cold_start", "is_unlikely", "error",
    }
    assert required == set(result.keys()), (
        f"Missing keys: {required - set(result.keys())}"
    )


# ---------------------------------------------------------------------------
# Test 2 — STATUS: correct status for ok and error cases
# ---------------------------------------------------------------------------
def test_known_course_returns_ok():
    result = predict("CMPT", "225", "fall", 2027)
    assert result["status"] == "ok"


def test_unknown_course_returns_error():
    result = predict("CMPT", "999", "fall", 2027)
    assert result["status"] == "error"
    assert result["error"] is not None


def test_bad_semester_returns_error():
    result = predict("CMPT", "225", "autumn", 2027)
    assert result["status"] == "error"


def test_bad_year_returns_error():
    result = predict("CMPT", "225", "fall", 1995)
    assert result["status"] == "error"


def test_unknown_dept_returns_error():
    result = predict("ZZZZ", "225", "fall", 2027)
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Test 3 — NORMALISATION: case and format variations all resolve correctly
# ---------------------------------------------------------------------------
def test_lowercase_dept_and_semester():
    result = predict("cmpt", "225", "fall", 2027)
    assert result["status"] == "ok"
    assert result["dept"] == "CMPT"
    assert result["semester"] == "fall"


def test_mixed_case_dept():
    result = predict("Cmpt", "225", "Fall", 2027)
    assert result["status"] == "ok"


def test_lowercase_course_num():
    """360w should resolve same as 360W."""
    lower = predict("CMPT", "360w", "fall", 2027)
    upper = predict("CMPT", "360W", "fall", 2027)
    # both should have same status (either both ok or both error)
    assert lower["status"] == upper["status"]


# ---------------------------------------------------------------------------
# Test 4 — TYPES: fields are the right Python types in ok result
# ---------------------------------------------------------------------------
def test_ok_field_types():
    result = predict("CMPT", "225", "fall", 2027)
    assert result["status"] == "ok"
    assert isinstance(result["offered_prob"],  float)
    assert isinstance(result["capacity"],      int)
    assert isinstance(result["enrollment"],    int)
    assert isinstance(result["is_cold_start"], bool)
    assert isinstance(result["is_unlikely"],   bool)
    assert result["error"] is None


def test_error_fields_are_none():
    result = predict("CMPT", "999", "fall", 2027)
    assert result["offered_prob"]  is None
    assert result["capacity"]      is None
    assert result["enrollment"]    is None
    assert result["is_cold_start"] is None
    assert result["is_unlikely"]   is None


# ---------------------------------------------------------------------------
# Test 5 — RANGES: prediction values in sensible bounds
# ---------------------------------------------------------------------------
def test_offered_prob_in_range():
    result = predict("CMPT", "225", "fall", 2027)
    assert result["status"] == "ok"
    assert 0.0 <= result["offered_prob"] <= 1.0


def test_capacity_positive():
    result = predict("CMPT", "225", "fall", 2027)
    assert result["status"] == "ok"
    assert result["capacity"] > 0


def test_enrollment_positive():
    result = predict("CMPT", "225", "fall", 2027)
    assert result["status"] == "ok"
    assert result["enrollment"] > 0


# ---------------------------------------------------------------------------
# Test 6 — FLAGS
# ---------------------------------------------------------------------------
def test_is_unlikely_false_for_consistent_course():
    """CMPT 225 runs every term — should not be unlikely."""
    result = predict("CMPT", "225", "fall", 2027)
    assert result["status"] == "ok"
    assert result["is_unlikely"] is False


def test_is_cold_start_false_for_known_course():
    """CMPT 225 has years of history — should not be cold start."""
    result = predict("CMPT", "225", "fall", 2027)
    assert result["status"] == "ok"
    assert result["is_cold_start"] is False


# ---------------------------------------------------------------------------
# Test 7 — FUTURE TERM: prediction works for terms not yet in DB
# ---------------------------------------------------------------------------
def test_future_term_ok():
    result = predict("CMPT", "225", "spring", 2030)
    assert result["status"] == "ok"
    assert result["year"] == 2030


def test_past_term_in_db_ok():
    """Terms that exist in the DB should also work fine."""
    result = predict("CMPT", "225", "fall", 2023)
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 8 — CONTEXT: get_context returns expected structure
# ---------------------------------------------------------------------------
def test_context_schema():
    ctx = get_context()
    assert "semesters"         in ctx
    assert "year_range"        in ctx
    assert "depts"             in ctx
    assert "course_pairs"      in ctx
    assert "semester_examples" in ctx


def test_context_semesters():
    ctx = get_context()
    assert set(ctx["semesters"]) == {"spring", "summer", "fall"}


def test_context_year_range():
    ctx = get_context()
    assert ctx["year_range"]["min"] > 2025
    assert ctx["year_range"]["max"] > ctx["year_range"]["min"]


def test_context_course_pairs_have_required_keys():
    ctx = get_context()
    assert len(ctx["course_pairs"]) > 0
    first = ctx["course_pairs"][0]
    assert "dept"       in first
    assert "course_num" in first
    assert "title"      in first


# ---------------------------------------------------------------------------
# Test 9 — SMOKE: save full results to TEST_OUT for inspection
# ---------------------------------------------------------------------------
def test_smoke_save_results():
    """
    Runs predict() on a handful of real cases and saves results to
    TEST_OUT so you can inspect actual prediction values after a run.
    """
    cases = [
        ("CMPT", "225",  "fall",   2027),
        ("CMPT", "120",  "spring", 2026),
        ("MATH", "151",  "fall",   2026),
        ("CMPT", "225",  "summer", 2030),   # far future
        ("CMPT", "999",  "fall",   2027),   # error case
        ("CMPT", "225",  "autumn", 2027),   # bad semester
    ]

    all_results = {}
    for dept, course_num, semester, year in cases:
        key = f"{dept}_{course_num}_{semester}_{year}"
        all_results[key] = predict(dept, course_num, semester, year)

    save("smoke_results.json", all_results)

    # At least the known good cases should be ok
    assert all_results["CMPT_225_fall_2027"]["status"]   == "ok"
    assert all_results["CMPT_225_autumn_2027"]["status"] == "error"
    assert all_results["CMPT_999_fall_2027"]["status"]   == "error"