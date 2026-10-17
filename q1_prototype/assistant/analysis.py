"""Deterministic analyses behind research answers, summaries and briefing decks.

Design rules (from the pipeline review, docs/review/research_pipeline_review.md):
- no invented thresholds: outputs are factual ranked lists ("most results still to deliver", "most people without
  access"), each defined by one measure, plus explicit data checks;
- no inference from names: indicator direction and population basis come from Scorecard metadata or the reviewed
  catalogue (pipeline/measures.csv); if a measure is not catalogued, it is not computed;
- footprint = the Scorecard's own institution split (WB / IFC / MIGA) and Scorecard project-level rows (World Bank
  projects only); nothing is matched by sector names;
- rows flagged by the pipeline (e.g. achieved above expected) never enter delivery-rate statements.
Every number is registered as a claim that records its entity, measure and period.
"""
from __future__ import annotations

from explorer import queries as q
from explorer.formatting import fmt

from .pcn import Claims

BORROWERS = ("IDA", "BLEND", "IBRD")   # WBG borrowing countries (lending category in the Scorecard country table)
TOP_N = 5                              # list length shown to readers (display choice, not an analytic threshold)


def primary_indicator(outcome_id: int) -> dict | None:
    p = q.primary_result(outcome_id)
    return q.indicators().get(p["ind_code"]) if p else None


def need_measure(outcome_id: int) -> dict | None:
    """A context indicator catalogued as a share of the total population (so population x share is valid)."""
    cands = [i for i in q.outcome_indicators(outcome_id)["context"] if i.get("population_basis") == "total_population"]
    if not cands:
        return None
    fy = q.latest_fy()
    best, best_n = None, -1
    for i in cands:
        n = q.one("SELECT count(*) n FROM v_context_latest c JOIN areas a USING (area_code) WHERE c.snapshot_fy=? AND c.ind_code=? "
                  "AND a.area_type='COUNTRY'", [fy, i["ind_code"]])["n"]
        if n > best_n:
            best, best_n = i, n
    return best


def coverage() -> list[dict]:
    """Per outcome area: how much country-level data exists (shown to the user when no area is named)."""
    fy = q.latest_fy()
    out = []
    for o in q.outcomes():
        ind = primary_indicator(o["outcome_id"])
        if not ind:
            continue
        n_res = q.one("SELECT count(*) n FROM v_results v JOIN areas a USING (area_code) WHERE v.snapshot_fy=? AND v.ind_code=? "
                      "AND v.org='WBG' AND a.area_type='COUNTRY' AND a.lending IN ('IDA','BLEND','IBRD') AND v.quality_flag IS NULL",
                      [fy, ind["ind_code"]])["n"]
        need = need_measure(o["outcome_id"])
        out.append({"outcome": o, "ind_code": ind["ind_code"], "indicator": ind["display_name"],
                    "countries_with_results": n_res, "need_measure": need["people_measure"] if need else None})
    return sorted(out, key=lambda x: (x["need_measure"] is None, -x["countries_with_results"]))


