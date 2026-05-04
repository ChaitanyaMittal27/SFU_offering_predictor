# Data — SFU Course Predictor

This folder contains the raw data for the SFU Course Predictor ML project.
Everything here is the output of the **data collection stage** — no cleaning,
no feature engineering, no derived metrics. All of that happens in
`notebooks/01_eda.ipynb` and `notebooks/02_features.ipynb`.

---

## What's in here

```
data/
├── raw/
│   ├── sfu_ml.db          # SQLite database — the entire dataset
│   ├── courses.csv        # Exported from Supabase (source of ml_courses)
│   ├── departments.csv    # Exported from Supabase (source of ml_courses)
│   └── collection_log.txt # Log from the last collection run
└── processed/             # Empty until feature engineering runs
```

The SQLite database contains three tables:

| Table                  | Rows   | Description                           |
| ---------------------- | ------ | ------------------------------------- |
| `ml_terms`             | 18     | All semesters Spring 2020 → Fall 2025 |
| `ml_courses`           | 3,310  | SFU course catalogue from Supabase    |
| `ml_section_offerings` | 50,581 | Raw section data from Coursys API     |

---

## Database schema

### ml_terms

One row per semester. Seeded manually.

| Column            | Type       | Notes                                    |
| ----------------- | ---------- | ---------------------------------------- |
| ml_term_id        | INTEGER PK |                                          |
| year              | INTEGER    | e.g. 2023                                |
| term              | TEXT       | spring / summer / fall                   |
| term_order        | INTEGER    | 1=spring, 2=summer, 3=fall               |
| semester_code     | INTEGER    | Coursys API code e.g. 1257 for Fall 2025 |
| is_covid_affected | INTEGER    | 1 for 2020 and 2021 terms                |

Semester code pattern: `1` + `2` + 2-digit year + semester digit (1/4/7)

- Spring 2023 = 1231, Summer 2023 = 1234, Fall 2023 = 1237

### ml_courses

Flat copy of courses + departments. Populated once from CSV export.

| Column           | Type       | Notes                               |
| ---------------- | ---------- | ----------------------------------- |
| ml_course_id     | INTEGER PK |                                     |
| source_course_id | INTEGER    | courses.course_id in Supabase       |
| dept_code        | TEXT       | e.g. CMPT, MATH, BUS (uppercase)    |
| dept_name        | TEXT       | Full department name                |
| course_number    | TEXT       | e.g. 225, 120, 360W (uppercase)     |
| course_level     | INTEGER    | First digit × 100 (100/200/.../900) |
| title            | TEXT       |                                     |
| units            | INTEGER    | Credit units                        |
| degree_level     | TEXT       | UGRD / GRAD                         |
| prereq_count     | INTEGER    | Count of prerequisites              |
| has_coreqs       | INTEGER    | 0/1 boolean                         |
| designation      | TEXT       | e.g. Quantitative/Breadth-Science   |

### ml_section_offerings

Raw API data. One row per section per term. Core training data.

| Column        | Type       | Notes                              |
| ------------- | ---------- | ---------------------------------- |
| offering_id   | INTEGER PK |                                    |
| ml_course_id  | INTEGER    | NULL if course not in ml_courses   |
| ml_term_id    | INTEGER FK | References ml_terms                |
| dept_code     | TEXT       | Raw from API e.g. CMPT             |
| course_number | TEXT       | Raw from API e.g. 276              |
| section_code  | TEXT       | Raw from API e.g. D100, G300, I100 |
| instructor    | TEXT       | As returned, NULL if not assigned  |
| campus        | TEXT       | Burnaby / Surrey / Vancouver       |
| capacity      | INTEGER    | NULL if not published              |
| enrolled      | INTEGER    | NULL if not published              |
| waitlist      | INTEGER    | NULL if no waitlist, 0 if none     |
| collected_at  | TIMESTAMP  | When this row was collected        |

**Important:** `section_code` is stored raw — no classification.
`section_type` and `is_primary` are derived in EDA, not stored here.
The full classification of section code prefixes is documented below.

---

## Data source — Coursys API

The `ml_section_offerings` table is populated from SFU's Coursys system
via its undocumented but publicly accessible JSON endpoint:

```
GET https://coursys.sfu.ca/browse/?subject[]=CMPT&semester[]=1257&tabledata=yes&length=-1
```

Parameters:

- `subject[]` — department code e.g. CMPT, MATH, BUS
- `semester[]` — semester code e.g. 1257 for Fall 2025
- `tabledata=yes` — returns JSON instead of HTML
- `length=-1` — returns all rows (without this, only 10 rows returned)

Example response row:

```json
[
  "Fall 2025",
  "<a href=\"/browse/info/2025fa-cmpt-276-d1\">CMPT 276 D100</a>",
  "Intro Software Engineering",
  "96/100",
  "Alimadadi Jani, Saba",
  "Burnaby"
]
```

Fields: term label, section link (HTML), title, enrolled/capacity, instructor, campus

The enrollment string has four formats:

- `"96/100"` → enrolled=96, capacity=100, waitlist=0
- `"138/150 (+33)"` → enrolled=138, capacity=150, waitlist=33
- `"?/20"` → enrolled=NULL, capacity=20, waitlist=NULL
- `"?/?"` → all NULL

**Coursys does not require login.** This is public data.
Please rate-limit requests to at least 1 second between calls.

Alternatively, you could use https://sfucourseplanner.com/docs for more customized data pulling.

---

## Section code prefixes

Section codes are stored raw. Here is the complete classification
used during EDA (derived, not stored in the DB):

