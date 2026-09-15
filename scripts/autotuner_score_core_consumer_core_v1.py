from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA = "autotuner-score-core-ephemeral-x25519-v1"
HARNESS = "autotuner_crw_score_core_v1"
AUTHORITY = "research_only"
PAYLOAD_SCHEMA = "autotuner-crw-score-core-private-payload-v1"
DATA_SHA256 = "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e"
EXPECTED_ROWS = 192553
BASELINE = {"window": 96, "entry": -2.8, "exit": 4.5, "fee_points_per_contract_side": 0.3}
EXPECTED_CALIBRATION = {
    "trades": 91,
    "net": 16483.4,
    "profit_factor": 2.087790617101462,
    "sortino": 0.23400854823150793,
    "max_drawdown": 5271.75,
}


@njit
def _sim(opens, z, entry_thr, exit_thr, start_idx, end_idx, fee):
    inpos = False
    entry_px = 0.0
    entry_cost_basis = 0.0
    pending = 0
    n = 0
    wins = 0
    gross_win = 0.0
    gross_loss = 0.0
    net = 0.0
    equity = 0.0
    peak = 0.0
    maxdd = 0.0
    ret_sum = 0.0
    neg_sq = 0.0
    neg_n = 0
    for i in range(start_idx, end_idx + 1):
        if pending != 0:
            if pending == 1 and not inpos:
                inpos = True
                entry_px = opens[i]
                entry_cost_basis = entry_px + fee
            elif pending == -1 and inpos:
                pnl = (opens[i] - entry_px) - 2.0 * fee
                net += pnl
                equity += pnl
                if equity > peak:
                    peak = equity
                dd = equity - peak
                if dd < maxdd:
                    maxdd = dd
                n += 1
                r = pnl / entry_cost_basis if entry_cost_basis != 0 else 0.0
                ret_sum += r
                if r < 0:
                    neg_sq += r * r
                    neg_n += 1
                    gross_loss += -pnl
                else:
                    gross_win += pnl
                    if pnl > 0:
                        wins += 1
                inpos = False
            pending = 0
        zi = z[i]
        if np.isnan(zi):
            continue
        if not inpos and zi < entry_thr:
            if i < end_idx:
                pending = 1
        elif inpos and zi > exit_thr:
            if i < end_idx:
                pending = -1
    pf = gross_win / gross_loss if gross_loss > 0 else np.nan
    sortino = np.nan
    if n > 0 and neg_n > 0:
        downside = math.sqrt(neg_sq / neg_n)
        if downside > 0:
            sortino = (ret_sum / n) / downside
    return n, net, pf, sortino, -maxdd, wins / n if n > 0 else 0.0


def _zscore(close: pd.Series, window: int) -> np.ndarray:
    mean = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=1)
    return ((close - mean) / std).to_numpy(np.float64)


def _metric_dict(values) -> dict:
    return {
        "trades": int(values[0]),
        "net_points": float(values[1]),
        "profit_factor": None if not math.isfinite(float(values[2])) else float(values[2]),
        "sortino": None if not math.isfinite(float(values[3])) else float(values[3]),
        "max_drawdown_points": float(values[4]),
        "win_rate": float(values[5]),
    }


def _calibration_ok(metric: dict) -> bool:
    return (
        metric["trades"] == EXPECTED_CALIBRATION["trades"]
        and abs(metric["net_points"] - EXPECTED_CALIBRATION["net"]) < 1e-6
        and abs(metric["profit_factor"] - EXPECTED_CALIBRATION["profit_factor"]) < 1e-9
        and abs(metric["sortino"] - EXPECTED_CALIBRATION["sortino"]) < 1e-9
        and abs(metric["max_drawdown_points"] - EXPECTED_CALIBRATION["max_drawdown"]) < 1e-6
    )


def _load_payload(raw: bytes) -> pd.DataFrame:
    node = json.loads(raw.decode("utf-8"))
    required = {"schema", "authority", "contract", "data_b64"}
    if not isinstance(node, dict) or set(node) != required:
        raise RuntimeError("AutoTuner private payload field set mismatch")
    if node["schema"] != PAYLOAD_SCHEMA or node["authority"] != AUTHORITY:
        raise RuntimeError("AutoTuner private payload schema/authority mismatch")
    expected_contract = {
        "symbol": "MNQ",
        "timeframe": "12Min",
        "dataset_sha256": DATA_SHA256,
        "rows": EXPECTED_ROWS,
        "scope": "score_core_only_dca_policy_held_out",
        "search": {
            "window": {"start": 48, "stop": 144, "step": 6},
            "entry": {"start": -1.8, "stop": -3.6, "step": -0.1},
            "exit": {"start": 2.5, "stop": 6.0, "step": 0.25},
        },
        "calendar_folds": [2020, 2021, 2022, 2023, 2024, 2025],
        "baseline": BASELINE,
        "dca_policy": "EXCLUDED_UNTIL_VALIDATED_SIGNAL_REENTRY_CAPITAL_POLICY",
    }
    if node["contract"] != expected_contract:
        raise RuntimeError("AutoTuner score-core contract mismatch")
    data = base64.b64decode(node["data_b64"].encode("ascii"), validate=True)
    if hashlib.sha256(data).hexdigest() != DATA_SHA256:
        raise RuntimeError("MNQ score-core dataset SHA mismatch")
    frame = pd.read_csv(io.BytesIO(data))
    if len(frame) != EXPECTED_ROWS:
        raise RuntimeError("MNQ score-core row count mismatch")
    required_cols = {"timestamp", "open", "close"}
    if not required_cols.issubset(frame.columns):
        raise RuntimeError("MNQ score-core required columns missing")
    return frame


