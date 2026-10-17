# Scorecard data pipeline

Reproducible extract → transform → load → validate pipeline for the **WBG Corporate Scorecard**, plus World Bank
**Data360** and the **Projects API**. It feeds both the Q1 web app and the Q3 analysis/deck.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pipeline                      # all snapshots (FY24-FY26), ~3-4 minutes
python -m pipeline --skip-extract       # rebuild tables from cached raw files (seconds)
python -m pipeline --refresh            # force re-download
python -m pipeline --snapshots 2026 --countries-limit 5   # quick smoke test
```

Output:
| Path | Content |
|---|---|
| `data/raw/` | Unmodified API extracts (Parquet, all columns as text), one folder per snapshot + `global/` |
| `data/processed/*.parquet` | Clean, typed tables (below) |
| `data/scorecard.duckdb` | Same tables + analysis views; this is what the web app reads (read-only) |
| `data/processed/data_quality.json` | Data-quality report |

## Sources and access
| Source | Endpoint(s) | Auth |
|---|---|---|
| Scorecard data API | `ext.api.worldbank.org/api/Scorecard/` `getSCMETADATA`, `getSCSubIndicatorMetaData`, `getSCCountryDATA`, `getSCSUMMARYDATA` (per region / FCS / institution / country), `getSCResultIndicatorSummary` (project level) | public `apikey` header |
| Scorecard CMS API | `scorecardcmsapi.worldbank.org/scorecard/cache/` `get_outcomes_indicators`, `get_home_narratives` | public `apikey` header |
| Data360 | `data360api.worldbank.org/data360/data` (WDI population, GDP per capita) | none |
| Projects API | `search.worldbank.org/api/v2/projects` (all active projects) | none |

The Scorecard site is an Angular app; its two API keys are shipped in its JavaScript bundle and sent by every
visitor's browser. `clients.scorecard_keys()` reads them from the live bundle at run time (no hardcoded secrets);
set `SCORECARD_API_KEY` / `SCORECARD_CMS_KEY` to override. Responses are Databricks SQL result sets
(`manifest.schema.columns` + `result.data_array`, all values as strings); multi-chunk results are flagged.

Requests run in parallel (10 workers) with retries and exponential backoff; failures are logged to
`data/raw/fy*/summary_failures.json` instead of aborting the run.

## Tables
| Table | Grain | Notes |
|---|---|---|
| `areas` | area | 8 region codes (incl. `ACW` = all countries), `FCS`, and ~245 countries keyed by **ISO3** with region, FCS flag, income group, IDA/IBRD, LDC, SIDS |
| `outcomes` | outcome area | 15 areas from the CMS (name, description, vertical, slug) |
| `indicators` / `sub_indicators` | indicator | type (`results` / `context` / `vision`), unit, outcome, definitions, WB/IFC/MIGA flags, `higher_is_better` |
| `results` | snapshot × indicator × sub-indicator × institution × area × sex × age × disability × joint programming × eligibility | `achieved`, `expected`, cumulative, unit, flags |
| `context` | snapshot × indicator × sub-indicator × area × sex × age × disability × year | `value` (client context and vision time series) |
| `projects` | snapshot × indicator × project × disaggregation | project-level contributions: country, commitments (total/IBRD/IDA), achieved, expected |
| `active_projects` | project × country | Projects API: commitment, sectors, dates (regional projects have no single country) |
| `wdi` | indicator × country × year | Data360 population and GDP per capita |
| `stories` | story | CMS results narratives with images and links |

Views: `v_results` (WBG totals with `remaining_gap` and `delivery_ratio`), `v_results_female`, `v_context`,
`v_context_latest`, `v_population`, `v_snapshots`.

## Cleaning rules (the data is not clean)
- **Numbers arrive as text**, sometimes in scientific notation (`1.949E7`); parsed to floats. The `*_base_*` fields
  carry full precision; the display fields are rounded (`214.5` + unit multiplier), so base values are used.
- **Country codes** are the Bank's ISO2-like codes (e.g. `ZR` for DR Congo, `XK` Kosovo); they are mapped to ISO3
  with the Scorecard's own country table, not a generic ISO list.
- **Periods** are usually dates (`2023-12-31`) but some are ranges (`2011-2021`); the text is kept and `year` = end year.
- **Duplicates:** rows returned by several requests (e.g. WBG totals in institution queries) are de-duplicated on the
  full natural key; where the source repeats a key with conflicting values (an all-zero row next to the real one,
  e.g. Türkiye FY24), the row with the largest expected value is kept and the count is logged (19 rows).
- **Dimensions:** `_T` = total for sex/age/disability; missing joint-programming flags are treated as total.

## Data-quality report (latest run)
- 0 duplicate keys after resolution.
- 50 rows where achieved > 105% of expected (kept, but flagged; the app excludes them from "strong delivery").
- 8 indicator-snapshots without a world total (results reported only by sub-indicator, e.g. WASH, gender).
- 15 indicator-snapshots where regional sums differ from the world total by > 2% (expected: the world total
  includes global/multi-region operations).
- Regional/multi-country projects in the Projects API have no single country (196 project-country rows).

Verified against the live site (FY26): social safety nets 282.1M / 338.5M, students 326.6M / 439.2M,
health services 615.0M / 742.2M.
