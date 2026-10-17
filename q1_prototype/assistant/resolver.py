"""Entity resolution by exact lookup (no pattern matching).

The router LLM extracts phrases ("western africa", "Ghana") and picks codes from enumerated lists; this module maps
phrases to codes by exact match on normalised official names and a small reviewed alias table. Anything that does not
match exactly is reported as unresolved, never guessed.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache

from explorer import queries as q

REGION_ALIASES = {
    "AFE": ["eastern and southern africa", "east and southern africa", "eastern africa", "east africa", "southern africa", "afe"],
    "AFW": ["western and central africa", "west and central africa", "western africa", "west africa", "central africa", "afw"],
    "EAP": ["east asia and pacific", "east asia and the pacific", "east asia", "pacific", "eap"],
    "ECA": ["europe and central asia", "europe", "central asia", "eca"],
    "LCR": ["latin america and caribbean", "latin america and the caribbean", "latin america", "caribbean", "lac", "lcr"],
    "MENAAP": ["middle east north africa afghanistan and pakistan", "mena afghanistan and pakistan", "middle east and north africa",
               "middle east", "north africa", "mena", "menaap"],
    "SAR": ["south asia", "sar"],
    "FCS": ["fragile and conflict affected situations", "fragile and conflict affected", "fragile states", "fcs", "fcv"],
    "ACW": ["all countries", "world", "global", "worldwide"],
}
COUNTRY_ALIASES = {"dr congo": "COD", "drc": "COD", "democratic republic of the congo": "COD", "ivory coast": "CIV",
                   "turkey": "TUR", "turkiye": "TUR", "vietnam": "VNM", "laos": "LAO", "egypt": "EGY", "iran": "IRN",
                   "syria": "SYR", "yemen": "YEM", "gambia": "GMB", "kyrgyzstan": "KGZ", "russia": "RUS", "south korea": "KOR",
                   "west bank and gaza": "PSE", "micronesia": "FSM", "venezuela": "VEN", "slovakia": "SVK", "saint lucia": "LCA"}


def norm(s: str) -> str:
    """Lower-case, strip accents and punctuation, collapse spaces: 'Côte d’Ivoire' -> 'cote divoire'."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace("&", " and ")
    s = "".join(ch if ch.isalnum() or ch == " " else (" " if ch in "-,/()" else "") for ch in s)
    return " ".join(s.split())


@lru_cache(maxsize=1)
def lookup() -> dict[str, str]:
    table: dict[str, str] = {}
    for code, a in q.areas().items():
        if a["area_type"] != "COUNTRY":
            continue
        for name in (a["name"], a["label"], (a["name"] or "").split(",")[0]):
            if name:
                table.setdefault(norm(name), code)
    table.update({norm(k): v for k, v in COUNTRY_ALIASES.items() if v in q.areas()})
    for code, names in REGION_ALIASES.items():
        for n in names:
            table[norm(n)] = code
    return table


def area(phrase: str) -> str | None:
    key = norm(phrase)
    for prefix in ("the ", "in "):
        if key.startswith(prefix):
            key = key[len(prefix):]
    return lookup().get(key)


def areas(phrases: list[str]) -> tuple[list[str], list[str]]:
    """Exact lookup of LLM-extracted place phrases -> (codes, unresolved phrases)."""
    found, unresolved = [], []
    for p in phrases or []:
        code = area(p)
        if code and code not in found:
            found.append(code)
        elif not code:
            unresolved.append(p)
    return found, unresolved
