"""Typed, read-only tools for the assistant.

Every number a tool returns is registered as a Proof-Carrying-Numbers claim and handed to the LLM as
``{"value": ..., "display": "41.5M", "claim": "c1a2b3c4"}``. Ratios, gaps and changes are computed here.
Arguments are validated with pydantic against allowlists (indicator codes, area codes) before any query runs.
"""
from __future__ import annotations

import re
from typing import Literal

import sqlglot
from pydantic import BaseModel, Field, ValidationError, field_validator

from explorer import queries as q
from explorer.formatting import fmt

from .pcn import Claims

MIN_SHARE = 0.002  # ignore countries whose expected results are < 0.2% of the world total in rankings


class ToolError(Exception):
    def __init__(self, error: str, message: str, hint: str = ""):
        super().__init__(message)
        self.payload = {"error": error, "message": message, "hint": hint}


def _ind(code: str) -> str:
    if code not in q.indicators():
        raise ValueError(f"unknown indicator {code}")
    return code


def _area(code: str) -> str:
    if code not in q.areas():
        raise ValueError(f"unknown area {code}")
    return code


class Ctx:
    """Per-request context: the claim registry and the snapshot."""

    def __init__(self, claims: Claims, fy: int | None = None):
        self.claims, self.fy = claims, fy or q.latest_fy()

    def num(self, value, unit, ind, area, field, fy=None):
        src = f"WBG Scorecard API · {ind} · {q.area_name(area)} · {field} · FY{str(fy or self.fy)[2:]} snapshot"
        cid = self.claims.add(value, unit=unit, source=src, label=field)
        disp = fmt(value, "Percentage" if unit == "Percentage" else unit) if value is not None else None
        return {"value": value, "display": disp, "claim": cid}


# ------------------------------------------------------------------------------------------------ schemas
class ResultsArgs(BaseModel):
    ind_code: str
    areas: list[str] = Field(default_factory=lambda: ["ACW"], max_length=40)
    org: Literal["WBG", "WB", "IFC", "MIGA"] = "WBG"
    sex: Literal["_T", "F"] = "_T"
    snapshot: int | None = None
    _v_ind = field_validator("ind_code")(lambda cls, v: _ind(v))
    _v_areas = field_validator("areas")(lambda cls, v: [_area(a) for a in v])


class RankArgs(BaseModel):
    ind_code: str
    level: Literal["REGION", "COUNTRY"] = "REGION"
    within: str | None = None  # region code or FCS (countries only)
    metric: Literal["delivery_ratio", "remaining_gap", "achieved", "expected"] = "delivery_ratio"
    order: Literal["asc", "desc"] = "asc"
    top_n: int = Field(5, ge=1, le=15)
    sex: Literal["_T", "F"] = "_T"
    snapshot: int | None = None
    _v_ind = field_validator("ind_code")(lambda cls, v: _ind(v))


class SnapArgs(BaseModel):
    ind_code: str
    area: str = "ACW"
    _v_ind = field_validator("ind_code")(lambda cls, v: _ind(v))
    _v_area = field_validator("area")(lambda cls, v: _area(v))


class ContextArgs(BaseModel):
    ind_code: str
    areas: list[str] = Field(default_factory=lambda: ["ACW"], max_length=40)
    _v_ind = field_validator("ind_code")(lambda cls, v: _ind(v))
    _v_areas = field_validator("areas")(lambda cls, v: [_area(a) for a in v])


class OverviewArgs(BaseModel):
    outcome_id: int | None = None
    area: str = "ACW"
    _v_area = field_validator("area")(lambda cls, v: _area(v))


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=80)


class DefArgs(BaseModel):
    ind_code: str
    _v_ind = field_validator("ind_code")(lambda cls, v: _ind(v))


class SqlArgs(BaseModel):
    sql: str = Field(max_length=2000)


