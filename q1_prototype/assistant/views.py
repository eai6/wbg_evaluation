import html
import json
import time

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from explorer import queries as q
from explorer.formatting import fmt

from . import artifacts, llm, pcn, pipelines


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


def _artifact(request, artifact_id) -> dict:
    for conv in (request.session.get("convs") or {}).values():
        a = (conv.get("artifacts") or {}).get(artifact_id)
        if a:
            return a
    raise Http404("Artifact not found in this session")


@require_GET
def notebook(request, artifact_id):
    a = _artifact(request, artifact_id)
    if a["type"] != "deck":  # notebooks are scoped to a 3-slide briefing
        raise Http404("Notebooks are exported with a 3-slide briefing")
    nb = artifacts.notebook(a)
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
