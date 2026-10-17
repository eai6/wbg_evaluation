"""Number formatting shared by templates, the assistant and artifacts (mirrors common.js)."""
from __future__ import annotations

import html
import math
import re

VERTICALS = {"People": "--v-people", "Prosperity": "--v-prosperity", "Planet": "--v-planet",
             "Infrastructure": "--v-infra", "Digital": "--v-digital", "Cross-cutting themes": "--v-cross"}
ICONS = {1: "shield", 2: "book-open", 3: "heart-pulse", 4: "landmark", 5: "leaf", 6: "droplets", 7: "wheat", 8: "bus",
         9: "zap", 10: "wifi", 11: "smartphone", 12: "users", 13: "house", 14: "briefcase", 15: "trending-up"}


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def compact(v: float) -> str:
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            digits = 0 if (suf == "M" and a >= 1e8) else 1
            return f"{v / div:.{digits}f}".rstrip("0").rstrip(".") + suf
    return f"{round(v, 1):g}"


def fmt(v, unit: str | None = None) -> str:
    if not _ok(v):
        return "—"
    unit = unit or ""
    if unit == "USD":
        return "$" + compact(v)
    if unit == "Percentage":
        return f"{v:.0f}%"
    if "MtCO2" in unit:
        return compact(v * 1e6) + " tCO₂e/yr"
    if "Hectare" in unit:
        return compact(v) + " ha"
    if "Gigawatt" in unit:
        return compact(v) + " GW"
    return compact(v)


def short_title_html(name: str) -> str:
    """'Number of people receiving…' -> '<b>People</b> receiving…' (Scorecard tile style)."""
    t = re.sub(r"^(Number|Percentage|Total)( of)? ", "", name, flags=re.I)
    t = re.sub(r"\(.*?\)", "", t).strip()
    t = t[:1].upper() + t[1:]
    first, _, rest = t.partition(" ")
    return f"<b>{html.escape(first)}</b> {html.escape(rest)}"
