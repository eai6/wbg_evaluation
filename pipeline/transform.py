"""Transform: clean the raw extracts into tidy, typed tables.

Main cleaning rules (all values arrive as text):
- numbers: parse to float; the API's ``*_base_*`` fields carry full precision, the other value fields are rounded
  for display, so base values are used and display values are only a fallback;
- areas: countries are keyed by ISO3 (the API uses the Bank's ISO2-like codes, e.g. ``ZR`` for DR Congo, so the
  Scorecard's own country table is the mapping, not a generic ISO list); regions/groups keep their codes;
- dimensions: ``_T`` = total for sex/age/disability; missing joint-programming flags are treated as total;
- duplicates: rows returned by more than one request (e.g. WBG totals in the institution queries) are dropped on
  the full natural key; remaining conflicts are reported by ``validate``.
"""
from __future__ import annotations

import json
import logging
import re

import pandas as pd

from . import config

log = logging.getLogger(__name__)

RES_KEY = ["snapshot_fy", "ind_code", "sub_ind_code", "org", "area_code", "sex", "age", "disability",
           "joint_programming", "eligibility"]
CTX_KEY = ["snapshot_fy", "ind_code", "sub_ind_code", "area_code", "sex", "age", "disability", "year"]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype("string").str.replace(",", "", regex=False), errors="coerce")


def _raw(fy: int, name: str) -> pd.DataFrame:
    return pd.read_parquet(config.RAW_DIR / f"fy{fy}" / f"{name}.parquet")


def _global(name: str) -> pd.DataFrame:
    return pd.read_parquet(config.RAW_DIR / "global" / f"{name}.parquet")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# --------------------------------------------------------------------------------------------- reference tables
def build_areas(snapshots) -> pd.DataFrame:
    frames = [_raw(fy, "countries").assign(snapshot_fy=fy) for fy in snapshots]
    c = pd.concat(frames).sort_values("snapshot_fy").drop_duplicates("cntry_code", keep="last")
    countries = pd.DataFrame({
        "area_code": c["cntry_iso3_code"], "area_type": "COUNTRY", "name": c["cntry_short_name"],
        "iso2": c["cntry_code"], "iso3": c["cntry_iso3_code"], "region_code": c["rgn_wb_code"],
        "region_name": c["rgn_wb_name"], "fcs": c["cntry_fcv_ind"].eq("Y"), "ldc": c["least_dev_cntry_flag"].eq("Y"),
        "income_code": c["cntry_inc_class_code"], "income_name": c["cntry_inc_class_name"],
        "lending": c["cntry_elig_class_code"], "sids": c["cntry_sids_class_flag"].eq("Y"),
        "small_state": c["cntry_small_state_class_flag"].eq("Y")})
    countries = countries.dropna(subset=["area_code"])
    names = (c.dropna(subset=["rgn_wb_code"]).drop_duplicates("rgn_wb_code")
              .set_index("rgn_wb_code")["rgn_wb_name"].to_dict())
    names["ACW"] = "All countries"
    groups = pd.DataFrame([{"area_code": r, "area_type": "REGION", "name": names.get(r, r), "region_code": r}
                           for r in config.REGIONS]
                          + [{"area_code": "FCS", "area_type": "GROUP", "name": "Fragile and conflict-affected situations"}])
    return pd.concat([groups, countries], ignore_index=True)


def iso2_to_area(areas: pd.DataFrame) -> dict:
    m = areas.dropna(subset=["iso2"]).set_index("iso2")["area_code"].to_dict()
    m.update({r: r for r in config.REGIONS}, FCS="FCS")
    return m


def build_outcomes(indicators: pd.DataFrame) -> pd.DataFrame:
    cms = _global("outcomes")
    out = pd.DataFrame({"outcome_id": cms["outcome_id"].astype(int), "name": cms["outcome_name"],
                        "description": cms["outcome_desc"],
                        "context_description": cms["client_context_description"],
                        "results_description": cms["results_description"]})
    vert = indicators.dropna(subset=["outcome_id"]).groupby("outcome_id")["vertical"].agg(
        lambda s: s.dropna().mode().iat[0] if s.dropna().size else None)
    out["vertical"] = out["outcome_id"].map(vert)
    out["slug"] = out["name"].map(slugify)
    return out.sort_values("outcome_id")


