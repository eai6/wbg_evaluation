"""Router + pipelines. ``handle`` yields UI events streamed to the browser (SSE).

Events: status · filters · navigate · choices · plan · plan_step · message · artifact · done · error
The LLM routes, selects tools and writes short prose; every number and factual statement is rendered here from claims.
Without an LLM the chat is unavailable (filters and charts still work) — there is no keyword fallback.
"""
from __future__ import annotations

import html
import json
import logging
import time
from html.parser import HTMLParser

from django.conf import settings

from explorer import queries as q
from explorer.formatting import fmt

from . import analysis, artifacts, llm, pcn, prompts, resolver, tools

log = logging.getLogger(__name__)
INTENTS = {"filter", "analyze", "explain", "research", "summary", "deck", "notebook", "navigate", "clarify", "out_of_scope"}


def _ev(type_, **kw):
    return {"type": type_, **kw}


# ------------------------------------------------------------------------------------------------ routing
def route(message: str, state: dict, history: list, usage: list) -> dict:
    """LLM router; every code it returns is validated (outcome ids, area names by exact lookup, enumerations)."""
    outs = "; ".join(f"{o['outcome_id']}: {o['name']}" for o in q.outcomes())
    recent = recent_conversation(history)
    ctx = f"current outcome page: {state.get('outcome_name') or 'none (landing page)'}; current filters: {state.get('filters') or {}}"
    out = llm.complete_json([{"role": "system", "content": prompts.ROUTER.format(outcomes=outs)},
                             {"role": "user", "content": f"Context: {ctx}\nRecent conversation:\n{recent}\n\nMessage: {message}"}],
                            fast=True, max_tokens=1200, usage=usage)
    intent = out.get("intent") if out.get("intent") in INTENTS else "clarify"
    oid = out.get("outcome_id")
    oid = oid if isinstance(oid, int) and q.outcome(oid) else None
    codes, unresolved = resolver.areas([a for a in out.get("areas") or [] if isinstance(a, str)])
    ents = {"topic": oid, "areas": codes, "unresolved": unresolved}
    if out.get("sex") == "F":
        ents["sex"] = "F"
    if out.get("org") in ("WB", "IFC", "MIGA"):
        ents["org"] = out["org"]
    if out.get("fy") in [s["fy"] for s in q.snapshots()]:
        ents["fy"] = out["fy"]
    return {"intent": intent, "entities": ents, "reason": out.get("reason", "")}


def _filters_from(ents: dict) -> dict:
    f = {}
    if ents.get("areas"):
        f["area"] = ents["areas"][0]
    for k in ("sex", "org", "fy"):
        if ents.get(k):
            f[k] = ents[k]
    return f


def _describe(f: dict) -> str:
    parts = [q.area_name(f["area"])] if "area" in f else []
    if f.get("sex") == "F":
        parts.append("female beneficiaries")
    if f.get("org"):
        parts.append({"WB": "World Bank"}.get(f["org"], f["org"]))
    if f.get("fy"):
        parts.append(f"FY{str(f['fy'])[2:]} snapshot")
    return ", ".join(parts)


# ------------------------------------------------------------------------------------------------ facts → HTML
def all_entity_names() -> set[str]:
    return {a["label"] for a in q.areas().values()} | set(q.REGION_NAMES.values())


