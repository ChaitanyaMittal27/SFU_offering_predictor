"""
src/model.py  —  Model Layer

Loads the three trained final models from disk once at import time.
Exposes exactly three functions — one per prediction target.

Rules:
  - No business logic here. No feature building. No formatting.
  - Each function receives a ready-to-use feature dict and returns a raw number.
  - The controller (controller.py) is responsible for building that feature dict.
"""

import json
import joblib
import pandas as pd
from paths import MODELS

# ---------------------------------------------------------------------------
# Load everything once at import time
# ---------------------------------------------------------------------------
_model_offered    = joblib.load(MODELS / "final_model_offered.pkl")
_model_capacity   = joblib.load(MODELS / "final_model_capacity.pkl")
_model_enrollment = joblib.load(MODELS / "final_model_enrollment.pkl")
_scaler           = joblib.load(MODELS / "scaler.pkl")

with open(MODELS / "feature_sets.json") as f:
    _feature_sets = json.load(f)

with open(MODELS / "scale_cols.json") as f:
    _scale_cols = json.load(f)

_FEATURES_OFFERED    = _feature_sets["model_offered"]
_FEATURES_CAPACITY   = _feature_sets["model_capacity"]
_FEATURES_ENROLLMENT = _feature_sets["model_enrollment"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _to_df(features: dict, columns: list) -> pd.DataFrame:
    """
    Select required columns from the feature dict → single-row DataFrame.
    Raises KeyError if any required feature is missing.
    """
    return pd.DataFrame([{col: features[col] for col in columns}])


def _scale(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the saved scaler to columns that need it; leave others alone."""
    cols = [c for c in _scale_cols if c in df.columns]
    if cols:
        df = df.copy()
        df[cols] = _scaler.transform(df[cols])
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_offered(features: dict) -> float:
    """Probability [0, 1] that the course will be offered."""
    df = _scale(_to_df(features, _FEATURES_OFFERED))
    return float(_model_offered.predict_proba(df)[0][1])


def predict_capacity(features: dict) -> float:
    """Expected total seat capacity if the course runs."""
    df = _scale(_to_df(features, _FEATURES_CAPACITY))
    return float(_model_capacity.predict(df)[0])


def predict_enrollment(features: dict) -> float:
    """Expected number of students who will enroll."""
    df = _scale(_to_df(features, _FEATURES_ENROLLMENT))
    return float(_model_enrollment.predict(df)[0])