"""Extract: pull every source and store it unchanged (all columns as text) in data/raw/ as Parquet.

Raw files are cached; re-running only fetches what is missing unless ``refresh=True``.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
from pathlib import Path

import pandas as pd

from . import clients, config

log = logging.getLogger(__name__)


def _save(rows: list[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df = df.astype("string") if len(df) else df
    df.to_parquet(path, index=False)
    return len(df)


def _cached(path: Path, refresh: bool) -> bool:
    if path.exists() and not refresh:
        log.info("cached  %s", path.relative_to(config.DATA_DIR))
        return True
    return False


def _summary(area_type: str, area_code: str, org: str, fy: int) -> list[dict]:
    rows = clients.scorecard("getSCSUMMARYDATA", refareatype=area_type, refareacode=area_code,
                             orgCode=org, snapshotfy=fy)
    for r in rows:  # keep the request that produced each row (useful for lineage and debugging)
        r.update(query_area_type=area_type, query_area_code=area_code, query_org=org)
    return rows


def extract_snapshot(fy: int, refresh: bool = False, countries_limit: int | None = None) -> None:
    out = config.RAW_DIR / f"fy{fy}"

    for name, endpoint in [("indicators", "getSCMETADATA"), ("sub_indicators", "getSCSubIndicatorMetaData"),
                           ("countries", "getSCCountryDATA")]:
        path = out / f"{name}.parquet"
        if not _cached(path, refresh):
            n = _save(clients.scorecard(endpoint, snapshotfy=fy), path)
            log.info("fetched %s fy%s: %s rows", name, fy, n)

    path = out / "summary.parquet"
    if not _cached(path, refresh):
        countries = pd.read_parquet(out / "countries.parquet")
        codes = sorted(countries["cntry_code"].dropna().unique())[:countries_limit]
        jobs = ([("REGION", r, "ALL") for r in config.REGIONS] + [("FCS", "FCS", "ALL")]
                + [("REGION", "ACW", o) for o in config.INSTITUTIONS] + [("COUNTRY", c, "ALL") for c in codes])
        if fy == max(config.SNAPSHOTS):  # institution split (WB / IFC / MIGA) by country, latest snapshot only
            jobs += [("COUNTRY", c, o) for c in codes for o in config.INSTITUTIONS]
        rows, failed = [], []
        with cf.ThreadPoolExecutor(config.MAX_WORKERS) as ex:
            futures = {ex.submit(_summary, t, c, o, fy): (t, c, o) for t, c, o in jobs}
            for f in cf.as_completed(futures):
                try:
                    rows += f.result()
                except clients.ApiError as exc:
                    failed.append(futures[f])
                    log.warning("summary failed %s: %s", futures[f], exc)
        n = _save(rows, path)
        (out / "summary_failures.json").write_text(json.dumps(failed))
        log.info("fetched summary fy%s: %s rows from %s requests (%s failed)", fy, n, len(jobs), len(failed))

    # Institution splits the Scorecard data page shows for every area: WB / IFC / MIGA and the World Bank financing
    # institutions IBRD / IDA, for the world, regions and FCS (all snapshots) and for countries (IBRD / IDA, latest
    # snapshot, like the WB / IFC / MIGA country split above). Kept separate so the large summary cache stays valid.
    path = out / "org_split.parquet"
    if not _cached(path, refresh):
        orgs = config.INSTITUTIONS + config.FINANCING
        # the FCS group is requested as FCS up to FY25 and as FCV from FY26; ask for both, empty answers are harmless
        jobs = [("REGION", r, o) for r in config.REGIONS for o in orgs] + [(g, g, o) for g in ("FCS", "FCV") for o in ["ALL"] + orgs]
        if fy == max(config.SNAPSHOTS):
            codes = sorted(pd.read_parquet(out / "countries.parquet")["cntry_code"].dropna().unique())[:countries_limit]
            jobs += [("COUNTRY", c, o) for c in codes for o in config.FINANCING]
        rows, failed = [], []
        with cf.ThreadPoolExecutor(config.MAX_WORKERS) as ex:
            futures = {ex.submit(_summary, t, c, o, fy): (t, c, o) for t, c, o in jobs}
            for f in cf.as_completed(futures):
                try:
                    rows += f.result()
                except clients.ApiError as exc:
                    failed.append(futures[f])
                    log.warning("org split failed %s: %s", futures[f], exc)
        log.info("fetched org split fy%s: %s rows from %s requests (%s failed)", fy, _save(rows, path), len(jobs), len(failed))

    path = out / "projects.parquet"
    if not _cached(path, refresh):
        meta = pd.read_parquet(out / "indicators.parquet")
        codes = meta.loc[meta["ind_type_name"] == "WBG Results", "ind_code"].tolist()

        def one(code):
            rows = clients.scorecard("getSCResultIndicatorSummary", key="ind_code", value=code, snapshotfy=fy)
            return [{**r, "query_ind_code": code} for r in rows]

        with cf.ThreadPoolExecutor(config.MAX_WORKERS) as ex:
            rows = [r for batch in ex.map(one, codes) for r in batch]
        log.info("fetched projects fy%s: %s rows", fy, _save(rows, path))


def extract_global(refresh: bool = False) -> None:
    out = config.RAW_DIR / "global"
    latest = max(config.SNAPSHOTS)

    path = out / "outcomes.parquet"
    if not _cached(path, refresh):
        cms = clients.scorecard_cms("get_outcomes_indicators", fy=latest)
        _save(cms["outcomes"], path)
        _save(cms.get("indicators") or [], out / "outcome_indicators.parquet")
        log.info("fetched CMS outcomes: %s", len(cms["outcomes"]))

    path = out / "stories.parquet"
    if not _cached(path, refresh):
        rows = clients.scorecard_cms("get_home_narratives", fy=latest)
        for r in rows:
            r["related_outcomes"] = json.dumps(r.get("related_outcomes") or [])
        log.info("fetched CMS stories: %s", _save(rows, path))

    for name, code in config.DATA360_INDICATORS.items():
        path = out / f"data360_{name}.parquet"
        if not _cached(path, refresh):
            log.info("fetched Data360 %s: %s rows", code, _save(clients.data360(code, 2015, latest), path))

    path = out / "active_projects.parquet"
    if not _cached(path, refresh):
        rows = clients.active_projects()
        for r in rows:  # flatten nested fields
            r["countrycode"] = json.dumps(r.get("countrycode") or [])
            for k in ("sector1", "sector2", "sector3"):
                v = r.get(k)
                r[k] = v.get("Name") if isinstance(v, dict) else v
        log.info("fetched active projects: %s", _save(rows, path))


def run(snapshots=None, refresh: bool = False, countries_limit: int | None = None) -> None:
    extract_global(refresh)
    for fy in snapshots or config.SNAPSHOTS:
        extract_snapshot(fy, refresh, countries_limit)
