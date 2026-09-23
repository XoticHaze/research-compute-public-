from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "p01-crw-dca-adapter-receipt-v1"
WORKLOAD_MODULE = "scripts.operator.crw_backtest_summary_13z"
COST_BPS = (0.0, 2.5, 5.0, 10.0)


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


def _folds(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = result.get("trade_rows") or []
    by_year: dict[int, list[float]] = {}
    for row in rows:
        raw = str(row.get("exit_ts") or row.get("entry_ts") or "")
        try:
            year = int(raw[:4])
            pnl = float(row.get("net_pnl") or 0.0)
        except Exception:
            continue
        by_year.setdefault(year, []).append(pnl)
    return [
        {"year": year, "trades": len(vals), "net_pnl": sum(vals)}
        for year, vals in sorted(by_year.items())
    ]


def _metrics(result: dict[str, Any], capital: float) -> dict[str, Any]:
    pnl = float(result.get("net_pnl") or 0.0)
    return {
        "after_cost_net_pnl": pnl,
        "after_cost_return_pct": 100.0 * pnl / capital,
        "max_drawdown": float(result.get("max_drawdown") or 0.0),
        "trade_count": int(result.get("total_trades") or 0),
        "bar_support": sum(int(x.get("bar_count") or 0) for x in (result.get("symbol_rows") or [])),
        "chronology_folds": _folds(result),
    }


def _arm(seed: dict[str, Any], *, trigger_mode: str, extra_cost_bps: float) -> dict[str, Any]:
    req = copy.deepcopy(seed)
    params = req.setdefault("params", {})
    if not bool(params.get("ENABLE_DCA", False)):
        raise SystemExit("W96 seed is not DCA-enabled; DCA_TRIGGER_MODE discriminator is inadmissible")
    params["DCA_TRIGGER_MODE"] = trigger_mode
    base_slippage = float(params.get("slippage_bps", params.get("SLIPPAGE_BPS", 0.0)) or 0.0)
    params["slippage_bps"] = base_slippage + extra_cost_bps
    req["paper_only"] = True
    req["live_allowed"] = False
    return req


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--payload-dir", required=True, help="Decrypted admitted payload root")
    p.add_argument("--source-root", default="mm-IBKR")
    p.add_argument("--seed-request", default="w96_seed_request.json")
    p.add_argument("--corpus", default="mnq-strategy-backtest-12min.csv")
    p.add_argument("--expected-corpus-sha256", required=True)
    p.add_argument("--expected-corpus-bytes", required=True, type=int)
    p.add_argument("--capital-basis", required=True, type=float)
    args = p.parse_args()

    root = Path(args.payload_dir).resolve()
    source_root = (root / args.source_root).resolve()
    seed_path = (root / args.seed_request).resolve()
    corpus = (root / args.corpus).resolve()
    if args.capital_basis <= 0:
        raise SystemExit("capital basis must be positive")
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

    arms = {
        "control": "tiered_previous_buy",
        "challenger": "legacy_pine_v0_2",
    }
    scenarios: dict[str, Any] = {}
    for cost in COST_BPS:
        pair: dict[str, Any] = {}
        for name, mode in arms.items():
            request = _arm(seed, trigger_mode=mode, extra_cost_bps=cost)
            result = _canonical(source_root, request, root)
            pair[name] = _metrics(result, args.capital_basis)
        pair["challenger_minus_control_return_pct"] = (
            pair["challenger"]["after_cost_return_pct"] - pair["control"]["after_cost_return_pct"]
        )
        pair["challenger_minus_control_net_pnl"] = (
            pair["challenger"]["after_cost_net_pnl"] - pair["control"]["after_cost_net_pnl"]
        )
        scenarios[str(cost)] = pair

    receipt = {
        "schema": SCHEMA,
        "authority": "research_only",
        "canonical_workload": WORKLOAD_MODULE,
        "source_root": args.source_root,
        "corpus": {
            "path_basename": corpus.name,
            "expected_sha256": args.expected_corpus_sha256,
            "observed_sha256": observed_sha,
            "expected_bytes": args.expected_corpus_bytes,
            "observed_bytes": observed_bytes,
        },
        "dca_discriminator": "DCA_TRIGGER_MODE",
        "arms": arms,
        "matched_controls": {"DCA_BASE_QTY": base_qty, "DCA_MAX_CONTRACTS": max_contracts},
        "capital_basis": args.capital_basis,
        "cost_sensitivity_extra_slippage_bps": list(COST_BPS),
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
