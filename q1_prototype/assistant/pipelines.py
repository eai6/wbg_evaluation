"""Router + pipelines. ``handle`` is a generator of UI events streamed to the browser (SSE).

Events: status · filters · navigate · message · artifact · done · error
Each pipeline is a fixed path (predictable, testable). Without an LLM the app degrades gracefully: the deterministic
resolver routes, and answers are templated from the same verified tool results.
"""
from __future__ import annotations

import json
import logging
import re
import time

from django.conf import settings

from explorer import queries as q
from explorer.formatting import fmt

from . import analysis, artifacts, llm, pcn, prompts, resolver, tools

log = logging.getLogger(__name__)
INJECTION = re.compile(r"ignore (all |any )?(previous|prior|above) instructions|you are now|system prompt|reveal your|developer mode", re.I)


# ------------------------------------------------------------------------------------------------ routing
def route(message: str, state: dict, history: list, usage: list) -> dict:
    ents = resolver.resolve(message)
    if llm.available():
        ctx = f"page outcome: {state.get('outcome_name')}; current filters: {state.get('filters')}"
        recent = "\n".join(f"{h['role']}: {h['content'][:200]}" for h in history[-4:])
        try:
            out = llm.complete_json([
                {"role": "system", "content": prompts.ROUTER},
                {"role": "user", "content": f"Context: {ctx}\nRecent conversation:\n{recent}\n\nMessage: {message}"}],
                fast=True, max_tokens=250, usage=usage)
            intent = out.get("intent")
            if intent in {"filter", "analyze", "explain", "research", "summary", "deck", "notebook", "navigate", "clarify", "out_of_scope"}:
                phr = out.get("phrases") or {}
                extra = resolver.resolve(" ".join([*(phr.get("areas") or []), phr.get("topic") or "", phr.get("sex") or "",
                                                   phr.get("institution") or "", phr.get("year") or ""]))
                for k, v in extra.items():  # phrases resolved deterministically; message-level matches take precedence
                    if v and not ents.get(k):
                        ents[k] = v
                return {"intent": intent, "also_filter": bool(out.get("also_filter")), "entities": ents, "by": "llm",
                        "reason": out.get("reason", "")}
        except llm.LLMUnavailable as exc:
            log.warning("router fallback: %s", exc)
    intent = resolver.heuristic_intent(message)
    if intent == "analyze" and re.search(r"chart|figure|plot|graph", message, re.I):
        intent = "analyze"
    return {"intent": intent, "also_filter": False, "entities": ents, "by": "rules"}


# ------------------------------------------------------------------------------------------------ helpers
def _ev(type_, **kw):
    return {"type": type_, **kw}


def _filters_from(ents: dict) -> dict:
    f = {}
    if ents.get("areas"):
        f["area"] = ents["areas"][0]
    if ents.get("sex"):
        f["sex"] = ents["sex"]
    if ents.get("org"):
        f["org"] = ents["org"]
    if ents.get("fy"):
        f["fy"] = ents["fy"]
    return f


def _describe(f: dict) -> str:
    parts = []
    if "area" in f:
        parts.append(q.area_name(f["area"]))
    if f.get("sex") == "F":
        parts.append("female beneficiaries")
    if f.get("org"):
        parts.append({"WBG": "World Bank Group", "WB": "World Bank"}.get(f["org"], f["org"]))
    if f.get("fy"):
        parts.append(f"FY{str(f['fy'])[2:]} snapshot")
    return ", ".join(parts)


def write(question: str, context: str, results: dict, claims: pcn.Claims, usage: list, system: str | None = None) -> tuple[str, dict]:
    """Writer step: LLM drafts from raw tool results; PCN verifies; one repair turn if any claim fails."""
    sys_prompt = (system or prompts.WRITER).format(question=question, context=context, outcome=context)
    msgs = [{"role": "system", "content": sys_prompt + "\n\nRAW TOOL RESULTS (JSON):\n" + json.dumps(results, default=str)[:24000]},
            {"role": "user", "content": question}]
    text = llm.complete(msgs, temperature=0.2, max_tokens=900, usage=usage).content or ""
    html_, stats = pcn.render(text, claims)
    if stats["failed"] or len(stats["untagged"]) > 2:
        fix = (f"Some numbers could not be verified: {[f['shown'] for f in stats['failed']]}; untagged: {stats['untagged'][:6]}. "
               "Rewrite the answer using only claim-tagged numbers from the tool results (exact claim ids and display values).")
        text = llm.complete(msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": fix}],
                            temperature=0, max_tokens=900, usage=usage).content or text
        html_, stats = pcn.render(text, claims)
        stats["repaired"] = True
    return html_, stats