def fact_html(f: dict, claims: pcn.Claims, compact: int = 0) -> str:
    head = f"<b>{html.escape(f['entity'])}</b>"
    if f.get("url", "").startswith("https://"):
        head = f"<a href='{html.escape(f['url'])}' target='_blank' rel='noopener'>{head}</a>"
    meta = [x for x in (f.get("region"), f.get("lending")) if x]
    if meta:
        head += f" <span class='na'>({html.escape(' · '.join(meta))})</span>"
    if f.get("label"):
        head = f"{html.escape(f['label'])}: " + head
    if f.get("measure"):  # which indicator these numbers belong to (an answer can span several)
        head = f"<span class='na'>{html.escape(f['measure'])}</span> · " + head
    parts = [f"{html.escape(k)} {pcn.badge(v['claim'], claims)}" if v.get("claim") else f"{html.escape(k)} <span class='na'>not reported</span>"
             for k, v in f.get("items", []) if v]
    if compact:  # slides: only the first `compact` (headline) numbers
        parts = parts[:compact]
    inst = []
    for x in f.get("by_institution") or []:
        inst.append(html.escape(x) if isinstance(x, str) else f"{html.escape(x[0])} {pcn.badge(x[1]['claim'], claims)}" if x[1] else "")
    tail = f" <span class='na'>· expected by institution: {', '.join(i for i in inst if i)}</span>" if any(inst) and not compact else ""
    if "wb_projects" in f and not compact:
        tail += f" <span class='na'>· World Bank projects (Scorecard project level): {int(f['wb_projects'])}</span>"
    if f.get("no_results"):
        tail += " <span class='na'>· no WBG results reported for this indicator</span>"
    if f.get("data_check"):
        tail += " <span class='na'>· data check: achieved exceeds expected, so no delivery rate is shown</span>"
    return f"<li>{head}: {' · '.join(parts)}{tail}</li>"


def facts_list(facts: list[dict], claims: pcn.Claims, compact: int = 0) -> str:
    return "<ul class='facts'>" + "".join(fact_html(f, claims, compact) for f in facts) + "</ul>" if facts else ""


def entities_of(facts: list[dict]) -> set[str]:
    out = set()
    for f in facts:
        out.add(f["entity"].split(" · ")[0])
        if f.get("region"):
            out.add(f["region"])
    return out


def _facts_for_llm(facts: list[dict]) -> list[dict]:
    """What the writer sees: entities, measures and displayed values (so it can reason), never claim ids."""
    return [{"entity": f["entity"], **({"measure": f["measure"]} if f.get("measure") else {}),
             **({"region": f["region"]} if f.get("region") else {}), **({"label": f["label"]} if f.get("label") else {}),
             "values": {k: v["display"] if v.get("claim") else "not reported" for k, v in f.get("items", []) if v},
             **({"data_check": "achieved exceeds expected; not a delivery rate"} if f.get("data_check") else {})} for f in facts]


def write_prose(system: str, usage: list, max_tokens=1500) -> dict:
    return llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": "Write it."}],
                             max_tokens=max_tokens, usage=usage)


