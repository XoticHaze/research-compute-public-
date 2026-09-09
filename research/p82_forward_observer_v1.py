from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import fixed_multifactor_cross_sectional_r1 as base
import p47_deep_robustness_r2 as p47
import p57_crossasset_parsimonious_r1 as p57
import p66_combination_serial_persistence_r1 as p66

DEFAULT_CONTRACT = Path("research/p82_forward_observer_contract_v1.json")
DEFAULT_OUTPUT = Path("artifacts/p82_forward_observer_v1.json")


def _latest_completed_month(index: pd.DatetimeIndex) -> pd.Timestamp:
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    completed = (now.to_period("M") - 1).to_timestamp("M")
    eligible = index[index <= completed]
    if len(eligible) == 0:
        raise RuntimeError("no_completed_month_available")
    return pd.Timestamp(eligible[-1])


def _rank_top(block: pd.DataFrame, top_k: int) -> list[str]:
    if block.isna().any().any():
        raise RuntimeError("non_finite_feature_block")
    score = block.rank(axis=0, pct=True, method="average").mean(axis=1)
    return score.sort_values(ascending=False).head(top_k).index.tolist()


def _add_weight(weights: dict[str, float], symbol: str, weight: float) -> None:
    weights[symbol] = weights.get(symbol, 0.0) + float(weight)


def _normalized(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise RuntimeError(f"weights_do_not_sum_to_one:{total}")
    return {k: float(v) for k, v in sorted(weights.items()) if abs(v) > 1e-15}


def _verify_frozen_blobs(expected: dict[str, str]) -> None:
    for path, expected_blob in expected.items():
        actual = subprocess.check_output(["git", "hash-object", path], text=True).strip()
        if actual != expected_blob:
            raise RuntimeError(f"frozen_model_blob_drift:{path}:{actual}:{expected_blob}")


def run(contract_path: Path, output_path: Path) -> dict:
    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes)
    if contract.get("schema") != "research.p82_forward_observer_contract.v1":
        raise RuntimeError("contract_schema_drift")
    _verify_frozen_blobs(contract["frozen_model_blobs"])
    if contract["candidate"]["p82_weights"] != {"P64": 0.5, "P36": 0.5}:
        raise RuntimeError("p82_weight_drift")
    if contract["economics"]["component_cost_bps"] != 50:
        raise RuntimeError("cost_contract_drift")
    if not contract["economics"].get("no_parameter_or_weight_tuning"):
        raise RuntimeError("tuning_not_forbidden")

    cross_symbols = tuple(contract["candidate"]["p64"]["crossasset_universe"])
    industry_symbols = tuple(contract["candidate"]["p64"]["industry_universe"])
    if cross_symbols != tuple(p57.SYMS):
        raise RuntimeError("crossasset_universe_drift")
    if industry_symbols != tuple(p66.IND):
        raise RuntimeError("industry_universe_drift")
    if tuple(contract["candidate"]["p64"]["industry_factors"]) != tuple(p66.FACTORS):
        raise RuntimeError("industry_factor_drift")

    cross_close = base.load(cross_symbols).sort_index()
    cross_monthly = cross_close.resample("ME").last()
    cross_trend = (cross_close / cross_close.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    cross_mom = cross_monthly.pct_change(6)

    industry_close = base.load(industry_symbols).sort_index()
    industry_monthly, industry_maps = p47.maps(industry_close)

    p36_close = base.load(("SOXX",)).dropna(subset=["SOXX", "QQQ"]).sort_index()
    p36_monthly = p36_close.resample("ME").last()

    selection_month = min(
        _latest_completed_month(cross_monthly.index),
        _latest_completed_month(industry_monthly.index),
        _latest_completed_month(p36_monthly.index),
    )
    if selection_month not in cross_monthly.index or selection_month not in industry_monthly.index or selection_month not in p36_monthly.index:
        raise RuntimeError(f"common_selection_month_missing:{selection_month}")

    cross_block = pd.DataFrame(
        {
            "mom6": cross_mom.loc[selection_month, list(cross_symbols)],
            "trend200": cross_trend.loc[selection_month, list(cross_symbols)],
        },
        index=list(cross_symbols),
    )
    cross_selected = _rank_top(cross_block, int(contract["candidate"]["p64"]["crossasset_top_k"]))

    industry_block = pd.DataFrame(
        {factor: industry_maps[factor].loc[selection_month, list(industry_symbols)] for factor in p66.FACTORS},
        index=list(industry_symbols),
    )
    industry_selected = _rank_top(industry_block, int(contract["candidate"]["p64"]["industry_top_k"]))

    p36_loc = p36_monthly.index.get_loc(selection_month)
    if not isinstance(p36_loc, int) or p36_loc < 6:
        raise RuntimeError("insufficient_p36_lookback")
    p36_start = p36_monthly.index[p36_loc - 6]
    soxx_6m = float(p36_monthly.loc[selection_month, "SOXX"] / p36_monthly.loc[p36_start, "SOXX"] - 1.0)
    qqq_6m = float(p36_monthly.loc[selection_month, "QQQ"] / p36_monthly.loc[p36_start, "QQQ"] - 1.0)
    rel6 = soxx_6m - qqq_6m
    p36_symbol = "SOXX" if rel6 > 0 else "QQQ"

    candidate: dict[str, float] = {}
    for symbol in cross_selected:
        _add_weight(candidate, symbol, 0.5 * 0.5 * (1.0 / len(cross_selected)))
    for symbol in industry_selected:
        _add_weight(candidate, symbol, 0.5 * 0.5 * (1.0 / len(industry_selected)))
    _add_weight(candidate, p36_symbol, 0.5)

    matched: dict[str, float] = {}
    for symbol in cross_symbols:
        _add_weight(matched, symbol, 0.5 * 0.5 * (1.0 / len(cross_symbols)))
    for symbol in industry_symbols:
        _add_weight(matched, symbol, 0.5 * 0.5 * (1.0 / len(industry_symbols)))
    _add_weight(matched, "SOXX", 0.5 * 0.5)
    _add_weight(matched, "QQQ", 0.5 * 0.5)

    candidate = _normalized(candidate)
    matched = _normalized(matched)
    forward_month = (selection_month.to_period("M") + 1).strftime("%Y-%m")
    result = {
        "schema": "research.p82_forward_observer.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parent": "P82",
        "source_result_event": contract["source_result_event"],
        "source_execution": contract["source_execution"],
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "frozen_model_blobs": contract["frozen_model_blobs"],
        "selection_month": selection_month.strftime("%Y-%m-%d"),
        "forward_month": forward_month,
        "candidate": {
            "weights": candidate,
            "p64_crossasset_selected": cross_selected,
            "p64_industry_selected": industry_selected,
            "p36_selected": p36_symbol,
            "p36_soxx_6m_return": soxx_6m,
            "p36_qqq_6m_return": qqq_6m,
            "p36_relative_6m_soxx_minus_qqq": rel6,
        },
        "controls": {
            "matched_weights": matched,
            "opportunity_control": {"QQQ": 1.0},
        },
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only",
            "crossasset_panel_sha256": base.source_hash(cross_close),
            "industry_panel_sha256": base.source_hash(industry_close),
            "p36_panel_sha256": base.source_hash(p36_close),
        },
        "economics": contract["economics"],
        "maturity": {
            "outcome_not_used": True,
            "score_after_forward_month_closes": True,
        },
        "protected_boundaries": contract["protected_boundaries"],
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