# ------------------------------------------------------------------------------------------------ tools
def _row(ctx: Ctx, ind: str, unit: str, area: str, a, e, fy) -> dict:
    out = {"area": area, "area_name": q.area_name(area),
           "achieved": ctx.num(a, unit, ind, area, "achieved", fy), "expected": ctx.num(e, unit, ind, area, "expected", fy)}
    if a is not None and e:
        out["delivery_pct"] = ctx.num(100 * a / e, "Percentage", ind, area, "achieved ÷ expected (computed)", fy)
        out["remaining_gap"] = ctx.num(e - a, unit, ind, area, "expected − achieved (computed)", fy)
    return out


def get_results(ctx: Ctx, args: ResultsArgs) -> dict:
    ind = q.indicators()[args.ind_code]
    fy = args.snapshot or ctx.fy
    rows = []
    for area in args.areas:
        r = q.result(args.ind_code, area, args.org, fy, args.sex)
        if r is None or (r["achieved"] is None and r["expected"] is None):
            rows.append({"area": area, "area_name": q.area_name(area), "no_data": True})
            continue
        rows.append(_row(ctx, args.ind_code, ind["unit"], area, r["achieved"], r["expected"], fy))
    return {"indicator": ind["display_name"], "ind_code": args.ind_code, "unit": ind["unit"], "org": args.org,
            "sex": "female" if args.sex == "F" else "total", "snapshot": f"FY{str(fy)[2:]}", "rows": rows}


def rank_areas(ctx: Ctx, args: RankArgs) -> dict:
    ind = q.indicators()[args.ind_code]
    fy = args.snapshot or ctx.fy
    table = q.results_table([args.ind_code], fy, args.sex)
    world = (table.get("ACW", {}).get(args.ind_code) or [None, None])[1] or 0
    areas = q.areas()
    cand = []
    for code, vals in table.items():
        a, e = vals.get(args.ind_code, [None, None])
        if a is None or not e or e <= 0:
            continue
        info = areas.get(code, {})
        if args.level == "REGION":
            if code not in q.REGIONS:
                continue
        else:
            if info.get("area_type") != "COUNTRY" or e < MIN_SHARE * world:
                continue
            if args.within == "FCS" and not info.get("fcs"):
                continue
            if args.within and args.within not in ("FCS", "ACW") and info.get("region_code") != args.within:
                continue
        ratio = a / e
        if args.metric == "delivery_ratio" and ratio > 1.05:
            continue  # achieved > expected: data check, not a ranking candidate
        cand.append((code, a, e, {"delivery_ratio": ratio, "remaining_gap": e - a, "achieved": a, "expected": e}[args.metric]))
    cand.sort(key=lambda x: x[3], reverse=args.order == "desc")
    excluded = sum(1 for code, vals in table.items() if (vals.get(args.ind_code) or [0, 0])[1]
                   and (vals[args.ind_code][0] or 0) > 1.05 * vals[args.ind_code][1]) if args.metric == "delivery_ratio" else 0
    return {"indicator": ind["display_name"], "ind_code": args.ind_code, "unit": ind["unit"], "level": args.level,
            "within": q.area_name(args.within) if args.within else "all", "metric": args.metric, "order": args.order,
            "snapshot": f"FY{str(fy)[2:]}", "excluded_achieved_above_expected": excluded,
            "rows": [{"rank": i + 1, **_row(ctx, args.ind_code, ind["unit"], c, a, e, fy)} for i, (c, a, e, _) in enumerate(cand[:args.top_n])]}


def compare_snapshots(ctx: Ctx, args: SnapArgs) -> dict:
    ind = q.indicators()[args.ind_code]
    rows, prev = [], None
    for s in q.snapshots():
        r = q.result(args.ind_code, args.area, "WBG", s["fy"])
        if not r:
            continue
        row = {"snapshot": f"FY{str(s['fy'])[2:]}", "date": s["date"],
               "achieved": ctx.num(r["achieved"], ind["unit"], args.ind_code, args.area, "achieved", s["fy"]),
               "expected": ctx.num(r["expected"], ind["unit"], args.ind_code, args.area, "expected", s["fy"])}
        if prev and prev[0] is not None and r["achieved"] is not None:
            row["achieved_change"] = ctx.num(r["achieved"] - prev[0], ind["unit"], args.ind_code, args.area,
                                             f"change in achieved since FY{str(prev[1])[2:]} (computed)", s["fy"])
        rows.append(row)
        prev = (r["achieved"], s["fy"])
    return {"indicator": ind["display_name"], "area": q.area_name(args.area), "rows": rows}


