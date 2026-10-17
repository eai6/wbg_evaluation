from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from . import queries as q
from .formatting import ICONS, VERTICALS, fmt, short_title_html


def _common():
    snaps = q.snapshots()
    return {"latest_fy": str(q.latest_fy())[2:], "snapshot_date": snaps[-1]["date"]}


@require_GET
def home(request):
    tiles = []
    for t in q.landing_tiles():
        p = t["primary"]
        tile = {**t, "icon": ICONS.get(t["outcome_id"], "circle"), "color_var": VERTICALS.get(t["vertical"], "--muted"),
                "title_html": short_title_html(p["name"]) if p else f"<b>{t['name']}</b>"}
        if p:
            a, e = p["achieved"], p["expected"]
            tile["achieved_fmt"] = fmt(a, p["unit"]) if a is not None else ""
            tile["expected_fmt"] = fmt(e, p["unit"])
            ratio = (a / e) if (a is not None and e) else 0
            tile["bar_px"] = max(4, min(1, ratio) * 52) if a is not None and e and e > 0 else 0
        tiles.append(tile)
    return render(request, "explorer/home.html", {
        "page": "home", "tiles": tiles, "verticals": list(VERTICALS.items()), **_common()})


@require_GET
def outcome(request, slug):
    o = q.outcome(slug)
    if not o:
        raise Http404("Unknown outcome area")
    boot = {"outcome_id": o["outcome_id"], "data_url": f"/api/outcomes/{o['outcome_id']}/data",
            "ask": request.GET.get("q", "")[:500], "research": request.GET.get("research") == "1",
            # shareable view: ?ind=&fy=&org=&area=&sex= (validated again client-side against the payload)
            "view": {k: request.GET[k][:40] for k in ("ind", "fy", "org", "area", "sex") if request.GET.get(k)}}
    return render(request, "explorer/workspace.html", {
        "page": "outcome", "outcome": o, "icon": ICONS.get(o["outcome_id"], "circle"),
        "color_var": VERTICALS.get(o["vertical"], "--muted"), "boot": boot, **_common()})


@require_GET
def indicator_data(request, ind_code: str):
    """The Scorecard data page for one results indicator (all areas, institutions, breakdowns and projects)."""
    try:
        fy = int(request.GET["fy"]) if request.GET.get("fy") else None
    except ValueError:
        raise Http404
    d = q.indicator_detail(ind_code, fy)
    if not d:
        raise Http404("Unknown results indicator")
    return JsonResponse(d, json_dumps_params={"default": str})


@require_GET
def outcome_data(request, outcome_id: int):
    if not q.outcome(outcome_id):
        raise Http404
    return JsonResponse(q.outcome_payload(outcome_id), json_dumps_params={"default": str})
