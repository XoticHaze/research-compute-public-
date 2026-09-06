from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

import research.fnspid_next_session_arrival_ablation_20260906 as ablation

TARGETS = ablation.TEST
REQUIRED_MIN_RECORDED_DATE = date(2017, 12, 31)
REQUIRED_MAX_RECORDED_DATE = date(2023, 11, 30)
PRICE_QUERY_END = "2023-12-31"


def _recorded_span(path: Path) -> dict[str, dict[str, str | None]]:
    out = {s: {"min": None, "max": None} for s in TARGETS}
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            symbol = str(row.get("Stock_symbol") or "").strip().upper()
            if symbol not in out:
                continue
            raw = str(row.get("Date") or "").strip()
            if len(raw) < 10:
                continue
            try:
                d = datetime.fromisoformat(raw[:10]).date()
            except ValueError:
                continue
            iso = d.isoformat()
            cur_min = out[symbol]["min"]
            cur_max = out[symbol]["max"]
            out[symbol]["min"] = iso if cur_min is None else min(str(cur_min), iso)
            out[symbol]["max"] = iso if cur_max is None else max(str(cur_max), iso)
    return out


def _span_pass(spans: dict[str, dict[str, str | None]]) -> bool:
    for symbol in TARGETS:
        lo = spans[symbol]["min"]
        hi = spans[symbol]["max"]
        if lo is None or hi is None:
            return False
        if date.fromisoformat(str(lo)) > REQUIRED_MIN_RECORDED_DATE:
            return False
        if date.fromisoformat(str(hi)) < REQUIRED_MAX_RECORDED_DATE:
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--news-csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    spans = _recorded_span(args.news_csv)
    if not _span_pass(spans):
        result = {
            "schema": "research.fnspid_next_session_arrival_ablation.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "classification": "FNSPID_BOUNDED_PREFIX_SPAN_INADEQUATE_NO_ECONOMIC_ABLATION",
            "economic_ablation_executed": False,
            "recorded_span": spans,
            "span_gate": {
                "required_min_recorded_date_on_or_before": REQUIRED_MIN_RECORDED_DATE.isoformat(),
                "required_max_recorded_date_on_or_after": REQUIRED_MAX_RECORDED_DATE.isoformat(),
                "pass": False,
            },
            "price_query_end": PRICE_QUERY_END,
            "causal_intraday_admission": "REJECT_UPSTREAM_UTC_CONVERSION_UNSAFE",
            "eligibility": "STRICT_NEXT_TRADING_SESSION_AFTER_RECORDED_DATE_ONLY",
            "full_family_news_state_admission": False,
            "research_only": True,
            "promotion_authority": False,
            "runtime_mutation": False,
            "broker_authority": False,
            "live_trading_change": False,
        }
    else:
        # Keep the price calendar inside the sampled source span. The underlying
        # fixed20 target automatically leaves HOLD+DELAY terminal sessions unused.
        ablation.END = PRICE_QUERY_END
        result = ablation.run(args.news_csv)
        result["recorded_span"] = spans
        result["span_gate"] = {
            "required_min_recorded_date_on_or_before": REQUIRED_MIN_RECORDED_DATE.isoformat(),
            "required_max_recorded_date_on_or_after": REQUIRED_MAX_RECORDED_DATE.isoformat(),
            "pass": True,
        }
        result["price_query_end"] = PRICE_QUERY_END

    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FNSPID_NEXT_SESSION_DISPATCH=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