def get_context(ctx: Ctx, args: ContextArgs) -> dict:
    ind = q.indicators()[args.ind_code]
    series = q.context_series([args.ind_code])
    rows = []
    for area in args.areas:
        s = series.get(area, {}).get(args.ind_code)
        if not s:
            rows.append({"area": area, "area_name": q.area_name(area), "no_data": True})
            continue
        years = sorted(s)
        first, last = years[0], years[-1]
        src = f"WBG Scorecard client context · {args.ind_code} · {q.area_name(area)}"
        rows.append({"area": area, "area_name": q.area_name(area), "latest_year": last,
                     "latest": {"value": s[last], "display": f"{s[last]:.1f}",
                                "claim": ctx.claims.add(s[last], unit=ind["unit"], source=f"{src} · {last}", label=ind["display_name"])},
                     "first_year": first,
                     "first": {"value": s[first], "display": f"{s[first]:.1f}",
                               "claim": ctx.claims.add(s[first], unit=ind["unit"], source=f"{src} · {first}", label=ind["display_name"])}})
    return {"indicator": ind["display_name"], "ind_code": args.ind_code, "unit": ind["unit"],
            "higher_is_better": ind["higher_is_better"], "rows": rows}


def outcome_overview(ctx: Ctx, args: OverviewArgs) -> dict:
    out = []
    for o in q.outcomes():
        if args.outcome_id and o["outcome_id"] != args.outcome_id:
            continue
        for i in q.outcome_indicators(o["outcome_id"])["results"]:
            r = q.result(i["ind_code"], args.area, "WBG", ctx.fy)
            if not r or r["expected"] is None:
                continue
            row = {"outcome": o["name"], "outcome_id": o["outcome_id"], "ind_code": i["ind_code"],
                   "indicator": i["display_name"], "unit": i["unit"],
                   **{k: v for k, v in _row(ctx, i["ind_code"], i["unit"], args.area, r["achieved"], r["expected"], ctx.fy).items()
                      if k not in ("area", "area_name")}}
            out.append(row)
    return {"area": q.area_name(args.area), "snapshot": f"FY{str(ctx.fy)[2:]}", "indicators": out}


def search_indicators(ctx: Ctx, args: SearchArgs) -> dict:
    terms = [t for t in re.split(r"\W+", args.query.lower()) if len(t) > 2]
    hits = []
    for i in q.indicators().values():
        text = f"{i['name']} {i['display_name']} {i['definition'] or ''}".lower()
        score = sum(t in text for t in terms)
        if score:
            hits.append((score, i))
    hits.sort(key=lambda x: -x[0])
    return {"indicators": [{"ind_code": i["ind_code"], "name": i["display_name"], "type": i["type"], "unit": i["unit"],
                            "outcome_id": i["outcome_id"]} for _, i in hits[:8]]}


def get_definition(ctx: Ctx, args: DefArgs) -> dict:
    i = q.indicators()[args.ind_code]
    return {"ind_code": i["ind_code"], "name": i["display_name"], "type": i["type"], "unit": i["unit"],
            "definition": i["definition"], "note": i["note"],
            "achieved_vs_expected": "Achieved = results delivered so far by WBG-financed operations; expected = results the "
                                    "active portfolio is expected to deliver by completion (not a corporate target)."}


# ------------------------------------------------------------------------------------------------ guarded SQL
SQL_VIEWS = {"v_results", "v_results_female", "v_context", "v_context_latest", "v_population", "areas", "indicators", "outcomes"}


