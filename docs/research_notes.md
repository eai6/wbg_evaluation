# Research Notes — WBG Scorecard Data Access (2026-10-17)

How the public Scorecard site (scorecard.worldbank.org) gets its data, reverse-engineered from the
site's Angular bundle (`main.<hash>.js`) and verified with live requests.

## 1. Architecture of the public site

- Angular single-page app. All data comes from two Azure API Management (APIM) backends:
  | Backend | Base URL | Purpose |
  |---|---|---|
  | Data API | `https://ext.api.worldbank.org/api/Scorecard/` | Indicator metadata, values, project-level results |
  | CMS API | `https://scorecardcmsapi.worldbank.org/scorecard/cache/` | Outcome-area text, narratives, page content |
- Every request carries an `apikey` HTTP header. The keys are **public**: they are shipped in the site's
  frontend bundle (`environment.apiKey.data` / `.cms`) and sent by every visitor's browser.
  The pipeline should read the key from the live bundle at runtime (env-var override), not hardcode it.
- Responses are **Databricks SQL Statement API** payloads:
  `manifest.schema.columns[]` (names/types) + `result.data_array[][]` (rows, all values as strings).
  Large results are chunked (`manifest.total_chunk_count`, e.g. `getSCGEOLOC` = 5 chunks / 84,659 rows,
  only chunk 0 returned inline) — pipeline must handle this.

## 2. Endpoints (verified working = ✅)

| Endpoint | Params | Returns |
|---|---|---|
| ✅ `getSCMETADATA` | `snapshotfy` | 52 indicators: 8 Vision, 22 Client Context, 22 WBG Results; definitions, units, outcome area, WB/IFC/MIGA flags, disaggregation flags (64 cols) |
| ✅ `getSCSubIndicatorMetaData` | `snapshotfy` | 22 sub-indicators (e.g. electricity: new vs existing connections) |
| ✅ `getSCCountryDATA` | `snapshotfy` | 249 economies: ISO2/ISO3, WB region, FCV flag, LDC, income class, IDA/IBRD eligibility, SIDS, small state |
| ✅ `getSCSUMMARYDATA` | `refareatype` (REGION/COUNTRY/FCS), `refareacode`, `orgCode` (ALL/WB/IFC/MIGA), `snapshotfy` | **Main values table** (~600–690 rows per area): achieved / expected / cumulative values, time period, sex/age/disability disaggregation, unit multiplier |
| ✅ `getSCResultIndicatorSummary` | `key=ind_code&value=<code>`, `snapshotfy` | **Project-level** contributions to a results indicator (288 projects for electricity): project ID/name, country, approval/closing FY, practice, commitments (IBRD/IDA), baseline/progress/target values |
| ✅ `getSCGEOLOC` | — | 84k project geo-locations (lat/lon, admin units) — chunked |
| ✅ `IndicatorsDownloaded?indType=Metadata&indCode=Scorecard_Metadata` | | Metadata as XLSX |
| ✅ CMS `get_outcomes_indicators` | `fy` | 15 outcome areas with descriptions + indicator mapping |
| CMS `get_outcome`, `get_narrative`, `get_home_narratives`, `get_related_content`, `get_datacorrections` | | Narrative text (not yet tested) |
| ❌ `getSCSUMMARYDATAXLSX`, `getSCSummayDataByType`, `getFYList` | | 500/404 with the params tried |
| ❌ `swaggerJson` | | 401 (needs a different key) |

**Parameter notes**
- `refareacode` for COUNTRY is **ISO2** (`KE` works, `KEN` returns 0 rows).
- Region codes: `ACW` (All Countries / World), `AFE`, `AFW`, `EAP`, `ECA`, `LCR`, `MENAAP`, `SAR`, `OTH`; plus `refareatype=FCS&refareacode=FCS`.
- Snapshots available: **FY2024, FY2025, FY2026** (`snapshotfy`).
- Default disaggregation used by the site: `sex=_T, age=_T, disability=_T` (`_T` = total). Other values: `F`, `Y14T24` (youth), `Yes` (disability).

## 3. Data model (WBG Results)

- Key: `snapshot_fy × ind_code × sub_ind_code × org_code (WBG/WB/IFC/MIGA) × ref_area × sex × age × disability × ind_time_per`.
- **Achieved vs expected**: `ind_achieved_val` (delivered so far) vs `ind_expected_val` (expected from active portfolio).
  The achieved/expected ratio is a natural "delivery" metric for both Q1 and Q3.
