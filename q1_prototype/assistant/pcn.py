"""Proof-Carrying Numbers (adapted from the World Bank DECDG protocol, arXiv:2509.06902).

1. Tools register every value they return as a *claim* (id -> value, unit, source) before the LLM sees it.
2. The writer must wrap each number taken from data as <claim id="c1a2b3c4">41.5M</claim>.
3. ``render`` checks the shown number against the registered value at the precision shown, turns verified claims
   into ✓ badges with a source tooltip, marks failures ⚠, and flags untagged numbers in the prose.
Derived values (ratios, gaps, changes) are computed in Python and registered too, so the LLM never does arithmetic.
"""
from __future__ import annotations

import html
import json
import math
import re
import zlib

TAG = re.compile(r'<claim\s+id="([a-z0-9]+)"\s*>(.*?)</claim>', re.S)
NUMBER = re.compile(r"(?<![\w.])[-+]?\$?\d[\d,]*(?:\.\d+)?\s*(?:%|[KMB]\b|thousand|million|billion)?", re.I)
SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}


class Claims:
    """Registry of claims for one conversation (stored in the Django session as a plain dict)."""

    def __init__(self, store: dict | None = None):
        self.store = store if store is not None else {}

    def add(self, value, *, unit: str | None, source: str, label: str) -> str | None:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        meta = {"v": float(value), "u": unit or "", "s": source, "l": label}
        cid = "c" + format(zlib.crc32(json.dumps(meta, sort_keys=True).encode()) & 0xFFFFFFFF, "08x")
        self.store[cid] = meta
        return cid

    def get(self, cid: str) -> dict | None:
        return self.store.get(cid)


def parse_shown(text: str) -> tuple[float, float] | None:
    """'41.5M' -> (41_500_000, tolerance). Tolerance = half a unit of the last digit shown."""
    t = html.unescape(text).replace("−", "-").strip()
    m = re.search(r"([-+]?)\$?\s*(\d[\d,]*)(?:\.(\d+))?\s*(%|k|m|b|thousand|million|billion)?", t, re.I)
    if not m:
        return None
    sign, whole, dec, suf = m.groups()
    value = float(whole.replace(",", "") + ("." + dec if dec else ""))
    decimals = len(dec) if dec else 0
    scale = SCALE.get((suf or "").lower(), 1.0)
    value *= scale * (-1 if sign == "-" else 1)
    return value, 0.5 * 10 ** (-decimals) * scale + 1e-9


def check(shown: str, claim: dict) -> bool:
    parsed = parse_shown(shown)
    if not parsed:
        return False
    value, tol = parsed
    src = claim["v"]
    if claim["u"] == "Percentage" and "%" not in shown and abs(src) <= 1.5 and value > 1.5:
        src *= 100
    return abs(value - src) <= tol * 1.0001 or abs(abs(value) - abs(src)) <= tol * 1.0001


def render(text: str, claims: Claims) -> tuple[str, dict]:
    """Escape the LLM text, then turn <claim> tags into verified/unverified badges. Returns (html, stats).

    Claims are swapped for placeholders first so Markdown (lists, bold) is applied to the whole text.
    """
    stats = {"tagged": 0, "verified": 0, "failed": [], "untagged": []}
    spans: list[str] = []

    def sub(m):
        cid, shown = m.group(1), m.group(2)
        stats["tagged"] += 1
        c = claims.get(cid)
        if c and check(shown, c):
            stats["verified"] += 1
            tip = f"{c['l']} · {c['s']} · source value {c['v']:,.4g}"
            spans.append(f'<span class="claim" title="{html.escape(tip)}">{html.escape(shown)}<span class="b">✓</span></span>')
        else:
            stats["failed"].append({"id": cid, "shown": shown, "known": bool(c)})
            tip = "Could not verify this number against the source data" if c else "Unknown claim id"
            spans.append(f'<span class="claim bad" title="{tip}">{html.escape(shown)}<span class="b">⚠</span></span>')
        return f"\x00{len(spans) - 1}\x00"

    body = TAG.sub(sub, text)
    for n in NUMBER.finditer(re.sub(r"\x00\d+\x00", " ", body)):
        tok = n.group(0).strip()
        bare = re.sub(r"[^\d.]", "", tok)
        if re.fullmatch(r"(19|20)\d\d", bare) or re.fullmatch(r"\d", bare):
            continue  # years and single digits (ranks, list numbers, "3 slides") are not data claims
        stats["untagged"].append(tok)
    out = _md(html.escape(body))
    out = re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], out)
    return out, stats


def _md(s: str) -> str:
    """Tiny, safe Markdown subset on already-escaped text: **bold**, lists, paragraphs."""
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    lines, html_out, list_tag = s.split("\n"), [], None
    for line in lines:
        m = re.match(r"\s*(?:([-*•])|(\d+)[.)])\s+(.*)", line)
        if m:
            tag = "ul" if m.group(1) else "ol"
            if list_tag != tag:
                if list_tag:
                    html_out.append(f"</{list_tag}>")
                html_out.append(f"<{tag}>")
                list_tag = tag
            html_out.append(f"<li>{m.group(3)}</li>")
            continue
        if list_tag:
            html_out.append(f"</{list_tag}>")
            list_tag = None
        html_out.append(line)
        html_out.append("\n")
    if list_tag:
        html_out.append(f"</{list_tag}>")
    out = "".join(html_out).rstrip("\n") if not s.endswith("\n") else "".join(html_out)
    return re.sub(r"\n{2,}", "<br><br>", out).replace("\n", "<br>")
