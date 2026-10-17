"""Load: write tidy tables to Parquet (data/processed/) and a DuckDB database with analysis views."""
from __future__ import annotations

import logging

import duckdb
import pandas as pd

from . import config

log = logging.getLogger(__name__)

VIEWS = """
-- WBG Results totals (no sub-indicator, no disaggregation): the main analysis table
CREATE OR REPLACE VIEW v_results AS
SELECT r.snapshot_fy, r.snapshot_date, r.ind_code, i.name AS indicator, i.unit, i.outcome_id, r.org,
       r.area_code, r.area_type, a.name AS area_name, a.region_code,
       r.achieved, r.expected,
       r.expected - r.achieved AS remaining_gap,
       CASE WHEN r.expected > 0 THEN r.achieved / r.expected END AS delivery_ratio,
       -- data-quality flag: ratios are only meaningful when 0 <= achieved <= expected
       CASE WHEN r.achieved IS NULL AND r.expected IS NULL THEN 'not_disclosed'
            WHEN r.achieved IS NULL THEN 'achieved_missing'
            WHEN r.expected IS NULL OR r.expected <= 0 THEN 'expected_missing'
            WHEN r.achieved > r.expected THEN 'achieved_above_expected' END AS quality_flag
FROM results r
JOIN indicators i USING (ind_code)
LEFT JOIN areas a USING (area_code)
WHERE r.sub_ind_code = '' AND r.sex = '_T' AND r.age = '_T' AND r.disability = '_T'
  AND r.joint_programming = '_T';

-- Same, female beneficiaries
CREATE OR REPLACE VIEW v_results_female AS
SELECT r.snapshot_fy, r.ind_code, r.org, r.area_code, r.achieved, r.expected
FROM results r
WHERE r.sub_ind_code = '' AND r.sex = 'F' AND r.age = '_T' AND r.disability = '_T' AND r.joint_programming = '_T';

-- Client context / vision time series (totals)
CREATE OR REPLACE VIEW v_context AS
SELECT c.snapshot_fy, c.ind_code, i.name AS indicator, i.unit, i.type, i.outcome_id, i.higher_is_better,
       c.area_code, a.name AS area_name, c.year, c.value
FROM context c
JOIN indicators i USING (ind_code)
LEFT JOIN areas a USING (area_code)
WHERE c.sub_ind_code = '' AND c.sex = '_T' AND c.age = '_T' AND c.disability = '_T';

-- Latest available year per indicator x area (within each snapshot)
CREATE OR REPLACE VIEW v_context_latest AS
SELECT * FROM v_context
QUALIFY row_number() OVER (PARTITION BY snapshot_fy, ind_code, area_code ORDER BY year DESC) = 1;

-- Latest population per country (Data360 / WDI)
CREATE OR REPLACE VIEW v_population AS
SELECT area_code, year, value AS population FROM wdi WHERE indicator = 'population'
QUALIFY row_number() OVER (PARTITION BY area_code ORDER BY year DESC) = 1;

-- Project-level contributions (World Bank operations). NOTE: at project level "disability = Yes" marks a
-- disability-inclusive project (there is no separate total row), so it must NOT be filtered like a breakdown.
CREATE OR REPLACE VIEW v_projects AS
SELECT snapshot_fy, ind_code, proj_id, project_name, area_code, region_code, approval_fy, closing_fy, status,
       commitment_usd, achieved, expected, ibrd_achieved, ibrd_expected, ida_achieved, ida_expected,
       overlap_flag = 'Y' AS overlap, disability = 'Yes' AS disability_inclusive, url
FROM projects WHERE sub_ind_code = '' AND sex = '_T' AND age = '_T';

-- Does the project level add up to the World Bank total for each indicator? (used to decide whether project
-- figures may be shown)
CREATE OR REPLACE VIEW v_project_reconciliation AS
WITH p AS (SELECT snapshot_fy, ind_code, count(DISTINCT proj_id) projects, sum(achieved) a, sum(expected) e
           FROM v_projects GROUP BY ALL),
     w AS (SELECT snapshot_fy, ind_code, achieved a, expected e FROM v_results WHERE org = 'WB' AND area_code = 'ACW')
SELECT w.snapshot_fy, w.ind_code, p.projects, p.a AS projects_achieved, w.a AS wb_achieved, p.e AS projects_expected, w.e AS wb_expected,
       coalesce((p.a IS NULL OR p.a = 0) AND w.a IS NULL OR abs(p.a - w.a) <= 0.005 * abs(w.a), false)
         AND coalesce(abs(p.e - w.e) <= 0.005 * abs(w.e), false) AS reconciles
FROM w LEFT JOIN p USING (snapshot_fy, ind_code);

CREATE OR REPLACE VIEW v_snapshots AS
SELECT snapshot_fy, max(snapshot_date) AS snapshot_date FROM results GROUP BY 1 ORDER BY 1;
"""


def run(tables: dict[str, pd.DataFrame]) -> None:
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(config.PROCESSED_DIR / f"{name}.parquet", index=False)
    tmp = config.DB_PATH.with_suffix(".tmp.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    for name, df in tables.items():
        con.register("df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM df")
        con.unregister("df")
    con.execute(VIEWS)
    con.close()
    tmp.replace(config.DB_PATH)  # atomic swap so the web app never sees a half-written database
    log.info("wrote %s tables to %s", len(tables), config.DB_PATH)
