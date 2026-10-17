# Q3 · Scorecard analytics and executive deck: No Learning Poverty

**Deliverables**
- **Q3B deck:** [`output/deck_no-learning-poverty.pdf`](output/deck_no-learning-poverty.pdf), also as [HTML](output/deck_no-learning-poverty.html).
- **Reproducible workflow:** [`output/notebook_no-learning-poverty.ipynb`](output/notebook_no-learning-poverty.ipynb). The [executed copy](output/notebook_no-learning-poverty.executed.ipynb) holds the outputs of a live run.
- **Country extract:** [`output/priorities_no-learning-poverty.csv`](output/priorities_no-learning-poverty.csv).
- **Q3A data pipeline:** [`pipeline/`](../pipeline/README.md), shared with the Q1 app.

## How the deck and notebook are produced

The deck is the web app's **3-slide briefing** export, and the notebook is the code that comes with that briefing. In the app,
open an outcome area and ask for a briefing ("3-slide briefing + notebook"). The briefing has a **Slides | Notebook**
switch: export the deck as HTML/PDF, and copy or download the notebook. `build_deck.py` runs the same export from the
command line with the same code:

```bash
python q3_scorecard_deck/build_deck.py --execute     # deck (HTML + PDF), notebook, executed notebook, CSV
python q3_scorecard_deck/build_deck.py --outcome 9   # the same briefing for any other outcome area
```

| Step | Code (shared with the app) | What it does |
|---|---|---|
| Analysis | `assistant/analysis.py` `research()` | WBG results for every borrowing country (IDA, Blend, IBRD), regions and institutions; flags data checks |
| Deck | `assistant/artifacts.py` `deck()` | Three slides; every number is rendered from a verified claim; titles computed from the data; no LLM text |
| Notebook | `assistant/artifacts.py` `notebook()` | Rebuilds each slide from the **public APIs** (not our database) and checks it against the deck |

The notebook runs anywhere with `pip install requests pandas plotly` and needs no API key. Its last run (in
`notebook_no-learning-poverty.executed.ipynb`) passed **12 of 12 checks** against the deck:
- the world total and its split by World Bank, IFC and MIGA;
- the 7 regions;
- the top 3 countries.

## The story (FY26 snapshot)

**Question:** which areas and countries should a three-year plan prioritise, and where are the biggest gaps?

**Slide 1 · Where the portfolio stands.** The active portfolio has supported **326.6M students** of the **439.2M** it is
expected to reach (**74%**), so **112.6M** are still to be reached. Almost all of it is the World Bank: 323.8M achieved of 436.5M
expected (IFC 2.8M; MIGA 2.5K).

**Slide 2 · Where results remain.** **Western & Central Africa holds the most still to deliver** (47.4M; 41% delivered),
followed by Eastern & Southern Africa (21M; 79%) and East Asia & Pacific (18M, with only 15% delivered so far).

**Slide 3 · Three-year priorities.** Countries are selected by **one rule: most results still to deliver (expected −
achieved)**. The chart shows the rule: still to deliver up, share delivered across (context only), and a dashed line
between the 3rd and 4th country.
- **Nigeria:** 24.8M still to deliver, 24% delivered.
- **Philippines:** 16.1M still to deliver, 5% delivered.
- **Uganda:** 8.6M still to deliver, 10% delivered.

All three combine a large remaining portfolio with early delivery.

**What the data does not support:** 23 countries report achieved above expected (for example Tanzania, Mozambique,
Nepal). A "delivery rate" above 100% is not meaningful there, often because a project carries the Scorecard's Results
Overlap Flag. These countries are listed as data checks and are not ranked.

## Method choices

- **Expected is not a target.** It is what the active portfolio is expected to deliver. The deck says so on slide 2.
- **No thresholds.** Lists are ranked by a single measure; no invented cut-offs ("below 40%") decide anything.
- **No model-written claims on slides.** In testing, model-written comparisons included false statements (for example,
  "the region furthest behind" while another region was further behind) that validators cannot catch. The deck is therefore fully
  deterministic. The AI is used only to understand questions in the app.
- **Project-level ground truth.** For this indicator, the 323 World Bank projects behind the numbers add up exactly to the
  published World Bank total (`v_project_reconciliation`). They are browsable, with links, in the app's World Bank
  Operations table.
