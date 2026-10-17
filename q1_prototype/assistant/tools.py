"""Typed, read-only tools for the assistant.

Every number a tool returns is registered as a Proof-Carrying-Numbers claim and handed to the LLM as
``{"value": ..., "display": "41.5M", "claim": "c1a2b3c4"}``. Ratios, gaps and changes are computed here.
Arguments are validated with pydantic against allowlists (indicator codes, area codes) before any query runs.
"""
from __future__ import annotations

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


def _fy(v: int | None) -> int | None:
    """Snapshot fiscal year: accepts 2026 or the FY shorthand 26; anything else is rejected with the valid list."""
    if v is None:
        return None
    v = v + 2000 if 0 <= v < 100 else v
    valid = [s["fy"] for s in q.snapshots()]
    if v not in valid:
        raise ValueError(f"unknown snapshot {v}; valid snapshots are {valid}")
    return v


def _area(code: str) -> str:
    if code not in q.areas():
        raise ValueError(f"unknown area {code}")
    return code


class Ctx:
    """Per-request context: the claim registry and the snapshot."""

    def __init__(self, claims: Claims, fy: int | None = None):
        self.claims, self.fy = claims, fy or q.latest_fy()

    def num(self, value, unit, ind, area, field, fy=None):
        """Register a value as a claim that records entity, measure and period, not just the number."""
        period = f"FY{str(fy or self.fy)[2:]} snapshot"
        disp = fmt(value, "Percentage" if unit == "Percentage" else unit) if value is not None else None
        name = q.indicators().get(ind, {}).get("display_name", ind)
        cid = self.claims.add(value, unit=unit, source=f"WBG Scorecard API · {ind}", label=field, entity=q.area_name(area),
                              measure=f"{name}: {field}", period=period, display=disp)
        return {"value": value, "display": disp, "claim": cid}


# ------------------------------------------------------------------------------------------------ schemas
class ResultsArgs(BaseModel):
    ind_code: str
    areas: list[str] = Field(default_factory=lambda: ["ACW"], max_length=40)
    org: Literal["WBG", "WB", "IFC", "MIGA", "IBRD", "IDA"] = "WBG"
    sex: Literal["_T", "F"] = "_T"
    snapshot: int | None = None
    _v_fy = field_validator("snapshot")(lambda cls, v: _fy(v))
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
    _v_fy = field_validator("snapshot")(lambda cls, v: _fy(v))
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


class ProjectsArgs(BaseModel):
    ind_code: str
    area: str = "ACW"
    org: Literal["WB", "IBRD", "IDA"] = "WB"
    limit: int = Field(default=10, ge=1, le=25)
    snapshot: int | None = None
    _v_fy = field_validator("snapshot")(lambda cls, v: _fy(v))
    _v_ind = field_validator("ind_code")(lambda cls, v: _ind(v))
    _v_area = field_validator("area")(lambda cls, v: _area(v))


class DefArgs(BaseModel):
    ind_code: str
    _v_ind = field_validator("ind_code")(lambda cls, v: _ind(v))


class SqlArgs(BaseModel):
    sql: str = Field(max_length=2000)


# ------------------------------------------------------------------------------------------------ tools
def _row(ctx: Ctx, ind: str, unit: str, area: str, a, e, fy) -> dict:
    out = {"area": area, "area_name": q.area_name(area),
           "achieved": ctx.num(a, unit, ind, area, "achieved", fy), "expected": ctx.num(e, unit, ind, area, "expected", fy)}
    # a delivery rate / remaining gap is meaningful only when 0 <= achieved <= expected (same rule as the pipeline's
    # quality_flag); achieved above expected is reported as a data check instead of a rate above 100%
    if a is not None and e and e > 0 and 0 <= a <= e:
        out["delivery_pct"] = ctx.num(100 * a / e, "Percentage", ind, area, "achieved ÷ expected (computed)", fy)
        out["remaining_gap"] = ctx.num(e - a, unit, ind, area, "expected − achieved (computed)", fy)
    elif a is not None and e and e > 0 and a > e:
        out["data_check"] = "achieved above expected"
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


