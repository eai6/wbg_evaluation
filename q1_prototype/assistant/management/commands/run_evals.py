"""python manage.py run_evals [--build] [--configs rules haiku:sonnet sonnet:sonnet ...] [--limit N]

Scores each configuration (router model : main model) on the golden set:
- accuracy: intent, filters, numeric correctness vs live-API ground truth, PCN verified rate, untagged numbers, refusals
- latency: end-to-end per question (p50 / p95)
- cost: tokens x published per-token prices -> $ per question and per 1,000 questions
"""
import html as H
import json
import statistics
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from assistant import pipelines
from assistant.evals import goldens as G

# $ per 1M tokens (input, output) - Anthropic first-party prices (cached 2026-10-06)
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00),
          "claude-fable-5-1": (10.00, 50.00)}
ALIASES = {"haiku": "anthropic/claude-haiku-5-5", "sonnet": "anthropic/claude-sonnet-5-5", "opus": "anthropic/claude-opus-5-5",
           "fable": "anthropic/claude-fable-5-1"}
OUT = Path(__file__).resolve().parents[2] / "evals" / "results"


def _cost(usage):
    total = 0.0
    for u in usage:
        pin, pout = PRICES.get(u["model"].split("/")[-1], (0, 0))
        total += u["in"] / 1e6 * pin + u["out"] / 1e6 * pout
    return total


def run_one(g: dict) -> dict:
    conv: dict = {}
    state = {"outcome_id": g["outcome_id"], "filters": {}}
    t0 = time.time()
    events = list(pipelines.handle(g["question"], state, conv))
    ms = int((time.time() - t0) * 1000)
    route = next((e["route"] for e in events if e.get("route")), {})
    filters = next((e["filters"] for e in events if e["type"] == "filters"), {})
    msgs = [e for e in events if e["type"] == "message"]
    html = " ".join(m["html"] for m in msgs)
    stats = [m.get("stats") or {} for m in msgs]
    tagged = verified = sum(s.get("facts", 0) for s in stats)  # facts are rendered from claims, so verified by construction
    untagged = sum(1 for s in stats if s.get("prose_dropped"))  # answers whose interpretation was withheld by the checks
    values = [c["v"] for c in (conv.get("claims") or {}).values()]  # every number shown is rendered from these claims
    usage = next((e["usage"] for e in events if e["type"] == "done"), [])
    res = {"id": g["id"], "type": g["type"], "question": g["question"], "intent": route.get("intent"), "routed_by": route.get("by"),
           "ms": ms, "cost": _cost(usage), "tagged": tagged, "verified": verified, "untagged": untagged,
           "errors": [e["text"] for e in events if e["type"] == "error"]}
    res["intent_ok"] = res["intent"] in g["expected_intent"]
    if g.get("expected_filters"):
        res["filters_ok"] = all(str(filters.get(k)) == str(v) for k, v in g["expected_filters"].items())
    if g.get("expected_values"):
        hits = []
        for ev in g["expected_values"]:
            tol = max(abs(ev["value"]) * 0.006, 0.6)
            hits.append(any(abs(v - ev["value"]) <= tol for v in values))
        res["numbers_ok"] = all(hits)
        res["numbers_found"] = f"{sum(hits)}/{len(hits)}"
    if g.get("expected_text"):
        res["text_ok"] = g["expected_text"].lower() in H.unescape(html).lower()
    if g["type"] == "no_data":
        low = html.lower()
        res["no_data_ok"] = any(p in low for p in ("no wbg results", "no data", "not reported", "no results"))
    if g["type"] == "out_of_scope":
        res["refusal_ok"] = not values and res["intent_ok"]
    checks = [res[k] for k in ("intent_ok", "filters_ok", "numbers_ok", "text_ok", "no_data_ok", "refusal_ok") if k in res]
    res["correct"] = all(checks) and not res["errors"]
    return res