# ------------------------------------------------------------------------------------------------ tool results → facts
def tool_facts(collected: dict) -> list[dict]:
    facts = []
    for key, res in collected.items():
        name = key.split("#")[0]
        if not isinstance(res, dict) or res.get("error"):
            continue
        if name in ("get_results", "rank_areas"):
            measure = res.get("indicator", "") + (f" · {res['org']}" if res.get("org") not in (None, "WBG") else "") + \
                (" · female" if res.get("sex") == "female" else "") + (f" · {res['snapshot']}" if res.get("snapshot") else "")
            for r in res.get("rows", []):
                if r.get("no_data"):
                    facts.append({"entity": r["area_name"], "measure": measure, "items": [], "no_results": True})
                    continue
                items = [("still to deliver", r.get("remaining_gap")), ("delivery rate", r.get("delivery_pct")),
                         ("achieved", r.get("achieved")), ("expected", r.get("expected"))]
                lab = f"#{r['rank']}" if r.get("rank") else None
                facts.append({"entity": r["area_name"], "measure": measure, "items": items, **({"label": lab} if lab else {}),
                              **({"data_check": True} if r.get("data_check") else {})})
        elif name == "compare_snapshots":
            for r in res.get("rows", []):
                facts.append({"entity": f"{res['area']} · {r['snapshot']}", "items": [("achieved", r.get("achieved")), ("expected", r.get("expected")),
                                                                                     ("achieved change", r.get("achieved_change"))]})
        elif name == "get_context":
            for r in res.get("rows", []):
                if not r.get("no_data"):
                    facts.append({"entity": r["area_name"], "items": [(f"{res['indicator']} ({r['latest_year']})", r["latest"]),
                                                                       (f"{res['indicator']} ({r['first_year']})", r["first"])]})
        elif name == "outcome_overview":
            for r in res.get("indicators", []):
                facts.append({"entity": res["area"], "label": r["indicator"], "items": [("achieved", r.get("achieved")), ("expected", r.get("expected")),
                                                                                       ("delivery rate", r.get("delivery_pct"))],
                              **({"data_check": True} if r.get("data_check") else {})})
        elif name == "get_projects":
            ok = res.get("projects_add_up_to_total")
            check = ("the total for this indicator is not a sum of project values, so there is no sum check" if ok is None else
                     "the project rows sum to the published total (a sum check only: projects flagged for results overlap may still "
                     "share beneficiaries)" if ok
                     else "the project rows do not sum to the published total; the difference is in the total but not attributed to projects in the API")
            n, m = res["projects"], res["countries"]
            facts.append({"entity": f"{res['area']} · {res['org']} · {n} project{'s' if n != 1 else ''} in {m} "
                                    f"{'countries/economies' if m != 1 else 'country/economy'}",
                          "items": [("sum of project rows, achieved", res["sum_of_projects"]["achieved"]),
                                    ("sum of project rows, expected", res["sum_of_projects"]["expected"])]
                                   + ([("published total, achieved", res["published_total"]["achieved"]),
                                       ("published total, expected", res["published_total"]["expected"])] if res.get("published_total") else []),
                          "label": check})
            for r in res.get("rows", []):
                facts.append({"entity": r["project"], "url": r["url"], "items": [("achieved", r["achieved"]), ("expected", r["expected"])],
                              "region": r["country"] + (" · Results Overlap Flag Y" if r["overlap_flag"] == "Y" else "")})
        elif name == "run_sql":
            for r in res.get("rows", [])[:15]:
                ent = next((str(v) for k, v in r.items() if k in ("area_name", "area_code", "indicator", "ind_code") and v), "Result")
                facts.append({"entity": ent, "items": [(k, v) for k, v in r.items() if isinstance(v, dict) and v.get("claim")]})
    return facts


