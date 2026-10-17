"""Data-quality checks. Problems are reported (data/processed/data_quality.json), not silently fixed."""
from __future__ import annotations

import json
import logging

import duckdb

from . import config

log = logging.getLogger(__name__)

CHECKS = {
    "row_counts": """SELECT 'results' t, count(*) n FROM results UNION ALL SELECT 'context', count(*) FROM context
                     UNION ALL SELECT 'projects', count(*) FROM projects UNION ALL SELECT 'areas', count(*) FROM areas
                     UNION ALL SELECT 'active_projects', count(*) FROM active_projects UNION ALL SELECT 'wdi', count(*) FROM wdi""",
    "snapshots": "SELECT * FROM v_snapshots",
    "duplicate_result_keys": """SELECT snapshot_fy, ind_code, org, area_code, count(*) n FROM v_results
                                GROUP BY ALL HAVING count(*) > 1 ORDER BY n DESC LIMIT 20""",
    "achieved_above_expected": """SELECT snapshot_fy, ind_code, area_code, achieved, expected, round(delivery_ratio, 2) ratio
                                  FROM v_results WHERE org = 'WBG' AND delivery_ratio > 1.05
                                  ORDER BY snapshot_fy DESC, ratio DESC LIMIT 50""",
    "results_without_total": """SELECT DISTINCT r.snapshot_fy, r.ind_code FROM results r
                                WHERE r.area_code = 'ACW' AND r.org = 'WBG' AND NOT EXISTS (
                                  SELECT 1 FROM v_results v WHERE v.snapshot_fy = r.snapshot_fy AND v.ind_code = r.ind_code
                                    AND v.area_code = 'ACW' AND v.org = 'WBG') ORDER BY 1, 2""",
    "regions_vs_world": """WITH reg AS (SELECT snapshot_fy, ind_code, sum(achieved) s FROM v_results
                                        WHERE org = 'WBG' AND area_type = 'REGION' AND area_code <> 'ACW' GROUP BY ALL)
                           SELECT v.snapshot_fy, v.ind_code, v.achieved world, reg.s regions_sum,
                                  round(reg.s / nullif(v.achieved, 0), 3) ratio
                           FROM v_results v JOIN reg USING (snapshot_fy, ind_code)
                           WHERE v.org = 'WBG' AND v.area_code = 'ACW' AND abs(reg.s / nullif(v.achieved, 0) - 1) > 0.02
                           ORDER BY ratio LIMIT 30""",
    "unmapped_project_countries": """SELECT count(*) n FROM active_projects WHERE area_code IS NULL""",
}


def run() -> dict:
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    report = {}
    for name, sql in CHECKS.items():
        df = con.execute(sql).df()
        report[name] = json.loads(df.to_json(orient="records", date_format="iso"))
        log.info("check %-26s %s rows", name, len(df))
    failures = list((config.RAW_DIR).glob("fy*/summary_failures.json"))
    report["failed_requests"] = {p.parent.name: json.loads(p.read_text()) for p in failures}
    con.close()
    (config.PROCESSED_DIR / "data_quality.json").write_text(json.dumps(report, indent=1, default=str))
    return report