- Values are pre-scaled: `ind_achieved_val` = display value (e.g. `214.5` with `achieved_uom_display_code=M`);
  `ind_base_achieved_val` = raw number (`2.145E8`). Use the base values for analysis.
- Vision & Client Context indicators have **time series** (2011–2024, calendar years); WBG Results are a single
  reporting point per snapshot (`2025-06-30` for FY25). Trends for Results therefore come from comparing snapshots.
- Data quirks spotted already: everything typed as strings, scientific notation (`1.9490347E7`),
  nulls, mixed casing in outcome-area names across endpoints ("Digital connectivity" vs "Digital Connectivity"),
  an outlier where achieved ≫ expected (displaced-people services: 818.1 vs 8.5) — cleaning step required.

**15 outcome areas → 22 WBG Results indicators**
| # | Outcome area | Results indicator(s) |
|---|---|---|
| 1 | Protection for the Poorest | Social safety net beneficiaries (WB only) |
| 2 | No Learning Poverty | Students supported with better education |
| 3 | Healthier Lives | People receiving health services; economies with health-emergency capacity |
| 4 | Effective Macro & Fiscal Mgmt | Tax revenue reforms; debt sustainability reforms (WB only) |
| 5 | Green & Blue Planet, Resilient Populations | Climate-resilience beneficiaries; net GHG emissions; hectares under conservation |
| 6 | Water & Sanitation | People provided with WASH |
| 7 | Sustainable Food Systems | Food & nutrition security beneficiaries |
| 8 | Connected Communities | Transport access beneficiaries |
| 9 | Energy for All | People with electricity access; GW renewables enabled |
| 10 | Digital Connectivity | Broadband users |
| 11 | Digital Services | Digitally enabled services users |
| 12 | Gender Equality & Youth | Gender-equality beneficiaries; financial services (women) |
| 13 | FCV | Displaced people & host communities served |
| 14 | More and Better Jobs | New or better-paid jobs |
| 15 | More Private Investment | Private capital enabled; private capital mobilized |

## 4. Other relevant sources

- **World Bank Data Catalog — "World Bank Group Scorecard"** (dataset 0066369, CC-BY 4.0): catalog entry only,
  links back to the site; no bulk file. The live API above is the real source.
- **World Bank Open Data / WDI API** (`api.worldbank.org/v2`): many Vision/Client Context indicators share WDI codes
  (`dec_ind_code`, e.g. `EG_ELC_ACCS_ZS` = `EG.ELC.ACCS.ZS`) → can enrich with population, GDP, etc.
- **Projects API** (`search.worldbank.org/api/v2/projects`) and **Documents & Reports API**
  (`search.worldbank.org/api/v3/wds`): project details/documents keyed by `proj_id` from `getSCResultIndicatorSummary`.
- Background: the scorecard was redesigned in 2024 (from ~150 to 22 results indicators).

Sources:
- https://scorecard.worldbank.org
- https://datacatalog.worldbank.org/search/dataset/0066369/world-bank-group-scorecard
- https://www.worldbank.org/en/news/press-release/2024/04/09/world-bank-group-announces-new-approach-to-measuring-impact
- https://ieg.worldbankgroup.org/sites/default/files/Data/reports/report-approach_paper-WBG_Scorecard_Formative_Evaluation.pdf
- https://www.brettonwoodsproject.org/2024/10/new-world-bank-corporate-scorecard-overlooking-client-priorities-and-ignoring-development-impact/

---

# Part 2 — Current Scorecard UX & how others build LLM-powered data interfaces

## 5. Current Scorecard user journey (observed on the live site)

1. **Outcome Areas landing** — 15 static tiles (icon, name, vertical tag: People / Prosperity / Planet /
   Infrastructure / Digital). No numbers on the tiles — the user must click to see anything.
2. **Outcome-area page** — filter chips (World Bank Group org, Countries/Economies, WBG Regions, Income
   Groups, Country Groups, Female*, Youth*, Disability-Inclusive*; * = Results only), then per indicator:
   - **Client Context card** → headline value + time-series line (e.g. learning poverty 53.6%, 2019).
   - **WBG Results card** → "Active Portfolio Results" Achieved vs Expected (e.g. 326.6M / 439.2M students)
     + choropleth map toggling Achieved / Expected.
3. Pain points: answering one question ("learning poverty in Ghana?") needs several clicks across filter
   dropdowns; no comparison across countries/areas; no "so what" narrative; tiles give no sense of
   performance at a glance.