# ------------------------------------------------------------------------------------------------ conversation memory
class _Text(HTMLParser):
    """Visible text of a rendered answer (tags dropped, list items on their own line)."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("li", "p", "br", "div"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def answer_text(rendered_html: str, limit: int = 1500) -> str:
    """What the user saw, as plain text: the remembered assistant turn (numbers included, so follow-ups such as
    "how does this compare?" can be resolved)."""
    p = _Text()
    p.feed(rendered_html or "")
    lines = [" ".join(x.split()) for x in "".join(p.parts).replace("✓", "").split("\n")]
    return "\n".join(x for x in lines if x)[:limit]


def recent_conversation(history: list, turns: int = 3) -> str:
    """The last few exchanges before the current message, for the router and the analysis model."""
    prior = history[:-1] if history and history[-1]["role"] == "user" else history
    return "\n".join(f"{h['role']}: {h['content']}" for h in prior[-2 * turns:]) or "none"


# ------------------------------------------------------------------------------------------------ main entry
def handle(message: str, state: dict, conv: dict):
    """Runs one turn and remembers what was shown (the text of the messages, not a placeholder)."""
    shown = []
    for ev in _handle(message, state, conv):
        if ev["type"] == "message" and ev.get("html"):
            shown.append(answer_text(ev["html"]))
        if ev["type"] == "artifact":
            shown.append(f"[created {ev['artifact'].get('type')}: {ev['artifact'].get('title')}]")
        if ev["type"] == "done":
            history = conv.setdefault("history", [])
            if shown:
                if history and history[-1]["role"] == "assistant":
                    history[-1]["content"] = "\n".join(shown)[:2000]
                elif history and history[-1]["role"] == "user":
                    history.append({"role": "assistant", "content": "\n".join(shown)[:2000]})
        yield ev


def _handle(message: str, state: dict, conv: dict):
    t0 = time.time()
    usage: list = []
    claims = pcn.Claims(conv.setdefault("claims", {}))
    history = conv.setdefault("history", [])
    message = message.strip()[: settings.ASSISTANT["max_message_chars"]]
    answer = ""
    try:
        if not message:
            return
        if not llm.available():
            yield _ev("error", text="The assistant needs a language model (set LLM_MODEL and LLM_API_KEY in .env). "
                                    "The filters, map and charts work without it.")
            return
        outcome_id = state.get("outcome_id")
        o = q.outcome(outcome_id) if outcome_id else None
        state["outcome_name"] = o["name"] if o else None
        filters = state.get("filters") or {}
        fy = int(filters.get("fy") or q.latest_fy())
        ind_code = state.get("ind_code") or ((analysis.primary_indicator(outcome_id) or {}).get("ind_code") if outcome_id else None)

        yield _ev("status", text="Understanding the question…")
        r = route(message, state, history, usage)
        intent, ents = r["intent"], r["entities"]
        yield _ev("status", text=f"Router → {intent}", route=r)
        history.append({"role": "user", "content": message})
        if ents.get("unresolved") and not ents.get("areas") and intent in ("filter", "analyze"):
            answer = f"I couldn't match {', '.join(repr(u) for u in ents['unresolved'])} to a country or region in the Scorecard."
            yield _ev("message", html=html.escape(answer))
            return

        if ents.get("topic") and ents["topic"] != outcome_id and intent in ("navigate", "filter", "analyze", "explain", "summary", "research", "deck"):
            target = q.outcome(ents["topic"])
            extra = "&research=1" if intent in ("research", "deck") else ""
            yield _ev("navigate", url=f"/outcomes/{target['slug']}/?q={message}{extra}")
            answer = f"Opening {target['name']}."
            return

        if intent == "filter":
            f = _filters_from(ents)
            if f:
                yield _ev("filters", filters=f)
                answer = f"Overview filtered: {_describe(f)}."
                yield _ev("message", html=html.escape(answer), kind="sys")
            else:
                answer = "Tell me which area, institution, snapshot or group to show."
                yield _ev("message", html=answer)
            return

        if intent in ("research", "deck"):
            if not outcome_id:
                yield from _choose_area(message)
                return
            yield from _research(message, outcome_id, conv, claims, usage, deck_only=intent == "deck")
            answer = "[research]"
            return

        if intent == "notebook":  # notebooks come with the 3-slide briefing: one scoped, re-computable analysis
            if not outcome_id:
                yield from _choose_area(message)
                return
            yield _ev("message", html="Notebooks are exported with the 3-slide briefing, so the code reproduces one specific analysis. "
                                      "Building the briefing and its notebook now.")
            yield from _research(message, outcome_id, conv, claims, usage, deck_only=True)
            answer = "[deck]"
            return

        if intent == "explain":
            d = q.indicators().get(ind_code) or {}
            answer = (f"<b>{html.escape(d.get('display_name', ''))}</b>: {html.escape(d.get('definition') or 'No definition published.')}"
                      "<br><br><b>Achieved</b> is what WBG-financed operations have delivered so far; <b>expected</b> is what the active "
                      "portfolio is expected to deliver by completion. Expected is not a corporate target.")
            yield _ev("message", html=answer, how=f"Source: Scorecard indicator metadata ({ind_code}), quoted verbatim.")
            return

        if intent == "summary":
            yield _ev("status", text="Reading the current view…")
            s = analysis.view_summary(outcome_id, ind_code, filters.get("area", "ACW"), filters.get("org", "WBG"), filters.get("sex", "_T"), fy, claims)
            ev, _ = _render_answer("Summarize what this view shows.", s["facts"], usage, claims, heading="What this view shows")
            yield ev
            answer = "[summary]"
            return

        if intent == "analyze" and outcome_id:
            yield from _analyze(message, ents, filters, fy, ind_code, o, conv, claims, usage)
            answer = "[analysis]"
            return

        if intent == "clarify":
            answer = "Could you say which outcome area, country or region you mean? For example “energy access in Nigeria”."
            yield _ev("message", html=answer)
            return
        answer = "I can answer questions about World Bank Group Scorecard results: filters, comparisons, rankings, definitions, briefings and data exports."
        yield _ev("message", html=answer)
    except llm.LLMUnavailable as exc:
        yield _ev("error", text=f"The language model is unavailable ({str(exc)[:120]}). Filters and charts still work.")
    except Exception:  # never leak internals
        log.exception("assistant failure")
        yield _ev("error", text="Something went wrong while answering. Please try again or rephrase.")
    finally:
        if answer:
            history.append({"role": "assistant", "content": answer[:600]})
        del history[:-2 * settings.ASSISTANT["history_turns"]]
        yield _ev("done", ms=int((time.time() - t0) * 1000), usage=usage)


def _render_answer(question, facts, usage, claims, heading=None, how=None, artifact=None):
    out = write_prose(prompts.WRITER.format(question=question, facts=json.dumps(_facts_for_llm(facts))[:20000]), usage)
    text, dropped = pcn.prose(out.get("text"), entities_of(facts), all_entity_names())
    stats = {"facts": sum(1 for f in facts for _, v in f.get("items", []) if v), "prose_dropped": dropped}
    body = (f"<div><b>{html.escape(heading)}</b></div>" if heading else "") + (f"<p>{text}</p>" if text else "") + facts_list(facts, claims)
    if not facts:
        body += "<p class='na'>No data was found for this question.</p>"
    fus = [f for f in (out.get("followups") or [])[:2] if isinstance(f, str) and not any(ch.isdigit() for ch in f)]
    return _ev("message", html=body, stats=stats, how=how, followups=fus), artifact


def _analyze(message, ents, filters, fy, ind_code, o, conv, claims, usage):
    ctx = tools.Ctx(claims, fy)
    inds = ", ".join(f"{i['ind_code']} ({i['display_name']})" for i in q.outcome_indicators(o["outcome_id"])["results"])
    context = (f"outcome area: {o['name']}; selected indicator {ind_code}; filters: {filters or 'none'}; snapshot FY{str(fy)[2:]}; "
               f"places named in the question (codes): {ents.get('areas') or 'none'}\n"
               f"Earlier in this conversation (what the user was shown; use it to resolve 'this', 'there', 'them'):\n"
               f"{recent_conversation(conv.get('history') or [])}")
    msgs = [{"role": "system", "content": prompts.RESEARCHER.format(context=context, indicators=inds, max_calls=settings.ASSISTANT["max_tool_calls"])},
            {"role": "user", "content": message}]
    collected, figure_src, calls, sqls = {}, None, 0, []
    while calls < settings.ASSISTANT["max_tool_calls"]:
        m = llm.complete(msgs, tools=tools.schemas(), max_tokens=2000, usage=usage, effort="low")
        tcs = getattr(m, "tool_calls", None) or []
        if not tcs:
            break
        turn = {"role": "assistant", "content": m.content or "",
                "tool_calls": [{"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}} for t in tcs]}
        if getattr(m, "thinking_blocks", None):  # Claude: thinking blocks must be passed back unchanged with tool calls
            turn["thinking_blocks"] = m.thinking_blocks
        msgs.append(turn)
        for t in tcs:
            calls += 1
            try:
                args = json.loads(t.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            yield _ev("status", text=f"{t.function.name}({', '.join(f'{k}={v}' for k, v in args.items())[:120]})")
            res = tools.call(ctx, t.function.name, args)
            collected[f"{t.function.name}#{calls}"] = res
            if t.function.name == "run_sql" and res.get("sql"):
                sqls.append(res["sql"])
            if t.function.name in ("get_results", "rank_areas") and len([x for x in res.get("rows") or [] if not x.get("no_data")]) >= 2:
                figure_src = (t.function.name, res)
            msgs.append({"role": "tool", "tool_call_id": t.id, "content": json.dumps(res, default=str)[:12000]})
    facts = tool_facts(collected)
    yield _ev("status", text="Writing the interpretation…")
    how = "Tools: " + (", ".join(k.split("#")[0] for k in collected) or "none") + f" · Scorecard FY{str(fy)[2:]} snapshot · ratios computed in code"
    if sqls:
        how += " · SQL: " + " | ".join(sqls)
    ev, _ = _render_answer(message, facts, usage, claims, how=how)
    yield ev
    if figure_src:
        name, res = figure_src
        title = (f"{'Regions' if res.get('level') == 'REGION' else 'Countries'} by {res.get('metric', '').replace('_', ' ')}"
                 + (f" · {res['within']}" if res.get("within") not in (None, "all") else "")) if name == "rank_areas" else \
                f"Achieved vs expected · {', '.join(r['area_name'] for r in res['rows'][:3])}"
        art = artifacts.results_figure(res["ind_code"], res["rows"], title=title, sex=filters.get("sex", "_T"), fy=fy)
        conv.setdefault("artifacts", {})[art["id"]] = art
        yield _ev("artifact", artifact=art)


# ------------------------------------------------------------------------------------------------ research
def _choose_area(message: str):
    """No thematic area named: ask, showing how complete each area's country data is (plain counts, no cut-offs)."""
    cov = analysis.coverage()
    yield _ev("choices", text="Which thematic area should I analyze? Areas are listed by how complete their country-level data is "
                              "(countries with WBG results; whether a population-based need measure exists).",
              options=[{"label": c["outcome"]["name"], "detail": f"{c['countries_with_results']} countries with results"
                        + (f" · need: {c['need_measure']}" if c["need_measure"] else " · no population-based need measure"),
                        "url": f"/outcomes/{c['outcome']['slug']}/?research=1&q={message}"} for c in cov])