def research(outcome_id: int, claims: Claims) -> dict:
    fy = q.latest_fy()
    period = f"FY{str(fy)[2:]} snapshot"
    o = q.outcome(outcome_id)
    ind = primary_indicator(outcome_id)
    unit = ind["unit"]
    need = need_measure(outcome_id)
    areas = q.areas()

    def claim(value, entity, measure, display=None, p=period, source="WBG Scorecard API", u=unit):
        if value is None:
            return None
        d = display or fmt(value, u)
        return {"display": d, "claim": claims.add(value, unit=u, source=source, label=measure, entity=entity,
                                                   measure=measure, period=p, display=d)}

    # ---- S2 assemble (all from the database; one source per concept)
    wbg = {r["area_code"]: r for r in q.rows(
        "SELECT area_code, achieved, expected, quality_flag FROM v_results WHERE snapshot_fy=? AND org='WBG' AND ind_code=?",
        [fy, ind["ind_code"]])}
    by_org: dict = {}
    for r in q.rows("SELECT area_code, org, achieved, expected, quality_flag FROM v_results WHERE snapshot_fy=? AND org IN ('WB','IFC','MIGA') "
                    "AND ind_code=?", [fy, ind["ind_code"]]):
        by_org.setdefault(r["area_code"], {})[r["org"]] = r
    recon = q.one("SELECT reconciles, projects FROM v_project_reconciliation WHERE snapshot_fy=? AND ind_code=?", [fy, ind["ind_code"]]) or {}
    projects_ok = bool(recon.get("reconciles"))
    wbproj = {r["area_code"]: r for r in q.rows(
        "SELECT area_code, count(DISTINCT proj_id) n, sum(commitment_usd) usd FROM v_projects WHERE snapshot_fy=? AND ind_code=? GROUP BY 1",
        [fy, ind["ind_code"]])} if projects_ok else {}
    ctx = {r["area_code"]: r for r in q.rows("SELECT area_code, year, value FROM v_context_latest WHERE snapshot_fy=? AND ind_code=?",
                                             [fy, need["ind_code"]])} if need else {}
    # population for the SAME year as the need value (falls back to the latest earlier year available)
    pop_by = {}
    for r in q.rows("SELECT area_code, year, value FROM wdi WHERE indicator='population' ORDER BY year"):
        pop_by.setdefault(r["area_code"], {})[r["year"]] = r["value"]

    def pop_for(code, year):
        ys = pop_by.get(code) or {}
        cands = [y for y in ys if year is None or y <= year]
        if not cands:
            return None
        y = max(cands)
        return {"population": ys[y], "year": y}

    rows = []
    for code, a in areas.items():
        if a["area_type"] != "COUNTRY" or a.get("lending") not in BORROWERS:
            continue
        r, c = wbg.get(code), ctx.get(code)
        p = pop_for(code, c["year"] if c else None)
        people = None
        if need and c and p:  # catalogued as a share of total population, so population x share is valid
            share = c["value"] if need["direction"] == "lower_is_better" else 100 - c["value"]
            people = p["population"] * share / 100
        rows.append({"code": code, "name": a["label"], "region": a["region_code"], "region_name": q.REGION_NAMES.get(a["region_code"], a["region_code"]),
                     "lending": a["lending"], "fcs": bool(a["fcs"]),
                     "achieved": r["achieved"] if r else None, "expected": r["expected"] if r else None,
                     "flag": r["quality_flag"] if r else "no_results",
                     "need_value": c["value"] if c else None, "need_year": c["year"] if c else None,
                     "population": p["population"] if p else None, "pop_year": p["year"] if p else None, "people": people,
                     "orgs": by_org.get(code, {}), "wb_projects": (wbproj.get(code) or {}).get("n", 0),
                     "wb_commitments": (wbproj.get(code) or {}).get("usd")})
    clean = [x for x in rows if x["flag"] is None]
    for x in clean:
        x["gap"] = x["expected"] - x["achieved"]
        x["rate"] = x["achieved"] / x["expected"]

    # ---- S4 factual lists (each defined by one measure; no thresholds)
    most_to_deliver = sorted(clean, key=lambda x: -x["gap"])[:TOP_N]
    most_people = sorted([x for x in rows if x["people"]], key=lambda x: -x["people"])[:TOP_N] if need else []
    data_checks = [x for x in rows if x["flag"] == "achieved_above_expected"]
    regions = []
    for code in q.REGIONS:
        rr = q.result(ind["ind_code"], code, "WBG", fy)
        if not rr or rr["achieved"] is None or not rr["expected"]:
            continue
        members = [x for x in rows if x["region"] == code]
        regions.append({"code": code, "name": q.REGION_NAMES[code], "achieved": rr["achieved"], "expected": rr["expected"],
                        "gap": rr["expected"] - rr["achieved"], "rate": rr["achieved"] / rr["expected"],
                        "flag": "achieved_above_expected" if rr["achieved"] > rr["expected"] else None,
                        # None when no country in the region has data: "no data" is not zero people
                        "people": sum(x["people"] for x in members if x["people"]) if need and any(x["people"] for x in members) else None,
                        "people_countries": sum(1 for x in members if x["people"]) if need else None})
    regions.sort(key=lambda r: -r["gap"])
    world = q.result(ind["ind_code"], "ACW", "WBG", fy)
    prev = q.result(ind["ind_code"], "ACW", "WBG", fy - 1)
    world_orgs = {r["org"]: r for r in q.rows("SELECT org, achieved, expected FROM v_results WHERE snapshot_fy=? AND area_code='ACW' "
                                              "AND org IN ('WB','IFC','MIGA') AND ind_code=?", [fy, ind["ind_code"]])}

    # ---- S5 facts (claims with entity + measure + period) for rendering; the writer only sees entity names
    ind_name = ind["display_name"]
    people_label = need["people_measure"] if need else None
    facts = {"overall": [], "regions": [], "most_to_deliver": [], "most_people": [], "data_checks": []}
    W = "All countries"
    facts["overall"].append({"entity": W, "items": [
        ("achieved", claim(world["achieved"], W, f"{ind_name}: achieved")),
        ("expected", claim(world["expected"], W, f"{ind_name}: expected (active portfolio)")),
        ("still to deliver", claim(world["expected"] - world["achieved"], W, f"{ind_name}: expected − achieved")),
        ("delivery rate", claim(100 * world["achieved"] / world["expected"], W, f"{ind_name}: achieved ÷ expected", u="Percentage")),
        *([("achieved change since previous snapshot", claim(world["achieved"] - prev["achieved"], W, f"{ind_name}: change in achieved since FY{str(fy - 1)[2:]}"))]
          if prev and prev["achieved"] is not None else [])]})
    for org, label in (("WB", "World Bank"), ("IFC", "IFC"), ("MIGA", "MIGA")):
        r = world_orgs.get(org)
        if r and r["expected"] is not None:
            facts["overall"].append({"entity": f"{W} · {label}", "items": [
                ("achieved", claim(r["achieved"], f"{W} · {label}", f"{ind_name}: achieved")),
                ("expected", claim(r["expected"], f"{W} · {label}", f"{ind_name}: expected"))]})
    for r in regions:
        items = [("still to deliver", claim(r["gap"], r["name"], f"{ind_name}: expected − achieved")),
                 ("expected", claim(r["expected"], r["name"], f"{ind_name}: expected"))]
        if not r["flag"]:
            items.append(("delivery rate", claim(100 * r["rate"], r["name"], f"{ind_name}: achieved ÷ expected", u="Percentage")))
        if need and r["people"]:
            items.append((people_label, claim(r["people"], r["name"], f"{people_label} (sum over {r['people_countries']} borrowing countries with data)",
                                              u="People", source=f"Data360 population × {need['ind_code']}", p="latest year per country")))
        facts["regions"].append({"entity": r["name"], "items": items})

    def org_note(x):
        parts = []
        for org, label in (("WB", "WB"), ("IFC", "IFC"), ("MIGA", "MIGA")):
            r = x["orgs"].get(org)
            if not r:
                continue
            if r["expected"] is None and r["achieved"] is None:
                parts.append(f"{label}: not disclosed")
            elif r["expected"] is not None:
                parts.append((label, claim(r["expected"], x["name"], f"{ind_name}: expected ({label})")))
        return parts

    for x in most_to_deliver:
        facts["most_to_deliver"].append({"entity": x["name"], "region": x["region_name"], "lending": x["lending"], "items": [
            ("still to deliver", claim(x["gap"], x["name"], f"{ind_name}: expected − achieved")),
            ("delivery rate", claim(100 * x["rate"], x["name"], f"{ind_name}: achieved ÷ expected", u="Percentage")),
            ("expected", claim(x["expected"], x["name"], f"{ind_name}: expected (all WBG institutions)"))],
            "by_institution": org_note(x), **({"wb_projects": x["wb_projects"]} if projects_ok else {})})
    for x in most_people:
        items = [(people_label, claim(x["people"], x["name"], people_label, u="People",
                                      source=f"Data360 population ({x['pop_year']}) × Scorecard {need['ind_code']} ({x['need_year']})",
                                      p=f"{x['need_year']}")),
                 (need["display_name"], claim(x["need_value"], x["name"], need["display_name"], display=f"{x['need_value']:.1f}%",
                                              u="Percentage", p=str(x["need_year"]), source=f"WBG Scorecard client context · {need['ind_code']}"))]
        if x["expected"] is not None:
            items.append(("WBG expected results", claim(x["expected"], x["name"], f"{ind_name}: expected (all WBG institutions)")))
        facts["most_people"].append({"entity": x["name"], "region": x["region_name"], "lending": x["lending"], "items": items,
                                     "no_results": x["expected"] is None})
    for x in data_checks:
        facts["data_checks"].append({"entity": x["name"], "region": x["region_name"], "items": [
            ("achieved", claim(x["achieved"], x["name"], f"{ind_name}: achieved")),
            ("expected", claim(x["expected"], x["name"], f"{ind_name}: expected"))]})

    return {
        "outcome": o, "indicator": ind, "need": need, "snapshot_fy": fy, "rows": rows, "regions": regions,
        "most_to_deliver": most_to_deliver, "most_people": most_people, "data_checks": data_checks, "facts": facts,
        "definitions": {
            "universe": "WBG borrowing countries (IDA, Blend, IBRD) in the Scorecard country table",
            "still to deliver": "expected − achieved (expected = what the active portfolio is expected to deliver; not a target)",
            "delivery rate": "achieved ÷ expected; not shown when the pipeline flags the row (e.g. achieved above expected)",
            "people measure": (f"{people_label} = population (Data360) × {'share' if need['direction'] == 'lower_is_better' else '(100 − share)'} "
                               f"of '{need['display_name']}' (catalogued as a share of total population)") if need
                              else "no population-based need measure is catalogued for this outcome area",
            "footprint": "WBG results split by institution (WB / IFC / MIGA) from the Scorecard; IFC country values are often not disclosed. "
                         + (f"World Bank project counts come from the Scorecard project-level table, which reconciles exactly with the World Bank "
                            f"total for this indicator ({recon.get('projects')} projects)." if projects_ok else
                            "World Bank project counts are not shown: for this indicator the Scorecard project-level table does not add up to the "
                            "World Bank total."),
        },
        "sources": {"countries_considered": len(rows), "countries_with_results": len(clean),
                    "countries_with_need": sum(1 for x in rows if x["people"]), "data_checks": len(data_checks)},
    }