## 6. Prior art — LLM + development/statistical data

| Product | Pattern | Takeaway for us |
|---|---|---|
| **World Bank Data AI Chatbot** (Next.js + FastAPI, LiteLLM, default `gpt-4o-mini`) | LLM calls Data360 **MCP tools** (search indicator → get series → metadata → Vega-Lite chart). Charts render in a side "artifact" panel. | Same institution, same pattern: tool-calling over a curated data API, not free-form SQL. |
| **Proof-Carrying Numbers (PCN)** — WB Development Data Group, arXiv 2509.06902 | Every number in the answer is checked *by the renderer* against tool results; verified numbers get a ✓ badge + source link, everything else defaults to "unverified". | Directly answers the brief's "guardrails against hallucinated numbers". We can implement a light version: cross-check numbers in the answer against the tool-call results and badge them. |
| **Google Data Commons — Explore** | LLM only **maps the question to the data vocabulary** (place, variable, comparison type) and picks a chart; it never generates values. Answers are a page of charts with provenance. | "LLM as router/filter-setter, data layer produces the numbers." Fits the Scorecard's filter model perfectly. |
| **Statista Research AI, YouGov Crunch AI Agent, ServiceNow AI Data Explorer** | NL question → chart + short narrative over a proprietary curated database. | Commercial norm: answer = chart + 2–3 sentence summary + source. |
| Tableau Research (25k-dashboard study; Lexara LLM-eval toolkit) | Simple charts + text dominate effective dashboards; evaluate LLMs with graded test questions. | Keep charts simple; build a small eval question set to justify model choice. |

No comparable public LLM interface found from IMF, UNDP, OECD or ADB data portals.

## 7. Design implications for the Q1 prototype

1. **LLM as a "conversational filter bar"**: NL query → structured filter state
   (`indicator, area_type, area_code, org, sex/age/disability, snapshot_fy`) → the *same* two canonical
   visuals the site already uses (trend card + achieved/expected map). Filters stay visible as editable chips,
   so the user sees exactly what the LLM understood (transparency, easy correction).
2. **Analyst mode** for open questions ("compare FCS vs non-FCS", "top lagging indicators"): tool-calling over
   a fixed set of typed query functions on DuckDB (no arbitrary SQL by default) → table/chart + narrative.
3. **Numbers are never generated by the LLM**: tool results are the only source; PCN-style verification
   badges on every figure; a "show data / query" expander for provenance.
4. **Landing page with numbers**: turn the 15 static tiles into live "delivery" tiles (achieved vs expected
   progress bar per results indicator, client-context need sparkline), with an "Ask the Scorecard" bar and
   suggested questions on top.

Additional sources:
- https://github.com/worldbank/data-ai-chatbot
- https://github.com/worldbank/data360-mcp
- https://arxiv.org/abs/2509.06902
- https://blogs.worldbank.org/en/opendata/strengthening-governance-and-trust-in-ai-based-data-disseminatio
- https://datacommons.org/faq
- https://arxiv.org/pdf/2409.13741
- https://www.tableau.com/en-gb/blog/research

---

# Part 3 — Review of World Bank open-source repos (data360-mcp, data-ai-chatbot)

Both repos were cloned read-only into a scratch directory and reviewed without running code.

## 8. Data360 API (beyond-the-Scorecard data) — verified live

- Base: `https://data360api.worldbank.org/data360` — **public, no API key**.
- `GET /data?DATABASE_ID=WB_WDI&INDICATOR=WB_WDI_<WDI code with _>&REF_AREA=<ISO3,...>&timePeriodFrom=&timePeriodTo=&top=&skip=`
  → `{"count": n, "value": [{OBS_VALUE, TIME_PERIOD, REF_AREA, UNIT_MEASURE, UNIT_MULT, ...}]}`.
  Verified: `WB_WDI_EG_ELC_ACCS_ZS` (Ghana 2018–2023: 80.4 → 89.5), `WB_WDI_SP_POP_TOTL`.