def _cite(x: dict | None) -> str:
    return f'<claim id="{x["claim"]}">{x["display"]}</claim>' if x and x.get("claim") else "—"


# ------------------------------------------------------------------------------------------------ main entry
def handle(message: str, state: dict, conv: dict):
    t0 = time.time()
    usage: list = []
    claims = pcn.Claims(conv.setdefault("claims", {}))
    history = conv.setdefault("history", [])
    message = message.strip()[: settings.ASSISTANT["max_message_chars"]]
    if not message:
        return
    if INJECTION.search(message):
        yield _ev("message", html="I can only help with questions about World Bank Group Scorecard results.")
        yield _ev("done", ms=int((time.time() - t0) * 1000), usage=usage)
        return
    outcome_id = state.get("outcome_id")
    o = q.outcome(outcome_id) if outcome_id else None
    state["outcome_name"] = o["name"] if o else None
    filters = state.get("filters") or {}
    fy = int(filters.get("fy") or q.latest_fy())
    ind_code = state.get("ind_code") or (analysis.primary_indicator(outcome_id) or {}).get("ind_code") if outcome_id else None

    yield _ev("status", text="Understanding the question…")
    r = route(message, state, history, usage)
    intent, ents = r["intent"], r["entities"]
    if conv.get("research_q") and ents.get("topic") and ents["topic"] != outcome_id and intent in ("navigate", "filter", "clarify"):
        intent = "research"  # typing an area after a research answer re-runs the research for that area
    yield _ev("status", text=f"Router → {intent}", route=r)
    history.append({"role": "user", "content": message})
    answer_text = ""

    try:
        if intent == "navigate" or (ents.get("topic") and ents["topic"] != outcome_id and intent in ("filter", "analyze", "explain")):
            target = q.outcome(ents["topic"]) if ents.get("topic") else None
            if target:
                yield _ev("navigate", url=f"/outcomes/{target['slug']}/?q={message}")
                answer_text = f"Opening {target['name']}."
                yield _ev("message", html=answer_text)
                return

        if intent == "filter" or (r.get("also_filter") and _filters_from(ents)):
            f = _filters_from(ents)
            if f:
                yield _ev("filters", filters=f)
                if intent == "filter":
                    answer_text = f"Overview filtered: {_describe(f)}."
                    yield _ev("message", html=answer_text, kind="sys")
                    return
                filters = {**filters, **f}
                fy = int(filters.get("fy") or fy)

        if intent == "research" or (intent in ("deck",) and outcome_id):
            yield from _research(message, ents, outcome_id, conv, claims, usage, deck_only=intent == "deck")
            answer_text = "[research answer]"
            return

        if intent == "notebook":
            art = (conv.get("artifacts") or {}).get(state.get("active_artifact") or "")
            if not art:
                tab = q.REGIONS if filters.get("area", "ACW") == "ACW" else [filters["area"]]
                ctx = tools.Ctx(claims, fy)
                res = tools.get_results(ctx, tools.ResultsArgs(ind_code=ind_code, areas=["ACW", *tab] if tab == q.REGIONS else tab,
                                                                sex=filters.get("sex", "_T"), snapshot=fy))
                art = artifacts.results_figure(ind_code, res["rows"], title="Overview data", sex=filters.get("sex", "_T"), fy=fy)
            nb = {"id": artifacts.new_id(), "type": "notebook", "title": f"Notebook · {art['title']}", "source_id": art["id"],
                  "data_ref": art.get("data_ref"), "cells": artifacts.notebook(art)["cells"]}
            conv.setdefault("artifacts", {})[nb["id"]] = nb
            yield _ev("artifact", artifact={**nb, "download_url": f"/api/artifacts/{nb['id']}.ipynb"})
            answer_text = "This notebook re-downloads the same data from the public Scorecard API, cleans it, re-checks the ✓ values, reproduces the figure and saves a CSV."
            yield _ev("message", html=answer_text)
            return

        if intent == "explain":
            ctx = tools.Ctx(claims, fy)
            d = tools.get_definition(ctx, tools.DefArgs(ind_code=ind_code))
            if llm.available():
                yield _ev("status", text="Looking up the indicator definition…")
                html_, stats = write(message, f"{o['name'] if o else ''}", {"get_definition": d}, claims, usage)
            else:
                html_, stats = pcn.render(f"**{d['name']}**: {d['definition'] or ''}\n\n{d['achieved_vs_expected']}", claims)
            answer_text = html_
            yield _ev("message", html=html_, stats=stats, how=f"Source: Scorecard indicator metadata · {ind_code}")
            return

        if intent == "summary":
            yield _ev("status", text="Reading the current view…")
            facts = analysis.view_summary(outcome_id, ind_code, filters.get("area", "ACW"), filters.get("org", "WBG"),
                                          filters.get("sex", "_T"), fy, claims)
            if llm.available():
                html_, stats = write("Summarize what this view shows in 3 bullet points.", o["name"], facts, claims, usage)
            else:
                html_, stats = pcn.render(_template_summary(facts), claims)
            answer_text = html_
            yield _ev("message", html="<div><b>What this view shows</b></div>" + html_, stats=stats,
                      followups=["Which regions lag most?", "Make a 3-slide briefing"])
            return

        if intent in ("analyze",) and outcome_id:
            yield from _analyze(message, ents, filters, fy, ind_code, o, conv, claims, usage)
            answer_text = "[analysis]"
            return

        if intent == "clarify":
            answer_text = "Could you say which area, country or indicator you mean? For example: “energy access in Nigeria” or “compare regions”."
            yield _ev("message", html=answer_text)
            return

        answer_text = "I can answer questions about World Bank Group Scorecard results: filters, comparisons, rankings, definitions, briefings and data exports."
        yield _ev("message", html=answer_text, followups=["Which countries are furthest behind?", "Summarize this view"])
    except llm.LLMUnavailable as exc:
        yield _ev("error", text=f"The language model is unavailable ({exc}). Filters and data views still work.")
    except Exception:  # never leak internals to the user
        log.exception("assistant failure")
        yield _ev("error", text="Something went wrong while answering. Please try again or rephrase.")
    finally:
        if answer_text:
            history.append({"role": "assistant", "content": re.sub(r"<[^>]+>", "", answer_text)[:600]})
        del history[:-2 * settings.ASSISTANT["history_turns"]]
        yield _ev("done", ms=int((time.time() - t0) * 1000), usage=usage)