def get_projects(ctx: Ctx, args: ProjectsArgs) -> dict:
    """World Bank operations behind a result (the Scorecard's "World Bank Operations" table), largest first, with a
    check that the project rows add up to the published World Bank (or IBRD / IDA) total for the same area."""
    ind = q.indicators()[args.ind_code]
    if ind["type"] != "results":
        raise ToolError("not_results", "Projects exist only for WBG Results indicators.")
    fy, unit, col = args.snapshot or ctx.fy, ind["unit"], {"WB": "", "IBRD": "ibrd_", "IDA": "ida_"}[args.org]
    where, params = "", []
    if args.area in q.REGIONS:
        where, params = " AND region_code = ?", [args.area]
    elif args.area == "FCS":
        where = " AND area_code IN (SELECT area_code FROM areas WHERE fcs)"
    elif args.area != "ACW":
        where, params = " AND area_code = ?", [args.area]
    rows = q.rows(f"""SELECT proj_id, project_name, coalesce(area_code, cntry_code) area, {col}achieved a, {col}expected e, overlap_flag, url
                      FROM projects WHERE ind_code=? AND snapshot_fy=? AND sub_ind_code='' AND sex='_T' AND age='_T'{where}
                        AND ({col}expected <> 0 OR {col}achieved <> 0)
                      ORDER BY {col}achieved DESC NULLS LAST""", [args.ind_code, fy, *params])
    total = q.result(args.ind_code, args.area, args.org, fy)
    sa, se = sum(r["a"] or 0 for r in rows), sum(r["e"] or 0 for r in rows)
    summable = unit not in ("Percentage", "Countries/Economies")  # these totals are not sums of project values
    adds_up = None if not summable else bool(total and total["expected"] is not None and abs(se - total["expected"]) <= 0.005 * abs(total["expected"]) + 1
                   and abs(sa - (total["achieved"] or 0)) <= 0.005 * abs(total["achieved"] or 0) + 1)
    src = "WBG Scorecard API · getSCResultIndicatorSummary"
    out = []
    for r in rows[: args.limit]:
        ent = f"{r['project_name']} ({r['proj_id']})"
        def c(v, field, r=r, ent=ent):
            disp = fmt(v, unit) if v is not None else None
            return {"value": v, "display": disp, "claim": ctx.claims.add(v, unit=unit, source=f"{src} · {r['proj_id']}", label=field, entity=ent,
                                                                          measure=f"{ind['display_name']}: {field}", period=f"FY{str(fy)[2:]} snapshot", display=disp)}
        out.append({"project": ent, "country": q.area_name(r["area"]), "url": r["url"], "overlap_flag": r["overlap_flag"],
                    "achieved": c(r["a"], "achieved"), "expected": c(r["e"], "expected")})
    return {"indicator": ind["display_name"], "ind_code": args.ind_code, "area": q.area_name(args.area), "org": args.org,
            "snapshot": f"FY{str(fy)[2:]}", "projects": len({r["proj_id"] for r in rows}), "countries": len({r["area"] for r in rows}),
            "rows": out, "sum_of_projects": {"achieved": ctx.num(sa, unit, args.ind_code, args.area, f"sum of {args.org} project rows (achieved)", fy),
                                             "expected": ctx.num(se, unit, args.ind_code, args.area, f"sum of {args.org} project rows (expected)", fy)},
            "published_total": {"achieved": ctx.num(total["achieved"], unit, args.ind_code, args.area, f"{args.org} achieved", fy),
                                "expected": ctx.num(total["expected"], unit, args.ind_code, args.area, f"{args.org} expected", fy)} if total else None,
            "projects_add_up_to_total": adds_up}


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
        src = f"WBG Scorecard client context · {args.ind_code}"

        def val(y):
            d = f"{s[y]:.1f}%" if ind["unit"] == "Percentage" else f"{s[y]:,.1f}"
            return {"value": s[y], "display": d,
                    "claim": ctx.claims.add(s[y], unit=ind["unit"], source=src, label=ind["display_name"], entity=q.area_name(area),
                                            measure=ind["display_name"], period=str(y), display=d)}
        rows.append({"area": area, "area_name": q.area_name(area), "latest_year": last, "latest": val(last),
                     "first_year": first, "first": val(first)})
    return {"indicator": ind["display_name"], "ind_code": args.ind_code, "unit": ind["unit"],
            "direction": ind["direction"] or "unknown", "rows": rows}


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
    terms = [t for t in "".join(ch if ch.isalnum() else " " for ch in args.query.lower()).split() if len(t) > 2]
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
SQL_VIEWS = {"v_results", "v_results_female", "v_context", "v_context_latest", "v_population", "v_projects", "areas", "indicators", "outcomes"}


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
        rec = dict(zip(cols, r))
        entity = rec.get("area_name") or rec.get("area_code") or rec.get("indicator") or rec.get("ind_code")
        for c, v in zip(cols, r):
            if isinstance(v, float):
                cid = ctx.claims.add(v, unit=None, source="run_sql (read-only query shown in 'How I got this')", label=c,
                                     entity=str(entity) if entity else None, measure=c, display=f"{v:,.4g}")
                row[c] = {"value": v, "display": f"{v:,.4g}", "claim": cid}
            else:
                row[c] = v if isinstance(v, (int, str, bool, type(None))) else str(v)
        out.append(row)
    return {"sql": tree.sql(dialect="duckdb"), "rows": out}


