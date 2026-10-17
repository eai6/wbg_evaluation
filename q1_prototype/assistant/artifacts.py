"""Artifact specs (rendered client-side by charts.js / workspace.js) and Jupyter notebook export.

Every artifact keeps a ``data_ref`` describing the exact query behind it, which is what the notebook export replays
against the live public APIs.
"""
from __future__ import annotations

import datetime as dt
import html
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


def _short(name: str) -> str:
    return name.replace("Democratic Republic of Congo", "DR Congo").replace("Central African Republic", "CAR")


def matrix_figure(R: dict, top: int | None = None) -> dict:
    """The selection rule as a chart, the same for every outcome area: countries are ranked by results still to deliver
    (expected − achieved). y = still to deliver, x = share delivered so far (context only), and a dashed line between the
    N-th and (N+1)-th country, so the selected countries are exactly the dots above the line."""
    from .analysis import TOP_N
    n = top or TOP_N
    top_gap = {x["code"] for x in R["most_to_deliver"][:n]}
    pts = [{"code": x["code"], "label": _short(x["name"]), "x": 100 * x["rate"], "y": x["gap"], "floor": False, "gap": x["gap"],
            "ratio": x["rate"], "group": "gap" if x["code"] in top_gap else "other", "flag": x["flag"]}
           for x in R["rows"] if x["flag"] is None and (x.get("gap") or 0) > 0]
    gaps = sorted((p["y"] for p in pts), reverse=True)
    cut = (gaps[n - 1] * gaps[n]) ** 0.5 if len(gaps) > n else (gaps[-1] * 0.85 if gaps else None)
    flagged = sum(1 for x in R["rows"] if x["flag"] == "achieved_above_expected")
    return {"id": new_id(), "type": "figure", "kind": "matrix", "title": "Why these countries: results still to deliver",
            "unit": R["indicator"]["unit"], "points": pts, "xlog": False, "xpct": True, "floor": None,
            "cuts": {"y": {"v": cut, "label": f"Top {min(n, len(gaps))} still to deliver ↑"}} if cut else {},
            "xlab": "Share of expected results delivered so far", "ylab": "Results still to deliver",
            "legend": {"gap": "Most still to deliver"},
            "prov": f"Each dot is a WBG borrowing country with results still to deliver. Countries are ranked by results still to "
                    f"deliver (expected − achieved); the dashed line sits between the {n}th and {n + 1}th country, so the {n} dots above it "
                    "are the selection. The x-axis (achieved ÷ expected) is context only and does not change the ranking. "
                    + (f"{flagged} countries report achieved above expected; they are data checks and are not ranked. " if flagged else "")
                    + f"Source: WBG Scorecard FY{str(R['snapshot_fy'])[2:]}.",
            "data_ref": {"kind": "research", "outcome_id": R["outcome"]["outcome_id"]}}