def _campaign(frame: pd.DataFrame) -> dict:
    opens = frame["open"].astype(float).to_numpy(np.float64)
    close = frame["close"].astype(float)
    years = pd.to_datetime(frame["timestamp"], utc=True).dt.year.to_numpy()
    fee = float(BASELINE["fee_points_per_contract_side"])
    z96 = _zscore(close, 96)
    baseline = _metric_dict(_sim(opens, z96, -2.8, 4.5, 0, len(frame) - 1, fee))
    if not _calibration_ok(baseline):
        raise RuntimeError("score-core calibration failed against canonical DCA-off checksum")

    fold_ranges = {}
    baseline_fold_net = {}
    for year in range(2020, 2026):
        idx = np.where(years == year)[0]
        if not len(idx):
            raise RuntimeError(f"missing calendar fold {year}")
        a, b = int(idx[0]), int(idx[-1])
        fold_ranges[year] = (a, b)
        baseline_fold_net[year] = float(_sim(opens, z96, -2.8, 4.5, a, b, fee)[1])

    windows = list(range(48, 145, 6))
    entries = [round(-1.8 - i * 0.1, 2) for i in range(19)]
    exits = [round(2.5 + i * 0.25, 2) for i in range(15)]
    z_by_window = {window: _zscore(close, window) for window in windows}
    rows = []
    for window in windows:
        z = z_by_window[window]
        for entry in entries:
            for exit_level in exits:
                metric = _metric_dict(_sim(opens, z, entry, exit_level, 0, len(frame) - 1, fee))
                yearly = []
                deltas = []
                positive_years = 0
                beats = 0
                for year, (a, b) in fold_ranges.items():
                    net = float(_sim(opens, z, entry, exit_level, a, b, fee)[1])
                    delta = net - baseline_fold_net[year]
                    yearly.append(net)
                    deltas.append(delta)
                    positive_years += int(net > 0)
                    beats += int(delta > 0)
                rows.append({
                    "window": window,
                    "entry": entry,
                    "exit": exit_level,
                    **metric,
                    "positive_years": positive_years,
                    "beats_baseline_years": beats,
                    "year_sum_net_points": float(sum(yearly)),
                    "year_sum_delta_points": float(sum(deltas)),
                    "worst_year_net_points": float(min(yearly)),
                    "worst_year_delta_points": float(min(deltas)),
                })

    def full_gate(row):
        return (
            row["net_points"] >= baseline["net_points"]
            and row["profit_factor"] is not None and row["profit_factor"] >= baseline["profit_factor"]
            and row["sortino"] is not None and row["sortino"] >= baseline["sortino"]
            and row["max_drawdown_points"] <= baseline["max_drawdown_points"]
            and row["trades"] >= 40
            and row["positive_years"] >= 5
            and row["beats_baseline_years"] >= 3
        )

    robust = [row for row in rows if full_gate(row)]
    strong = [row for row in robust if row["beats_baseline_years"] >= 4 and row["year_sum_delta_points"] > 0]
    strong_sorted = sorted(strong, key=lambda r: (r["beats_baseline_years"], r["year_sum_delta_points"], r["net_points"]), reverse=True)

    def support(key):
        out = {}
        for row in strong:
            token = str(row[key])
            out[token] = out.get(token, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    clusters = []
    pairs = {}
    for row in strong:
        pair = (row["window"], row["exit"])
        pairs.setdefault(pair, []).append(row)
    for (window, exit_level), members in sorted(pairs.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:12]:
        entries_here = sorted({float(row["entry"]) for row in members})
        clusters.append({
            "window": window,
            "exit": exit_level,
            "support": len(members),
            "entries": entries_here,
            "entry_min": min(entries_here),
            "entry_max": max(entries_here),
            "net_min": min(float(row["net_points"]) for row in members),
            "net_max": max(float(row["net_points"]) for row in members),
            "calendar_delta_min": min(float(row["year_sum_delta_points"]) for row in members),
            "calendar_delta_max": max(float(row["year_sum_delta_points"]) for row in members),
        })

    return {
        "schema": "autotuner-crw-score-core-receipt-v1",
        "authority": AUTHORITY,
        "symbol": "MNQ",
        "timeframe": "12Min",
        "dataset_sha256": DATA_SHA256,
        "rows": EXPECTED_ROWS,
        "scientific_scope": "score_core_only_dca_policy_held_out",
        "calibration": {"state": "PASS_EXACT", "baseline": baseline, "expected": EXPECTED_CALIBRATION},
        "search": {"configuration_count": len(rows), "windows": windows, "entries": entries, "exits": exits},
        "baseline": baseline,
        "robust_gate_count": len(robust),
        "strong_robust_count": len(strong),
        "strong_support": {"window": support("window"), "exit": support("exit"), "entry": support("entry")},
        "strong_clusters": clusters,
        "top_strong": strong_sorted[:20],
        "interpretation": {
            "point_optimizer": False,
            "robust_band_evidence": True,
            "dca_ladder_used": False,
            "dca_policy_next": "test validated adaptive signal-reentry/capital policies separately over robust score regions",
            "model_context_role": "parameter-range and sensitivity context only; no automatic promotion",
        },
        "safety": {
            "strategy_spec_write": False,
            "runtime_activation": False,
            "broker_submit": False,
            "promotion_authority": False,
            "live_trading_change": False,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--ciphertext", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    args = p.parse_args()
    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=Path(args.ciphertext).read_bytes(),
        private_key_path=Path(args.private_key),
        expected_schema=SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=HARNESS,
        response_root=args.response_root,
    )
    receipt = _campaign(_load_payload(plaintext))
    print("AUTOTUNER_SCORE_CORE_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