**Primary sections** — standalone lectures with their own enrollment/capacity.
Only these are used for capacity and enrollment prediction models.

| Prefix | Type                         | Example          |
| ------ | ---------------------------- | ---------------- |
| D      | In-person lecture            | D100, D200       |
| E      | Evening lecture (standalone) | E100, E200       |
| O      | Online lecture               | O100, OL01, OP01 |
| C      | Old distance education       | C100, C200       |
| J      | NoW cohort lecture           | J100             |
| G      | Grad / alternate campus      | G100, G200       |
| N      | Night section                | N100             |

**Non-primary sections** — sub-sections tied to a lecture.
Enrollment overlaps with primary — do not double count.

| Prefix | Type                            | Example    |
| ------ | ------------------------------- | ---------- |
| I      | Individual/directed study       | I100, I200 |
| L      | Laboratory                      | L100, LA01 |
| T      | Tutorial                        | T100       |
| S      | Seminar sub-section             | S100       |
| P      | Practicum                       | P100       |
| W      | Workshop                        | W100       |
| R      | Recitation / rotation           | R100       |
| B      | Blended/hybrid sub-section      | B100       |
| A      | Asynchronous online sub-section | A100       |
| F      | Field study                     | F100       |

Rare prefixes confirmed in data: `Z` (1 row), `H` (1 row) — investigate in EDA.

---

## Known limitations

**13,648 rows (27%) have no instructor listed.**
Expected — grad thesis, directed study, and unassigned sections have
no instructor in Coursys. Mostly G and I section types.

**4,607 rows (9.1%) have `ml_course_id = NULL`.**
Courses that appear in Coursys but were not in the Supabase catalogue.
Most common: CMNS, STAT, GEOG, REM, EVSC, ARCH departments.
Rows are kept — filter with `WHERE ml_course_id IS NOT NULL` when
course-level features are needed.

**470 rows have both enrolled=0 and capacity=0.**
Placeholder or thesis registration sections. Filter during EDA.

**1,066 rows are over-enrolled (enrolled > capacity).**
Stored as-is. Real demand signal — do not cap or filter.

**2020 and 2021 terms are COVID-affected.**
`is_covid_affected = 1` on those 6 terms. Abnormal delivery and
enrollment patterns. Include in training but use the flag as a feature.

---

## Setup — reproduce the dataset from scratch

**Time required: 30–40 minutes** (mostly Coursys API rate limiting)

### Prerequisites

```bash
# Python 3.10+ with virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

You also need `data/raw/courses.csv` and `data/raw/departments.csv`
you can get these data using this api: https://sfucourseplanner.com/docs

---

### Step 1 — Create database and seed terms

```bash
python sql/run_setup.py
```

Creates `data/raw/sfu_ml.db` with all three empty tables.
Seeds `ml_terms` with all 18 semesters (Spring 2020 → Fall 2025).

Expected output:

```
Running 01_create_tables.sql... done.
Running 02_seed_terms.sql... done.
ml_terms: 18 rows
ml_courses: 0 rows
ml_section_offerings: 0 rows
```

---

### Step 2 — Populate ml_courses from CSV

```bash
python src/collect/01_init_db.py
```

Reads `courses.csv` + `departments.csv`, joins them, derives
`course_level` and `prereq_count`, inserts into `ml_courses`.
Course numbers are uppercased to match Coursys format.

Expected output:

```
courses.csv:     3314 rows
departments.csv: 78 rows
Inserted: ~3310
Skipped:  4
```

---

### Step 3 — Collect all offerings from Coursys

```bash
python src/collect/02_collect_offerings.py
```

Loops 18 terms × 76 departments = ~1,368 API calls at 1.2s per call.
Resume-safe — re-running skips rows already collected.

Expected output:

```
Inserted:      ~50,581
API errors:    0
Parse failures:0
Match rate:    ~90%
```

**This step takes 30–40 minutes. Let it run.**

---

### Step 4 — Verify

```bash
python src/test/verify_db.py
```

Runs 10 checks and prints a full report.
All checks should pass before proceeding to EDA.

Expected final line:

```
ALL CHECKS PASSED — data stage complete
```

---

## Useful queries

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect('data/raw/sfu_ml.db')

# Full working dataset — matched courses only
df = pd.read_sql("""
    SELECT
        c.dept_code, c.course_number, c.course_level,
        c.units, c.degree_level,
        t.year, t.term, t.term_order, t.is_covid_affected,
        o.section_code, o.instructor, o.campus,
        o.capacity, o.enrolled, o.waitlist
    FROM ml_section_offerings o
    JOIN ml_courses c ON o.ml_course_id = c.ml_course_id
    JOIN ml_terms   t ON o.ml_term_id   = t.ml_term_id
    WHERE o.ml_course_id IS NOT NULL
""", conn)

# Primary sections only (filter by section code prefix)
primary_prefixes = ('D', 'E', 'O', 'C', 'J', 'G', 'N')
df_primary = df[df['section_code'].str[0].str.upper().isin(primary_prefixes)]

# Specific course history
cmpt120 = pd.read_sql("""
    SELECT t.year, t.term, o.section_code,
           o.enrolled, o.capacity, o.waitlist, o.instructor
    FROM ml_section_offerings o
    JOIN ml_courses c ON o.ml_course_id = c.ml_course_id
    JOIN ml_terms   t ON o.ml_term_id   = t.ml_term_id
    WHERE c.dept_code = 'CMPT' AND c.course_number = '120'
    ORDER BY t.year, t.term_order
""", conn)
```