- Scorecard `dec_ind_code` maps to Data360 by prefixing `WB_WDI_` (works for WDI-sourced indicators;
  `SE_LPV_PRIM` is not in WDI — use the Scorecard's own country data for learning poverty).
- Country codes: Data360 = **ISO3**, Scorecard = **ISO2** → join via `cntry_iso3_code` from `getSCCountryDATA`.
- Other endpoints (from repo): `POST /portal/v1/public_data360_search` (indicator search), `POST /metadata`,
  `POST /portal/v1/dimensions`, `GET /indicators?datasetId=WB_WDI`.
- Decision: **call the REST API directly from Django** with a fixed allowlist of ~10 contextual WDI indicators
  (population, GDP per capita, poverty, electricity access, internet use, ...), cached. Running the MCP server
  or importing the `data360-mcp` package is not worth it (async, heavy deps: fastmcp, pandas 3, sklearn, Azure OTel).
- License: data360-mcp is MIT + WB IGO Rider; data-ai-chatbot is Apache-2.0 + IGO Rider. We re-implement
  patterns (not copy code) and credit both repos.

## 9. Patterns adopted from data-ai-chatbot

| Pattern | Their implementation | Our Django version |
|---|---|---|
| **Proof-Carrying Numbers** | Tool server stamps each data row with `claim_id = crc32(json.dumps(row, sort_keys=True))`; LLM must write `<claim id="…">value</claim>`; renderer verifies against stored source value (`auto` / `rounded` policies); "never invent a claim_id — if no id, don't present the value" | Python: tools stamp rows → session claim registry → regex-parse the LLM answer → verify (exact / rounded / tolerance, unit-scale aware) → render ✓ verified / ⚠ unverified badges with source tooltip, server-side |
| **Retrieval ≠ writing** | Research node calls tools; narrator gets RAW TOOL RESULTS JSON in the system message and writes; numbers never pass through an extra LLM paraphrase | Tool loop (≤5 calls) → final answer prompt with raw tool JSON + grounding rules |
| **Cheap JSON router** | temp 0, `json_object`, intents quick_answer / research / explain / clarify / out-of-scope | Router decides: **set filters** (drive the indicator page) vs **analyst answer** vs **clarify / out-of-scope** |
| **Grounding prompt rules** | Use ONLY tool results; no qualitative labels ("high/low") without a tagged benchmark; always units + year; Sources + Limitations sections; prompt-injection resistance block | Same rules, adapted to Scorecard semantics (achieved vs expected, snapshot FY) |
| **Quick-answer card + follow-up chips** | `single_fact` / `comparison` / `trend` cards; 2–3 follow-ups in the user's voice | Answer card with headline number + chart + chips (HTMX) |
| **Thinking vs answer channels** | SSE with separate thinking/tool events | Collapsible "How I got this" panel listing tool calls & filters |
| **LiteLLM provider abstraction** | `MODEL_PROVIDER` + model; role-split models | `.env`: `LLM_MODEL` (any LiteLLM id), `LLM_API_KEY`, optional `LLM_API_BASE` → plug-and-play for reviewers |
| **Evals** | DeepEval personas + LLM judge | Lightweight: ~12 golden questions with known answers; per model measure routing accuracy, **PCN verified rate**, untagged-number count, refusal correctness, latency, cost → model-choice table |
| **Security** | Content-policy catch, server-side identity, CSRF origin, rate limits, explicit CORS, sanitizer allowlist, generic 500s | Django CSRF + autoescape, allowlisted tool args (regex-validated codes), read-only typed tools (no free SQL), rate limit on `/ask`, generic errors, secrets only in `.env` |

## 10. Proposed Q1 architecture (Django)

```
                ┌───────────────────── pipeline/ (shared with Q3) ─────────────────────┐
 Scorecard API ─┤ fetch (apikey from live bundle) → chunk-aware parse → clean → tidy  │
 Data360 API  ──┤ allowlisted WDI context indicators (ISO3)                            ├─► data/scorecard.duckdb
                └──────────────────────────────────────────────────────────────────────┘    + parquet snapshots
                                                                                              │
 Django app (q1_prototype/)                                                                  ▼
  ├─ pages:  /  (live outcome tiles + Ask bar)   /outcome/<id>  (filters + trend + map)  /ask
  ├─ api:    /api/indicator-data?filters…  (JSON for Plotly)
  └─ llm/
      ├─ router.py      NL → {mode: filters|analyst|clarify|out_of_scope, filters{…}}
      ├─ tools.py       typed, read-only DuckDB queries; every row stamped with claim_id
      ├─ agent.py       LiteLLM tool-calling loop (≤5 calls) → narrator with raw tool JSON
      └─ pcn.py         claim registry + verification → ✓ / ⚠ badges
  Frontend: Django templates + HTMX + Plotly.js (+ a light map); no SPA build step
```