# ------------------------------------------------------------------------------------------------ deck
def deck(R: dict, claims: pcn.Claims) -> dict:
    """3-slide stocktake, fully deterministic: titles, lists and the selection chart are computed from the data and every
    number carries a claim. No model-written text appears on the slides."""
    from .pipelines import facts_list  # local import to avoid a cycle
    F, ind, fy, need = R["facts"], R["indicator"], R["snapshot_fy"], R["need"]
    o = R["outcome"]["name"]
    overall = dict(F["overall"][0]["items"])
    b = lambda key: pcn.badge(overall[key]["claim"], claims)
    kpis = [{"v_html": b("achieved"), "l": f"{ind['display_name']}: achieved"},
            {"v_html": b("expected"), "l": "Expected from the active portfolio"},
            {"v_html": b("still to deliver"), "l": "Still to deliver (expected − achieved)"},
            {"v_html": b("delivery rate"), "l": "Delivered so far (achieved ÷ expected)"}]
    top_region = R["regions"][0]["name"] if R["regions"] else None
    gap_codes = [x["code"] for x in R["most_to_deliver"]]
    titles = [f"{b('delivery rate')} of expected results delivered; {b('still to deliver')} still to deliver",
              f"{top_region} holds the most results still to deliver" if top_region else "Where results remain to be delivered",
              f"Countries with the most still to deliver: {', '.join(x['name'] for x in R['most_to_deliver'][:3])}"]
    titles = [t if "<span" in t else html.escape(t) for t in titles]
    src = (f"Source: WBG Scorecard API ({ind['ind_code']}), FY{str(fy)[2:]} snapshot; "
           + (f"need: {need['ind_code']} × Data360 population (same year); " if need else "")
           + "WBG borrowing countries (IDA, Blend, IBRD). Expected = active portfolio, not a target. Ratios computed in code.")
    # the coloured dot is the key of the selection chart beside the list
    head = "<div class='slab' style='color:var(--s2)'>● Most still to deliver (expected − achieved)</div>"
    # one selection rule for every outcome area: most still to deliver. The AI interpretation stays in the chat answer
    # (its length varies, and a slide must never cut text).
    s3 = (head + facts_list(F["most_to_deliver"][:3], claims, compact=2)
          + "<div class='note'>Selected by results still to deliver (expected − achieved): the three countries above the dashed line. "
            "Share delivered is shown for context.</div>")
    return {"id": new_id(), "type": "deck", "title": f"Briefing · {o}", "outcome": o,
            "kicker": f"{o} · Leadership stocktake · FY{str(fy)[2:]}", "kpis": kpis,
            "slides": [{"title_html": titles[0], "body_html": "<div class='slab'>By institution</div>" + facts_list(F["overall"][1:], claims)},
                       {"title_html": titles[1], "body_html": facts_list(F["regions"][:4], claims, compact=4)},
                       {"title_html": titles[2], "body_html": s3}],
            "regions": [{"key": r["code"], "label": r["name"], "v": [r["achieved"], r["expected"]]} for r in R["regions"]],
            "focus": R["regions"][0]["code"] if R["regions"] else None,
            "matrix": matrix_figure(R, top=3),
            "gap_bars": [{"key": x["code"], "label": x["name"], "v": [x["achieved"], x["expected"]]} for x in R["most_to_deliver"][:3]],
            "gap_codes": gap_codes, "unit": ind["unit"], "source": src,
            "data_ref": {"kind": "research", "outcome_id": R["outcome"]["outcome_id"]}}


# ------------------------------------------------------------------------------------------------ notebooks
def _md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s.splitlines(keepends=True)}


def _code(s):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.splitlines(keepends=True)}


