"""Build the Q3 executive deck (3 slides) + reproducible notebook + data extract for one thematic area.

    python q3_scorecard_deck/build_deck.py                 # Energy for All (outcome 9)
    python q3_scorecard_deck/build_deck.py --outcome 2     # another outcome area
    python q3_scorecard_deck/build_deck.py --no-llm        # deterministic slide text (no API key needed)

Uses the same verified analysis as the web app (assistant.analysis.research): Scorecard results by country, client-context
need, Data360 population and the operational footprint (Scorecard project-level + Projects API). Slide titles can be
drafted by the LLM, but every number in them must pass Proof-Carrying-Numbers verification or it is flagged.
Outputs go to q3_scorecard_deck/output/: deck .html, deck .pdf (headless Chrome), notebook .ipynb, priorities .csv.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "q1_prototype"
OUT = Path(__file__).resolve().parent / "output"
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scorecard_explorer.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from assistant import analysis, artifacts, llm, pcn, pipelines  # noqa: E402

CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium", "chromium-browser"]


def standalone_html(deck: dict) -> str:
    static = APP / "explorer" / "static" / "explorer"
    css = (static / "app.css").read_text()
    js = (static / "common.js").read_text() + "\n" + (static / "charts.js").read_text()
    data = json.dumps(deck).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{deck['title']}</title>
<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<style>{css}
body{{background:#e9edf1;padding:24px}}.slidewrap{{width:1280px;height:720px!important;margin:0 auto 24px;page-break-after:always;break-after:page}}
.slide{{position:relative!important;transform:none!important}}.claim{{border:0}}.claim .b{{display:none}}
@media print{{body{{padding:0;background:#fff}}.slidewrap{{margin:0;box-shadow:none}}}}.slidewrap:last-child{{page-break-after:auto;break-after:auto}}.sgrid{{grid-template-columns:690px 1fr!important}}.kpis{{grid-template-columns:repeat(4,1fr)!important}}@page{{size:1280px 720px;margin:0}}</style>
</head><body><div id="deck"></div><script id="deck-data" type="application/json">{data}</script>
<script>{js}
renderDeck(document.getElementById('deck'), JSON.parse(document.getElementById('deck-data').textContent), {{exportMode:true}})
  .then(()=>document.body.setAttribute('data-ready','1'));</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome", type=int, default=9, help="Scorecard outcome area id (9 = Energy for All)")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    if a.no_llm:
        settings.LLM.update(api_key="", api_base=None)
    claims = pcn.Claims()
    R = analysis.research(a.outcome, claims)
    usage = []  # the deck is fully deterministic: titles and selection are computed from the data
    deck = artifacts.deck(R, claims)
    stats = {"numbers_rendered_from_claims": len(claims.store), "selection": [x["name"] for x in R["most_to_deliver"][:3]]}
    OUT.mkdir(parents=True, exist_ok=True)
    slug = R["outcome"]["slug"]
    html_path = OUT / f"deck_{slug}.html"
    html_path.write_text(standalone_html(deck))
    nb_path = OUT / f"notebook_{slug}.ipynb"
    nb_path.write_text(json.dumps(artifacts.notebook(deck), indent=1))
    csv_path = OUT / f"priorities_{slug}.csv"
    top_gap, top_people = {x["code"] for x in R["most_to_deliver"]}, {x["code"] for x in R["most_people"]}
    with csv_path.open("w", newline="") as f:
        cols = ["code", "name", "region_name", "lending", "fcs", "achieved", "expected", "flag", "need_value", "need_year",
                "population", "pop_year", "people"]
        w = csv.DictWriter(f, fieldnames=cols + ["still_to_deliver", "delivery_rate", "in_most_to_deliver", "in_most_people"])
        w.writeheader()
        for x in sorted(R["rows"], key=lambda x: -(x.get("gap") or 0)):
            w.writerow({**{k: x.get(k) for k in cols}, "still_to_deliver": x.get("gap"), "delivery_rate": x.get("rate"),
                        "in_most_to_deliver": x["code"] in top_gap, "in_most_people": x["code"] in top_people})
    pdf_path = OUT / f"deck_{slug}.pdf"
    chrome = next((c for c in CHROME if Path(c).exists() or shutil.which(c)), None)
    if chrome:
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                        f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=False, capture_output=True)
    print(json.dumps({"outcome": R["outcome"]["name"], "checks": stats,
                      "most_to_deliver": [x["name"] for x in R["most_to_deliver"]], "most_people": [x["name"] for x in R["most_people"]],
                      "data_checks": [x["name"] for x in R["data_checks"]], "usage": usage,
                      "files": [str(p.relative_to(ROOT)) for p in (html_path, pdf_path, nb_path, csv_path) if p.exists()]}, indent=1, default=str))


if __name__ == "__main__":
    main()
