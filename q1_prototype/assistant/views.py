import json
import time

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from explorer import queries as q
from explorer.formatting import fmt

from . import analysis, artifacts, llm, pcn, pipelines, resolver


def _conv(request, outcome_id) -> dict:
    convs = request.session.setdefault("convs", {})
    return convs.setdefault(str(outcome_id or "home"), {})


def _rate_limited(request) -> bool:
    if not request.session.session_key:
        request.session.save()
    key = f"rl:{request.session.session_key}"
    hits = [t for t in cache.get(key, []) if t > time.time() - 300]
    hits.append(time.time())
    cache.set(key, hits, 300)
    return len(hits) > settings.ASSISTANT["rate_limit_per_5min"]


@require_POST
def chat(request):
    """Streams assistant events as Server-Sent Events (text/event-stream)."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    message = str(body.get("message", ""))[: settings.ASSISTANT["max_message_chars"]]
    state = {"outcome_id": body.get("outcome_id"), "ind_code": body.get("ind_code"),
             "filters": {k: v for k, v in (body.get("filters") or {}).items() if k in ("area", "sex", "org", "fy")},
             "active_artifact": body.get("active_artifact")}
    if state["filters"].get("area") and state["filters"]["area"] not in q.areas():
        state["filters"].pop("area")
    if _rate_limited(request):
        def limited():
            yield "data: " + json.dumps({"type": "error", "text": "Too many questions in a short time. Please wait a minute."}) + "\n\n"
        return StreamingHttpResponse(limited(), content_type="text/event-stream")
    conv = _conv(request, state["outcome_id"])

    def stream():
        for ev in pipelines.handle(message, state, conv):
            yield "data: " + json.dumps(ev, default=str) + "\n\n"
        request.session.modified = True
        request.session.save()

    resp = StreamingHttpResponse(stream(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@require_POST
def route_home(request):
    """Landing-page Ask: navigate to an outcome, answer cross-area questions, or start research."""
    body = json.loads(request.body or "{}")
    message = str(body.get("message", ""))[:500].strip()
    if not message or pipelines.INJECTION.search(message) or _rate_limited(request):
        return JsonResponse({"action": "answer", "html": "Ask a question about World Bank Group Scorecard results."})
    r = pipelines.route(message, {"outcome_id": None, "filters": {}}, [], [])
    ents = r["entities"]
    if r["intent"] in ("research", "deck"):
        if ents.get("topic"):
            o = q.outcome(ents["topic"])
            return JsonResponse({"action": "navigate", "url": f"/outcomes/{o['slug']}/?research=1&q={message}"})
        ranked = analysis.choose_area()
        pick = ranked[0]["outcome"]
        note = (f"No thematic area was named, so I compared all outcome areas and picked <b>{pick['name']}</b>: the largest "
                f"remaining gap among areas with country-level results and need data. Starting the analysis…")
        return JsonResponse({"action": "navigate", "url": f"/outcomes/{pick['slug']}/?research=1&q={message}", "html": note})
    if ents.get("topic") and r["intent"] in ("filter", "navigate", "analyze", "explain", "summary"):
        o = q.outcome(ents["topic"])
        return JsonResponse({"action": "navigate", "url": f"/outcomes/{o['slug']}/?q={message}"})
    if r["intent"] == "analyze":  # cross-area question: rank outcome areas by delivery rate
        claims = pcn.Claims()
        rows = []
        for o in q.outcomes():
            p = q.primary_result(o["outcome_id"])
            if p and p["achieved"] is not None and p["expected"] and p["unit"] == "Beneficiaries" and p["achieved"] <= 1.05 * p["expected"]:
                rows.append((p["achieved"] / p["expected"], o, p))
        rows.sort(key=lambda x: x[0])
        items = []
        for ratio, o, p in rows[:3]:
            cid = claims.add(100 * ratio, unit="Percentage", source=f"{p['ind_code']} · all countries · computed", label="achieved ÷ expected")
            items.append(f"<li>{o['name']}: <claim id=\"{cid}\">{100 * ratio:.0f}%</claim> of expected</li>")
        html_, _ = pcn.render("".join(items), claims)
        html_ = html_.replace("&lt;li&gt;", "<li>").replace("&lt;/li&gt;", "</li>")
        return JsonResponse({"action": "answer", "highlight": [o["outcome_id"] for _, o, _ in rows[:3]],
                             "html": f"<p style='margin:0 0 6px'><b>Furthest from expected results</b> (people-reached indicators, all countries, FY{str(q.latest_fy())[2:]}):</p><ol style='margin:0;padding-left:20px'>{html_}</ol>"})
    return JsonResponse({"action": "answer", "html": "Which outcome area do you mean? Try “energy access in Nigeria”, “students supported in Ghana”, or ask for three-year priorities."})


def _artifact(request, artifact_id) -> dict:
    for conv in (request.session.get("convs") or {}).values():
        a = (conv.get("artifacts") or {}).get(artifact_id)
        if a:
            return a
    raise Http404("Artifact not found in this session")


@require_GET
def notebook(request, artifact_id):
    a = _artifact(request, artifact_id)
    nb = artifacts.notebook(a) if a["type"] != "notebook" else {
        "nbformat": 4, "nbformat_minor": 5, "cells": a["cells"],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}, "language_info": {"name": "python"}}}
    resp = HttpResponse(json.dumps(nb, indent=1), content_type="application/x-ipynb+json")
    resp["Content-Disposition"] = f'attachment; filename="scorecard_{artifact_id}.ipynb"'
    return resp


@require_GET
def deck(request, artifact_id):
    a = _artifact(request, artifact_id)
    if a["type"] != "deck":
        raise Http404
    return render(request, "assistant/deck_export.html", {"deck": a})


@require_GET
def health(request):
    return JsonResponse({"db": str(settings.SCORECARD_DB), "latest_fy": q.latest_fy(), "llm_configured": llm.available(),
                         "model": settings.LLM["model"], "fast_model": settings.LLM["fast_model"]})