def build_indicators(snapshots) -> tuple[pd.DataFrame, pd.DataFrame]:
    latest = max(snapshots)
    m = _raw(latest, "indicators")
    kind = {"WBG Results": "results", "Client Context": "context", "Vision": "vision"}
    ind = pd.DataFrame({
        "ind_code": m["ind_code"], "name": m["ind_name"], "display_name": m["ind_display_name"].fillna(m["ind_name"]),
        "type": m["ind_type_name"].map(kind), "unit": m["ind_unit_of_measure"],
        "outcome_id": _num(m["ind_outcome_area_code"].str.extract(r"(\d+)")[0]).astype("Int64"),
        "vertical": m["ind_vertical_name"], "definition": m["ind_definition"],
        "long_definition": m["ind_long_definition"], "wdi_code": m["dec_ind_code"],
        "wb": m["ind_wb_flag"].eq("Y"), "ifc": m["ind_ifc_flag"].eq("Y"), "miga": m["ind_miga_flag"].eq("Y"),
        "has_sub_indicators": m["sub_ind_flag"].eq("Y"), "sex_disaggregated": m["ind_sex_disaggregate_flag"].eq("Y"),
        "country_disaggregated": m["ind_cntry_disaggregate_flag"].eq("Y"),
        "scale_type": m["scale_type_code"], "note": m["ind_note"]})
    # "higher is better" is needed to read need indicators correctly (poverty, stunting... are higher = worse)
    worse = r"cannot|poverty|stunt|insecur|risk|hazard|displaced|not in education|distress|inequality|emission|shortfall"
    ind["higher_is_better"] = ~ind["name"].str.contains(worse, case=False, regex=True)
    s = _raw(latest, "sub_indicators")
    sub = pd.DataFrame({"ind_code": s["ind_code"], "sub_ind_code": s["sub_ind_code"], "name": s["sub_ind_name"],
                        "display_name": s["sub_ind_display_name"], "female": s["female_sub_ind"].eq("Y"),
                        "unit": s["ind_unit_of_measure"]})
    return ind, sub


# --------------------------------------------------------------------------------------------- fact tables
def _dims(df: pd.DataFrame, area_map: dict) -> pd.DataFrame:
    return pd.DataFrame({
        "snapshot_fy": _num(df["snapshot_fy"]).astype("Int64"), "snapshot_date": pd.to_datetime(df["snapshot_date"]),
        "ind_code": df["ind_code"], "sub_ind_code": df["sub_ind_code"],
        "area_code": df["ref_area_code"].map(area_map), "area_type": df["ref_area_type_code"],
        "sex": df["sex_disaggregate_code"].fillna("_T"), "age": df["age_disaggregate_code"].fillna("_T"),
        "disability": df["disability_disaggregate_code"].fillna("_T")})


def build_results(snapshots, area_map) -> pd.DataFrame:
    frames = []
    for fy in snapshots:
        raw = _raw(fy, "summary")
        r = raw[raw["ind_type_name"] == "WBG Results"]
        df = _dims(r, area_map)
        df["org"] = r["org_code"]
        df["joint_programming"] = r["wbg_joint_progming_flag"].fillna("_T")
        df["eligibility"] = r["cntry_eligibility_code"].fillna("ALL")
        df["time_period"] = pd.to_datetime(r["ind_time_per"], errors="coerce")
        df["achieved"] = _num(r["ind_base_achieved_val"]).fillna(_num(r["ind_achieved_val"]) * 10 ** _num(r["unit_multiplier_nbr"]).fillna(0))
        df["expected"] = _num(r["ind_base_expected_val"]).fillna(_num(r["ind_expected_val"]) * 10 ** _num(r["unit_multiplier_nbr"]).fillna(0))
        df["cumulative_achieved"] = _num(r["cumulative_ind_base_achieved_val"])
        df["unit"] = r["unit_of_measure_code"]
        df["low_threshold"] = r["low_threshold_flag"]
        df["foot_note"] = r["ind_val_foot_note"]
        frames.append(df)
    res = pd.concat(frames, ignore_index=True).dropna(subset=["area_code"])
    res["sub_ind_code"] = res["sub_ind_code"].fillna("")
    res = res.drop_duplicates(RES_KEY + ["achieved", "expected"])
    # the source occasionally repeats a key with an all-zero row next to the real one (e.g. TUR, FY24):
    # keep the row with the largest expected value and log how many were dropped
    before = len(res)
    res = res.sort_values("expected", ascending=False, na_position="last").drop_duplicates(RES_KEY)
    if before - len(res):
        log.warning("results: dropped %s conflicting duplicate rows (kept largest expected)", before - len(res))
    return res.sort_values(RES_KEY[:5]).reset_index(drop=True)


def build_context(snapshots, area_map) -> pd.DataFrame:
    frames = []
    for fy in snapshots:
        raw = _raw(fy, "summary")
        r = raw[raw["ind_type_name"] != "WBG Results"]
        df = _dims(r, area_map)
        df["type"] = r["ind_type_name"].map({"Client Context": "context", "Vision": "vision"})
        # periods are usually dates ("2023-12-31") but some are ranges ("2011-2021"): keep the text, use the end year
        df["period"] = r["ind_time_per"]
        df["year"] = _num(r["ind_time_per"].str.findall(r"(?:19|20)\d{2}").str[-1]).astype("Int64")
        df["value"] = _num(r["ind_base_achieved_val"]).fillna(_num(r["ind_achieved_val"]))
        df["unit"] = r["unit_of_measure_code"]
        frames.append(df)
    ctx = pd.concat(frames, ignore_index=True).dropna(subset=["area_code", "value", "year"])
    ctx["sub_ind_code"] = ctx["sub_ind_code"].fillna("")
    return ctx.drop_duplicates(CTX_KEY).reset_index(drop=True)