def view_summary(outcome_id: int, ind_code: str, area: str, org: str, sex: str, fy: int, claims: Claims) -> dict:
    """Facts for 'Summarize this view' (rendered by the server; the writer adds prose)."""
    ind = q.indicators()[ind_code]
    u, name, period = ind["unit"], ind["display_name"], f"FY{str(fy)[2:]} snapshot"

    def c(v, entity, measure, unit=u):
        if v is None:
            return None
        d = fmt(v, unit)
        return {"display": d, "claim": claims.add(v, unit=unit, source=f"WBG Scorecard API · {ind_code}", label=measure,
                                                   entity=entity, measure=measure, period=period, display=d)}
    facts = []
    r = q.one("SELECT achieved, expected, quality_flag FROM v_results WHERE ind_code=? AND area_code=? AND org=? AND snapshot_fy=?",
              [ind_code, area, org, fy]) if sex == "_T" else q.result(ind_code, area, org, fy, sex)
    ent = q.area_name(area) + ("" if org == "WBG" else f" · {org}") + (" · female" if sex == "F" else "")
    if r and r.get("expected") is not None:
        items = [("achieved", c(r["achieved"], ent, f"{name}: achieved")), ("expected", c(r["expected"], ent, f"{name}: expected"))]
        if r["achieved"] is not None and r["expected"] and r["achieved"] <= r["expected"]:
            items += [("still to deliver", c(r["expected"] - r["achieved"], ent, f"{name}: expected − achieved")),
                      ("delivery rate", c(100 * r["achieved"] / r["expected"], ent, f"{name}: achieved ÷ expected", "Percentage"))]
        facts.append({"entity": ent, "items": items})
    regs = []
    for code in q.REGIONS:
        rr = q.result(ind_code, code, "WBG", fy, sex)
        if rr and rr["achieved"] is not None and rr["expected"] and rr["achieved"] <= rr["expected"]:
            regs.append((code, rr))
    if regs:
        g = max(regs, key=lambda x: x[1]["expected"] - x[1]["achieved"])
        lo = min(regs, key=lambda x: x[1]["achieved"] / x[1]["expected"])
        facts.append({"entity": q.REGION_NAMES[g[0]], "label": "Region with the most still to deliver", "items": [
            ("still to deliver", c(g[1]["expected"] - g[1]["achieved"], q.REGION_NAMES[g[0]], f"{name}: expected − achieved"))]})
        facts.append({"entity": q.REGION_NAMES[lo[0]], "label": "Region with the lowest delivery rate", "items": [
            ("delivery rate", c(100 * lo[1]["achieved"] / lo[1]["expected"], q.REGION_NAMES[lo[0]], f"{name}: achieved ÷ expected", "Percentage"))]})
    prev, now = q.result(ind_code, "ACW", "WBG", fy - 1), q.result(ind_code, "ACW", "WBG", fy)
    if prev and now and prev["achieved"] is not None and now["achieved"] is not None:
        facts.append({"entity": "All countries", "label": "Change between snapshots", "items": [
            (f"achieved FY{str(fy - 1)[2:]}", c(prev["achieved"], "All countries", f"{name}: achieved (FY{str(fy - 1)[2:]})")),
            (f"achieved FY{str(fy)[2:]}", c(now["achieved"], "All countries", f"{name}: achieved (FY{str(fy)[2:]})"))]})
    return {"indicator": name, "facts": facts}