def _research(message, outcome_id, conv, claims, usage, deck_only=False):
    conv["research_q"] = message
    yield _ev("plan", steps=["WBG results by country (Scorecard)", "Results by institution: WB / IFC / MIGA (Scorecard)",
                             "Need measure from the reviewed catalogue × population (Data360)", "World Bank projects contributing (Scorecard project level)",
                             "Ranked lists and data checks", "Selection summary (computed from the lists) and artifacts"])
    R = analysis.research(outcome_id, claims)
    s = R["sources"]
    yield _ev("plan_step", index=0, detail=f"{s['countries_with_results']} borrowing countries with usable results ({R['indicator']['ind_code']})")
    yield _ev("plan_step", index=1, detail="institution split loaded (IFC country values may be undisclosed)")
    yield _ev("plan_step", index=2, detail=(f"{s['countries_with_need']} countries · {R['need']['ind_code']}" if R["need"] else "no catalogued population-based measure"))
    yield _ev("plan_step", index=3, detail="World Bank projects only (IFC/MIGA projects are not listed in this source)")
    yield _ev("plan_step", index=4, detail=f"{s['data_checks']} data checks (achieved above expected) excluded from rates")
    F = R["facts"]
    dropped = []

    def p(key, facts_key):  # per-section prose removed: comparisons in free text cannot be verified
        return ""
    plan = selection_summary(R)
    o, need = R["outcome"], R["need"]
    sec = lambda title: f"<div class='sec'>{html.escape(title)}</div>"
    body = (f"<div><b>Three-year priorities: {html.escape(o['name'])}</b> <span class='na'>· {html.escape(R['indicator']['display_name'])}, "
            f"FY{str(R['snapshot_fy'])[2:]} snapshot</span></div>"
            + sec("Where the portfolio stands") + p("overall", "overall") + facts_list(F["overall"], claims)
            + sec("Regions: most still to deliver") + p("regions", "regions") + facts_list(F["regions"], claims)
            + sec(f"Countries: most still to deliver (top {analysis.TOP_N})") + p("most_to_deliver", "most_to_deliver") + facts_list(F["most_to_deliver"], claims))
    if need:
        body += (sec(f"Context: most {need['people_measure']} (not used to select countries)") + facts_list(F["most_people"], claims))
    if plan:
        body += sec("Selection for a three-year plan (one rule: most still to deliver)") + "<ul>" + "".join(plan) + "</ul>"
    if F["data_checks"]:
        body += sec("Data checks (achieved above expected; excluded from delivery rates)") + facts_list(F["data_checks"], claims)
    how = " ".join(f"{k.capitalize()}: {v}." for k, v in R["definitions"].items())
    if dropped:
        how += " Interpretation removed because it failed checks: " + "; ".join(dropped) + "."
    if not deck_only:
        yield _ev("message", html=body, stats={"prose_dropped": dropped}, how=how)
        mat = artifacts.matrix_figure(R)  # the selection-logic chart exists for every outcome (need measure or not)
        conv.setdefault("artifacts", {})[mat["id"]] = mat
        yield _ev("artifact", artifact=mat)
    yield _ev("plan_step", index=5, detail="selection stated from the lists (no AI-written comparisons)")
    d = artifacts.deck(R, claims)
    # the briefing carries its notebook (slide-by-slide reproduction from the public APIs)
    d["notebook"] = {"cells": artifacts.notebook(d)["cells"], "download_url": f"/api/artifacts/{d['id']}.ipynb"}
    conv.setdefault("artifacts", {})[d["id"]] = d
    yield _ev("artifact", artifact=d)
    if deck_only:
        yield _ev("message", html=f"Here is a 3-slide briefing on <b>{html.escape(o['name'])}</b>. All numbers are rendered from verified data "
                                  "and the titles are computed from the data. Switch to <b>Notebook</b> on the briefing to see or download "
                                  "the code that rebuilds each slide from the public APIs.")


