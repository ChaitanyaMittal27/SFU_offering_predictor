-- ============================================================
-- sql/01_create_tables.sql
-- SFU Course Predictor — Create ML Tables
--
-- Run via: python sql/run_setup.py
--
-- Design principle: raw data only.
-- No derived columns. No classification. No filtering.
-- Everything derived (fill_rate, section_type, is_primary etc.)
-- is computed in EDA notebooks, not stored here.
-- ============================================================


-- ============================================================
-- TABLE: ml_terms
-- ============================================================
CREATE TABLE IF NOT EXISTS ml_terms (
    ml_term_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    year              INTEGER NOT NULL,
    term              TEXT    NOT NULL,
    term_order        INTEGER NOT NULL,
    semester_code     INTEGER NOT NULL UNIQUE,
    is_covid_affected INTEGER NOT NULL DEFAULT 0,
    UNIQUE(year, term)
);


-- ============================================================
-- TABLE: ml_courses
-- Flat copy of courses + departments. Populated once from CSVs.
-- ============================================================
CREATE TABLE IF NOT EXISTS ml_courses (
    ml_course_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_course_id  INTEGER NOT NULL UNIQUE,
    dept_code         TEXT    NOT NULL,
    dept_name         TEXT,
    course_number     TEXT    NOT NULL,
    course_level      INTEGER,
    title             TEXT,
    units             INTEGER,
    degree_level      TEXT,
    prereq_count      INTEGER NOT NULL DEFAULT 0,
    has_coreqs        INTEGER NOT NULL DEFAULT 0,
    designation       TEXT
);

CREATE INDEX IF NOT EXISTS idx_ml_courses_dept
    ON ml_courses(dept_code);

CREATE INDEX IF NOT EXISTS idx_ml_courses_level
    ON ml_courses(course_level);


-- ============================================================
-- TABLE: ml_section_offerings
-- One row per section per term. Purely raw API data.
--
-- ml_course_id is NULL if the course appeared in Coursys
-- but is not in our ml_courses table. Still stored — not skipped.
--
-- section_code is stored exactly as returned by the API (D100, G300 etc.)
-- section_type and is_primary are derived in EDA, not stored here.
--
-- capacity/enrolled/waitlist are NULL when the API returned ? for that field.
-- instructor/campus are stored as returned — empty string or value.
-- ============================================================
CREATE TABLE IF NOT EXISTS ml_section_offerings (
    offering_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ml_course_id      INTEGER,              -- NULL if course not in ml_courses
    ml_term_id        INTEGER NOT NULL REFERENCES ml_terms(ml_term_id),
    dept_code         TEXT    NOT NULL,     -- raw from API e.g. CMPT
    course_number     TEXT    NOT NULL,     -- raw from API e.g. 276
    section_code      TEXT    NOT NULL,     -- raw from API e.g. D100
    instructor        TEXT,                 -- as returned, may be empty
    campus            TEXT,                 -- as returned, may be empty
    capacity          INTEGER,              -- NULL if API returned ?
    enrolled          INTEGER,              -- NULL if API returned ?
    waitlist          INTEGER,              -- NULL if no (+N) in response
    collected_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ml_term_id, dept_code, course_number, section_code)
);

CREATE INDEX IF NOT EXISTS idx_offerings_course
    ON ml_section_offerings(ml_course_id);

CREATE INDEX IF NOT EXISTS idx_offerings_term
    ON ml_section_offerings(ml_term_id);

CREATE INDEX IF NOT EXISTS idx_offerings_dept
    ON ml_section_offerings(dept_code);