def run_sql(ctx: Ctx, args: SqlArgs) -> dict:
    """Read-only SQL over curated views: one SELECT, no DDL/DML/table functions, row-limited."""
    try:
        parsed = sqlglot.parse(args.sql, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        raise ToolError("sql_parse", str(exc)[:200], "Write one DuckDB SELECT over the allowed views.")
    if len(parsed) != 1 or not isinstance(parsed[0], (sqlglot.exp.Select, sqlglot.exp.Union)):
        raise ToolError("sql_not_select", "Only a single SELECT statement is allowed.")
    tree = parsed[0]
    ctes = {c.alias_or_name for c in tree.find_all(sqlglot.exp.CTE)}
    tables = {t.name for t in tree.find_all(sqlglot.exp.Table)} - ctes
    bad = tables - SQL_VIEWS
    if bad or any(True for _ in tree.find_all(sqlglot.exp.Anonymous) if _.name.lower().startswith(("read_", "glob"))):
        raise ToolError("sql_forbidden", f"Not allowed: {sorted(bad) or 'table functions'}",
                        f"Allowed views: {sorted(SQL_VIEWS)}")
    if not tree.args.get("limit"):
        tree = tree.limit(200)
    try:
        cur = q.con().execute(tree.sql(dialect="duckdb"))
    except Exception as exc:  # duckdb errors are returned to the model as hints
        raise ToolError("sql_error", str(exc)[:300], "Check column names with the views listed in the system prompt.")
    cols = [d[0] for d in cur.description]
    out = []
    for r in cur.fetchmany(200):
        row = {}
        for c, v in zip(cols, r):
            if isinstance(v, float):
                cid = ctx.claims.add(v, unit=None, source=f"run_sql · column {c}", label=c)
                row[c] = {"value": v, "display": f"{v:,.4g}", "claim": cid}
            else:
                row[c] = v if isinstance(v, (int, str, bool, type(None))) else str(v)
        out.append(row)
    return {"sql": tree.sql(dialect="duckdb"), "rows": out}


TOOLS = {
    "get_results": (ResultsArgs, get_results, "Achieved, expected, delivery % and remaining gap for one WBG Results indicator in given areas (region codes ACW AFE AFW EAP ECA LCR MENAAP SAR, FCS, or ISO3 country codes)."),
    "rank_areas": (RankArgs, rank_areas, "Rank regions or countries (optionally within a region or FCS) for one results indicator by delivery_ratio, remaining_gap, achieved or expected. Excludes tiny portfolios and achieved>expected data anomalies."),
    "compare_snapshots": (SnapArgs, compare_snapshots, "Achieved/expected for one indicator and area across the FY24-FY26 snapshots, with change."),
    "get_context": (ContextArgs, get_context, "Client-context or vision indicator: first and latest values for given areas."),
    "outcome_overview": (OverviewArgs, outcome_overview, "All results indicators (optionally for one outcome area) with achieved/expected/delivery % for an area."),
    "search_indicators": (SearchArgs, search_indicators, "Find indicator codes by keywords."),
    "get_definition": (DefArgs, get_definition, "Definition and notes for an indicator."),
    "run_sql": (SqlArgs, run_sql, "Last resort: one read-only DuckDB SELECT over views v_results(snapshot_fy, ind_code, indicator, unit, outcome_id, org, area_code, area_type, area_name, region_code, achieved, expected, remaining_gap, delivery_ratio), v_results_female, v_context(snapshot_fy, ind_code, indicator, unit, type, outcome_id, higher_is_better, area_code, area_name, year, value), v_context_latest, v_population(area_code, year, population), areas, indicators, outcomes. Prefer the typed tools."),
}


def schemas() -> list[dict]:
    """OpenAI-style function schemas (LiteLLM translates them for each provider)."""
    out = []
    for name, (model, _, desc) in TOOLS.items():
        js = model.model_json_schema()
        js.pop("title", None)
        out.append({"type": "function", "function": {"name": name, "description": desc, "parameters": js}})
    return out


def call(ctx: Ctx, name: str, arguments: dict) -> dict:
    if name not in TOOLS:
        return {"error": "unknown_tool", "message": f"No tool {name}", "hint": f"Use one of {list(TOOLS)}"}
    model, fn, _ = TOOLS[name]
    try:
        return fn(ctx, model.model_validate(arguments or {}))
    except ValidationError as exc:
        return {"error": "invalid_arguments", "message": exc.errors()[0]["msg"][:200],
                "hint": "Valid areas: ACW, AFE, AFW, EAP, ECA, LCR, MENAAP, SAR, FCS or ISO3 country codes; use search_indicators for codes."}
    except ToolError as exc:
        return exc.payload
