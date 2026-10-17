"""Deterministic analyses behind research answers, summaries and briefing decks.

The prioritization rules are code, not LLM judgement, so they are reproducible (the exported notebook re-runs them):
- accelerate delivery: expected >= 60th percentile of countries with results AND delivery < 40%  -> top 4 by gap
- expand footprint:    highest people in need where expected results cover < 25% of need          -> top 4
- strong delivery:     75%-105% delivered with an above-median portfolio (achieved > 105% = data check, excluded)
"""
from __future__ import annotations

import re

from explorer import queries as q
from explorer.formatting import fmt

from .pcn import Claims

SECTORS = {1: r"Social Protection", 2: r"Education", 3: r"Health", 4: r"Central Government|Public Administration - (Finance|Other)|Tax",
           5: r"Forestry|Environment|Flood|Disaster|Climate", 6: r"Water|Sanitation", 7: r"Agri|Food|Fishing|Irrigation|Livestock",
           8: r"Road|Transport|Rail|Port|Aviation", 9: r"Energy|Solar|Renewable|Hydro|Power|Electric|Transmission|Thermal|Geothermal",
           10: r"ICT", 11: r"ICT|Digital", 12: r"Social|Banking|Finance", 13: r"Social|Displac", 14: r"Labor|Employment|SME|Private",
           15: r"Private|Banking|Capital Markets|Finance"}


def _quantile(vals: list[float], p: float) -> float:
    s = sorted(vals)
    if not s:
        return 0.0
    pos = (len(s) - 1) * p
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def primary_indicator(outcome_id: int) -> dict | None:
    p = q.primary_result(outcome_id)
    return q.indicators().get(p["ind_code"]) if p else None


def need_indicator(outcome_id: int) -> dict | None:
    """The client-context indicator with the widest country coverage."""
    best, best_n = None, -1
    for i in q.outcome_indicators(outcome_id)["context"]:
        n = q.one("SELECT count(DISTINCT area_code) n FROM v_context_latest c JOIN areas a USING (area_code) "
                  "WHERE c.snapshot_fy=? AND c.ind_code=? AND a.area_type='COUNTRY'", [q.latest_fy(), i["ind_code"]])["n"]
        if n > best_n:
            best, best_n = i, n
    return best


def choose_area() -> list[dict]:
    """When no thematic area is named: largest remaining gap among areas with good country-level data."""
    out = []
    for o in q.outcomes():
        p = q.primary_result(o["outcome_id"])
        if not p or p["achieved"] is None or p["unit"] != "Beneficiaries":
            continue
        need = need_indicator(o["outcome_id"])
        n_res = q.one("SELECT count(*) n FROM v_results WHERE snapshot_fy=? AND ind_code=? AND org='WBG' AND area_type='COUNTRY' AND expected>0",
                      [q.latest_fy(), p["ind_code"]])["n"]
        n_need = q.one("SELECT count(*) n FROM v_context_latest c JOIN areas a USING (area_code) WHERE snapshot_fy=? AND ind_code=? AND a.area_type='COUNTRY'",
                       [q.latest_fy(), need["ind_code"]])["n"] if need else 0
        gap = p["expected"] - p["achieved"]
        ok = n_res >= 40 and n_need >= 80
        out.append({"outcome": o, "ind_code": p["ind_code"], "gap": gap, "n_results": n_res, "n_need": n_need, "ok": ok,
                    "score": gap if ok else gap * 0.1})
    return sorted(out, key=lambda x: -x["score"])


