"""Artifact specs (rendered client-side by charts.js / workspace.js) and Jupyter notebook export.

Every artifact keeps a ``data_ref`` describing the exact query behind it, which is what the notebook export replays
against the live public APIs.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from explorer import queries as q
from explorer.formatting import fmt

from . import pcn


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def results_figure(ind_code: str, rows: list[dict], *, title: str, sex: str = "_T", fy: int | None = None) -> dict:
    ind = q.indicators()[ind_code]
    fy = fy or q.latest_fy()
    return {"id": new_id(), "type": "figure", "kind": "bullet", "title": title, "unit": ind["unit"],
            "rows": [{"key": r["area"], "label": r["area_name"], "v": [r["achieved"]["value"], r["expected"]["value"]]}
                     for r in rows if not r.get("no_data") and r.get("achieved")],
            "prov": f"Source: WBG Scorecard API · {ind_code}{' · female' if sex == 'F' else ''} · FY{str(fy)[2:]} snapshot. "
                    "Bars: achieved (dark) within expected (light); labels = achieved ÷ expected, computed in code.",
            "data_ref": {"kind": "results", "ind_code": ind_code, "areas": [r["area"] for r in rows], "sex": sex, "fy": fy}}


def matrix_points(R: dict) -> list[dict]:
    acc, exp = {x["code"] for x in R["accelerate"]}, {x["code"] for x in R["expand"]}
    pts = []
    for x in R["rows"]:
        xv = x["people_in_need"] if R["need_is_pop_share"] else x["need"]
        if xv is None:
            continue
        pts.append({"code": x["code"], "label": x["name"], "x": xv, "y": x["expected"] or 0, "size": x["active_commitments"] or 0,
                    "ratio": x["ratio"], "n_active": x["active_projects"],
                    "group": "accelerate" if x["code"] in acc else "expand" if x["code"] in exp else "other"})
    return pts


def matrix_figure(R: dict) -> dict:
    need = R["need"]
    xlab = (f"People {'affected' if R['need_is_negative'] else 'without access'} (population × {need['ind_code']})"
            if R["need_is_pop_share"] else need["display_name"])
    return {"id": new_id(), "type": "figure", "kind": "matrix", "title": "Opportunity matrix", "unit": R["indicator"]["unit"],
            "points": matrix_points(R), "xlab": xlab, "xlog": R["need_is_pop_share"], "ylab": "Expected results (active portfolio)",
            "prov": f"Each dot is a client country. x: {xlab}; y: expected results of the active portfolio; size: active "
                    f"sector commitments (Projects API). Orange = accelerate delivery, blue = expand footprint. "
                    f"Sources: WBG Scorecard FY{str(R['snapshot_fy'])[2:]}, Data360 population, World Bank Projects API.",
            "data_ref": {"kind": "research", "outcome_id": R["outcome"]["outcome_id"]}}


# ------------------------------------------------------------------------------------------------ deck
def deck(R: dict, claims: pcn.Claims, slide_text: dict | None) -> dict:
    """3-slide leadership stocktake. ``slide_text`` comes from the LLM (claim-tagged) or None for the template."""
    fw, ind, fy = R["for_writer"], R["indicator"], R["snapshot_fy"]
    w, u = fw["world"], ind["unit"]

    def tag(x):
        return f'<claim id="{x["claim"]}">{x["display"]}</claim>' if x and x.get("claim") else "—"

    if not slide_text:  # deterministic fallback, still claim-tagged
        acc = fw["accelerate_delivery"][:3]
        expd = fw["expand_footprint"][:3]
        slide_text = {"slides": [
            {"title": f"The portfolio has delivered {tag(w['delivery_rate'])} of expected results; {tag(w['remaining_gap'])} remain to be delivered",
             "bullets": [f"{tag(w['achieved'])} achieved of {tag(w['expected'])} expected from the active portfolio (FY{str(fy)[2:]}).",
                         f"{fw['regional_focus']['region']} holds the largest remaining gap: {tag(fw['regional_focus']['remaining_gap'])}."]},
            {"title": f"{fw['regional_focus']['region']} carries the largest remaining gap",
             "bullets": [f"{r['name']}: {fmt(r['gap'], u)} still to deliver" for r in sorted(R['regions'], key=lambda r: -(r['gap'] or 0))[:3]]},
            {"title": f"Accelerate in {', '.join(x['country'] for x in acc[:2])}; expand in {', '.join(x['country'] for x in expd[:2])}",
             "bullets": [f"Accelerate delivery where portfolios are large but behind: " + ", ".join(f"{x['country']} ({tag(x.get('delivery_rate'))})" for x in acc),
                         f"Expand where need far exceeds the pipeline: " + ", ".join(x["country"] for x in expd)]},
        ]}
    slides = []
    for s in slide_text.get("slides", [])[:3]:
        title_html, st1 = pcn.render(s.get("title", ""), claims)
        bullets = [pcn.render(b, claims)[0] for b in s.get("bullets", [])[:3]]
        slides.append({"title_html": title_html, "bullets_html": bullets})
    while len(slides) < 3:
        slides.append({"title_html": "", "bullets_html": []})
    kpis = [{"v": tag(w["achieved"]), "l": f"{ind['display_name']}: achieved"}, {"v": tag(w["expected"]), "l": "Expected from active portfolio"},
            {"v": tag(w.get("change_since_previous_snapshot")) if w.get("change_since_previous_snapshot") else "—", "l": "Achieved since previous snapshot"},
            {"v": tag(w["delivery_rate"]), "l": "Delivered (achieved ÷ expected)"}]
    kpis = [{"v_html": pcn.render(k["v"], claims)[0], "l": k["l"]} for k in kpis]
    lists = {"accelerate": [{"name": x["country"], "html": pcn.render(f"{tag(x.get('delivery_rate'))} of {tag(x.get('expected'))}", claims)[0]} for x in fw["accelerate_delivery"][:3]],
             "expand": [{"name": x["country"], "html": pcn.render((f"{tag(x['people_in_need'])} people in need" if x.get("people_in_need") else tag(x.get("need_indicator")))
                                                                  + f"; pipeline {tag(x['expected']) if x.get('expected') else 'none'}", claims)[0]} for x in fw["expand_footprint"][:3]]}
    src = (f"Source: WBG Scorecard API ({ind['ind_code']}), FY{str(fy)[2:]} snapshot; client context {R['need']['ind_code'] if R['need'] else ''}; "
           "population: Data360 WDI; footprint: Scorecard project-level + Projects API (sector match, approximate). Ratios computed in code.")
    return {"id": new_id(), "type": "deck", "title": f"Briefing · {R['outcome']['name']}", "outcome": R["outcome"]["name"],
            "kicker": f"{R['outcome']['name']} · Leadership stocktake · FY{str(fy)[2:]}", "slides": slides, "kpis": kpis, "lists": lists,
            "regions": [{"key": r["code"], "label": r["name"], "v": [r["achieved"], r["expected"]]} for r in R["regions"] if r["expected"]],
            "focus": R["focus"]["code"], "matrix": matrix_figure(R), "unit": ind["unit"], "source": src,
            "data_ref": {"kind": "research", "outcome_id": R["outcome"]["outcome_id"]}}


# ------------------------------------------------------------------------------------------------ notebooks
def _md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s.splitlines(keepends=True)}


def _code(s):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.splitlines(keepends=True)}


SETUP = '''import os, re, requests, pandas as pd, concurrent.futures as cf

BASE = "https://ext.api.worldbank.org/api/Scorecard/"
SNAPSHOT_FY = {fy}

def scorecard_api_key():
    """The Scorecard website ships a public API key in its JavaScript bundle; read it from there
    (or set SCORECARD_API_KEY to override)."""
    if os.getenv("SCORECARD_API_KEY"):
        return os.environ["SCORECARD_API_KEY"]
    html = requests.get("https://scorecard.worldbank.org/", timeout=30).text
    bundle = re.search(r'src="(main\\.[0-9a-f]+\\.js)"', html).group(1)
    js = requests.get("https://scorecard.worldbank.org/" + bundle, timeout=60).text
    return re.search(r'apiKey:\\{{data:"([0-9a-f]+)"', js).group(1)

HEADERS = {{"apikey": scorecard_api_key(), "User-Agent": "scorecard-explorer-notebook"}}

def fetch_summary(area_type, area_code, fy=SNAPSHOT_FY):
    """getSCSUMMARYDATA returns a Databricks SQL result set: manifest.schema.columns + result.data_array (all text)."""
    url = f"{{BASE}}getSCSUMMARYDATA?refareatype={{area_type}}&refareacode={{area_code}}&orgCode=ALL&snapshotfy={{fy}}"
    for attempt in range(3):
        try:
            p = requests.get(url, headers=HEADERS, timeout=90).json()
            cols = [c["name"] for c in p["manifest"]["schema"]["columns"]]
            return pd.DataFrame(p["result"].get("data_array") or [], columns=cols)
        except Exception:
            if attempt == 2:
                raise

def totals(df):
    return (df.sub_ind_code.isna() & (df.sex_disaggregate_code == "_T") & (df.age_disaggregate_code == "_T")
            & (df.disability_disaggregate_code == "_T"))'''


def notebook(artifact: dict) -> dict:
    ref = artifact.get("data_ref") or {}
    if ref.get("kind") == "research":
        cells = _research_cells(ref["outcome_id"], artifact)
    else:
        cells = _results_cells(ref, artifact)
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                         "language_info": {"name": "python"}}}


def _area_spec(codes):
    areas, spec = q.areas(), []
    for c in codes:
        a = areas.get(c)
        if not a:
            continue
        if c == "FCS":
            spec.append(["FCS", "FCS"])
        elif a["area_type"] == "COUNTRY":
            spec.append(["COUNTRY", a["iso2"]])
        else:
            spec.append(["REGION", c])
    return spec


def _results_cells(ref: dict, artifact: dict) -> list:
    ind = q.indicators()[ref["ind_code"]]
    fy = ref.get("fy") or q.latest_fy()
    spec = _area_spec(ref.get("areas") or ["ACW", *q.REGIONS])
    shown = {}
    for c in ref.get("areas") or []:
        r = q.result(ref["ind_code"], c, "WBG", fy, ref.get("sex", "_T"))
        if r and r["expected"] is not None:
            a = q.areas()[c]
            shown[a["iso2"] if a["area_type"] == "COUNTRY" else c] = [r["achieved"], r["expected"]]
    sex = ref.get("sex", "_T")
    return [
        _md(f"# {artifact.get('title', 'Scorecard figure')}\n\n**Indicator:** {ind['display_name']} (`{ind['ind_code']}`)  \n"
            f"**Snapshot:** FY{str(fy)[2:]}  \n**Generated by:** Scorecard Explorer, {dt.date.today()}\n\n"
            "Re-downloads the data behind this artifact from the public WBG Scorecard API, cleans it, checks it against the "
            "values shown in the app (✓), reproduces the figure and saves a CSV."),
        _code(SETUP.format(fy=fy)),
        _md("## 1. Pull"),
        _code(f'INDICATOR = "{ind["ind_code"]}"\nSEX = "{sex}"\nAREAS = {json.dumps(spec)}  # (area type, code); countries use the Bank\'s ISO2-like codes\n'
              "with cf.ThreadPoolExecutor(8) as ex:\n    raw = pd.concat(ex.map(lambda a: fetch_summary(*a), AREAS), ignore_index=True)\nraw.shape"),
        _md("## 2. Clean & structure\nWBG totals for the indicator (no sub-indicator, totals for age/disability), numbers parsed from text; "
            "`*_base_*` fields carry full precision."),
        _code("df = raw[(raw.ind_code == INDICATOR) & (raw.org_code == \"WBG\") & raw.sub_ind_code.isna()\n"
              "         & (raw.sex_disaggregate_code == SEX) & (raw.age_disaggregate_code == \"_T\") & (raw.disability_disaggregate_code == \"_T\")].copy()\n"
              "tidy = pd.DataFrame({\"area\": df.ref_area_code, \"area_name\": df.ref_area_name,\n"
              "                     \"achieved\": pd.to_numeric(df.ind_base_achieved_val, errors=\"coerce\"),\n"
              "                     \"expected\": pd.to_numeric(df.ind_base_expected_val, errors=\"coerce\")})\n"
              "tidy = tidy.sort_values(\"expected\", ascending=False).drop_duplicates(\"area\")\n"
              "tidy[\"delivery_rate\"] = tidy.achieved / tidy.expected\ntidy[\"remaining_gap\"] = tidy.expected - tidy.achieved\ntidy"),
        _md("## 3. Verify against the app (✓)"),
        _code(f"SHOWN = {json.dumps(shown)}  # area -> [achieved, expected] as shown in the app\n"
              "for area, (ach, exp) in SHOWN.items():\n    row = tidy[tidy.area == area]\n"
              "    ok = len(row) and abs((row.achieved.iloc[0] or 0) - (ach or 0)) <= 0.5 and abs(row.expected.iloc[0] - exp) <= 0.5\n"
              "    print(\"✓\" if ok else \"⚠ (updated since snapshot?)\", area, ach, exp)"),
        _md("## 4. Figure"),
        _code("import plotly.graph_objects as go\nt = tidy.sort_values(\"expected\")\nfig = go.Figure([\n"
              "    go.Bar(y=t.area_name, x=t.expected, orientation=\"h\", name=\"Expected\", marker_color=\"#cde7f9\"),\n"
              "    go.Bar(y=t.area_name, x=t.achieved, orientation=\"h\", name=\"Achieved\", marker_color=\"#0071bc\", width=0.4)])\n"
              f"fig.update_layout(barmode=\"overlay\", template=\"simple_white\", title={json.dumps(ind['display_name'] + ': achieved vs expected')}, height=140 + 40 * len(t))\nfig.show()"),
        _code("tidy.to_csv(f\"scorecard_{INDICATOR}_FY{SNAPSHOT_FY}.csv\", index=False)\nprint(\"saved\", len(tidy), \"rows\")"),
    ]


def _research_cells(outcome_id: int, artifact: dict) -> list:
    from .analysis import research  # local import to avoid a cycle

    R = research(outcome_id, pcn.Claims())
    countries = {q.areas()[x["code"]]["iso2"]: x["code"] for x in R["rows"] if q.areas()[x["code"]].get("iso2")}
    shown = {"accelerate": [[x["code"], x["achieved"], x["expected"]] for x in R["accelerate"]], "expand": [x["code"] for x in R["expand"]]}
    need = R["need"]
    return [
        _md(f"# Three-year priorities: {R['outcome']['name']}\n\n**Question:** Based on the Scorecard data and the Bank's current operational "
            "footprint, which areas and countries should a three-year plan prioritize? Where are the biggest gaps and opportunities?\n\n"
            "**Sources:** WBG Scorecard API (results + client context by country) · World Bank Data360 (population) · World Bank "
            f"Projects API (active portfolio).  \n**Generated by:** Scorecard Explorer research agent, {dt.date.today()}.\n\n"
            "Re-pulls every source, cleans and joins them, re-runs the prioritization rules and checks the result against the app."),
        _code(SETUP.format(fy=R["snapshot_fy"]) + f'\n\nINDICATOR = "{R["indicator"]["ind_code"]}"   # WBG Results indicator\n'
              f'NEED = "{need["ind_code"] if need else ""}"   # client-context need indicator\nNEED_IS_NEGATIVE = {R["need_is_negative"]}  # True if higher = worse\n'
              f'NEED_IS_POP_SHARE = {R["need_is_pop_share"]}  # % of population -> people in need\nSECTOR_PATTERN = r"{R["sector_pattern"]}"\n'
              f"COUNTRIES = {json.dumps(countries)}  # Bank ISO2-like code -> ISO3"),
        _md("## 1. Scorecard: results and client context for every country"),
        _code("with cf.ThreadPoolExecutor(10) as ex:\n    raw = pd.concat(ex.map(lambda c: fetch_summary(\"COUNTRY\", c), COUNTRIES), ignore_index=True)\n"
              "res = raw[totals(raw) & (raw.ind_code == INDICATOR) & (raw.org_code == \"WBG\")].copy()\n"
              "res[\"achieved\"] = pd.to_numeric(res.ind_base_achieved_val, errors=\"coerce\")\nres[\"expected\"] = pd.to_numeric(res.ind_base_expected_val, errors=\"coerce\")\n"
              "res = res.sort_values(\"expected\", ascending=False).drop_duplicates(\"ref_area_code\").set_index(\"ref_area_code\")[[\"achieved\", \"expected\"]]\n"
              "ctx = raw[totals(raw) & (raw.ind_code == NEED)].copy()\nctx[\"value\"] = pd.to_numeric(ctx.ind_base_achieved_val, errors=\"coerce\").fillna(pd.to_numeric(ctx.ind_achieved_val, errors=\"coerce\"))\n"
              "ctx[\"year\"] = ctx.ind_time_per.str.findall(r\"(?:19|20)\\d{2}\").str[-1].astype(float)\n"
              "ctx = ctx.dropna(subset=[\"value\"]).sort_values(\"year\").groupby(\"ref_area_code\").last()[[\"value\", \"year\"]]\n"
              "print(len(res), \"countries with results;\", len(ctx), \"with need data\")"),
        _md("## 2. Data360: population"),
        _code("d = requests.get(\"https://data360api.worldbank.org/data360/data\", params={\"DATABASE_ID\": \"WB_WDI\", \"INDICATOR\": \"WB_WDI_SP_POP_TOTL\",\n"
              f"    \"timePeriodFrom\": 2015, \"timePeriodTo\": {R['snapshot_fy']}, \"top\": 1000, \"skip\": 0}}, timeout=60).json()\n"
              "pop = pd.DataFrame(d[\"value\"]).assign(pop=lambda x: x.OBS_VALUE.astype(float)).sort_values(\"TIME_PERIOD\").groupby(\"REF_AREA\").last()[\"pop\"]"),
        _md("## 3. Projects API: active operational footprint in the sector"),
        _code("rows, start = [], 0\nwhile True:\n    p = requests.get(\"https://search.worldbank.org/api/v2/projects\", params={\"format\": \"json\", \"status_exact\": \"Active\",\n"
              "        \"rows\": 500, \"os\": start, \"fl\": \"id,countrycode,totalcommamt,sector1,sector2,sector3\"}, timeout=120).json()\n"
              "    batch = list(p[\"projects\"].values()); rows += batch; start += 500\n    if not batch or start >= int(p[\"total\"]): break\nact = []\n"
              "for pr in rows:\n    secs = \"|\".join(pr[k][\"Name\"] for k in (\"sector1\", \"sector2\", \"sector3\") if isinstance(pr.get(k), dict) and pr[k].get(\"Name\"))\n"
              "    if re.search(SECTOR_PATTERN, secs):\n        amt = float(str(pr.get(\"totalcommamt\", \"0\")).replace(\",\", \"\") or 0)\n"
              "        act += [(c, amt) for c in pr.get(\"countrycode\") or []]\n"
              "act = pd.DataFrame(act, columns=[\"iso2\", \"usd\"]).groupby(\"iso2\").agg(active_projects=(\"usd\", \"size\"), active_usd=(\"usd\", \"sum\"))"),
        _md("## 4. Join and compute need, gap and delivery rate"),
        _code("df = pd.DataFrame({\"iso2\": list(COUNTRIES), \"iso3\": list(COUNTRIES.values())}).set_index(\"iso2\")\n"
              "df = df.join(res).join(ctx.rename(columns={\"value\": \"need\", \"year\": \"need_year\"})).join(act)\ndf[\"population\"] = df.iso3.map(pop)\n"
              "df[\"remaining_gap\"] = df.expected - df.achieved\ndf[\"ratio\"] = df.achieved / df.expected\n"
              "if NEED_IS_POP_SHARE:\n    df[\"people_in_need\"] = df.population * (df.need if NEED_IS_NEGATIVE else 100 - df.need) / 100\n"
              "df = df[df.expected.notna() | df.need.notna()]\ndf.sort_values(\"remaining_gap\", ascending=False).head(10)"),
        _md("## 5. Prioritization rules (same code path as the app)\n- **Accelerate delivery:** expected ≥ 60th percentile and achieved < 40% of expected → top 4 by remaining gap.\n"
            "- **Expand footprint:** highest people in need where expected results cover < 25% of need → top 4."),
        _code("r = df[(df.expected > 0) & df.ratio.notna()]\naccelerate = r[(r.expected >= r.expected.quantile(0.6)) & (r.ratio < 0.4)].sort_values(\"remaining_gap\", ascending=False).head(4)\n"
              "if NEED_IS_POP_SHARE:\n    n = df[df.people_in_need > 0].copy()\n    n[\"coverage\"] = n.expected.fillna(0) / n.people_in_need\n"
              "    expand = n[(n.coverage < 0.25) & ~n.iso3.isin(accelerate.iso3)].sort_values(\"people_in_need\", ascending=False).head(4)\n"
              "else:\n    n = df[df.need.notna() & ~df.iso3.isin(accelerate.iso3) & ~(df.expected > 0)]\n    expand = n.sort_values(\"need\", ascending=not NEED_IS_NEGATIVE).head(4)\n"
              "print(\"Accelerate:\", list(accelerate.iso3)); print(\"Expand:\", list(expand.iso3))"),
        _md("## 6. Verify against the app (✓)"),
        _code(f"SHOWN = {json.dumps(shown)}\nprint(\"accelerate\", \"✓\" if list(accelerate.iso3) == [x[0] for x in SHOWN[\"accelerate\"]] else \"⚠ (data updated?)\")\n"
              "print(\"expand    \", \"✓\" if list(expand.iso3) == SHOWN[\"expand\"] else \"⚠ (inputs updated?)\")"),
        _md("## 7. Opportunity matrix"),
        _code("import plotly.express as px\nxcol = \"people_in_need\" if NEED_IS_POP_SHARE else \"need\"\nplot = df.dropna(subset=[xcol]).copy()\n"
              "plot[\"group\"] = \"Other\"\nplot.loc[plot.iso3.isin(accelerate.iso3), \"group\"] = \"Accelerate delivery\"\nplot.loc[plot.iso3.isin(expand.iso3), \"group\"] = \"Expand footprint\"\n"
              "plot[\"expected_plot\"] = plot.expected.fillna(0).clip(lower=1e4)\n"
              "fig = px.scatter(plot, x=xcol, y=\"expected_plot\", color=\"group\", size=plot.active_usd.fillna(0).clip(lower=1e6), hover_name=\"iso3\",\n"
              "                 log_x=NEED_IS_POP_SHARE, log_y=True, template=\"simple_white\",\n"
              "                 color_discrete_map={\"Other\": \"#c3c9cf\", \"Accelerate delivery\": \"#eb6834\", \"Expand footprint\": \"#0071bc\"})\nfig.show()"),
        _code("df.to_csv(f\"priorities_{INDICATOR}_FY{SNAPSHOT_FY}.csv\")\nprint(\"saved\", len(df), \"countries\")"),
    ]