TOOLS = {
    "get_results": (ResultsArgs, get_results, "Achieved, expected, delivery % and remaining gap for one WBG Results indicator in given areas (region codes ACW AFE AFW EAP ECA LCR MENAAP SAR, FCS, or ISO3 country codes). org IBRD/IDA (World Bank financing institutions) is reported for ACW and regions only."),
    "rank_areas": (RankArgs, rank_areas, "Rank regions or countries (optionally within a region or FCS) for one results indicator by delivery_ratio, remaining_gap, achieved or expected. Excludes tiny portfolios and achieved>expected data anomalies."),
    "compare_snapshots": (SnapArgs, compare_snapshots, "Achieved/expected for one indicator and area across the FY24-FY26 snapshots, with change."),
    "get_context": (ContextArgs, get_context, "Client-context or vision indicator: first and latest values for given areas."),
    "outcome_overview": (OverviewArgs, outcome_overview, "All results indicators (optionally for one outcome area) with achieved/expected/delivery % for an area."),
    "search_indicators": (SearchArgs, search_indicators, "Find indicator codes by keywords."),
    "get_definition": (DefArgs, get_definition, "Definition and notes for an indicator."),
    "get_projects": (ProjectsArgs, get_projects, "The World Bank operations (projects) behind a results number for an area (ACW, a region, FCS or an ISO3 country): largest first with links, the Results Overlap Flag, and whether the project rows add up to the published WB / IBRD / IDA total. Use when asked which projects deliver a result or to verify a number."),
    "run_sql": (SqlArgs, run_sql, "Last resort: one read-only DuckDB SELECT over views v_results(snapshot_fy, ind_code, indicator, unit, outcome_id, org, area_code, area_type, area_name, region_code, achieved, expected, remaining_gap, delivery_ratio; org is WBG, WB, IFC, MIGA, or IBRD/IDA for ACW and regions), v_results_female, v_projects(snapshot_fy, ind_code, proj_id, project_name, area_code, region_code, approval_fy, closing_fy, achieved, expected, ibrd_achieved, ibrd_expected, ida_achieved, ida_expected, overlap, disability_inclusive, url: World Bank operations, one row per project and country), v_context(snapshot_fy, ind_code, indicator, unit, type, outcome_id, higher_is_better, area_code, area_name, year, value), v_context_latest, v_population(area_code, year, population), areas, indicators, outcomes. Prefer the typed tools."),
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
