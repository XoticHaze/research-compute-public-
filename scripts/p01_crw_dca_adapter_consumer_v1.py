from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "p01-crw-dca-adapter-receipt-v1"
WORKLOAD_MODULE = "scripts.operator.crw_backtest_summary_13z"
EXECUTION_VIEW = "simulated_next_bar_open"
COST_BPS = (0.0, 2.5, 5.0, 10.0)
CHRONOLOGY_FOLDS = (
    ("2019-2020", 2019, 2020),
    ("2021-2022", 2021, 2022),
    ("2023-2024", 2023, 2024),
    ("2025-development-cutoff", 2025, 9999),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return node


def _canonical(source_root: Path, request: dict[str, Any], data_root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(source_root))
    try:
        from scripts.operator.crw_backtest_summary_13z import run_backtest
        return run_backtest(request, data_root)
    finally:
        sys.path.pop(0)


def _folds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = {name: [] for name, _, _ in CHRONOLOGY_FOLDS}
    for row in rows:
        raw = str(row.get("exit_ts") or row.get("entry_ts") or "")
        try:
            year = int(raw[:4])
            pnl = float(row.get("net_pnl") or 0.0)
        except Exception:
            continue
        for name, start, end in CHRONOLOGY_FOLDS:
            if start <= year <= end:
                buckets[name].append(pnl)
                break
    return [
        {"fold": name, "trades": len(buckets[name]), "net_pnl": sum(buckets[name])}
        for name, _, _ in CHRONOLOGY_FOLDS
    ]


def _full_simulation_rows(result: dict[str, Any], source_root: Path) -> list[dict[str, Any]]:
    view = (result.get("execution_views") or {}).get(EXECUTION_VIEW) or {}
    expected = int(view.get("total_trades") or 0)
    artifact_rel = str(result.get("artifact_dir") or "")
    artifact_csv = source_root / artifact_rel / "simulation_trade_rows.csv" if artifact_rel else None
    rows: list[dict[str, Any]]
    if artifact_csv and artifact_csv.exists():
        with artifact_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    else:
        rows = [dict(row) for row in (result.get("simulation_trade_rows") or [])]
    if len(rows) != expected:
        raise SystemExit(
            f"{EXECUTION_VIEW} trade-row support incomplete: expected {expected}, observed {len(rows)}"
        )
    return rows


def _metrics(result: dict[str, Any], source_root: Path) -> dict[str, Any]:
    views = result.get("execution_views") or {}
    view = views.get(EXECUTION_VIEW)
    if not isinstance(view, dict) or view.get("execution_view") != EXECUTION_VIEW:
        raise SystemExit(f"canonical {EXECUTION_VIEW} economics missing")
    rows = _full_simulation_rows(result, source_root)
    pnl = float(view.get("net_pnl") or 0.0)
    return {
        "execution_view": EXECUTION_VIEW,
        "after_cost_net_pnl": pnl,
        "after_cost_return_points": pnl,
        "return_unit": "MNQ_index_points",
        "max_drawdown": float(view.get("max_drawdown") or 0.0),
        "trade_count": int(view.get("total_trades") or 0),
        "bar_support": sum(int(x.get("bar_count") or 0) for x in (result.get("symbol_rows") or [])),
        "chronology_folds": _folds(rows),
        "cost_model": dict(result.get("cost_model") or {}),
    }


HISTORICAL_TV_DCA_LADDER = [6.0, 6.0, 8.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
CORRECTED_TWO_ADD_LADDER = [6.0, 8.0]


def _arm(
    seed: dict[str, Any],
    *,
    slippage_bps: float,
    trigger_mode: str | None = None,
    tier_drawdowns_pct: list[float] | None = None,
) -> dict[str, Any]:
    req = copy.deepcopy(seed)
    params = req.setdefault("params", {})
    if not bool(params.get("ENABLE_DCA", False)):
        raise SystemExit("W96 seed is not DCA-enabled; DCA discriminator is inadmissible")
    if trigger_mode is not None:
        params["DCA_TRIGGER_MODE"] = trigger_mode
    if tier_drawdowns_pct is not None:
        params["DCA_TIER_DRAWDOWNS_PCT"] = list(tier_drawdowns_pct)
    # Cost sensitivity is absolute, not additive, so 0 really means the 0 bp slippage arm.
    params["slippage_bps"] = float(slippage_bps)
    params["SLIPPAGE_BPS"] = float(slippage_bps)
    req["paper_only"] = True
    req["live_allowed"] = False
    return req


def _dca_params(request: dict[str, Any]) -> dict[str, Any]:
    params = request.get("params") or {}
    keys = sorted(k for k in params if k == "ENABLE_DCA" or str(k).startswith("DCA_"))
    return {str(k): params[k] for k in keys}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--payload-dir", required=True, help="Decrypted admitted payload root")
    p.add_argument("--source-root", default="mm-IBKR")
    p.add_argument("--seed-request", default="w96_seed_request.json")
    p.add_argument("--corpus", default="mnq-strategy-backtest-12min.csv")
    p.add_argument("--expected-corpus-sha256", required=True)
    p.add_argument("--expected-corpus-bytes", required=True, type=int)
    args = p.parse_args()

    root = Path(args.payload_dir).resolve()
    source_root = (root / args.source_root).resolve()
    seed_path = (root / args.seed_request).resolve()
    corpus = (root / args.corpus).resolve()
    observed_sha = _sha256(corpus)
    observed_bytes = corpus.stat().st_size
    if observed_sha != args.expected_corpus_sha256 or observed_bytes != args.expected_corpus_bytes:
        raise SystemExit("governed corpus identity mismatch")

    seed = _load(seed_path)
    params = seed.get("params") or {}
    base_qty = params.get("DCA_BASE_QTY")
    max_contracts = params.get("DCA_MAX_CONTRACTS")
    if base_qty is None or max_contracts is None:
        raise SystemExit("matched-capital DCA controls missing from W96 seed")

    # Force canonical loader to the admitted corpus without mutating source/runtime authority.
    symbols = seed.get("symbols") or [seed.get("symbol") or "MNQ"]
    seed["_verified_source_paths"] = {str(s): str(corpus) for s in symbols}

    arm_specs = {
        # Frozen current survivor/control: preserve every DCA setting from the admitted W96 seed.
        "control": {},
        # Historical TradingView/Pine V0.2 operator settings. With legacy shifted lookup,
        # the first two realized adds are nominal 6% then 8% from prior buy signal-close.
        "challenger": {
            "trigger_mode": "legacy_pine_v0_2",
            "tier_drawdowns_pct": HISTORICAL_TV_DCA_LADDER,
        },
        # Corrected modular semantics for the same realized two-add 6% then 8% behavior.
        "corrected_6_8": {
            "trigger_mode": "tiered_previous_buy",
            "tier_drawdowns_pct": CORRECTED_TWO_ADD_LADDER,
        },
    }
    primary_requests = {
        name: _arm(seed, slippage_bps=2.5, **spec)
        for name, spec in arm_specs.items()
    }
    scenarios: dict[str, Any] = {}
    for cost in COST_BPS:
        pair: dict[str, Any] = {}
        for name, spec in arm_specs.items():
            request = _arm(seed, slippage_bps=cost, **spec)
            result = _canonical(source_root, request, root)
            pair[name] = _metrics(result, source_root)
        pair["challenger_minus_control_return_points"] = (
            pair["challenger"]["after_cost_return_points"] - pair["control"]["after_cost_return_points"]
        )
        pair["challenger_minus_control_net_pnl"] = (
            pair["challenger"]["after_cost_net_pnl"] - pair["control"]["after_cost_net_pnl"]
        )
        pair["corrected_6_8_minus_control_return_points"] = (
            pair["corrected_6_8"]["after_cost_return_points"] - pair["control"]["after_cost_return_points"]
        )
        pair["corrected_6_8_minus_control_net_pnl"] = (
            pair["corrected_6_8"]["after_cost_net_pnl"] - pair["control"]["after_cost_net_pnl"]
        )
        scenarios[str(cost)] = pair

    receipt = {
        "schema": SCHEMA,
        "authority": "research_only",
        "canonical_workload": WORKLOAD_MODULE,
        "execution_view": EXECUTION_VIEW,
        "source_root": args.source_root,
        "corpus": {
            "path_basename": corpus.name,
            "expected_sha256": args.expected_corpus_sha256,
            "observed_sha256": observed_sha,
            "expected_bytes": args.expected_corpus_bytes,
            "observed_bytes": observed_bytes,
        },
        "dca_discriminator": "historical_parity_and_trigger_semantics",
        "arms": {
            "control": "frozen_w96_seed",
            "challenger": {
                "trigger_mode": "legacy_pine_v0_2",
                "tier_drawdowns_pct": HISTORICAL_TV_DCA_LADDER,
                "realized_first_two_adds_pct": CORRECTED_TWO_ADD_LADDER,
                "reference": "previous_buy_signal_close",
                "historical_buffer": 0.0005,
            },
            "corrected_6_8": {
                "trigger_mode": "tiered_previous_buy",
                "tier_drawdowns_pct": CORRECTED_TWO_ADD_LADDER,
            },
        },
        "exact_dca_parameters_at_primary_2_5bp": {
            name: _dca_params(request) for name, request in primary_requests.items()
        },
        "matched_controls": {"DCA_BASE_QTY": base_qty, "DCA_MAX_CONTRACTS": max_contracts},
        "return_unit": "MNQ_index_points",
        "cost_sensitivity_slippage_bps": list(COST_BPS),
        "chronology_fold_contract": [name for name, _, _ in CHRONOLOGY_FOLDS],
        "scenarios": scenarios,
        "protected_holdout_read": False,
        "strategy_spec_write": False,
        "runtime_activation": False,
        "broker_submit": False,
        "promotion_authority": False,
        "live_trading_change": False,
    }
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    print("P01_CRW_DCA_ADAPTER_RECEIPT=" + encoded)
    print("P01_CRW_DCA_ADAPTER_RECEIPT_SHA256=" + hashlib.sha256(encoded.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