def build_projects(snapshots, area_map) -> pd.DataFrame:
    frames = []
    for fy in snapshots:
        p = _raw(fy, "projects")
        if p.empty:
            continue
        frames.append(pd.DataFrame({
            "snapshot_fy": fy, "ind_code": p["ind_code"].fillna(p["query_ind_code"]), "sub_ind_code": p["sub_ind_code"].fillna(""),
            "proj_id": p["proj_id"], "project_name": p["project_name"], "org": p["org_code"],
            "area_code": p["cntry_code"].map(area_map), "region_code": p["region_code"],
            "approval_fy": _num(p["approval_fy"]).astype("Int64"), "closing_fy": _num(p["closing_fy"]).astype("Int64"),
            "status": p["project_status_code"], "global_practice": p["global_practice_code"],
            "product_line": p["product_line_code"], "commitment_usd": _num(p["sum_tot_net_cmt_amt"]),
            "ibrd_usd": _num(p["sum_ibrd_net_cmt_amt"]), "ida_usd": _num(p["sum_ida_net_cmt_amt"]),
            "sex": p["sex_disaggregate_code"].fillna("_T"), "age": p["age_disaggregate_code"].fillna("_T"),
            "disability": p["disability_disaggregate_code"].fillna("_T"),
            "achieved": _num(p["sum_ind_base_achieved_val"]), "expected": _num(p["sum_ind_base_expected_val"]),
            "url": p["project_external_url"]}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_wdi(area_codes: set) -> pd.DataFrame:
    frames = []
    for name, code in config.DATA360_INDICATORS.items():
        d = _global(f"data360_{name}")
        frames.append(pd.DataFrame({"indicator": name, "source_code": code, "area_code": d["REF_AREA"],
                                    "year": _num(d["TIME_PERIOD"]).astype("Int64"), "value": _num(d["OBS_VALUE"])}))
    w = pd.concat(frames, ignore_index=True).dropna(subset=["value"])
    return w[w["area_code"].isin(area_codes)].drop_duplicates(["indicator", "area_code", "year"])


def build_active_projects(area_map) -> pd.DataFrame:
    a = _global("active_projects")
    df = pd.DataFrame({
        "proj_id": a["id"], "project_name": a["project_name"], "region": a["regionname"],
        "commitment_usd": _num(a["totalcommamt"]), "approval_date": pd.to_datetime(a["boardapprovaldate"], errors="coerce", format="ISO8601"),
        "closing_date": pd.to_datetime(a["closingdate"], errors="coerce", format="mixed"),
        "sectors": a[["sector1", "sector2", "sector3"]].apply(lambda r: "|".join(x for x in r if isinstance(x, str) and x), axis=1),
        "iso2": a["countrycode"].map(lambda s: json.loads(s) if isinstance(s, str) else []), "url": a["url"]})
    df = df.explode("iso2")
    df["area_code"] = df["iso2"].map(area_map)
    df["multi_country"] = df.groupby("proj_id")["iso2"].transform("size") > 1
    return df.drop(columns="iso2").reset_index(drop=True)


def build_stories() -> pd.DataFrame:
    s = _global("stories")
    url = s["embed_code"].str.extract(r'src="(https://[^"]+?)/embed\.js')[0]
    return pd.DataFrame({"story_id": s["narrative_id"], "title": s["narrative_title"].str.split().str.join(" "),
                         "image_url": s["banner_url"], "alt": s["alt_tags"], "url": url,
                         "outcome_ids": s["related_outcomes"].map(lambda j: [int(o["outcome_id"]) for o in json.loads(j or "[]")]),
                         "fy": s["fy"]})


def run(snapshots=None) -> dict[str, pd.DataFrame]:
    snapshots = sorted(snapshots or config.SNAPSHOTS)
    areas = build_areas(snapshots)
    amap = iso2_to_area(areas)
    indicators, sub_indicators = build_indicators(snapshots)
    return {
        "areas": areas, "indicators": indicators, "sub_indicators": sub_indicators,
        "outcomes": build_outcomes(indicators), "results": build_results(snapshots, amap),
        "context": build_context(snapshots, amap), "projects": build_projects(snapshots, amap),
        "wdi": build_wdi(set(areas["area_code"])), "active_projects": build_active_projects(amap),
        "stories": build_stories(),
    }
