# Research pipeline review: why the "three-year priorities" answer was wrong

> **Purpose:** trace the research agent stage by stage with real data, find where each wrong statement entered, and
> agree on structural fixes before changing code. **Please respond inline** (look for `> **YOUR DECISION:**` blocks).
>
> Case: the Q3 question asked on the landing page, no thematic area named → agent picked **Digital Connectivity**.
> Trace data: [`trace_digital_connectivity.json`](trace_digital_connectivity.json) (generated 2026-10-17 from the
> committed code `f33c0af` and the current working copy; FY26 snapshot).

---

## 0. The answer under review (as you received it)

> **Three-year priorities: Digital Connectivity**
> **Regional focus** – Prioritize Eastern & Southern Africa, which holds 166M✓ of the remaining gap and 26%✓ of people in need. Globally, 244M✓ of an expected 575M✓ broadband users have been reached (42%✓), leaving 331M✓.
> **Accelerate delivery** – Nigeria: 9%✓ delivery against 83.8M✓ expected, 76.2M✓ still to reach. Democratic Republic of Congo: 24%✓ against 59.3M✓; *no active sector projects*. India: 1%✓ against 27.9M✓. Ethiopia: 22%✓ against 32.5M✓.
> **Expand the footprint** – *China: 118M✓ in need, 91.6%✓ need indicator, and no active projects.* Pakistan: 109M✓ in need, with 57.3%✓ need indicator. Bangladesh: 81.8M✓ in need. Indonesia: 77.8M✓ in need.
> **Learn from strong delivery** – *South Sudan (101%✓ delivery)* and Guinea (78%✓).
> **Biggest gap overall:** *Nigeria, with 76.2M✓ people still to be reached at only 9%✓ delivery, within the Eastern & Southern Africa-led regional gap.*

Every number has a ✓ and every ✓ is "true". Yet five statements are wrong or misleading (italics). **That is the core
finding: the ✓ certifies numbers, not statements.**

---

## 1. The pipeline as built

```
 user question
   │
 S0 Route ................ /api/route → pipelines.route()            (LLM router, Haiku 5.5)      assistant/views.py:63, pipelines.py:27
 S1 Choose area .......... analysis.choose_area()                     (rule, code)                 analysis.py:52
   │  (navigate to the outcome workspace, then)
 S2 Assemble data ........ analysis.research() SQL over DuckDB        (code)                       analysis.py:71
      ├ results by country    v_results  (Scorecard getSCSUMMARYDATA, WBG = WB+IFC+MIGA)
      ├ need by country       v_context_latest  (client-context indicator)
      ├ population            v_population (Data360 WDI)
      ├ footprint A           projects (Scorecard getSCResultIndicatorSummary, project level)
      └ footprint B           active_projects (Projects API, matched by sector-name regex) <This regex is not robust. We should not be using regex. I would rather not have something than to be wrong.>
 S3 Derive metrics ....... gap, delivery ratio, people_in_need        (code)                       analysis.py:71
 S4 Prioritize ........... accelerate / expand / strong / focus        (rules, code)                analysis.py:71
 S5 Writer payload ....... R["for_writer"] + claim registration       (code)                       analysis.py:71
 S6 Write ................ LLM writer, RESEARCH_WRITER prompt          (LLM, Sonnet 5.5)            pipelines.py:86, prompts.py:58
 S7 Verify ............... pcn.render(): claim value vs shown value    (code)                       pcn.py:65
 S8 Render ............... message + caveats + artifacts               (code/UI)                    pipelines.py:363, workspace.js
```

---

## 2. Stage by stage (real data)

### S0 · Route
| Input | Output |
|---|---|
| The Q3 question (no area named) | `intent=research`, entities `{topic: None, areas: []}`, by LLM, 3.2 s |

✅ Correct. No issue at this stage.

### S1 · Choose the thematic area
Rule: among outcome areas whose headline indicator counts people, with results for ≥ 40 countries and need data for
≥ 80, pick the **largest absolute remaining gap** (expected − achieved, all countries). <i am worried about these metrics and thresholds. How did you come up witht the 40 and 80%>

| Rank | Outcome area | Indicator | Remaining gap | Countries with results | With need data |
|---|---|---|---|---|---|
| 1 | **Digital Connectivity** | CSC_RES_BRO_INTE | **331M** | 47 | 144 |
| 2 | Green & Blue Planet | CSC_RES_RESI_CLIM_RISK | 303M | 110 | 144 |
| 3 | Energy for All | CSC_RES_ELC_ACCS | 253M | 84 | 143 |
| 4 | Healthier Lives | CSC_RES_HEA_SERV | 127M | 86 | 143 |
| 5 | No Learning Poverty | CSC_RES_EDU_SUPP | 113M | 107 | 83 |

