"""Deterministic entity resolution: free text -> codes (outcome, areas, sex, institution, snapshot).

The router LLM only extracts phrases; this module maps them to valid codes, so a code can never be invented.
It is also the fallback router when no LLM is configured.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from explorer import queries as q

TOPICS = [
    (r"energy|electric|power|renewable|solar", 9), (r"learn|educat|school|student|read", 2),
    (r"health|uhc|stunt|nutrition services|pandemic", 3), (r"\btax|debt|fiscal|macro", 4),
    (r"climat|resilien|planet|ghg|emission|forest|ecosystem|biodivers|hectare", 5),
    (r"water|sanitation|wash\b|hygien", 6), (r"food|nutrition|hunger|agri", 7),
    (r"transport|road|connected communit|mobility", 8), (r"broadband|internet|connectivity", 10),
    (r"digital service|e-?gov|digital id|digitally", 11), (r"gender|women.?s empower|equality", 12),
    (r"displac|refugee|host communit|fragility|conflict and violence", 13), (r"\bjobs?\b|employ", 14),
    (r"private (capital|invest)|investment|mobiliz", 15), (r"poorest|safety net|social protect", 1),
]
REGION_ALIASES = [
    (r"west(ern)?( (and|&) central)? africa|central africa|\bafw\b", "AFW"),
    (r"east(ern)?( (and|&) southern)? africa|southern africa|\bafe\b", "AFE"),
    (r"east asia|pacific|\beap\b", "EAP"), (r"europe|central asia|\beca\b", "ECA"),
    (r"latin america|caribbean|\blcr\b|\blac\b", "LCR"), (r"middle east|north africa|\bmena", "MENAAP"),
    (r"south asia|\bsar\b", "SAR"), (r"fragile|\bfcs\b|\bfcv\b|conflict-affected", "FCS"),
    (r"\bworld\b|global|all countries|overall", "ACW"),
]


ALIASES = {"dr congo": "COD", "drc": "COD", "democratic republic of the congo": "COD", "ivory coast": "CIV",
           "turkey": "TUR", "turkiye": "TUR", "vietnam": "VNM", "laos": "LAO", "lao pdr": "LAO", "egypt": "EGY",
           "iran": "IRN", "syria": "SYR", "yemen": "YEM", "gambia": "GMB", "kyrgyzstan": "KGZ", "russia": "RUS",
           "south korea": "KOR", "north macedonia": "MKD", "west bank": "PSE", "gaza": "PSE", "micronesia": "FSM",
           "venezuela": "VEN", "slovakia": "SVK", "st lucia": "LCA", "saint lucia": "LCA"}


def norm(s: str) -> str:
    """Lower-case, strip accents and normalise apostrophes so 'Côte d’Ivoire' matches "cote d'ivoire"."""
    s = s.replace("\u2019", "").replace("'", "")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


@lru_cache(maxsize=1)
def _country_patterns() -> list[tuple[re.Pattern, str]]:
    pats = []
    for code, a in q.areas().items():
        if a["area_type"] != "COUNTRY":
            continue
        names = {norm(a["name"]), norm(a["label"])}
        if "," in a["name"]:
            names.add(norm(a["name"].split(",")[0]))
        for n in names:
            if n and len(n) > 3:
                pats.append((re.compile(r"\b" + re.escape(n) + r"\b"), code))
    for alias, code in ALIASES.items():
        if code in q.areas():
            pats.append((re.compile(r"\b" + re.escape(alias) + r"\b"), code))
    pats.sort(key=lambda p: -len(p[0].pattern))  # longest names first ("Niger" vs "Nigeria")
    return pats


def topic(text: str) -> int | None:
    t = text.lower()
    for pat, n in TOPICS:
        if re.search(pat, t):
            return n
    return None


def areas(text: str) -> list[str]:
    t = norm(text)
    found: list[str] = []
    for pat, code in REGION_ALIASES:
        if re.search(pat, t) and code not in found:
            found.append(code)
    taken = t
    for pat, code in _country_patterns():
        if pat.search(taken) and code not in found:
            found.append(code)
            taken = pat.sub(" ", taken)
    return found


def resolve(text: str) -> dict:
    """All entities in a message. Unknown things are simply absent (never guessed)."""
    t = text.lower()
    out: dict = {"topic": topic(text), "areas": areas(text)}
    if re.search(r"\b(girls?|women|woman|female)\b", t):
        out["sex"] = "F"
    if re.search(r"\bifc\b", t):
        out["org"] = "IFC"
    elif re.search(r"\bmiga\b", t):
        out["org"] = "MIGA"
    elif re.search(r"\bworld bank\b(?! group)|\bibrd\b|\bida\b", t):
        out["org"] = "WB"
    fy = re.search(r"fy ?(2[456])\b|\b20(2[456])\b", t)
    if fy:
        out["fy"] = int("20" + (fy.group(1) or fy.group(2)))
    return out


def heuristic_intent(text: str) -> str:
    """Keyword intent, used only when no LLM is configured (or the router call fails)."""
    t = text.lower()
    if re.search(r"priorit|three-year|3-year|multi-year|\bplan\b|strateg|where should|opportunit|allocat|footprint", t):
        return "research"
    if re.search(r"slide|deck|presentation|briefing", t):
        return "deck"
    if re.search(r"notebook|jupyter|download (the )?data|export", t):
        return "notebook"
    if re.search(r"summar|overview|what does this (view )?show", t):
        return "summary"
    if re.search(r"what (does|is)|mean|defin|how is .* measured", t):
        return "explain"
    if re.search(r"compare|versus|\bvs\b|rank|lag|worst|best|top|biggest|largest|lowest|highest|struggl|behind|chart|figure|plot|which|"
                 r"change|since|trend|grow|over time|how (is|are|did|has)|doing|progress", t):
        return "analyze"
    e = resolve(text)
    if e["areas"] or e.get("sex") or e.get("org") or e.get("fy"):
        return "filter"
    if e["topic"]:
        return "navigate"
    return "out_of_scope"
