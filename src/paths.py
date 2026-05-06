"""
src/paths.py  —  Project Directory Constants

Defines the key directories only. Individual files are constructed
from these in whatever module needs them.

Usage:
    from paths import MODELS, DATA_PROCESSED
    model = joblib.load(MODELS / "final_model_offered.pkl")
    df    = pd.read_csv(DATA_PROCESSED / "04_train.csv")
"""

from pathlib import Path

# Project root — two levels up from src/paths.py
ROOT = Path(__file__).parent.parent

SRC             = ROOT / "src"
DATA            = ROOT / "data"
DATA_RAW        = ROOT / "data" / "raw"
DATA_PROCESSED  = ROOT / "data" / "processed"
MODELS          = ROOT / "models"
NOTEBOOKS       = ROOT / "notebooks"
FIGURES         = ROOT / "figures"
DOCS            = ROOT / "docs"
SQL             = ROOT / "sql"