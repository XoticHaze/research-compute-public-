from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("p791_r1", HERE / "p791_sec_management_guidance_revision_r1.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)

# Frozen before execution. Small labeled corpus exercises the exact classifier contract
# on explicit forward-guidance revisions, including action-before-noun and noun-before-action.
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


def classify_text(text: str):
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
        "schema": "public_research.p791_parser_recall_r1",
        "experiment_id": "P791_PARSER_RECALL_R1_20260915",
        "frozen_case_count": len(rows),
        "positive_case_count": len(positives),
        "negative_case_count": len(negatives),
        "recall": recall,
        "specificity": specificity,
        "decision": decision,
        "rows": rows,
        "consequence": {
            "PARSER_RECALL_PASS": "re-admit frozen R1 economic test; zero-event failure lies outside the phrase classifier contract and must be localized before unchanged market execution",
            "PARSER_RECALL_FAIL_BOUNDED_REPAIR": "repair only demonstrated phrase-contract misses, then rerun this same frozen gate",
        }[decision],
        "forbidden_rescue": ["horizon", "ticker", "sector", "date", "cost", "post-result economic threshold"],
    }
    target = HERE / "results" / "p791_parser_recall_r1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
