from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yfinance as yf

START = "2005-01-01"
COST_BPS = 50


def _load(symbols: set[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    requested = sorted(set(symbols) | {"QQQ", "SOXX"})
    data = yf.download(
        requested,
        start=(start - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if data.empty:
        raise RuntimeError("empty_download")
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()
    missing = [s for s in requested if s not in close.columns]
    if missing:
        raise RuntimeError(f"missing:{missing}")
    return close.loc[:, requested].dropna(how="all").astype(float)


def _weights(selected: list[str], universe: list[str]) -> dict[str, float]:
    n = len(selected)
    return {s: (1.0 / n if s in selected else 0.0) for s in universe}


def _turnover(current: dict[str, float], previous: dict[str, float] | None) -> float:
    prev = previous or {s: 0.0 for s in current}
    return 0.5 * sum(abs(current[s] - prev.get(s, 0.0)) for s in current)


def _month_end_price(close: pd.DataFrame, month_end: pd.Timestamp, symbol: str) -> float:
    eligible = close.loc[close.index <= month_end, symbol].dropna()
    if eligible.empty:
        raise RuntimeError(f"missing_month_end_price:{symbol}:{month_end.date()}")
    return float(eligible.iloc[-1])


def _shifted_price(close: pd.DataFrame, month_end: pd.Timestamp, symbol: str, delay: int = 1) -> tuple[pd.Timestamp, float]:
    eligible = close.index[close.index <= month_end]
    if len(eligible) == 0:
        raise RuntimeError(f"missing_anchor:{month_end.date()}")
    anchor = eligible[-1]
    loc = close.index.get_loc(anchor)
    if not isinstance(loc, int) or loc + delay >= len(close.index):
        raise RuntimeError(f"missing_shifted_price:{symbol}:{month_end.date()}:{delay}")
    dt = pd.Timestamp(close.index[loc + delay])
    value = close.loc[dt, symbol]
    if pd.isna(value):
        raise RuntimeError(f"nan_shifted_price:{symbol}:{dt.date()}")
    return dt, float(value)


def _score_pair(previous: dict | None, current: dict, nxt: dict, close: pd.DataFrame) -> dict:
    current_dt = pd.Timestamp(current["selection_month"])
    next_dt = pd.Timestamp(nxt["selection_month"])
    if next_dt <= current_dt:
        raise RuntimeError("non_monotonic_prediction_receipts")

    cross_universe = current["economics"].get("crossasset_universe")
    industry_universe = current["economics"].get("industry_universe")
    if cross_universe is None:
        cross_universe = ["SPY", "QQQ", "TLT", "GLD", "DBC"]
    if industry_universe is None:
        industry_universe = ["SOXX", "XBI", "XHB", "KRE", "ITA", "IGV", "IYT", "XRT", "XOP", "IHI"]

    cross_sel = current["candidate"]["p64_crossasset_selected"]
    industry_sel = current["candidate"]["p64_industry_selected"]
    cross_w = _weights(cross_sel, cross_universe)
    industry_w = _weights(industry_sel, industry_universe)

    prev_cross = None
    prev_industry = None
    prev_p36 = None
    if previous is not None:
        prev_cross = _weights(previous["candidate"]["p64_crossasset_selected"], cross_universe)
        prev_industry = _weights(previous["candidate"]["p64_industry_selected"], industry_universe)
        prev_p36 = previous["candidate"]["p36_selected"]

    cross_returns = {
        s: _month_end_price(close, next_dt, s) / _month_end_price(close, current_dt, s) - 1.0
        for s in cross_universe
    }
    industry_returns = {
        s: _month_end_price(close, next_dt, s) / _month_end_price(close, current_dt, s) - 1.0
        for s in industry_universe
    }
    cross_gross = sum(cross_w[s] * cross_returns[s] for s in cross_universe)
    industry_gross = sum(industry_w[s] * industry_returns[s] for s in industry_universe)
    cross_turnover = _turnover(cross_w, prev_cross)
    industry_turnover = _turnover(industry_w, prev_industry)
    cross_net = cross_gross - cross_turnover * COST_BPS / 10000.0
    industry_net = industry_gross - industry_turnover * COST_BPS / 10000.0
    p64_candidate = 0.5 * cross_net + 0.5 * industry_net
    p64_matched = 0.5 * (sum(cross_returns.values()) / len(cross_returns)) + 0.5 * (
        sum(industry_returns.values()) / len(industry_returns)
    )

    p36_symbol = current["candidate"]["p36_selected"]
    start_shifted, p36_start = _shifted_price(close, current_dt, p36_symbol, 1)
    end_shifted, p36_end = _shifted_price(close, next_dt, p36_symbol, 1)
    p36_gross = p36_end / p36_start - 1.0
    p36_turnover = 1.0 if prev_p36 is None else (1.0 if p36_symbol != prev_p36 else 0.0)
    p36_candidate = p36_gross - p36_turnover * COST_BPS / 10000.0

    _, soxx_start = _shifted_price(close, current_dt, "SOXX", 1)
    _, soxx_end = _shifted_price(close, next_dt, "SOXX", 1)
    _, qqq_start = _shifted_price(close, current_dt, "QQQ", 1)
    _, qqq_end = _shifted_price(close, next_dt, "QQQ", 1)
    soxx_return = soxx_end / soxx_start - 1.0
    qqq_return = qqq_end / qqq_start - 1.0
    p36_matched = 0.5 * soxx_return + 0.5 * qqq_return

    return {
        "schema": "research.p82_forward_score.v1",
        "selection_month": current["selection_month"],
        "realized_through_selection_month": nxt["selection_month"],
        "p36_shifted_start": start_shifted.strftime("%Y-%m-%d"),
        "p36_shifted_end": end_shifted.strftime("%Y-%m-%d"),
        "candidate_return_net_50bps": 0.5 * p64_candidate + 0.5 * p36_candidate,
        "matched_return": 0.5 * p64_matched + 0.5 * p36_matched,
        "qqq_return": qqq_return,
        "components": {
            "p64_candidate_return_net_50bps": p64_candidate,
            "p64_matched_return": p64_matched,
            "p64_cross_turnover": cross_turnover,
            "p64_industry_turnover": industry_turnover,
            "p36_candidate_return_net_50bps": p36_candidate,
            "p36_matched_return": p36_matched,
            "p36_turnover": p36_turnover,
            "p36_selected": p36_symbol,
        },
        "provenance": {
            "current_contract_sha256": current["contract_sha256"],
            "next_contract_sha256": nxt["contract_sha256"],
            "source_result_event": current["source_result_event"],
            "cost_bps": COST_BPS,
            "outcome_was_not_available_to_prediction": bool(current["maturity"]["outcome_not_used"]),
        },
    }


def score_ledger(ledger_dir: Path, output_dir: Path) -> dict:
    paths = sorted(ledger_dir.glob("*.json"))
    receipts = [json.loads(p.read_text()) for p in paths]
    if len(receipts) < 2:
        return {"schema": "research.p82_forward_score_readiness.v1", "status": "NOT_MATURE", "prediction_receipts": len(receipts), "scored": 0}

    symbols: set[str] = {"SPY", "QQQ", "TLT", "GLD", "DBC", "SOXX", "XBI", "XHB", "KRE", "ITA", "IGV", "IYT", "XRT", "XOP", "IHI"}
    first = pd.Timestamp(receipts[0]["selection_month"])
    last = pd.Timestamp(receipts[-1]["selection_month"])
    close = _load(symbols, first, last)
    output_dir.mkdir(parents=True, exist_ok=True)
    scored = 0
    for i in range(len(receipts) - 1):
        previous = receipts[i - 1] if i > 0 else None
        score = _score_pair(previous, receipts[i], receipts[i + 1], close)
        target = output_dir / f"{receipts[i]['selection_month']}.json"
        normalized = json.dumps(score, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if target.exists() and target.read_text() != normalized:
            raise RuntimeError(f"IMMUTABILITY_VIOLATION:{target}")
        target.write_text(normalized)
        scored += 1
    return {"schema": "research.p82_forward_score_readiness.v1", "status": "SCORED", "prediction_receipts": len(receipts), "scored": scored}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-dir", default="research/forward_ledgers/p82/predictions")
    parser.add_argument("--output-dir", default="research/forward_ledgers/p82/scorecards")
    args = parser.parse_args()
    print(json.dumps(score_ledger(Path(args.ledger_dir), Path(args.output_dir)), sort_keys=True))


if __name__ == "__main__":
    main()