⚠️ **Issue S1-a (rule design):** "largest absolute gap" picks the area where the portfolio's *expectations* are
largest, not where the analysis is most reliable. Digital has the **thinnest country coverage** (47 countries) and its
footprint is dominated by IFC (see S2), which the footprint data cannot see.

> **YOUR DECISION (S1):** keep the agent's own choice rule, or make it prefer data completeness (e.g. Energy), or always
> ask the user to choose? ______ <prefer data completeness or ask. we cannot give incorrect thigns>

### S2 · Assemble data
Five sources are joined per country. Sample rows (current code; values as stored):

| Country | Region | Lending | Achieved | Expected | Internet users % (year) | Population | Scorecard projects (A) | Active sector projects (B) |
|---|---|---|---|---|---|---|---|---|
| Nigeria | AFW | Blend | 7.6M | 83.8M | 41.2 (2024) | 237.5M | 1 | 3 |
| DR Congo | AFE | IDA | 14.4M | 59.3M | 19.7 (2024) | 112.8M | 1 | **0** |
| India | SAR | IBRD | 0.25M | 27.9M | 70.0 (2025) | 1,464M | **0** | 10 |
| Ethiopia | AFE | IDA | 7.0M | 32.5M | 21.9 (2024) | 135.5M | **0** | 3 |
| Kenya | AFE | Blend | 27.7M | 49.5M | 35.0 (2024) | 57.5M | **0** | 3 |
| China | EAP | IBRD | — | — | 91.6 (2025) | 1,407M | 0 | 0 |
| South Sudan | AFE | IDA | 2.85M | 2.83M | 6.7 (**2019**) | 12.2M | 1 | 0 |

⚠️ **Issue S2-a (source coverage, structural):** Results (`v_results`) are **WBG = WB + IFC + MIGA**, but footprint A
(Scorecard project-level table) contains **only World Bank projects** (2,138 projects, all `org = WB`).
For broadband, WBG expected 575M = **IFC 282M** + WB 271M + MIGA 22M, while project-level rows sum to 197M.
→ Ethiopia (32.5M expected) and Kenya (49.5M) show **0 projects**: their results come largely from IFC. <can we pull in the IFC data? do they have an API?>

⚠️ **Issue S2-b (source reconciliation, structural):** footprint B matches Projects-API projects to the theme by a
**regex on sector names** (`ICT`). The "DRC Digital Transformation Project" (P180495) exists in the Projects API but has
**empty sector fields**, so DRC shows **0 active sector projects** while footprint A shows a project contributing
59.3M expected. The two footprint sources are never joined (no `proj_id` link), so they can contradict each other.
→ produced *"DR Congo … no active sector projects"*.

⚠️ **Issue S2-c (universe):** the country universe was "any country with results or need data" (145), including
non-borrowing / upper-middle-income IBRD economies (China). → enabled *"China: 118M in need"*.

⚠️ **Issue S2-d (staleness):** need values have different years (South Sudan 2019 vs most 2024); not surfaced.

### S3 · Derive metrics
| Metric | Formula | Note |
|---|---|---|
| remaining gap | expected − achieved | ✓ |
| delivery ratio | achieved ÷ expected | ✓ — but values > 1 occur (NER 3.59, ZMB 1.79, BRA 1.27, SSD 1.01) |
| people_in_need | population × (100 − need%) / 100 if "higher is better" else population × need% / 100 | here: **people *not using* the internet** |
| direction | `higher_is_better` = **keyword regex on the indicator name** (`pipeline/transform.py:100`) | fragile; Scorecard metadata has `scale_type_code` (e.g. `sequential_rev`) which is not used |

⚠️ **Issue S3-a (semantic layer, structural):** the derived measure "people not using the internet" is carried under
the generic name `people_in_need`, and the context value (91.6 = % **using** the internet) under `need_indicator`.
Fields are named by **role**, not **meaning**, and there is no catalogue that defines each measure (name, unit,
direction). → produced *"91.6% need indicator"* (high value = **low** need).

