from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

START = "2005-01-01"
DEFAULT_CONTRACT = Path("research/p82_forward_observer_contract_v1.json")
DEFAULT_OUTPUT = Path("artifacts/p82_forward_observer_v1.json")


def load(symbols: tuple[str, ...]) -> pd.DataFrame:
    requested = tuple(dict.fromkeys((*symbols, "SPY", "QQQ")))
    data = yf.download(list(requested), start=START, auto_adjust=True, progress=False, threads=False)
    if data.empty:
        raise RuntimeError("empty_download")
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()
    missing = [s for s in requested if s not in close.columns]
    if missing:
        raise RuntimeError(f"missing:{missing}")
    return close.loc[:, list(requested)].dropna(how="all").astype(float)


def source_hash(close: pd.DataFrame) -> str:
    return hashlib.sha256(close.reset_index().to_csv(index=False, float_format="%.10g").encode()).hexdigest()


def latest_completed_month(index: pd.DatetimeIndex) -> pd.Timestamp:
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    completed = (now.to_period("M") - 1).to_timestamp("M")
    eligible = index[index <= completed]
    if len(eligible) == 0:
        raise RuntimeError("no_completed_month_available")
    return pd.Timestamp(eligible[-1])


def factor_maps(close: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    monthly = close.resample("ME").last()
    trend200 = (close / close.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    return monthly, {"mom6": monthly.pct_change(6), "trend200": trend200}


def top_ranked(maps: dict[str, pd.DataFrame], month: pd.Timestamp, symbols: tuple[str, ...], factors: tuple[str, ...], top_k: int) -> list[str]:
    block = pd.DataFrame({f: maps[f].loc[month, list(symbols)] for f in factors}, index=list(symbols))
    if block.isna().any().any():
        raise RuntimeError("non_finite_feature_block")
    score = block.rank(axis=0, pct=True, method="average").mean(axis=1)
    return score.sort_values(ascending=False).head(top_k).index.tolist()


def add_weight(weights: dict[str, float], symbol: str, weight: float) -> None:
    weights[symbol] = weights.get(symbol, 0.0) + float(weight)


def normalized(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError(f"weights_do_not_sum_to_one:{total}")
    return {k: float(v) for k, v in sorted(weights.items()) if abs(v) > 1e-15}


def run(contract_path: Path, output_path: Path) -> dict:
    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes)
    if contract.get("schema") != "research.p82_forward_observer_contract.v1":
        raise RuntimeError("contract_schema_drift")
    if contract["candidate"]["p82_weights"] != {"P64": 0.5, "P36": 0.5}:
        raise RuntimeError("p82_weight_drift")
    if contract["economics"]["component_cost_bps"] != 50:
        raise RuntimeError("cost_contract_drift")
    if not contract["economics"].get("no_parameter_or_weight_tuning"):
        raise RuntimeError("tuning_not_forbidden")

    p64 = contract["candidate"]["p64"]
    cross_symbols = tuple(p64["crossasset_universe"])
    cross_factors = tuple(p64["crossasset_factors"])
    industry_symbols = tuple(p64["industry_universe"])
    industry_factors = tuple(p64["industry_factors"])
    if cross_symbols != ("SPY", "QQQ", "TLT", "GLD", "DBC") or cross_factors != ("mom6", "trend200") or int(p64["crossasset_top_k"]) != 2:
        raise RuntimeError("crossasset_contract_drift")
    if industry_symbols != ("SOXX", "XBI", "XHB", "KRE", "ITA", "IGV", "IYT", "XRT", "XOP", "IHI") or industry_factors != ("mom6", "trend200") or int(p64["industry_top_k"]) != 3:
        raise RuntimeError("industry_contract_drift")

    cross_close = load(cross_symbols).sort_index()
    cross_monthly, cross_maps = factor_maps(cross_close)
    industry_close = load(industry_symbols).sort_index()
    industry_monthly, industry_maps = factor_maps(industry_close)
    p36_close = load(("SOXX",)).dropna(subset=["SOXX", "QQQ"]).sort_index()
    p36_monthly = p36_close.resample("ME").last()

    selection_month = min(
        latest_completed_month(cross_monthly.index),
        latest_completed_month(industry_monthly.index),
        latest_completed_month(p36_monthly.index),
    )
    for name, index in (("crossasset", cross_monthly.index), ("industry", industry_monthly.index), ("p36", p36_monthly.index)):
        if selection_month not in index:
            raise RuntimeError(f"common_selection_month_missing:{name}:{selection_month}")

    cross_selected = top_ranked(cross_maps, selection_month, cross_symbols, cross_factors, 2)
    industry_selected = top_ranked(industry_maps, selection_month, industry_symbols, industry_factors, 3)

    loc = p36_monthly.index.get_loc(selection_month)
    if not isinstance(loc, int) or loc < 6:
        raise RuntimeError("insufficient_p36_lookback")
    start = p36_monthly.index[loc - 6]
    soxx_6m = float(p36_monthly.loc[selection_month, "SOXX"] / p36_monthly.loc[start, "SOXX"] - 1.0)
    qqq_6m = float(p36_monthly.loc[selection_month, "QQQ"] / p36_monthly.loc[start, "QQQ"] - 1.0)
    relative_6m = soxx_6m - qqq_6m
    p36_selected = "SOXX" if relative_6m > 0 else "QQQ"

    candidate: dict[str, float] = {}
    for symbol in cross_selected:
        add_weight(candidate, symbol, 0.5 * 0.5 / 2)
    for symbol in industry_selected:
        add_weight(candidate, symbol, 0.5 * 0.5 / 3)
    add_weight(candidate, p36_selected, 0.5)

    matched: dict[str, float] = {}
    for symbol in cross_symbols:
        add_weight(matched, symbol, 0.5 * 0.5 / len(cross_symbols))
    for symbol in industry_symbols:
        add_weight(matched, symbol, 0.5 * 0.5 / len(industry_symbols))
    add_weight(matched, "SOXX", 0.25)
    add_weight(matched, "QQQ", 0.25)

    result = {
        "schema": "research.p82_forward_observer.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parent": "P82",
        "source_result_event": contract["source_result_event"],
        "source_execution": contract["source_execution"],
        "frozen_source_semantics": contract["frozen_source_semantics"],
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "selection_month": selection_month.strftime("%Y-%m-%d"),
        "forward_month": (selection_month.to_period("M") + 1).strftime("%Y-%m"),
        "candidate": {
            "weights": normalized(candidate),
            "p64_crossasset_selected": cross_selected,
            "p64_industry_selected": industry_selected,
            "p36_selected": p36_selected,
            "p36_activation_delay_trading_days": 1,
            "p36_soxx_6m_return": soxx_6m,
            "p36_qqq_6m_return": qqq_6m,
            "p36_relative_6m_soxx_minus_qqq": relative_6m
        },
        "controls": {"matched_weights": normalized(matched), "opportunity_control": {"QQQ": 1.0}},
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only",
            "crossasset_panel_sha256": source_hash(cross_close),
            "industry_panel_sha256": source_hash(industry_close),
            "p36_panel_sha256": source_hash(p36_close)
        },
        "economics": contract["economics"],
        "maturity": {"outcome_not_used": True, "score_after_forward_month_closes": True},
        "protected_boundaries": contract["protected_boundaries"]
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    run(Path(args.contract), Path(args.output))


if __name__ == "__main__":
    main()
