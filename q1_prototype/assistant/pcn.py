"""Proof-Carrying Numbers, statement level.

A claim is not just a number: it records WHAT the number is about.
    {entity, measure, period, value, unit, display, source}
Every number the user sees is rendered by the server from a claim ("Nigeria · delivery rate, FY26: 9% ✓"), so the
subject, the measure and the value always travel together. The LLM never writes numbers: it contributes short prose
that must contain no digits and may only name entities that appear in the facts it sits next to. Prose that breaks
either rule is dropped (we would rather show less than show something wrong).
"""
from __future__ import annotations

import html
import json
import math
import zlib


class Claims:
    """Claim registry for one conversation (stored in the Django session as a plain dict)."""

    def __init__(self, store: dict | None = None):
        self.store = store if store is not None else {}

    def add(self, value, *, unit: str | None, source: str, label: str, entity: str | None = None,
            measure: str | None = None, period: str | None = None, display: str | None = None) -> str | None:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        meta = {"v": float(value), "u": unit or "", "s": source, "l": label, "e": entity, "m": measure or label,
                "p": period, "d": display}
        cid = "c" + format(zlib.crc32(json.dumps(meta, sort_keys=True).encode()) & 0xFFFFFFFF, "08x")
        self.store[cid] = meta
        return cid

    def get(self, cid: str) -> dict | None:
        return self.store.get(cid)


def badge(cid: str | None, claims: Claims, display: str | None = None) -> str:
    """A number with its proof: hover shows entity, measure, period, source and the raw value."""
    c = claims.get(cid) if cid else None
    if not c:
        return "—"
    shown = display or c.get("d") or f"{c['v']:,.4g}"
    tip = " · ".join(x for x in (c.get("e"), c.get("m"), c.get("p"), c["s"], f"source value {c['v']:,.6g}") if x)
    return f'<span class="claim" title="{html.escape(tip)}">{html.escape(shown)}<span class="b">✓</span></span>'


def prose(text: str | None, allowed_entities: set[str], all_entities: set[str]) -> tuple[str, str | None]:
    """Validate LLM prose with plain character/substring checks. Returns (safe_html, reason_dropped)."""
    if not text or not text.strip():
        return "", None
    if any(ch.isdigit() for ch in text):
        return "", "contains a number (numbers must come from facts)"
    low = text.lower()
    named = {e for e in all_entities if e and e.lower() in low}
    # a short name contained in a longer named entity ("Niger" inside "Nigeria") is not a separate mention
    named = {e for e in named if not any(e != o and e.lower() in o.lower() for o in named)}
    stray = named - allowed_entities
    if stray:
        return "", f"names entities that are not in its facts: {sorted(stray)}"
    return bold(html.escape(text.strip())), None


def bold(escaped: str) -> str:
    """**bold** → <b>bold</b> on already-escaped text."""
    parts = escaped.split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts)) if len(parts) % 2 else escaped