### S4 · Prioritize (rules in code)
| Rule | Definition | Committed result | Current working copy |
|---|---|---|---|
| Accelerate | expected ≥ p60 AND delivery < 40% → top 4 by gap | NGA, COD, IND, ETH | NGA, COD, IND, ETH |
| Expand | top people_in_need where expected < 25% of need | **CHN**, PAK, BGD, IDN | PAK, BGD, TZA, UGA *(IDA/Blend only)* |
| Strong | 75%–105% delivered, above-median portfolio | **SSD (100.9%)**, GIN (78%) | GIN *(≤ 100%)* |
| Focus region | max people_in_need | AFE (26% of need; 166M gap) | AFE |
| Data-quality | achieved > 100% of expected | NER 359%, ZMB 179%, BRA 127% (not used) | + SSD; excluded from Strong |

⚠️ **Issue S4-a (policy not specified):** eligibility (who can be "expanded") and ranking (absolute people favours
the most populous countries) were my defaults, never agreed. → *China* in Expand.
⚠️ **Issue S4-b (data quality not consumed, structural):** the pipeline's data-quality report flags achieved > expected,
but the analysis did not read those flags; the Strong band allowed up to 105%. → *South Sudan 101% "strong"*.

> **YOUR DECISION (S4):**
> - Country universe: WBG borrowers only (IDA, Blend, IBRD)? ______
> - Expand candidates: IDA + Blend only? ______
> - Expand ranking: absolute people in need / need share / need share with a minimum population? ______
> - Strong delivery band: 75–100%? Data-quality rows (> 100%) excluded and listed as "data checks"? ______

<I don't get anyuthing here>

### S5 · Writer payload (`R["for_writer"]`, committed)
Key names the writer saw (excerpt):
```json
{"indicator": "Number of people using broadband internet",
 "need_indicator": "Percentage of population using the internet",
 "world": {"achieved": {"display": "244M", "claim": "c4bef2553"}, "remaining_gap": {"display": "331M", ...}, ...},
 "regional_focus": {"region": "Eastern & Southern Africa", "remaining_gap": {...}, "share_of_people_in_need": {...}},
 "accelerate_delivery": [{"country": "Nigeria", "region": "Western & Central Africa", "delivery_rate": {...},
     "people_in_need": {...}, "need_indicator": {"display": "41.2%", ...}, "active_sector_projects": 3}, ...],
 "expand_footprint": [...], "strong_delivery": [...]}
```
⚠️ **Issue S5-a (structural):** relationships are implicit. "Nigeria is in AFW" is a string field; "AFE is the focus
region" is a separate object; "world" vs "biggest" is not defined. Nothing tells the writer which statements are
allowed (e.g. no superlative is pre-computed for "biggest gap").

### S6 · Write (LLM)
Committed prompt ended with: *"Then one sentence: **Biggest gap overall:** …"* (`git show f33c0af:…/prompts.py:69`).
The writer filled "biggest gap overall" with a **country** (Nigeria, the largest single-country gap) and attached it
to the **focus region** (AFE): a relationship invented by the LLM.

A re-run on the same payload (current prompt, which says "**Overall:** all-countries total") produced a different text
(full raw output in the trace JSON): correct regions this time, but still *"South Sudan … 101% **of its target**"*,
*"China … no active projects"*, and counts like *"3 active projects"*. **The output is stochastic**, so a prompt fix
moves the error around; it does not remove it.

### S7 · Verify (Proof-Carrying Numbers)
All 19 tagged numbers in the re-run were ✓. Examples of what each ✓ actually checked:

| Shown | ✓ | Claim label (what the registry knows) | What the sentence asserted |
|---|---|---|---|
| 101% | ✓ | `achieved ÷ expected` · South Sudan | "**strong delivery**", "**of its target**" |
| 118M | ✓ | `population × need share (IT_NET_USER_ZS)` · China | "China should **expand**" |
| 91.6% | ✓ | `Percentage of population using the internet` · China | "**need indicator**" (inverted meaning) |
| 76.2M | ✓ | `expected − achieved` · Nigeria | "**biggest gap overall** … within **AFE**" |
| "3 active projects" | (not tagged) | — | counts ≤ 9 are exempt from tagging (`pcn.py:91`) |

⚠️ **Issue S7-a (structural, most important):** a claim stores `{value, unit, source text}`; `pcn.check()` compares
**only the shown value** with that value (`pcn.py:54`). It never checks the **subject** (which country), the **measure**
(which metric), **relationships** (region membership), or **superlatives**. ✓ therefore means "this number exists",
which readers will understand as "this statement is true". Small counts are not checked at all.

### S8 · Render
Caveats are shown in a collapsed "How I got this" section; the data-quality list is appended there. Artifacts (matrix,
deck, notebook) reuse S4 outputs, so S2–S4 errors propagate into the deck and notebook too.

