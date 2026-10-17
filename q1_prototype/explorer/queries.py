"""Read-only query service over the pipeline's DuckDB database.

Used by the page views, the JSON API and the assistant's tools, so every number on screen and in an answer comes
from the same parameterised queries.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import duckdb
from django.conf import settings

REGIONS = ["AFE", "AFW", "EAP", "ECA", "LCR", "MENAAP", "SAR"]
REGION_NAMES = {"ACW": "All countries", "AFE": "Eastern & Southern Africa", "AFW": "Western & Central Africa",
                "EAP": "East Asia & Pacific", "ECA": "Europe & Central Asia", "LCR": "Latin America & Caribbean",
                "MENAAP": "MENA, Afghanistan & Pakistan", "SAR": "South Asia", "FCS": "Fragile & conflict-affected"}
_local = threading.local()


def con() -> duckdb.DuckDBPyConnection:
    """One read-only connection per thread (DuckDB connections are not thread-safe)."""
    c = getattr(_local, "con", None)
    if c is None:
        c = duckdb.connect(str(settings.SCORECARD_DB), read_only=True, config={"enable_external_access": False})
        _local.con = c
    return c


def rows(sql: str, params: list | tuple = ()) -> list[dict]:
    cur = con().execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(sql: str, params=()) -> dict | None:
    r = rows(sql, params)
    return r[0] if r else None


# ------------------------------------------------------------------------------------------------ reference
@lru_cache(maxsize=1)
def latest_fy() -> int:
    return one("SELECT max(snapshot_fy) fy FROM results")["fy"]


@lru_cache(maxsize=1)
def snapshots() -> list[dict]:
    return [{"fy": r["snapshot_fy"], "date": str(r["snapshot_date"])[:10]} for r in rows("SELECT * FROM v_snapshots")]


@lru_cache(maxsize=1)
def areas() -> dict[str, dict]:
    out = {r["area_code"]: r for r in rows("SELECT * FROM areas")}
    for code, name in REGION_NAMES.items():
        if code in out:
            out[code]["name"] = name
    for r in out.values():  # "Congo, Democratic Republic of" -> "Democratic Republic of Congo"
        n = r["name"] or r["area_code"]
        if r["area_type"] == "COUNTRY" and ", " in n:
            a, b = n.split(", ", 1)
            n = f"{b} {a}" if b.endswith(" of") else a
        r["label"] = n
    return out


def area_name(code: str) -> str:
    a = areas().get(code)
    return a["label"] if a else code


@lru_cache(maxsize=1)
def outcomes() -> list[dict]:
    return rows("SELECT * FROM outcomes ORDER BY outcome_id")


def outcome(key) -> dict | None:
    for o in outcomes():
        if str(o["outcome_id"]) == str(key) or o["slug"] == key:
            return o
    return None


@lru_cache(maxsize=1)
def indicators() -> dict[str, dict]:
    return {r["ind_code"]: r for r in rows("SELECT * FROM indicators")}


def outcome_indicators(outcome_id: int) -> dict[str, list[dict]]:
    inds = [i for i in indicators().values() if i["outcome_id"] == outcome_id]
    return {"results": [i for i in inds if i["type"] == "results"],
            "context": [i for i in inds if i["type"] != "results"]}


# ------------------------------------------------------------------------------------------------ results
def result(ind: str, area: str = "ACW", org: str = "WBG", fy: int | None = None, sex: str = "_T") -> dict | None:
    fy = fy or latest_fy()
    if sex == "F":
        return one("SELECT achieved, expected FROM v_results_female WHERE ind_code=? AND area_code=? AND org=? AND snapshot_fy=?",
                   [ind, area, org, fy])
    return one("SELECT achieved, expected, remaining_gap, delivery_ratio, unit FROM v_results "
               "WHERE ind_code=? AND area_code=? AND org=? AND snapshot_fy=?", [ind, area, org, fy])


def sub_result(ind: str, area: str = "ACW", fy: int | None = None) -> dict | None:
    """Largest sub-indicator, for indicators reported only by sub-indicator (e.g. WASH)."""
    return one("""SELECT r.sub_ind_code, s.name, r.achieved, r.expected FROM results r
                  LEFT JOIN sub_indicators s USING (ind_code, sub_ind_code)
                  WHERE r.ind_code=? AND r.area_code=? AND r.org='WBG' AND r.snapshot_fy=? AND r.sub_ind_code<>''
                    AND r.sex='_T' AND r.age='_T' AND r.disability='_T' AND r.joint_programming='_T'
                  ORDER BY r.expected DESC NULLS LAST LIMIT 1""", [ind, area, fy or latest_fy()])


def results_table(ind_codes: list[str], fy: int | None = None, sex: str = "_T") -> dict:
    """{area_code: {ind_code: [achieved, expected]}} for all areas (regions, FCS, countries)."""
    if not ind_codes:
        return {}
    view = "v_results_female" if sex == "F" else "v_results"
    q = f"SELECT area_code, ind_code, achieved, expected FROM {view} WHERE org='WBG' AND snapshot_fy=? AND ind_code IN ({','.join('?' * len(ind_codes))})"
    out: dict = {}
    for r in rows(q, [fy or latest_fy(), *ind_codes]):
        out.setdefault(r["area_code"], {})[r["ind_code"]] = [r["achieved"], r["expected"]]
    return out


def results_by_org(ind_codes: list[str], fy: int | None = None) -> dict:
    if not ind_codes:
        return {}
    q = f"SELECT org, ind_code, achieved, expected FROM v_results WHERE area_code='ACW' AND org IN ('WB','IFC','MIGA') AND snapshot_fy=? AND ind_code IN ({','.join('?' * len(ind_codes))})"
    out: dict = {}
    for r in rows(q, [fy or latest_fy(), *ind_codes]):
        out.setdefault(r["org"], {})[r["ind_code"]] = [r["achieved"], r["expected"]]
    return out


def results_over_time(ind_codes: list[str]) -> dict:
    if not ind_codes:
        return {}
    q = f"SELECT snapshot_fy, area_code, ind_code, achieved, expected FROM v_results WHERE org='WBG' AND ind_code IN ({','.join('?' * len(ind_codes))})"
    out: dict = {}
    for r in rows(q, ind_codes):
        out.setdefault(str(r["snapshot_fy"]), {}).setdefault(r["area_code"], {})[r["ind_code"]] = [r["achieved"], r["expected"]]
    return out


def context_series(ind_codes: list[str], fy: int | None = None) -> dict:
    """{area_code: {ind_code: {year: value}}} for the given context/vision indicators."""
    if not ind_codes:
        return {}
    q = f"SELECT area_code, ind_code, year, value FROM v_context WHERE snapshot_fy=? AND ind_code IN ({','.join('?' * len(ind_codes))}) ORDER BY year"
    out: dict = {}
    for r in rows(q, [fy or latest_fy(), *ind_codes]):
        out.setdefault(r["area_code"], {}).setdefault(r["ind_code"], {})[str(r["year"])] = r["value"]
    return out


def stories() -> list[dict]:
    return rows("SELECT * FROM stories")


# ------------------------------------------------------------------------------------------------ landing tiles
def primary_result(outcome_id: int, fy: int | None = None) -> dict | None:
    """The headline WBG Results figure for an outcome tile (prefers a people-reached indicator)."""
    fy = fy or latest_fy()
    inds = outcome_indicators(outcome_id)["results"]
    vals = [(i, result(i["ind_code"], fy=fy)) for i in inds]
    with_data = [(i, v) for i, v in vals if v and v["expected"] is not None]
    pick = (next(((i, v) for i, v in with_data if i["unit"] == "Beneficiaries" and v["achieved"] is not None), None)
            or next(((i, v) for i, v in with_data if v["achieved"] is not None), None)
            or (with_data[0] if with_data else None))
    if pick:
        i, v = pick
        return {"ind_code": i["ind_code"], "name": i["display_name"], "unit": i["unit"],
                "achieved": v["achieved"], "expected": v["expected"]}
    for i in inds:
        s = sub_result(i["ind_code"], fy=fy)
        if s:
            return {"ind_code": i["ind_code"], "sub_ind_code": s["sub_ind_code"], "name": s["name"], "unit": i["unit"],
                    "achieved": s["achieved"], "expected": s["expected"]}
    return None


def landing_tiles() -> list[dict]:
    return [{**o, "primary": primary_result(o["outcome_id"])} for o in outcomes()]


# ------------------------------------------------------------------------------------------------ workspace payload
def outcome_payload(outcome_id: int) -> dict:
    """Everything the outcome workspace needs to draw its Overview, for all snapshots and areas."""
    inds = outcome_indicators(outcome_id)
    res_codes = [i["ind_code"] for i in inds["results"]]
    ctx_codes = [i["ind_code"] for i in inds["context"]]
    fys = [s["fy"] for s in snapshots()]
    subs = {}
    for c in res_codes:
        for fy in fys:
            s = sub_result(c, fy=fy)
            if s:
                subs.setdefault(str(fy), {})[c] = s
    return {
        "outcome": outcome(outcome_id),
        "results_indicators": inds["results"], "context_indicators": inds["context"],
        "snapshots": snapshots(), "latest_fy": latest_fy(),
        "R": {str(fy): results_table(res_codes, fy) for fy in fys},
        "RF": {str(fy): results_table(res_codes, fy, sex="F") for fy in fys},
        "ORG": {str(fy): results_by_org(res_codes, fy) for fy in fys},
        "SUB": subs,
        "CTX": context_series(ctx_codes),
        "areas": {k: {"name": v["label"], "type": v["area_type"], "region": v.get("region_code"), "iso2": v.get("iso2"),
                      "fcs": bool(v.get("fcs")), "income": v.get("income_code"), "ldc": bool(v.get("ldc")),
                      "sids": bool(v.get("sids")), "small_state": bool(v.get("small_state"))} for k, v in areas().items()},
    }


# ------------------------------------------------------------------------------------------------ indicator data page
# Breakdowns as on the Scorecard "WBG Results Only" filter. At project level disability = 'Yes' marks a
# disability-inclusive project, so the total ('T') keeps both disability codes there.
BREAKDOWNS = {"T": ("_T", "_T", "_T"), "F": ("F", "_T", "_T"), "Y": ("_T", "Y14T24", "_T"), "D": ("_T", "_T", "Yes")}


def indicator_detail(ind_code: str, fy: int | None = None) -> dict | None:
    """Everything the Scorecard data page shows for one results indicator and snapshot:
    V[sub][org][breakdown][area] = [achieved, expected] for every area (world, regions, FCS, countries) and
    institution (WBG, WB, IFC, MIGA, IBRD, IDA), and the World Bank operations (projects) behind the numbers."""
    ind = indicators().get(ind_code)
    if not ind or ind["type"] != "results":
        return None
    fy = fy or latest_fy()
    V: dict = {}
    for r in rows("""SELECT sub_ind_code, org, sex, age, disability, area_code, achieved, expected FROM results
                     WHERE ind_code=? AND snapshot_fy=? AND joint_programming='_T'""", [ind_code, fy]):
        bd = next((k for k, v in BREAKDOWNS.items() if v == (r["sex"], r["age"], r["disability"])), None)
        if bd:
            V.setdefault(r["sub_ind_code"], {}).setdefault(r["org"], {}).setdefault(bd, {})[r["area_code"]] = [r["achieved"], r["expected"]]
    projects = []
    for r in rows("""SELECT sub_ind_code, sex, age, disability, proj_id, project_name, coalesce(area_code, cntry_code) area_code, region_code, achieved, expected,
                            ibrd_achieved, ibrd_expected, ida_achieved, ida_expected, overlap_flag, url
                     FROM projects WHERE ind_code=? AND snapshot_fy=? ORDER BY achieved DESC NULLS LAST""", [ind_code, fy]):
        bds = [k for k, (s, a, d) in BREAKDOWNS.items() if r["sex"] == s and r["age"] == a and (d == r["disability"] or (k != "D" and d == "_T"))]
        for bd in bds:
            projects.append([r["sub_ind_code"], bd, r["proj_id"], r["project_name"], r["area_code"], r["region_code"], r["achieved"], r["expected"],
                             r["overlap_flag"], r["url"], r["ibrd_achieved"], r["ibrd_expected"], r["ida_achieved"], r["ida_expected"]])
    rec = one("SELECT projects, projects_achieved, projects_expected, wb_achieved, wb_expected, reconciles "
              "FROM v_project_reconciliation WHERE ind_code=? AND snapshot_fy=?", [ind_code, fy])
    subs = {r["sub_ind_code"]: r["name"] for r in rows("SELECT sub_ind_code, name FROM sub_indicators WHERE ind_code=?", [ind_code])}
    return {"indicator": {k: ind[k] for k in ("ind_code", "display_name", "name", "unit", "description", "definition", "vertical", "outcome_id")},
            "fy": fy, "subs": {k: subs.get(k, k) for k in V if k}, "V": V,
            "project_cols": ["sub", "bd", "proj_id", "name", "area", "region", "achieved", "expected", "overlap", "url",
                             "ibrd_achieved", "ibrd_expected", "ida_achieved", "ida_expected"],
            "projects": projects, "reconciliation": rec}