SETUP = '''import os, requests, pandas as pd, concurrent.futures as cf

BASE = "https://ext.api.worldbank.org/api/Scorecard/"
SNAPSHOT_FY = {fy}

def scorecard_api_key():
    """The Scorecard website ships a public API key in its JavaScript bundle; read it from there
    (or set SCORECARD_API_KEY to override)."""
    if os.getenv("SCORECARD_API_KEY"):
        return os.environ["SCORECARD_API_KEY"]
    html = requests.get("https://scorecard.worldbank.org/", timeout=30).text
    bundle = next(p.split('"', 1)[0] for p in html.split('src="')[1:] if p.startswith("main."))
    js = requests.get("https://scorecard.worldbank.org/" + bundle, timeout=60).text
    return js.split('apiKey:{{data:"', 1)[1].split('"', 1)[0]

HEADERS = {{"apikey": scorecard_api_key(), "User-Agent": "scorecard-explorer-notebook"}}

def fetch_summary(area_type, area_code, org="ALL", fy=SNAPSHOT_FY):
    """getSCSUMMARYDATA returns a Databricks SQL result set: manifest.schema.columns + result.data_array (all text)."""
    url = f"{{BASE}}getSCSUMMARYDATA?refareatype={{area_type}}&refareacode={{area_code}}&orgCode={{org}}&snapshotfy={{fy}}"
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
    """The notebook that reproduces a 3-slide briefing (the only notebook export: one analysis, fully re-computable)."""
    ref = artifact.get("data_ref") or {}
    if ref.get("kind") != "research":
        raise ValueError("notebooks are exported with a 3-slide briefing only")
    cells = _deck_cells(ref["outcome_id"])
    cells.insert(1, _md("**Requirements:** Python 3.10+ with `pip install requests pandas plotly`. "
                        "The notebook downloads everything it needs from public World Bank APIs; no key or login is required."))
    for i, c in enumerate(cells):  # nbformat 4.5 requires a unique id per cell
        c.setdefault("id", f"cell-{i}")
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                         "language_info": {"name": "python"}}}


def _deck_cells(outcome_id: int) -> list:
    """Slide-by-slide reproduction of the briefing from the public APIs, each slide checked against the deck (✓)."""
    from .analysis import research  # local import to avoid a cycle

    R = research(outcome_id, pcn.Claims())
    fy, ind, need, areas = R["snapshot_fy"], R["indicator"], R["need"], q.areas()
    countries = {areas[x["code"]]["iso2"]: [x["code"], x["region"]] for x in R["rows"] if areas[x["code"]].get("iso2")}
    world = {o: q.result(ind["ind_code"], "ACW", o, fy) for o in ("WBG", "WB", "IFC", "MIGA")}
    shown = {"world": {o: [r["achieved"], r["expected"]] if r else None for o, r in world.items()},
             "regions": {r["code"]: [r["achieved"], r["expected"]] for r in R["regions"]},
             "region_people": {r["code"]: r["people"] for r in R["regions"]} if need else {},
             "top3": [x["code"] for x in R["most_to_deliver"][:3]]}
    share = "ctry.need" if (need and need["direction"] == "lower_is_better") else "(100 - ctry.need)"
    name = R["outcome"]["name"]
    return [
        _md(f"# Briefing notebook: {name}\n\n"
            f"Reproduces the 3-slide briefing for **{name}** ({ind['display_name']}, `{ind['ind_code']}`, FY{str(fy)[2:]} snapshot) "
            "from the public World Bank APIs, and checks every slide against the numbers in the deck (✓).\n\n"
            "| Slide | What is rebuilt |\n|---|---|\n"
            "| 1 · Where the portfolio stands | achieved, expected, still to deliver, delivery rate; split by World Bank, IFC, MIGA |\n"
            "| 2 · Where results remain | achieved vs expected by region, ranked by still to deliver |\n"
            "| 3 · Three-year priorities | WBG borrowing countries ranked by still to deliver (expected − achieved); the top 3 and the selection chart |\n\n"
            "**Rules:** expected = what the active portfolio is expected to deliver (not a target). A delivery rate is shown only when "
            "0 ≤ achieved ≤ expected; rows with achieved above expected are data checks and are not ranked.  \n"
            f"**Generated by:** Scorecard Explorer, {dt.date.today()}."),
        _code(SETUP.format(fy=fy) + f'\n\nINDICATOR = "{ind["ind_code"]}"\nREGIONS = {json.dumps(q.REGIONS)}\n'
              f'COUNTRIES = {json.dumps(countries)}  # WBG borrowers: Bank ISO2-like code -> [ISO3, region]\n'
              f'SHOWN = {shown!r}  # the numbers in the deck, for the ✓ checks (None = not reported)\n\n'
              "def tidy(raw, org):\n"
              "    d = raw[totals(raw) & (raw.ind_code == INDICATOR) & (raw.org_code == org)].copy()\n"
              "    d[\"achieved\"] = pd.to_numeric(d.ind_base_achieved_val, errors=\"coerce\")\n"
              "    d[\"expected\"] = pd.to_numeric(d.ind_base_expected_val, errors=\"coerce\")\n"
              "    # the source occasionally repeats a key; keep the row with the largest expected value\n"
              "    return d.sort_values(\"expected\", ascending=False).drop_duplicates(\"ref_area_code\").set_index(\"ref_area_code\")[[\"achieved\", \"expected\"]]\n\n"
              "def same(a, b, tol=0.5):\n"
              "    return (pd.isna(a) and b is None) or (not pd.isna(a) and b is not None and abs(a - b) <= tol)\n\n"
              "def rate_ok(a, e):  # a delivery rate is meaningful only when 0 <= achieved <= expected\n"
              "    return pd.notna(a) and pd.notna(e) and e > 0 and 0 <= a <= e"),
        _md("## Data: pull everything the slides use"),
        _code("with cf.ThreadPoolExecutor(10) as ex:\n"
              "    world_raw = dict(zip([\"ALL\", \"WB\", \"IFC\", \"MIGA\"], ex.map(lambda o: fetch_summary(\"REGION\", \"ACW\", o), [\"ALL\", \"WB\", \"IFC\", \"MIGA\"])))\n"
              "    region_raw = pd.concat(ex.map(lambda r: fetch_summary(\"REGION\", r), REGIONS), ignore_index=True)\n"
              "    country_raw = pd.concat(ex.map(lambda c: fetch_summary(\"COUNTRY\", c), COUNTRIES), ignore_index=True)\n"
              "world = {\"WBG\": tidy(world_raw[\"ALL\"], \"WBG\").loc[\"ACW\"], **{o: tidy(world_raw[o], o).loc[\"ACW\"] for o in [\"WB\", \"IFC\", \"MIGA\"]}}\n"
              "regions = tidy(region_raw, \"WBG\").reindex(REGIONS)\n"
              "ctry = pd.DataFrame.from_dict(COUNTRIES, orient=\"index\", columns=[\"iso3\", \"region\"]).join(tidy(country_raw, \"WBG\"))\n"
              "print(len(ctry), \"borrowing countries;\", int(ctry.expected.notna().sum()), \"with results\")"),
        *([_md(f"Context used on slide 2: **{need['people_measure']}** = population × "
               f"{'share' if need['direction'] == 'lower_is_better' else '(100 − share)'} of `{need['ind_code']}` "
               "(Scorecard client context), population from Data360 for the same year. It does not select countries."),
           _code("ctx = country_raw[totals(country_raw) & (country_raw.ind_code == " + json.dumps(need["ind_code"]) + ")].copy()\n"
                 "ctx[\"value\"] = pd.to_numeric(ctx.ind_base_achieved_val, errors=\"coerce\").fillna(pd.to_numeric(ctx.ind_achieved_val, errors=\"coerce\"))\n"
                 "ctx[\"year\"] = ctx.ind_time_per.map(lambda s: [int(x) for x in str(s).split(\"-\") if len(x) == 4 and x.isdigit()][-1])  # end year of a period or range\n"
                 "ctx = ctx.dropna(subset=[\"value\"]).sort_values(\"year\").groupby(\"ref_area_code\").last()[[\"value\", \"year\"]]\n"
                 "rows, skip = [], 0\nwhile True:  # Data360 population, all pages (1,000 rows each)\n"
                 "    d = requests.get(\"https://data360api.worldbank.org/data360/data\", params={\"DATABASE_ID\": \"WB_WDI\", \"INDICATOR\": \"WB_WDI_SP_POP_TOTL\",\n"
                 f"        \"timePeriodFrom\": 2015, \"timePeriodTo\": {fy}, \"top\": 1000, \"skip\": skip}}, timeout=60).json()\n"
                 "    rows += d.get(\"value\") or []\n    if len(d.get(\"value\") or []) < 1000: break\n    skip += 1000\n"
                 "pop = pd.DataFrame(rows).assign(year=lambda x: x.TIME_PERIOD.astype(int), pop=lambda x: x.OBS_VALUE.astype(float))\n"
                 "def pop_for(iso3, year):  # same year as the need value, else the latest earlier year\n"
                 "    p = pop[(pop.REF_AREA == iso3) & ((pop.year <= year) if pd.notna(year) else True)]\n"
                 "    return p.sort_values(\"year\")[\"pop\"].iloc[-1] if len(p) else None\n"
                 "ctry = ctry.join(ctx.rename(columns={\"value\": \"need\", \"year\": \"need_year\"}))\n"
                 "ctry[\"people\"] = [pop_for(i, y) for i, y in zip(ctry.iso3, ctry.need_year)]\n"
                 f"ctry[\"people\"] = ctry.people * {share} / 100\n"
                 "print(int(ctry.people.notna().sum()), \"countries with a people-in-need value\")")] if need else []),
        _md("## Slide 1 · Where the portfolio stands"),
        _code("w = world[\"WBG\"]\nslide1 = pd.Series({\"achieved\": w.achieved, \"expected\": w.expected, \"still to deliver\": w.expected - w.achieved,\n"
              "                   \"delivery rate\": w.achieved / w.expected if rate_ok(w.achieved, w.expected) else None})\n"
              "inst = pd.DataFrame({o: world[o] for o in [\"WB\", \"IFC\", \"MIGA\"]}).T\n"
              "for o in [\"WBG\", \"WB\", \"IFC\", \"MIGA\"]:\n"
              "    a, e = SHOWN[\"world\"][o] or (None, None)\n"
              "    print(\"✓\" if same(world[o].achieved, a) and same(world[o].expected, e) else \"⚠ (updated since snapshot?)\", o, world[o].achieved, world[o].expected)\n"
              "display(slide1.to_frame(\"all countries\"), inst)"),
        _md("## Slide 2 · Where results remain to be delivered (regions)"),
        _code("regions[\"still_to_deliver\"] = regions.expected - regions.achieved\n"
              "regions[\"delivery_rate\"] = [a / e if rate_ok(a, e) else None for a, e in zip(regions.achieved, regions.expected)]\n"
              "regions[\"data_check\"] = regions.achieved > regions.expected\n"
              + ("regions[\"people_in_need\"] = ctry.groupby(\"region\").people.sum(min_count=1).reindex(REGIONS)\n" if need else "")
              + "regions = regions.sort_values(\"still_to_deliver\", ascending=False)\n"
              "for r, row in regions.iterrows():\n"
              "    a, e = SHOWN[\"regions\"].get(r, (None, None))\n"
              + ("    p = SHOWN[\"region_people\"].get(r)\n    ok_p = same(row.people_in_need, p, tol=max(1, 1e-6 * (p or 0)))\n" if need else "    ok_p = True\n")
              + "    print(\"✓\" if same(row.achieved, a) and same(row.expected, e) and ok_p else \"⚠ (updated since snapshot?)\", r)\n"
              "import plotly.graph_objects as go\nt = regions.iloc[::-1]\n"
              "labels = [\"above expected (data check)\" if c else f\"{r:.0%}\" for r, c in zip(t.delivery_rate.fillna(0), t.data_check)]\n"
              "fig = go.Figure([go.Bar(y=t.index, x=t.expected, orientation=\"h\", name=\"Expected\", marker_color=\"#cde7f9\"),\n"
              "                 go.Bar(y=t.index, x=t.achieved, orientation=\"h\", name=\"Achieved\", marker_color=\"#0071bc\", width=0.4,\n"
              "                        text=labels, textposition=\"outside\")])\n"
              "fig.update_layout(barmode=\"overlay\", template=\"simple_white\", height=420, title=\"Achieved vs expected by region\")\nfig.show()\nregions"),
        _md("## Slide 3 · Three-year priorities (one rule: most still to deliver)"),
        _code("clean = ctry[ctry.achieved.notna() & (ctry.expected > 0) & (ctry.achieved <= ctry.expected)].copy()  # data checks are not ranked\n"
              "clean[\"still_to_deliver\"] = clean.expected - clean.achieved\nclean[\"delivered_share\"] = clean.achieved / clean.expected\n"
              "ranked = clean[clean.still_to_deliver > 0].sort_values(\"still_to_deliver\", ascending=False)\n"
              "top3 = ranked.head(3)\nprint(\"✓\" if list(top3.iso3) == SHOWN[\"top3\"] else \"⚠ (updated since snapshot?)\", \"top 3:\", list(top3.iso3))\n"
              "g = ranked.still_to_deliver.values\ncut = (g[2] * g[3]) ** 0.5 if len(g) > 3 else g[-1] * 0.85  # line between the 3rd and 4th country\n"
              "sel = ranked.index.isin(top3.index)\n"
              "fig = go.Figure([go.Scatter(x=100 * ranked.delivered_share[~sel], y=ranked.still_to_deliver[~sel], mode=\"markers\", name=\"Other countries\",\n"
              "                            marker=dict(color=\"#c3c9cf\", size=7), text=ranked.iso3[~sel]),\n"
              "                 go.Scatter(x=100 * top3.delivered_share, y=top3.still_to_deliver, mode=\"markers+text\", name=\"Most still to deliver\",\n"
              "                            marker=dict(color=\"#eb6834\", size=13), text=top3.iso3, textposition=\"top center\")])\n"
              "fig.add_hline(y=cut, line_dash=\"dash\", annotation_text=\"Top 3 still to deliver ↑\")\n"
              "fig.update_layout(template=\"simple_white\", height=460, yaxis_type=\"log\", xaxis_title=\"Share of expected results delivered so far (%)\",\n"
              "                  yaxis_title=\"Results still to deliver\", title=\"Why these countries\")\nfig.show()\n"
              "print(\"not ranked (achieved above expected):\", list(ctry[ctry.achieved > ctry.expected].iso3))\ntop3"),
        _code("ranked.to_csv(f\"briefing_{INDICATOR}_FY{SNAPSHOT_FY}_countries.csv\")\nregions.to_csv(f\"briefing_{INDICATOR}_FY{SNAPSHOT_FY}_regions.csv\")\n"
              "print(\"saved\", len(ranked), \"countries and\", len(regions), \"regions\")"),
    ]