def research_checks(outcomes=(2, 3, 9, 10)) -> list[dict]:
    """Semantic assertions on the research analysis (no LLM): facts must be true statements, not just true numbers."""
    from assistant import analysis, pcn
    from explorer import queries as q
    out = []
    for oid in outcomes:
        R = analysis.research(oid, pcn.Claims())
        areas = q.areas()
        listed = R["most_to_deliver"] + R["most_people"]
        checks = {
            "regions_correct": all(q.REGION_NAMES.get(areas[x["code"]]["region_code"]) == x["region_name"] for x in listed),
            "borrowers_only": all(areas[x["code"]]["lending"] in analysis.BORROWERS for x in listed),
            "flagged_rows_not_in_delivery_list": not ({x["code"] for x in R["data_checks"]} & {x["code"] for x in R["most_to_deliver"]}),
            "delivery_rates_within_0_100": all(0 <= x["rate"] <= 1 for x in R["most_to_deliver"]),
            "people_measure_only_if_catalogued": (R["need"] is None) == (not R["most_people"]) or R["need"] is not None,
            "people_and_need_same_year_or_earlier": all(x["pop_year"] is None or x["need_year"] is None or x["pop_year"] <= x["need_year"] for x in R["most_people"]),
        }
        out.append({"outcome": R["outcome"]["name"], "need_measure": R["need"]["people_measure"] if R["need"] else None,
                    "most_to_deliver": [x["code"] for x in R["most_to_deliver"]], "most_people": [x["code"] for x in R["most_people"]],
                    **checks, "all_pass": all(checks.values())})
    return out


class Command(BaseCommand):
    help = "Run the golden-set evaluation (accuracy, latency, cost) for one or more model configurations."

    def add_arguments(self, p):
        p.add_argument("--build", action="store_true", help="(re)build goldens.json from the live Scorecard API")
        p.add_argument("--configs", nargs="+", default=["haiku:sonnet"],
                       help="'rules' or ROUTER:MAIN using aliases haiku/sonnet/opus/fable or full LiteLLM ids")
        p.add_argument("--limit", type=int)

    def handle(self, *a, **o):
        path = Path(G.__file__).parent / "goldens.json"
        if o["build"] or not path.exists():
            gs = G.build()
            G.save(gs)
            self.stdout.write(f"built {len(gs)} goldens from the live API -> {path}")
        goldens = json.loads(path.read_text())[: o["limit"]]
        OUT.mkdir(parents=True, exist_ok=True)
        orig = dict(settings.LLM)
        rows = []
        for cfg in o["configs"]:
            r, m = cfg.split(":")
            settings.LLM.update(orig, fast_model=ALIASES.get(r, r), model=ALIASES.get(m, m))
            results = []
            for g in goldens:
                res = run_one(g)
                results.append(res)
                self.stdout.write(f"[{cfg}] {g['id']} {g['type']:<12} {'✓' if res['correct'] else '✗'} {res['intent']:<12} {res['ms']:>6} ms  {g['question'][:60]}")
            settings.LLM.clear()
            settings.LLM.update(orig)
            n = len(results)
            lat = sorted(r["ms"] for r in results)
            tagged = sum(r["tagged"] for r in results)
            summary = {
                "config": cfg, "n": n,
                "accuracy": round(sum(r["correct"] for r in results) / n, 3),
                "intent_accuracy": round(sum(r["intent_ok"] for r in results) / n, 3),
                "numbers_correct": f"{sum(r.get('numbers_ok', False) for r in results)}/{sum('numbers_ok' in r for r in results)}",
                "filters_correct": f"{sum(r.get('filters_ok', False) for r in results)}/{sum('filters_ok' in r for r in results)}",
                "pcn_verified_rate": round(sum(r["verified"] for r in results) / tagged, 3) if tagged else None,
                "untagged_numbers": sum(r["untagged"] for r in results),
                "p50_ms": int(statistics.median(lat)), "p95_ms": lat[min(n - 1, int(0.95 * n))],
                "cost_per_question_usd": round(sum(r["cost"] for r in results) / n, 5),
                "cost_per_1000_usd": round(1000 * sum(r["cost"] for r in results) / n, 2),
            }
            rows.append(summary)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            (OUT / f"{stamp}_{cfg.replace(':', '-')}.json").write_text(json.dumps({"summary": summary, "results": results}, indent=1))
        research = research_checks()
        (OUT / "research_checks.json").write_text(json.dumps(research, indent=1))
        self.stdout.write(json.dumps(research, indent=1))
        md = ["| Config (router:main) | Accuracy | Intent | Numbers | Filters | PCN verified | Untagged | p50 ms | p95 ms | $/question | $/1k |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for s in rows:
            md.append(f"| {s['config']} | {s['accuracy']:.0%} | {s['intent_accuracy']:.0%} | {s['numbers_correct']} | {s['filters_correct']} | "
                      f"{s['pcn_verified_rate'] if s['pcn_verified_rate'] is not None else '—'} | {s['untagged_numbers']} | {s['p50_ms']} | {s['p95_ms']} | "
                      f"{s['cost_per_question_usd']:.4f} | {s['cost_per_1000_usd']:.2f} |")
        (OUT / "summary.md").write_text("\n".join(md) + "\n")
        self.stdout.write("\n".join(md))