def selection_summary(R: dict) -> list[str]:
    """The three-year selection, stated deterministically from the ranked lists (no model-written comparisons: a sentence
    such as "the region furthest behind" cannot be checked by our validators and was wrong in testing)."""
    esc, out = html.escape, []
    regions = [r["name"] for r in R["regions"][:2]]
    countries = [x["name"] for x in R["most_to_deliver"][:3]]
    if regions:
        out.append(f"<li><b>Regions:</b> {esc(' and '.join(regions))} hold the most results still to deliver.</li>")
    if countries:
        out.append(f"<li><b>Countries:</b> {esc(', '.join(countries))} have the most results still to deliver "
                   f"(expected − achieved); the chart beside this answer shows the cut-off.</li>")
    need = R["need"]
    if need and countries:
        top_people = {x["code"] for x in R["most_people"]}
        also = [x["name"] for x in R["most_to_deliver"][:3] if x["code"] in top_people]
        out.append(f"<li><b>Context:</b> " + (f"{esc(', '.join(also))} {'is' if len(also) == 1 else 'are'} also among the countries with the most "
                                             f"{esc(need['people_measure'])}." if also else
                                             f"none of these is among the countries with the most {esc(need['people_measure'])}.") + "</li>")
    if R["data_checks"]:
        out.append(f"<li><b>Not ranked:</b> {len(R['data_checks'])} countries report achieved above expected (data checks).</li>")
    return out