---

## 3. Each wrong statement → stage → structural cause

| # | Statement | Entered at | Structural cause |
|---|---|---|---|
| 1 | "China: 91.6% need indicator" | S3 → S5 → S6, passed S7 | No semantic layer (role-named fields, regex direction) + value-only verification |
| 2 | "Biggest gap overall: Nigeria … within the AFE-led gap" | S6, passed S7 | Writer free to compose superlatives/relationships; none pre-computed or checked |
| 3 | "DR Congo … no active sector projects" | S2 (footprint B) | Two footprint sources not reconciled; sector regex fails on empty sector fields |
| 4 | "South Sudan 101% strong delivery" | S4 | Data-quality flags not consumed by analysis; threshold > 100% |
| 5 | "China, Indonesia … expand" | S2/S4 | Country universe and eligibility policy never specified |
| – | Ethiopia / Kenya "0 projects" (latent) | S2 (footprint A) | Project-level table is WB-only; results are WB + IFC + MIGA |
| – | "3 active projects" (unverified) | S7 | Counts ≤ 9 exempt from verification |
| – | Eval scored 100% | eval design | Goldens checked numbers only; no research or relationship checks |

---

## 4. Proposed structural fixes (per stage)

| Fix | Stage | What changes | Effort |
|---|---|---|---|
| **A. Semantic claims + statement assembly** | S5–S7 | A claim = `{entity, entity_type, measure_id, value, unit, period, source}`. The LLM returns a **structured plan** (sections → ordered claim ids + connective prose **without numbers**). The server renders every factual phrase from claim metadata ("Nigeria (Western & Central Africa): 9% delivered of 83.8M expected"). Superlatives / rankings only via **rank claims** computed in code. Counts become claims too. Verification checks claim ↔ entity in the same list item. | ~2 h |
| **B. Measure catalogue** | S3, S5 | One table of measures: id, display name, definition, unit, direction (from Scorecard `scale_type_code` + reviewed overrides), e.g. `internet_users_pct` (higher = better), `people_without_internet` (derived). Analysis outputs measure ids, never `need_*`. | ~45 min |
| **C. Data-quality flags in the data model** | pipeline, S4 | `v_results.quality_flag` (`above_expected`, `subindicator_only`, `low_threshold`) computed in the pipeline; analysis excludes flagged rows from rankings and lists them as data checks. | ~30 min |
| **D. Footprint by institution and project id** | S2 | Footprint = results by institution (WB / IFC / MIGA split already in `v_results` at aggregate level) + WB project-level rows joined to the Projects API on `proj_id` (no sector regex). State explicitly that IFC/MIGA country-level project attribution is not public in this API. | ~45 min |
| **E. Policy configuration** | S1, S4 | Your decisions above in one documented config (universe, eligibility, ranking, bands); shown in "How I got this". | ~15 min |
| **F. Evaluation with semantic assertions** | eval | Research goldens asserting: every country's region correct; expand ⊆ eligibility; strong ⊆ (0.75, 1.0]; no "target" wording; measure names correct; footprint counts consistent across sources. | ~45 min |

> **YOUR DECISION (fixes):** which of A–F to implement now, and in what order? My recommendation: **E → C → B → D → A → F**
> (settle policy and data semantics first, so A renders correct statements from correct data). ______

---

## 5. State of the working copy (uncommitted)

Already applied after the first diagnosis (before this review), uncommitted:
- `analysis.py`: universe = IDA/Blend/IBRD; Expand = IDA/Blend; Strong ≤ 100%; writer keys renamed
  (`all_countries_total`, `context_indicator` with name + direction, `people_without_access`, `scorecard_projects_contributing`).
- `prompts.py`: extra FACTS rules for the research writer (prompt-level; would be superseded by fix A).
- `pipelines.py` / `artifacts.py`: key renames; "target" wording repair turn (also prompt-level).
- Not applied: notebook alignment for the new rules (the notebook currently still uses the old Expand rule).

> **YOUR DECISION (working copy):** keep these as the starting point for E/C, or revert to `f33c0af` first? ______

---

## Appendix: reproduce the trace
```bash
# from q1_prototype/, with .env configured
python ../docs/review/trace_research.py 10 ../docs/review/trace_digital_connectivity.json   # 10 = Digital Connectivity
```
The trace script runs S0–S7 for the committed and current code, saving inputs/outputs of every stage, the writer's
raw claim-tagged text and a per-claim verification table.
