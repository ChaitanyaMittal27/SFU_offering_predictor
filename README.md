# SFU Course Predictor

A machine learning system that predicts future SFU course offerings using historical enrollment data from Coursys. Ask plain English questions or use the manual form — get offering probability, expected seat capacity, and expected enrollment.

> "Will CMPT 225 be offered in Spring 2027?" → 95% probability. Expect ~400 seats, ~280 enrolled.

## Live App

🤗 **[sfucoursepredictor.hf.space](https://huggingface.co/spaces/ChaitanyaMittal27/sfucoursepredictor)**

The app is deployed from a separate branch that includes the trained model files and databases. See the [hf-deploy branch](https://github.com/ChaitanyaMittal27/SFU_offering_predictor/tree/hf-deploy) for details.

## What It Predicts

- Will a course be offered in a given semester?
- How many seats will be available?
- How many students will enroll?

Supports any SFU course × semester (spring/summer/fall) × year combination.

## How It Works

1. **Data** — 19 terms of SFU section offerings (Spring 2020 – Spring 2026) collected from the Coursys public API, stored in SQLite
2. **Features** — historical averages, same-semester patterns, streaks, trends — computed with strict no-leakage splits
3. **Models** — three scikit-learn models, one per prediction target
4. **Interface** — Google Gemini parses plain English questions into structured parameters; Streamlit serves the app
5. **Updates** — GitHub Actions automatically collects each new semester and refits models (March 1 / July 1 / November 1)

## Model Performance

Evaluated on Spring 2026 (1,522 courses the models had never seen):

| Task          | Model             | Metric   | Score          |
| ------------- | ----------------- | -------- | -------------- |
| Offered?      | Gradient Boosting | AUC-ROC  | 0.864          |
| Offered?      | Gradient Boosting | Accuracy | 74.1%          |
| Seat capacity | Random Forest     | MAE      | 14.6 seats     |
| Seat capacity | Random Forest     | R²       | 0.886          |
| Enrollment    | Random Forest     | MAE      | 11.85 students |
| Enrollment    | Random Forest     | R²       | 0.906          |

**System accuracy** (all 3 predictions simultaneously, within ±10 or ±20%):

| Score | Result        | % of courses |
| ----- | ------------- | ------------ |
| 3/3   | Fully correct | 52.6%        |
| 2/3   | One wrong     | 30.2%        |
| 1/3   | Two wrong     | 14.3%        |
| 0/3   | All wrong     | 3.0%         |

## Project Structure

```
SFU_offering_predictor/
├── app.py                                    # Streamlit entry point
├── gemini.py                                 # Gemini API layer
├── src/
│   ├── collect/                              # One-time data collection scripts
│   ├── context.py                            # Valid input context for Gemini
│   ├── controller.py                         # Prediction orchestration
│   ├── lookup.py                             # Feature building from DB
│   ├── model.py                              # Model loading + inference
│   └── paths.py                              # Project directory constants
├── notebooks/
│   ├── 01_cleaning.ipynb                     # Raw → clean DB
│   ├── 02_eda.ipynb                          # Exploratory data analysis
│   ├── 03_feature_engineering.ipynb          # Feature engineering + train/test split
│   ├── 04a_model_offered.ipynb               # Offered model selection (GB wins)
│   ├── 04b_model_capacity.ipynb              # Capacity model selection (RF wins)
│   ├── 04c_model_enrollment.ipynb            # Enrollment model selection (RF wins)
│   ├── 05_combined_eval.ipynb                # Combined evaluation → eval_results.json
│   └── 06_refit.ipynb                        # Refit winners on all data
├── update/
│   ├── update_raw_db_latest_semester.py      # Collect one new semester from Coursys
│   └── run_update.py                         # Pipeline orchestrator
├── .github/workflows/
│   └── update.yml                            # Scheduled update (Mar 1 / Jul 1 / Nov 1)
├── figures/                                  # EDA and evaluation charts
├── sql/                                      # DB setup scripts
├── data/                                     # gitignored — local only
├── models/                                   # gitignored — local only
└── requirements.txt
```

## Auto-Update Pipeline

Every semester, GitHub Actions:

1. Collects new term data from Coursys API
2. Re-runs cleaning and feature engineering
3. Evaluates existing models against the new term
4. Refits all three models on the expanded dataset
5. Pushes updated models → Hugging Face auto-redeploys

If any step fails, all changes are rolled back via `git checkout -- .`

## Train Your Own

To collect the data and train from scratch locally:

```bash
# 1. Set up environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt

# 2. Set up the database
# Edit sql/02_seed_terms.sql if you want to add/remove terms
python sql/run_setup.py

# 3. Collect course catalog and offerings
python src/collect/01_init_db.py
python src/collect/02_collect_offerings.py   # takes ~1 hour

# 4. Run notebooks in order
# notebooks/01_cleaning.ipynb
# notebooks/02_eda.ipynb              (optional — exploration only)
# notebooks/03_feature_engineering.ipynb
# notebooks/04a_model_offered.ipynb
# notebooks/04b_model_capacity.ipynb
# notebooks/04c_model_enrollment.ipynb
# notebooks/05_combined_eval.ipynb
# notebooks/06_refit.ipynb

# 5. Add your Gemini API key
# Create .streamlit/secrets.toml:
# GEMINI_API_KEY = "your-key-here"

# 6. Run the app
streamlit run app.py
```

## Tech Stack

Python 3.12 · scikit-learn · pandas · numpy · Streamlit · Google Gemini API · SQLite · nbconvert · GitHub Actions

## Data Source

Course enrollment data from [SFU Coursys](https://coursys.sfu.ca/browse/) via its public JSON API. 19 terms (Spring 2020 – Spring 2026), ~50k section offerings across all SFU departments.

---

_Not affiliated with Simon Fraser University._
