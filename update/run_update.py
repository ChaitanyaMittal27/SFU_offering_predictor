"""
update/run_update.py
---------------------
Orchestrates the full update pipeline. Triggered by GitHub Actions on a schedule.

Sequence:
    1. update_raw_db_latest_semester.py  — adds new semester to sfu_ml.db
    2. 01_cleaning.ipynb                 — regenerates sfu_clean.db
    3. 03_feature_engineering.ipynb      — regenerates all CSVs
    4. 05_combined_eval.ipynb            — evaluates models, writes eval_results.json
    5. 06_refit.ipynb                    — refits models on all data, overwrites .pkl files
    6. git add + commit + push           — deploys to Streamlit Cloud

If anything fails: git checkout -- . (discard all changes, nothing is committed)

Usage:
    python update/run_update.py                   # uses today's date
    python update/run_update.py 2026-09-01        # explicit date
"""

import subprocess
import sys
import os
from datetime import date, datetime
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
NOTEBOOKS  = ROOT / "notebooks"
UPDATE_DIR = ROOT / "update"


# ── helpers ───────────────────────────────────────────────────────────────────
def run(cmd: list, label: str) -> bool:
    """Run a command, stream output, return True if it succeeded."""
    print(f"\n{'─'*60}")
    print(f"  ▶  {label}")
    print(f"{'─'*60}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\n  ✗  FAILED: {label}  (exit {result.returncode})")
        return False
    print(f"\n  ✓  {label}")
    return True


def run_notebook(nb_path: Path, label: str) -> bool:
    """Execute a Jupyter notebook in-place via nbconvert."""
    return run(
        [
            sys.executable, "-m", "nbconvert",
            "--to", "notebook",
            "--execute",
            "--inplace",
            "--ExecutePreprocessor.timeout=600",
            str(nb_path),
        ],
        label,
    )


def git_rollback():
    print("\n  Rolling back all changes...")
    subprocess.run(["git", "checkout", "--", "."], cwd=ROOT)
    print("  Rolled back. DB, CSVs, and .pkl files restored to last commit.")


def git_commit_push(term_label: str):
    msg = f"auto-update: add {term_label} data and refit models"
    subprocess.run(["git", "add", "-A"], cwd=ROOT)
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT)
    result = subprocess.run(["git", "push"], cwd=ROOT)
    if result.returncode != 0:
        print("  ✗  git push failed — models updated locally but not deployed.")
        sys.exit(1)
    print(f"  ✓  Pushed: '{msg}'")
    print("  Streamlit Cloud will redeploy automatically.")


# ── semester label (for commit message) ──────────────────────────────────────
def _semester_label(run_date: date) -> str:
    month = run_date.month
    if month <= 4:  return f"spring {run_date.year}"
    if month <= 8:  return f"summer {run_date.year}"
    return f"fall {run_date.year}"


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    # parse optional date arg
    if len(sys.argv) > 1:
        try:
            run_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            print(f"ERROR: date must be YYYY-MM-DD, got: {sys.argv[1]!r}")
            sys.exit(1)
    else:
        run_date = date.today()

    term_label = _semester_label(run_date)

    print(f"\n{'='*60}")
    print(f"  run_update.py")
    print(f"  Date:     {run_date}")
    print(f"  Semester: {term_label}")
    print(f"  Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    steps = [
        # (callable, label)
        (
            lambda: run(
                [sys.executable,
                 str(UPDATE_DIR / "update_raw_db_latest_semester.py"),
                 str(run_date)],
                "Step 1 — Collect new semester data"
            ),
            "Step 1 — Collect new semester data",
        ),
        (
            lambda: run_notebook(
                NOTEBOOKS / "01_cleaning.ipynb",
                "Step 2 — Cleaning"
            ),
            "Step 2 — Cleaning",
        ),
        (
            lambda: run_notebook(
                NOTEBOOKS / "03_feature_engineering.ipynb",
                "Step 3 — Feature engineering"
            ),
            "Step 3 — Feature engineering",
        ),
        (
            lambda: run_notebook(
                NOTEBOOKS / "05_combined_eval.ipynb",
                "Step 4 — Combined evaluation"
            ),
            "Step 4 — Combined evaluation",
        ),
        (
            lambda: run_notebook(
                NOTEBOOKS / "06_refit.ipynb",
                "Step 5 — Refit models"
            ),
            "Step 5 — Refit models",
        ),
    ]

    for step_fn, label in steps:
        if not step_fn():
            print(f"\n  Pipeline failed at: {label}")
            git_rollback()
            sys.exit(1)

    # all steps passed — commit and push
    print(f"\n{'─'*60}")
    print(f"  All steps passed. Committing and pushing...")
    print(f"{'─'*60}")
    git_commit_push(term_label)

    print(f"\n{'='*60}")
    print(f"  UPDATE COMPLETE — {term_label}")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()