def research(outcome_id: int, claims: Claims) -> dict:
    fy = q.latest_fy()
    ind = primary_indicator(outcome_id)
    need = need_indicator(outcome_id)
    unit = ind["unit"]
    neg = need is not None and not need["higher_is_better"]
    pop_share = need is not None and need["unit"] == "Percentage" and re.search(r"population|people", need["name"], re.I) is not None
    res = {r["area_code"]: r for r in q.rows(
        "SELECT area_code, achieved, expected FROM v_results WHERE snapshot_fy=? AND org='WBG' AND ind_code=? AND area_type='COUNTRY'",
        [fy, ind["ind_code"]])}
    ctx = {r["area_code"]: r for r in q.rows(
        "SELECT area_code, year, value FROM v_context_latest WHERE snapshot_fy=? AND ind_code=?", [fy, need["ind_code"]])} if need else {}
    pop = {r["area_code"]: r for r in q.rows("SELECT * FROM v_population")}
    proj = {r["area_code"]: r for r in q.rows(
        """SELECT area_code, count(DISTINCT proj_id) n, sum(commitment_usd) cmt FROM projects
           WHERE snapshot_fy=? AND ind_code=? AND sub_ind_code='' AND sex='_T' AND age='_T' AND disability='_T' GROUP BY 1""",
        [fy, ind["ind_code"]])}
    sector = SECTORS.get(outcome_id, ".")
    act = {r["area_code"]: r for r in q.rows(
        "SELECT area_code, count(*) n, sum(commitment_usd) cmt FROM active_projects WHERE area_code IS NOT NULL AND regexp_matches(sectors, ?) GROUP BY 1",
        [sector])}
    areas = q.areas()
    rows = []
    for code, a in areas.items():
        if a["area_type"] != "COUNTRY" or (code not in res and code not in ctx):
            continue
        r, c, p = res.get(code), ctx.get(code), pop.get(code)
        ach, exp = (r["achieved"], r["expected"]) if r else (None, None)
        people = None
        if pop_share and c and p:
            people = p["population"] * (c["value"] if neg else 100 - c["value"]) / 100
        rows.append({"code": code, "name": a["label"], "region": a["region_code"], "fcs": bool(a["fcs"]),
                     "achieved": ach, "expected": exp,
                     "gap": (exp - ach) if (ach is not None and exp is not None) else None,
                     "ratio": (ach / exp) if (ach is not None and exp) else None,
                     "need": c["value"] if c else None, "need_year": c["year"] if c else None,
                     "population": p["population"] if p else None, "pop_year": p["year"] if p else None, "people_in_need": people,
                     "projects": (proj.get(code) or {}).get("n", 0), "commitments": (proj.get(code) or {}).get("cmt") or 0,
                     "active_projects": (act.get(code) or {}).get("n", 0), "active_commitments": (act.get(code) or {}).get("cmt") or 0})
    with_res = [x for x in rows if x["expected"] and x["ratio"] is not None]
    thr = _quantile([x["expected"] for x in with_res], 0.6)
    accelerate = sorted([x for x in with_res if x["expected"] >= thr and x["ratio"] < 0.4], key=lambda x: -x["gap"])[:4]
    acc = {x["code"] for x in accelerate}
    if pop_share:
        cand = [x for x in rows if x["people_in_need"] and (x["expected"] or 0) / x["people_in_need"] < 0.25 and x["code"] not in acc]
        expand = sorted(cand, key=lambda x: -x["people_in_need"])[:4]
    else:
        cand = [x for x in rows if x["need"] is not None and x["code"] not in acc and not x["expected"]]
        expand = sorted(cand, key=lambda x: (-x["need"] if neg else x["need"]))[:4]
    med = _quantile([x["expected"] for x in with_res], 0.5)
    strong = sorted([x for x in with_res if 0.75 <= x["ratio"] <= 1.05 and x["expected"] >= med], key=lambda x: -x["achieved"])[:2]
    overshoot = sorted([x for x in with_res if x["ratio"] > 1.05], key=lambda x: -x["ratio"])
    regions = []
    for code in q.REGIONS:
        rr = q.result(ind["ind_code"], code, "WBG", fy)
        regions.append({"code": code, "name": q.REGION_NAMES[code],
                        "people_in_need": sum(x["people_in_need"] or 0 for x in rows if x["region"] == code),
                        "achieved": rr["achieved"] if rr else None, "expected": rr["expected"] if rr else None,
                        "gap": (rr["expected"] - rr["achieved"]) if rr and rr["achieved"] is not None else None})
    total_need = sum(r["people_in_need"] for r in regions)
    focus = max(regions, key=lambda r: (r["people_in_need"], r["gap"] or 0)) if pop_share else max(regions, key=lambda r: r["gap"] or 0)
    world = q.result(ind["ind_code"], "ACW", "WBG", fy)
    prev = q.result(ind["ind_code"], "ACW", "WBG", fy - 1)

    # ---- register claims for everything the writer may cite
    def c(v, u, area, label):
        return {"value": v, "display": fmt(v, u), "claim": claims.add(v, unit=u, source=f"{area} · FY{str(fy)[2:]}", label=label)}

    def pct(v, area, label):
        return {"value": 100 * v, "display": f"{100 * v:.0f}%", "claim": claims.add(100 * v, unit="Percentage", source=f"{area} · computed", label=label)}

    def country_view(x):
        out = {"country": x["name"], "region": q.REGION_NAMES.get(x["region"], x["region"]), "fcs": x["fcs"]}
        if x["expected"]:
            out["expected"] = c(x["expected"], unit, x["name"], f"{ind['ind_code']} expected")
        if x["achieved"] is not None:
            out["achieved"] = c(x["achieved"], unit, x["name"], f"{ind['ind_code']} achieved")
        if x["ratio"] is not None:
            out["delivery_rate"] = pct(x["ratio"], x["name"], "achieved ÷ expected")
        if x["gap"] is not None:
            out["remaining_gap"] = c(x["gap"], unit, x["name"], "expected − achieved (computed)")
        if x["people_in_need"] is not None:
            out["people_in_need"] = c(x["people_in_need"], None, x["name"], f"population × need share ({need['ind_code']}, Data360 population)")
        if x["need"] is not None:
            out["need_indicator"] = {"value": x["need"], "display": f"{x['need']:.1f}%" if need["unit"] == "Percentage" else f"{x['need']:.1f}",
                                     "claim": claims.add(x["need"], unit=need["unit"], source=f"{need['ind_code']} · {x['name']} · {x['need_year']}", label=need["display_name"]),
                                     "year": x["need_year"]}
        out["active_sector_projects"] = x["active_projects"]
        return out

    world_view = {"achieved": c(world["achieved"], unit, "All countries", "achieved"), "expected": c(world["expected"], unit, "All countries", "expected"),
                  "remaining_gap": c(world["expected"] - world["achieved"], unit, "All countries", "remaining gap (computed)"),
                  "delivery_rate": pct(world["achieved"] / world["expected"], "All countries", "achieved ÷ expected")}
    if prev and prev["achieved"] is not None:
        world_view["change_since_previous_snapshot"] = c(world["achieved"] - prev["achieved"], unit, "All countries", f"change since FY{str(fy - 1)[2:]} (computed)")
    focus_view = {"region": focus["name"], "remaining_gap": c(focus["gap"], unit, focus["name"], "remaining gap (computed)") if focus["gap"] is not None else None}
    if pop_share and total_need:
        focus_view["share_of_people_in_need"] = pct(focus["people_in_need"] / total_need, focus["name"], "regional share of people in need (computed)")
    return {
        "outcome": q.outcome(outcome_id), "indicator": ind, "need": need, "need_is_negative": neg, "need_is_pop_share": pop_share,
        "sector_pattern": sector, "snapshot_fy": fy, "rows": rows, "regions": regions,
        "accelerate": accelerate, "expand": expand, "strong": strong, "overshoot": overshoot, "focus": focus,
        "for_writer": {
            "indicator": ind["display_name"], "unit": unit, "need_indicator": need["display_name"] if need else None,
            "world": world_view, "regional_focus": focus_view,
            "accelerate_delivery": [country_view(x) for x in accelerate],
            "expand_footprint": [country_view(x) for x in expand],
            "strong_delivery": [country_view(x) for x in strong],
            "data_checks": [f"{x['name']} reports {100 * x['ratio']:.0f}% of expected" for x in overshoot[:3]],
        },
        "sources": {"countries_with_results": len(with_res), "countries_with_need": sum(1 for x in rows if x["need"] is not None),
                    "countries_with_population": sum(1 for x in rows if x["population"]),
                    "countries_with_projects": sum(1 for x in rows if x["projects"]),
                    "project_commitments": sum(x["commitments"] for x in rows),
                    "active_sector_projects": sum(x["active_projects"] for x in rows)},
    }


