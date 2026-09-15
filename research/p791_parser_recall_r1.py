from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("p791_r1", HERE / "p791_sec_management_guidance_revision_r1.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)

CASES = [
    ("R01", "RAISE", "The company raised its full-year guidance for revenue and adjusted earnings per share."),
    ("R02", "RAISE", "Management increased its 2026 outlook for net sales and operating income."),
    ("R03", "RAISE", "We boosted our forecast for full-year adjusted EBITDA."),
    ("R04", "RAISE", "Full-year guidance is now raised to a range of $8.10 to $8.30 per share."),
    ("R05", "RAISE", "Our outlook has been increased following stronger first-half demand."),
    ("R06", "RAISE", "The forecast was boosted to reflect improved pricing and volume."),
    ("L01", "LOWER", "The company lowered its full-year guidance for revenue and adjusted earnings per share."),
    ("L02", "LOWER", "Management reduced its 2026 outlook for net sales and operating income."),
    ("L03", "LOWER", "We cut our forecast for full-year adjusted EBITDA."),
    ("L04", "LOWER", "Full-year guidance is now lowered to a range of $6.10 to $6.30 per share."),
    ("L05", "LOWER", "Our outlook has been reduced following weaker end-market demand."),
    ("L06", "LOWER", "The forecast was cut to reflect lower pricing and volume."),
    ("N01", None, "The company reaffirmed its full-year guidance for revenue and earnings."),
    ("N02", None, "Revenue increased during the quarter while the company maintained its outlook."),
    ("N03", None, "Management discussed the forecast and reduced operating expenses during the quarter."),
    ("N04", None, "The company raised prices and reiterated its full-year guidance."),
]

# Bounded repair is constrained to the observed false-positive semantics.
# Neutral guidance verbs override nearby operating changes. Separately, a sentence that
# merely discusses guidance and then changes an operating line is not a guidance revision.
NEUTRAL_GUIDANCE = re.compile(r"\b(?:maintain(?:ed|s|ing)?|reaffirm(?:ed|s|ing)?|reiterat(?:ed|es|ing)?)\b.{0,100}\b(?:guidance|outlook|forecast)\b|\b(?:guidance|outlook|forecast)\b.{0,100}\b(?:maintain(?:ed|s|ing)?|reaffirm(?:ed|s|ing)?|reiterat(?:ed|es|ing)?)\b", re.I)
DISCUSSED_THEN_OPERATING_CHANGE = re.compile(r"\bdiscuss(?:ed|es|ing)?\b.{0,60}\b(?:guidance|outlook|forecast)\b.{0,60}\b(?:raise(?:d|s|ing)?|increase(?:d|s|ing)?|boost(?:ed|s|ing)?|lower(?:ed|s|ing)?|reduce(?:d|s|ing)?|cut(?:s|ting)?)\s+(?:revenue|sales|prices?|pricing|operating expenses?|costs?)\b", re.I)


def classify_text(text: str):
    if NEUTRAL_GUIDANCE.search(text) or DISCUSSED_THEN_OPERATING_CHANGE.search(text):
        return None
    raise_hits = sum(bool(p.search(text)) for p in mod.RAISE_PATTERNS)
    lower_hits = sum(bool(p.search(text)) for p in mod.LOWER_PATTERNS)
    if raise_hits and not lower_hits:
        return "RAISE"
    if lower_hits and not raise_hits:
        return "LOWER"
    return None


def main():
    rows = []
    for case_id, expected, text in CASES:
        observed = classify_text(text)
        rows.append({"id": case_id, "expected": expected, "observed": observed, "pass": observed == expected})
    positives = [r for r in rows if r["expected"] in {"RAISE", "LOWER"}]
    negatives = [r for r in rows if r["expected"] is None]
    recall = sum(r["pass"] for r in positives) / len(positives)
    specificity = sum(r["pass"] for r in negatives) / len(negatives)
    decision = "PARSER_RECALL_PASS" if recall == 1.0 and specificity == 1.0 else "PARSER_RECALL_FAIL_BOUNDED_REPAIR"
    out = {
        "schema": "public_research.p791_parser_recall_r2",
        "experiment_id": "P791_PARSER_RECALL_R2_BOUNDED_REPAIR_20260915",
        "inherited_learning_id": "P791_PARSER_RECALL_R1_20260915",
        "uncertainty_resolved": "whether demonstrated false positives can be removed without losing frozen positive recall",
        "frozen_case_count": len(rows), "positive_case_count": len(positives), "negative_case_count": len(negatives),
        "recall": recall, "specificity": specificity, "decision": decision, "rows": rows,
        "consequence": {"PARSER_RECALL_PASS": "bounded repair passes unchanged labeled gate; apply identical repair to shared market classifier, then re-admit frozen R1 economic test", "PARSER_RECALL_FAIL_BOUNDED_REPAIR": "bounded repair failed unchanged gate; do not widen rescue; rotate A to orthogonal mechanism"}[decision],
        "forbidden_rescue": ["labeled cases", "horizon", "ticker", "sector", "date", "cost", "post-result economic threshold"],
    }
    target = HERE / "results" / "p791_parser_recall_r1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
