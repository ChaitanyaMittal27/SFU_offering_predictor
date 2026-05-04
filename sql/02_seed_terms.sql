-- ============================================================
-- sql/02_seed_terms.sql
-- SFU Course Predictor — Seed ml_terms
--
-- Run this after 01_create_tables.sql.
-- Inserts all 15 semesters from Spring 2020 to Fall 2025.
--
-- Semester code pattern:
--   1 + 2 + 2-digit year + semester digit
--   spring=1, summer=4, fall=7
--   e.g. Fall 2025 = 1 + 2 + 25 + 7 = 1257
--
-- COVID flag: 2020 and 2021 terms marked is_covid_affected = 1
-- They stay in the dataset but the model learns they were abnormal.
-- ============================================================

INSERT OR IGNORE INTO ml_terms
    (year, term, term_order, semester_code, is_covid_affected)
VALUES
    -- 2020 (COVID affected)
    (2020, 'spring', 1, 1201, 1),
    (2020, 'summer', 2, 1204, 1),
    (2020, 'fall',   3, 1207, 1),

    -- 2021 (COVID affected)
    (2021, 'spring', 1, 1211, 1),
    (2021, 'summer', 2, 1214, 1),
    (2021, 'fall',   3, 1217, 1),

    -- 2022 (post-COVID, normal)
    (2022, 'spring', 1, 1221, 0),
    (2022, 'summer', 2, 1224, 0),
    (2022, 'fall',   3, 1227, 0),

    -- 2023 (normal)
    (2023, 'spring', 1, 1231, 0),
    (2023, 'summer', 2, 1234, 0),
    (2023, 'fall',   3, 1237, 0),

    -- 2024 (normal — training data)
    (2024, 'spring', 1, 1241, 0),
    (2024, 'summer', 2, 1244, 0),
    (2024, 'fall',   3, 1247, 0),

    -- 2025 (test data — model is evaluated on this)
    (2025, 'spring', 1, 1251, 0),
    (2025, 'summer', 2, 1254, 0),
    (2025, 'fall',   3, 1257, 0);
