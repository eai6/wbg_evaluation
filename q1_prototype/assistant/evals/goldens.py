"""Build the golden question set with ground truth taken from the LIVE Scorecard API (not our database).

Filter combinations (outcome, area, sex, snapshot) are sampled at random with a fixed seed, the way a user would
click through the Scorecard site, and the expected values are read straight from getSCSUMMARYDATA. Because the
ground truth bypasses the pipeline, the eval also checks the pipeline's cleaning.

Mix (30): 8 filter · 7 single fact · 5 comparison · 4 ranking · 2 snapshot change · 1 definition · 1 no-data · 2 out-of-scope
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

from django.conf import settings

sys.path.insert(0, str(settings.REPO_DIR))
from pipeline import clients  # noqa: E402

from explorer import queries as q  # noqa: E402

REGION_WORDS = {"AFE": "Eastern and Southern Africa", "AFW": "Western and Central Africa", "EAP": "East Asia and the Pacific",
                "ECA": "Europe and Central Asia", "LCR": "Latin America and the Caribbean", "MENAAP": "the Middle East and North Africa",
                "SAR": "South Asia"}


def _live(area_type: str, code: str, fy: int) -> list[dict]:
    return clients.scorecard("getSCSUMMARYDATA", refareatype=area_type, refareacode=code, orgCode="ALL", snapshotfy=fy)


def _value(rows, ind, sex="_T"):
    for r in rows:
        if (r["ind_code"] == ind and r["org_code"] == "WBG" and not r["sub_ind_code"] and r["sex_disaggregate_code"] == sex
                and r["age_disaggregate_code"] == "_T" and r["disability_disaggregate_code"] == "_T"
                and r.get("wbg_joint_progming_flag") in ("_T", None)):
            a, e = r["ind_base_achieved_val"], r["ind_base_expected_val"]
            if a is not None and e is not None:
                return float(a), float(e)
    return None


def build(seed: int = 26) -> list[dict]:
    rng = random.Random(seed)
    fy = q.latest_fy()
    out = []
    people = []  # outcomes with a people-reached primary indicator and country data
    for o in q.outcomes():
        p = q.primary_result(o["outcome_id"])
        if p and p["unit"] == "Beneficiaries" and p["achieved"] is not None:
            people.append((o, p))
    countries = [a for a in q.areas().values() if a["area_type"] == "COUNTRY"]
    cache: dict = {}

    def live(t, c, f=fy):
        if (t, c, f) not in cache:
            cache[(t, c, f)] = _live(t, c, f)
        return cache[(t, c, f)]

    def phrase(p):
        n = p["name"]
        for prefix in ("Number of ", "Total of "):
            if n.lower().startswith(prefix.lower()):
                n = n[len(prefix):]
        return n[0].lower() + n[1:]

    # ---- 8 filter requests (no numbers needed; the filters must be set correctly)
    for i in range(8):
        o, p = rng.choice(people)
        kind = i % 4
        if kind == 0:
            reg = rng.choice(list(REGION_WORDS))
            out.append({"type": "filter", "question": f"Show {REGION_WORDS[reg]}", "outcome_id": o["outcome_id"],
                        "expected_intent": ["filter"], "expected_filters": {"area": reg}})
        elif kind == 1:
            reg = rng.choice(list(REGION_WORDS))
            out.append({"type": "filter", "question": f"women in {REGION_WORDS[reg]}", "outcome_id": o["outcome_id"],
                        "expected_intent": ["filter"], "expected_filters": {"area": reg, "sex": "F"}})
        elif kind == 2:
            c = rng.choice(countries)
            out.append({"type": "filter", "question": f"{c['label']}", "outcome_id": o["outcome_id"],
                        "expected_intent": ["filter"], "expected_filters": {"area": c["area_code"]}})
        else:
            org = rng.choice(["IFC", "MIGA"])
            out.append({"type": "filter", "question": f"{org} only", "outcome_id": o["outcome_id"],
                        "expected_intent": ["filter"], "expected_filters": {"org": org}})

    # ---- 7 single facts: a sampled country with results, live values
    n = 0
    while n < 7:
        o, p = rng.choice(people)
        c = rng.choice(countries)
        v = _value(live("COUNTRY", c["iso2"]), p["ind_code"])
        if not v or v[1] <= 0:
            continue
        out.append({"type": "fact", "question": f"How many {phrase(p)} in {c['label']}?", "outcome_id": o["outcome_id"],
                    "expected_intent": ["analyze"], "expected_values": [{"label": f"{c['label']} achieved", "value": v[0]},
                                                                         {"label": f"{c['label']} expected", "value": v[1]}],
                    "source": f"getSCSUMMARYDATA COUNTRY {c['iso2']} FY{fy}"})
        n += 1

    # ---- 5 comparisons between two regions
    n = 0
    while n < 5:
        o, p = rng.choice(people)
        a, b = rng.sample(list(REGION_WORDS), 2)
        va, vb = _value(live("REGION", a), p["ind_code"]), _value(live("REGION", b), p["ind_code"])
        if not va or not vb:
            continue
        n += 1
        out.append({"type": "comparison", "question": f"Compare {REGION_WORDS[a]} and {REGION_WORDS[b]}", "outcome_id": o["outcome_id"],
                    "expected_intent": ["analyze"],
                    "expected_values": [{"label": f"{a} achieved", "value": va[0]}, {"label": f"{b} achieved", "value": vb[0]}],
                    "source": f"getSCSUMMARYDATA REGION {a},{b} FY{fy}"})

    # ---- 4 rankings: region with the lowest delivery rate (achieved > 105% excluded, as in the app)
    n = 0
    for o, p in rng.sample(people, len(people)):
        if n == 4:
            break
        rates = {}
        for reg in REGION_WORDS:
            v = _value(live("REGION", reg), p["ind_code"])
            if v and v[1] > 0 and v[0] / v[1] <= 1.05:
                rates[reg] = 100 * v[0] / v[1]
        if not rates:
            continue
        low = min(rates, key=rates.get)
        n += 1
        out.append({"type": "ranking", "question": "Which region has the lowest delivery rate?", "outcome_id": o["outcome_id"],
                    "expected_intent": ["analyze"], "expected_values": [{"label": f"{low} delivery %", "value": rates[low]}],
                    "expected_text": q.REGION_NAMES[low].split(" ")[0], "source": f"getSCSUMMARYDATA REGION * FY{fy}"})

    # ---- 2 snapshot changes (all countries, FY24 vs latest)
    for o, p in rng.sample(people, 2):
        v24, vnow = _value(live("REGION", "ACW", 2024), p["ind_code"]), _value(live("REGION", "ACW"), p["ind_code"])
        if v24 and vnow:
            out.append({"type": "change", "question": "How have results changed since FY24?", "outcome_id": o["outcome_id"],
                        "expected_intent": ["analyze"], "expected_values": [{"label": "FY24 achieved", "value": v24[0]},
                                                                            {"label": f"FY{str(fy)[2:]} achieved", "value": vnow[0]}],
                        "source": "getSCSUMMARYDATA REGION ACW FY2024 + latest"})

    # ---- definition, no-data, out-of-scope
    o, p = rng.choice(people)
    out.append({"type": "definition", "question": "What does 'expected' mean here?", "outcome_id": o["outcome_id"], "expected_intent": ["explain"]})
    o, p = people[0]
    for c in countries:
        if not _value(live("COUNTRY", c["iso2"]), p["ind_code"]):
            out.append({"type": "no_data", "question": f"How many {phrase(p)} in {c['label']}?", "outcome_id": o["outcome_id"],
                        "expected_intent": ["analyze"], "expect_no_numbers_for": c["label"]})
            break
    out.append({"type": "out_of_scope", "question": "Write me a poem about the ocean", "outcome_id": people[1][0]["outcome_id"], "expected_intent": ["out_of_scope", "clarify"]})
    out.append({"type": "out_of_scope", "question": "What's the weather in Paris tomorrow?", "outcome_id": people[2][0]["outcome_id"], "expected_intent": ["out_of_scope", "clarify"]})
    for i, g in enumerate(out):
        g["id"] = f"g{i + 1:02d}"
        g["retrieved"] = str(dt.date.today())
    return out


def save(goldens: list[dict]) -> Path:
    path = Path(__file__).parent / "goldens.json"
    path.write_text(json.dumps(goldens, indent=1))
    return path