# ------------------------------------------------------------------------------------------------ analyze
def _analyze(message, ents, filters, fy, ind_code, o, conv, claims, usage):
    ctx = tools.Ctx(claims, fy)
    collected: dict = {}
    figure_src = None
    if llm.available():
        inds = ", ".join(f"{i['ind_code']} ({i['display_name']})" for i in q.outcome_indicators(o["outcome_id"])["results"])
        context = (f"outcome area: {o['name']}; selected indicator {ind_code}; filters: {filters or 'none'}; "
                   f"snapshot FY{str(fy)[2:]}; resolved entities: {ents}")
        msgs = [{"role": "system", "content": prompts.RESEARCHER.format(context=context, indicators=inds,
                                                                        max_calls=settings.ASSISTANT["max_tool_calls"])},
                {"role": "user", "content": message}]
        calls = 0
        while calls < settings.ASSISTANT["max_tool_calls"]:
            m = llm.complete(msgs, tools=tools.schemas(), max_tokens=600, usage=usage)
            tcs = getattr(m, "tool_calls", None) or []
            if not tcs:
                break
            msgs.append({"role": "assistant", "content": m.content or "",
                         "tool_calls": [{"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}} for t in tcs]})
            for t in tcs:
                calls += 1
                try:
                    args = json.loads(t.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield _ev("status", text=f"{t.function.name}({', '.join(f'{k}={v}' for k, v in args.items())[:120]})")
                res = tools.call(ctx, t.function.name, args)
                collected[f"{t.function.name}#{calls}"] = res
                if t.function.name in ("get_results", "rank_areas") and len(res.get("rows") or []) >= 2:
                    figure_src = (t.function.name, res)
                msgs.append({"role": "tool", "tool_call_id": t.id, "content": json.dumps(res, default=str)[:12000]})
        if not collected:  # model answered without data: force the deterministic path below
            llm_ok = False
        else:
            llm_ok = True
    else:
        llm_ok = False
    if not llm_ok:
        collected, figure_src = _deterministic_analysis(message, ents, filters, fy, ind_code, ctx)
    yield _ev("status", text="Writing the answer from the results…")
    if llm.available():
        html_, stats = write(message, f"{o['name']}; filters {filters}; FY{str(fy)[2:]}", collected, claims, usage)
    else:
        html_, stats = pcn.render(_template_analysis(collected), claims)
    yield _ev("message", html=html_, stats=stats, how="Tools: " + ", ".join(k.split("#")[0] for k in collected) + f" · Scorecard FY{str(fy)[2:]} snapshot · ratios computed in code",
              followups=_followups(collected))
    if figure_src:
        name, res = figure_src
        what = {"delivery_ratio": "delivery rate", "remaining_gap": "remaining gap"}.get(res.get("metric"), res.get("metric", ""))
        lvl = "Regions" if res.get("level") == "REGION" else "Countries"
        title = (f"{lvl} by {what}" + (f" · {res['within']}" if res.get("within") not in (None, "all") else "")
                 if name == "rank_areas" else f"Achieved vs expected · {', '.join(r['area_name'].split(' ')[0] for r in res['rows'][:4])}")
        art = artifacts.results_figure(res["ind_code"], res["rows"], title=title, sex=filters.get("sex", "_T"), fy=fy)
        conv.setdefault("artifacts", {})[art["id"]] = art
        yield _ev("artifact", artifact=art)


def _deterministic_analysis(message, ents, filters, fy, ind_code, ctx):
    t = message.lower()
    sex = ents.get("sex") or filters.get("sex", "_T")
    regions = [a for a in ents.get("areas", []) if a in q.REGIONS or a == "FCS"]
    if re.search(r"countr|econom", t) or (re.search(r"lag|struggl|behind|worst|lowest", t) and regions):
        res = tools.rank_areas(ctx, tools.RankArgs(ind_code=ind_code, level="COUNTRY", within=regions[0] if regions else None,
                                                   metric="delivery_ratio", order="asc", top_n=5, sex=sex, snapshot=fy))
        return {"rank_areas#1": res}, ("rank_areas", res)
    if re.search(r"lag|struggl|behind|worst|lowest|rank|best|top|highest", t) and not ents.get("areas"):
        order = "desc" if re.search(r"best|top|highest|leading", t) else "asc"
        res = tools.rank_areas(ctx, tools.RankArgs(ind_code=ind_code, level="REGION", metric="delivery_ratio", order=order, top_n=7, sex=sex, snapshot=fy))
        return {"rank_areas#1": res}, ("rank_areas", res)
    if re.search(r"change|over time|since|trend|grow", t):
        res = tools.compare_snapshots(ctx, tools.SnapArgs(ind_code=ind_code, area=(ents.get("areas") or [filters.get("area", "ACW")])[0]))
        return {"compare_snapshots#1": res}, None
    areas = ents.get("areas") or []
    if len(areas) == 1 and filters.get("area") and filters["area"] != areas[0]:
        areas = [filters["area"], areas[0]]
    areas = areas or ["ACW", *q.REGIONS]
    res = tools.get_results(ctx, tools.ResultsArgs(ind_code=ind_code, areas=areas, sex=sex, snapshot=fy, org=ents.get("org") or "WBG"))
    return {"get_results#1": res}, ("get_results", res) if len(res["rows"]) >= 2 else None


def _template_analysis(collected: dict) -> str:
    out = []
    for key, res in collected.items():
        name = key.split("#")[0]
        if name == "rank_areas":
            what = "delivery rate (achieved ÷ expected)" if res["metric"] == "delivery_ratio" else res["metric"].replace("_", " ")
            out.append(f"**{res['indicator']}** · {'lowest' if res['order'] == 'asc' else 'highest'} {what}, {res['snapshot']}"
                       + (f" (within {res['within']})" if res["within"] != "all" else "") + ":")
            for r in res["rows"]:
                out.append(f"{r['rank']}. {r['area_name']}: {_cite(r.get('delivery_pct'))} delivered ({_cite(r['achieved'])} of {_cite(r['expected'])})")
            if res.get("excluded_achieved_above_expected"):
                out.append(f"\n{res['excluded_achieved_above_expected']} areas reporting achieved above expected were excluded as a data check.")
        elif name == "get_results":
            out.append(f"**{res['indicator']}** ({res['snapshot']}, {res['sex']}, {res['org']}):")
            for r in res["rows"]:
                if r.get("no_data"):
                    out.append(f"- {r['area_name']}: no results reported")
                else:
                    out.append(f"- {r['area_name']}: {_cite(r['achieved'])} achieved of {_cite(r['expected'])} expected"
                               + (f" ({_cite(r.get('delivery_pct'))}; {_cite(r.get('remaining_gap'))} still to deliver)" if r.get("delivery_pct") else ""))
        elif name == "compare_snapshots":
            out.append(f"**{res['indicator']}**, {res['area']}, across snapshots:")
            for r in res["rows"]:
                out.append(f"- {r['snapshot']}: {_cite(r['achieved'])} achieved of {_cite(r['expected'])} expected"
                           + (f" (change {_cite(r.get('achieved_change'))})" if r.get("achieved_change") else ""))
    return "\n".join(out) + "\n\n“Expected” is what the active portfolio is expected to deliver, not a corporate target."


def _template_summary(f: dict) -> str:
    lines = []
    s = f.get("selected")
    if s:
        lines.append(f"- {f['area']}: {_cite(s['achieved'])} achieved of {_cite(s['expected'])} expected ({_cite(s['delivery_rate'])} delivered).")
    if f["regions"]:
        gap = max(f["regions"], key=lambda r: r["remaining_gap"]["value"])
        low = min(f["regions"], key=lambda r: r["delivery_rate"]["value"])
        lines.append(f"- Most people still to reach: {gap['region']} ({_cite(gap['remaining_gap'])}).")
        lines.append(f"- Lowest delivery rate: {low['region']} ({_cite(low['delivery_rate'])}).")
    ch = f.get("all_countries_change")
    if ch:
        lines.append(f"- All countries: achieved moved from {_cite(ch['from'])} to {_cite(ch['to'])} between snapshots.")
    return "\n".join(lines) or "Not enough data in this view to summarize."


def _followups(collected: dict) -> list[str]:
    names = [k.split("#")[0] for k in collected]
    if "rank_areas" in names:
        return ["Show this for female beneficiaries", "Make a 3-slide briefing"]
    return ["Which countries are furthest behind?", "How has this changed since FY24?"]


# ------------------------------------------------------------------------------------------------ research
def _research(message, ents, outcome_id, conv, claims, usage, deck_only=False):
    scope_note = None
    target = ents.get("topic") or outcome_id
    if not target:
        ranked = analysis.choose_area()
        pick = ranked[0]
        target = pick["outcome"]["outcome_id"]
        scope_note = (f"<b>Scope:</b> no thematic area named, so I compared all outcome areas and picked <b>{pick['outcome']['name']}</b>: "
                      f"the largest remaining gap ({fmt(pick['gap'])} people) among areas with country-level results "
                      f"({pick['n_results']} countries) and need data ({pick['n_need']}). Runners-up: "
                      + "; ".join(f"{x['outcome']['name']} ({fmt(x['gap'])})" for x in ranked[1:3]) + ". Type another area to re-run.")
    if target != outcome_id:
        o = q.outcome(target)
        yield _ev("navigate", url=f"/outcomes/{o['slug']}/?research=1&q={message}")
        return
    conv["research_q"] = message
    if scope_note:
        yield _ev("message", html=scope_note, kind="sys")
    steps = ["Scorecard results by country", "Client-context need", "Population (World Bank Data360)",
             "Operational footprint (Scorecard projects + Projects API)", "Prioritization rules", "Writing the briefing"]
    yield _ev("plan", steps=steps)
    R = analysis.research(target, claims)
    s = R["sources"]
    details = [f"{s['countries_with_results']} countries with results ({R['indicator']['ind_code']})",
               f"{s['countries_with_need']} countries · {R['need']['ind_code'] if R['need'] else '—'}",
               f"{s['countries_with_population']} countries",
               f"{s['countries_with_projects']} countries with projects (${fmt(s['project_commitments'])[0:] if s['project_commitments'] else 0}) · {s['active_sector_projects']} active sector projects",
               "accelerate: large portfolio & < 40% delivered · expand: top need & pipeline < 25% of need",
               "from verified results only"]
    for i, d in enumerate(details[:-1]):
        yield _ev("plan_step", index=i, detail=d)
    o = R["outcome"]
    if not deck_only:
        if llm.available():
            html_, stats = write(message, o["name"], R["for_writer"], claims, usage, system=prompts.RESEARCH_WRITER)
        else:
            html_, stats = pcn.render(_template_research(R), claims)
        caveat = ("Results: Scorecard FY{fy}, WBG totals by country. Need: {need} (latest year). Population: Data360 WDI. Footprint: "
                  "Scorecard project-level contributions (World Bank only) and active projects from the Projects API matched by sector "
                  "(approximate). “Expected” = active portfolio, not a target; coverage vs need is indicative.").format(
            fy=str(R["snapshot_fy"])[2:], need=R["need"]["ind_code"] if R["need"] else "—")
        if R["overshoot"]:
            caveat += f" Data check: {len(R['overshoot'])} countries report achieved above expected (e.g. " + ", ".join(
                f"{x['name']} {100 * x['ratio']:.0f}%" for x in R["overshoot"][:3]) + "); excluded from strong delivery."
        yield _ev("message", html=f"<div><b>Three-year priorities: {o['name']}</b></div>" + html_, stats=stats, how=caveat,
                  followups=[f"Which countries in {R['focus']['name']} are furthest behind?"])
        mat = artifacts.matrix_figure(R)
        conv.setdefault("artifacts", {})[mat["id"]] = mat
        yield _ev("artifact", artifact=mat)
    yield _ev("plan_step", index=5, detail="slides drafted")
    slide_text = None
    if llm.available():
        try:
            out = llm.complete_json([{"role": "system", "content": prompts.DECK_WRITER.format(outcome=o["name"])
                                      + "\n\nRESULTS (JSON):\n" + json.dumps(R["for_writer"], default=str)},
                                     {"role": "user", "content": "Write the three slides."}], max_tokens=900, usage=usage)
            slide_text = out if out.get("slides") else None
        except llm.LLMUnavailable:
            slide_text = None
    d = artifacts.deck(R, claims, slide_text)
    conv.setdefault("artifacts", {})[d["id"]] = d
    yield _ev("artifact", artifact=d)
    nb = {"id": artifacts.new_id(), "type": "notebook", "title": "Notebook · research pipeline", "data_ref": d["data_ref"],
          "cells": artifacts.notebook(d)["cells"]}
    conv["artifacts"][nb["id"]] = nb
    yield _ev("artifact", artifact={**nb, "download_url": f"/api/artifacts/{nb['id']}.ipynb"})
    if deck_only:
        yield _ev("message", html=f"Here is a 3-slide briefing on <b>{o['name']}</b>, built from verified Scorecard, Data360 and Projects API data. Export it as HTML/PDF, or as a notebook that reproduces the analysis.")


def _template_research(R: dict) -> str:
    fw = R["for_writer"]
    f = fw["regional_focus"]
    lines = [f"1. **Regional focus: {f['region']}.** "
             + (f"It holds {_cite(f.get('share_of_people_in_need'))} of people in need in client countries; " if f.get("share_of_people_in_need") else "")
             + f"{_cite(f['remaining_gap'])} of expected results remain to be delivered there."]
    if fw["accelerate_delivery"]:
        lines.append("2. **Accelerate delivery** where portfolios are large but behind: " + ", ".join(
            f"{x['country']} ({_cite(x.get('delivery_rate'))} of {_cite(x.get('expected'))})" for x in fw["accelerate_delivery"]) + ".")
    if fw["expand_footprint"]:
        lines.append("3. **Expand the footprint** where need far exceeds the pipeline: " + ", ".join(
            f"{x['country']} ({_cite(x['people_in_need']) + ' people in need' if x.get('people_in_need') else _cite(x.get('need_indicator'))})"
            for x in fw["expand_footprint"]) + ".")
    if fw["strong_delivery"]:
        lines.append("4. **Learn from strong delivery:** " + ", ".join(f"{x['country']} ({_cite(x.get('delivery_rate'))})" for x in fw["strong_delivery"]) + ".")
    w = fw["world"]
    lines.append(f"\n**Biggest gap overall:** {_cite(w['remaining_gap'])} of expected results are still to be delivered ({_cite(w['delivery_rate'])} achieved).")
    return "\n".join(lines)
