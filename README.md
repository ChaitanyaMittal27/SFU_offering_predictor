# SFU Course Predictor

An AI-powered course prediction system for Simon Fraser University. Ask plain English questions about future course offerings and get data-backed probabilistic answers.

> "Will CMPT 225 be offered in Summer 2026?" → Yes, 78% probability. Expect ~90 seats, ~85 enrolled.

## Live App

🚧 Coming soon — deploying to Streamlit Cloud

## What It Can Answer

- Will a course be offered in a given semester?
- How many seats will there be?
- How many students will enroll?
- Will a specific instructor teach it?
- Which courses are likely to be cancelled in Summer?

## How It Works

1. Historical enrollment data (2020–2025) collected from SFU's Coursys system
2. Four scikit-learn models trained on that data (two classifiers, two regressors)
3. Google Gemini API extracts structured parameters from plain English questions
4. Models run, Gemini formats the answer in natural language
5. Streamlit web app wraps everything

## Model Accuracy

| Model            | Type       | Metric   | Score |
| ---------------- | ---------- | -------- | ----- |
| model_offered    | Classifier | Accuracy | TBD   |
| model_capacity   | Regressor  | MAE      | TBD   |
| model_enrollment | Regressor  | MAE      | TBD   |
| model_prof       | Classifier | Accuracy | TBD   |

## Project Structure

```
sfu-course-predictor/
├── data/               # SQLite DB + processed CSVs
├── notebooks/          # Jupyter notebooks (EDA, features, models)
├── src/                # Python source code
│   ├── collect/        # Data collection scripts
│   ├── features/       # Feature engineering
│   ├── models/         # Training scripts
│   └── predict/        # Prediction pipeline + Gemini layer
├── models/             # Saved .pkl model files
├── reports/figures/    # Charts and visualisations
├── sql/                # DB setup scripts
├── app/                # Streamlit web app
├── DATA_MODEL.md       # Database schema documentation
└── requirements.txt
```

## Tech Stack

Python 3.10+ · scikit-learn · pandas · Streamlit · Google Gemini API · SQLite

## Data Source

Course enrollment data collected from [SFU Coursys](https://coursys.sfu.ca/browse/) via its public JSON API. 2020–2025, ~50k section offerings across all departments.

---

_Built as a portfolio ML project. Not affiliated with Simon Fraser University._
