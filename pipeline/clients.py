"""HTTP clients for the Scorecard data/CMS APIs, Data360 and the World Bank Projects API.

The Scorecard website is an Angular app backed by two Azure API Management endpoints. Each request needs an
``apikey`` header; the keys are public (shipped in the site's JavaScript bundle and sent by every browser), so we
read them from the live bundle instead of hardcoding them. Set SCORECARD_API_KEY / SCORECARD_CMS_KEY to override.
"""
from __future__ import annotations

import logging
import os
import time
from functools import lru_cache

import requests

from . import config

log = logging.getLogger(__name__)
_session = requests.Session()
_session.headers["User-Agent"] = config.USER_AGENT


class ApiError(RuntimeError):
    pass


def _get(url: str, *, params=None, headers=None, expect_json=True):
    """GET with retries and exponential backoff on network errors, 429 and 5xx."""
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            resp = _session.get(url, params=params, headers=headers, timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise ApiError(f"HTTP {resp.status_code} for {resp.url}")
            resp.raise_for_status()
            return resp.json() if expect_json else resp.text
        except (requests.RequestException, ApiError, ValueError) as exc:
            last = exc
            time.sleep(1.5 * 2**attempt)
    raise ApiError(f"GET failed after {config.HTTP_RETRIES} attempts: {url} ({last})")


@lru_cache(maxsize=1)
def scorecard_keys() -> dict[str, str]:
    """Return {'data': key, 'cms': key}, read from env or from the site's main.<hash>.js bundle."""
    env = {"data": os.getenv("SCORECARD_API_KEY"), "cms": os.getenv("SCORECARD_CMS_KEY")}
    if all(env.values()):
        return env
    html = _get(config.SCORECARD_SITE, expect_json=False)
    bundle = next((part.split('"', 1)[0] for part in html.split('src="')[1:] if part.startswith("main.")), None)
    if not bundle:
        raise ApiError("Could not find the Scorecard JS bundle; set SCORECARD_API_KEY and SCORECARD_CMS_KEY")
    js = _get(config.SCORECARD_SITE + bundle, expect_json=False)
    marker = 'apiKey:{data:"'
    if marker not in js:
        raise ApiError("API keys not found in the Scorecard bundle; set SCORECARD_API_KEY and SCORECARD_CMS_KEY")
    rest = js.split(marker, 1)[1]
    data_key = rest.split('"', 1)[0]
    cms_key = rest.split('cms:"', 1)[1].split('"', 1)[0]
    return {"data": env["data"] or data_key, "cms": env["cms"] or cms_key}


def parse_statement(payload: dict) -> list[dict]:
    """Turn a Databricks SQL statement result (manifest + data_array) into a list of row dicts.

    Results larger than one chunk are only partially returned by the public API; we flag that instead of
    silently truncating.
    """
    if "manifest" not in payload:
        raise ApiError(f"Unexpected payload: {str(payload)[:200]}")
    manifest = payload["manifest"]
    cols = [c["name"] for c in manifest["schema"]["columns"]]
    rows = [dict(zip(cols, r)) for r in (payload.get("result") or {}).get("data_array") or []]
    chunks = manifest.get("total_chunk_count") or 0
    if chunks > 1:
        log.warning("Result has %s chunks; only the first (%s of %s rows) is available",
                    chunks, len(rows), manifest.get("total_row_count"))
    return rows


def scorecard(endpoint: str, **params) -> list[dict]:
    payload = _get(config.SCORECARD_API + endpoint, params=params, headers={"apikey": scorecard_keys()["data"]})
    return parse_statement(payload)


def scorecard_cms(endpoint: str, **params):
    return _get(config.SCORECARD_CMS + endpoint, params=params, headers={"apikey": scorecard_keys()["cms"]})


def data360(indicator: str, year_from: int, year_to: int, database: str = "WB_WDI") -> list[dict]:
    """All countries for one Data360 indicator, paging with skip/top."""
    rows, skip, top = [], 0, 1000
    while True:
        page = _get(config.DATA360_API + "data", params={
            "DATABASE_ID": database, "INDICATOR": indicator,
            "timePeriodFrom": year_from, "timePeriodTo": year_to, "skip": skip, "top": top})
        batch = page.get("value") or []
        rows += batch
        if len(batch) < top:
            return rows
        skip += top


def active_projects() -> list[dict]:
    """All active World Bank projects from the Projects API (paged, 500 per page)."""
    rows, start = [], 0
    while True:
        page = _get(config.PROJECTS_API, params={
            "format": "json", "status_exact": "Active", "rows": 500, "os": start,
            "fl": "id,project_name,countrycode,countryshortname,regionname,totalcommamt,boardapprovaldate,"
                  "closingdate,sector1,sector2,sector3,url"})
        batch = list((page.get("projects") or {}).values())
        rows += batch
        start += 500
        if not batch or start >= int(page.get("total", 0)):
            return rows