def view_summary(outcome_id: int, ind_code: str, area: str, org: str, sex: str, fy: int, claims: Claims) -> dict:
    """Facts for 'Summarize this view' (passed to the writer)."""
    ind = q.indicators()[ind_code]
    u = ind["unit"]
    facts = {"indicator": ind["display_name"], "area": q.area_name(area), "institution": org,
             "sex": "female" if sex == "F" else "all", "snapshot": f"FY{str(fy)[2:]}"}

    def c(v, label, unit=u):
        return None if v is None else {"value": v, "display": fmt(v, unit), "claim": claims.add(v, unit=unit, source=f"{ind_code} · FY{str(fy)[2:]}", label=label)}

    r = q.result(ind_code, area, org, fy, sex)
    if r and r["achieved"] is not None and r["expected"]:
        facts["selected"] = {"achieved": c(r["achieved"], f"achieved · {q.area_name(area)}"), "expected": c(r["expected"], f"expected · {q.area_name(area)}"),
                             "delivery_rate": c(100 * r["achieved"] / r["expected"], "achieved ÷ expected (computed)", "Percentage"),
                             "remaining_gap": c(r["expected"] - r["achieved"], "expected − achieved (computed)")}
    regs = []
    for code in q.REGIONS:
        rr = q.result(ind_code, code, "WBG", fy, sex)
        if rr and rr["achieved"] is not None and rr["expected"]:
            regs.append({"region": q.REGION_NAMES[code], "delivery_rate": c(100 * rr["achieved"] / rr["expected"], f"delivery rate · {code}", "Percentage"),
                         "remaining_gap": c(rr["expected"] - rr["achieved"], f"remaining gap · {code}")})
    facts["regions"] = regs
    prev = q.result(ind_code, "ACW", "WBG", fy - 1)
    now = q.result(ind_code, "ACW", "WBG", fy)
    if prev and now and prev["achieved"] is not None and now["achieved"] is not None:
        facts["all_countries_change"] = {"from": c(prev["achieved"], f"achieved FY{str(fy - 1)[2:]}"), "to": c(now["achieved"], f"achieved FY{str(fy)[2:]}")}
    return facts
