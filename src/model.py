"""
src/model.py  —  Model Layer

Loads the three refit models from disk once at import time.
Exposes exactly three functions — one per prediction target.

Rules:
  - No business logic. No feature building. No formatting.
  - Each function receives a complete feature dict and returns a raw float.
  - Capacity and enrollment models were trained on log-transformed targets.
    expm1() is applied here so callers always get real-unit values.
  - RF and GB do not require scaling — no scaler needed.
"""

import numpy as np
import joblib
import pandas as pd
from paths import MODELS

# ---------------------------------------------------------------------------
# Load once at import time
# ---------------------------------------------------------------------------
_model_offered    = joblib.load(MODELS / "model_offered.pkl")
_model_capacity   = joblib.load(MODELS / "model_capacity.pkl")
_model_enrollment = joblib.load(MODELS / "model_enrollment.pkl")

# ---------------------------------------------------------------------------
# Feature columns — must match feature engineering exactly
# ---------------------------------------------------------------------------
FEATURES_OFFERED = [
    "ml_course_id", "dept_code_enc", "degree_level_enc", "course_level", "units",
    "term_order", "is_covid_affected",
    "hist_n_offerings", "hist_n_this_semester_offerings", "same_semester_offer_ratio",
    "n_distinct_semesters_offered", "n_terms_since_last_offered",
    "n_consecutive_same_semester_streak",
]
FEATURES_CAPACITY = [
    "ml_course_id", "dept_code_enc", "degree_level_enc", "course_level", "units",
    "term_order", "is_covid_affected",
    "hist_avg_capacity_per_offering", "hist_avg_capacity_this_semester",
    "same_semester_capacity_ratio", "previous_term_capacity",
    "previous_same_semester_capacity", "capacity_trend",
    "hist_n_offerings", "hist_avg_sections_per_offering",
    "hist_avg_enrollment_per_offering",
]
FEATURES_ENROLLMENT = [
    "ml_course_id", "dept_code_enc", "degree_level_enc", "course_level", "units",
    "term_order", "is_covid_affected",
    "hist_avg_capacity_per_offering", "hist_avg_capacity_this_semester",
    "hist_avg_enrollment_per_offering", "hist_avg_enrollment_this_semester",
    "same_semester_enrollment_ratio", "previous_same_semester_enrollment",
    "previous_term_enrollment", "enrollment_trend",
    "hist_n_offerings", "hist_avg_sections_per_offering",
    "high_fill_rate_frequency", "prereq_count", "course_age_terms",
]


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------
def _to_df(features: dict, columns: list) -> pd.DataFrame:
    """
    Select required columns from feature dict → single-row DataFrame.
    Raises KeyError immediately if any required feature is missing.
    """
    return pd.DataFrame([{col: features[col] for col in columns}])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def predict_offered(features: dict) -> float:
    """Probability [0.0, 1.0] that the course will be offered."""
    df = _to_df(features, FEATURES_OFFERED)
    return float(_model_offered.predict_proba(df)[0][1])


def predict_capacity(features: dict) -> float:
    """
    Expected total seat capacity if the course runs.
    Returns real seats (inverse of log transform applied internally).
    """
    df = _to_df(features, FEATURES_CAPACITY)
    return float(np.expm1(_model_capacity.predict(df)[0]))


def predict_enrollment(features: dict) -> float:
    """
    Expected total enrollment if the course runs.
    Returns real students (inverse of log transform applied internally).
    """
    df = _to_df(features, FEATURES_ENROLLMENT)
    return float(np.expm1(_model_enrollment.predict(df)[0]))
