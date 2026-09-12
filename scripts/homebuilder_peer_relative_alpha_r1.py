from __future__ import annotations

"""Homebuilder peer-relative alpha test.

Purpose
-------
Test whether a shared, ticker-agnostic Homebuilder state model can add marginal
component-selection alpha over the stronger equal-weight Homebuilder baseline,
rather than merely beat ITB.

Development symbols provide all target training. Fresh external symbols provide
zero target rows to training. The target is 20-session component return minus the
equal-weight development-peer basket over the same +1/fixed20 window, less a
conservative 50 bps switching hurdle.

The investable test preserves a 75% equal-weight external Homebuilder core and
uses at most 25% for a marginal tilt into up to two predicted-positive external
components. No threshold, horizon, model-family, feature subset, or capacity sweep.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

START = "2019-01-01"
END_EXCLUSIVE = "2026-09-13"
DEV = ("DHI", "LEN", "PHM", "NVR", "TOL", "MTH", "KBH", "LGIH")
EXTERNAL = ("TMHC", "GRBK", "CVCO", "SKY")
CONTEXT = ("ITB", "QQQ")
ALL = (*DEV, *EXTERNAL, *CONTEXT)

DELAY = 1
HOLD = 20
TRAIN_STEP = 5
DECISION_STEP = 20
BURNIN = 504
PURGE = DELAY + HOLD
SWITCH_HURDLE_BPS = 50.0
COMMON_REBALANCE_BPS = 25.0
TILT_WEIGHT = 0.25
MAX_TILT_NAMES = 2
FOLDS = 5
MIN_TRAIN_ROWS = 560
MIN_DECISIONS = 60
MIN_TILT_DECISIONS = 20
MIN_SYMBOL_EVENTS = 5

FEATURES = (
    "ret5",
    "ret20",
    "ret60",
    "ret120",
    "rel_itb5",
    "rel_itb20",
    "rel_itb60",
    "rel_itb120",
    "vol20",
    "vol60",
    "distance_high60",
    "itb_ret20",
    "itb_ret60",
    "itb_vol20",
    "qqq_ret20",
    "qqq_ret60",
    "peer_rel20_percentile",
)

OUTPUT = Path("research/results/homebuilder_peer_relative_alpha_r1.json")


def epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def load(symbol: str) -> pd.Series:
    query = urlencode(
        {
            "period1": epoch(START),
            "period2": epoch(END_EXCLUSIVE),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    request = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}",
        headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 fixed HTTPS host
        payload = json.loads(response.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no chart result")
    exchange_tz = result.get("meta", {}).get("exchangeTimezoneName") or "America/New_York"
    timestamps = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True).tz_convert(exchange_tz).normalize().tz_localize(None)
    indicators = result.get("indicators", {})
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    close = adjusted or (indicators.get("quote") or [{}])[0].get("close")
    values = pd.to_numeric(pd.Series(close), errors="coerce").to_numpy()
    series = pd.Series(values, index=timestamps, name=symbol).dropna()
    return series[~series.index.duplicated(keep="last")].sort_index()


def ret(series: pd.Series, i: int, horizon: int) -> float:
    return float(series.iloc[i] / series.iloc[i - horizon] - 1.0)


def future_ret(series: pd.Series, signal_i: int) -> float:
    entry_i = signal_i + DELAY
    exit_i = entry_i + HOLD
    return float(series.iloc[exit_i] / series.iloc[entry_i] - 1.0)


def vol(series: pd.Series, i: int, horizon: int) -> float:
    window = series.pct_change().iloc[i - horizon + 1 : i + 1]
    return float(window.std(ddof=0) * np.sqrt(252.0))


def feature_vector(frame: pd.DataFrame, symbol: str, i: int) -> dict[str, float]:
    stock = frame[symbol]
    itb = frame["ITB"]
    qqq = frame["QQQ"]

    rel20 = ret(stock, i, 20) - ret(itb, i, 20)
    peer_rel20 = np.asarray(
        [ret(frame[s], i, 20) - ret(itb, i, 20) for s in DEV],
        dtype=float,
    )
    percentile = float(np.mean(peer_rel20 <= rel20))

    return {
        "ret5": ret(stock, i, 5),
        "ret20": ret(stock, i, 20),
        "ret60": ret(stock, i, 60),
        "ret120": ret(stock, i, 120),
        "rel_itb5": ret(stock, i, 5) - ret(itb, i, 5),
        "rel_itb20": rel20,
        "rel_itb60": ret(stock, i, 60) - ret(itb, i, 60),
        "rel_itb120": ret(stock, i, 120) - ret(itb, i, 120),
        "vol20": vol(stock, i, 20),
        "vol60": vol(stock, i, 60),
        "distance_high60": float(stock.iloc[i] / stock.iloc[i - 59 : i + 1].max() - 1.0),
        "itb_ret20": ret(itb, i, 20),
        "itb_ret60": ret(itb, i, 60),
        "itb_vol20": vol(itb, i, 20),
        "qqq_ret20": ret(qqq, i, 20),
        "qqq_ret60": ret(qqq, i, 60),
        "peer_rel20_percentile": percentile,
    }


def build_training_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    safe_stop = len(frame) - PURGE
    for signal_i in range(120, safe_stop, TRAIN_STEP):
        for symbol in DEV:
            feats = feature_vector(frame, symbol, signal_i)
            stock_future = future_ret(frame[symbol], signal_i)
            peer_future = float(
                np.mean([future_ret(frame[s], signal_i) for s in DEV if s != symbol])
            )
            target_bps = (stock_future - peer_future) * 10000.0 - SWITCH_HURDLE_BPS
            rows.append(
                {
                    "signal_i": signal_i,
                    "symbol": symbol,
                    "target_peer_excess_after50_bps": target_bps,
                    **feats,
                }
            )
    out = pd.DataFrame(rows)
    if not np.isfinite(out[list(FEATURES) + ["target_peer_excess_after50_bps"]].to_numpy(float)).all():
        raise RuntimeError("non-finite training row")
    return out


def fit_model(train: pd.DataFrame) -> Pipeline:
    if len(train) < MIN_TRAIN_ROWS:
        raise RuntimeError(f"insufficient causal train rows={len(train)}")
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=10.0)),
        ]
    )
    model.fit(
        train[list(FEATURES)].to_numpy(float),
        train["target_peer_excess_after50_bps"].to_numpy(float),
    )
    return model


def annualize_periodic(returns: list[float]) -> float | None:
    if not returns:
        return None
    arr = np.asarray(returns, dtype=float)
    if np.any(arr <= -1.0):
        return None
    periods_per_year = 252.0 / DECISION_STEP
    growth = float(np.prod(1.0 + arr))
    return float(growth ** (periods_per_year / len(arr)) - 1.0)


def fold_mean(values: list[float]) -> float | None:
    return None if not values else float(np.mean(np.asarray(values, dtype=float)))


def main() -> None:
    raw = {symbol: load(symbol) for symbol in ALL}
    source_last = {symbol: series.index[-1].isoformat() for symbol, series in raw.items()}
    common = pd.DatetimeIndex(sorted(set.intersection(*[set(series.index) for series in raw.values()])))
    if len(common) < 1700:
        raise RuntimeError(f"insufficient common calendar={len(common)}")
    frame = pd.DataFrame({symbol: raw[symbol].reindex(common) for symbol in ALL}).dropna()
    if len(frame) < 1700:
        raise RuntimeError(f"insufficient normalized common calendar={len(frame)}")

    training = build_training_rows(frame)
    decision_indices = list(range(BURNIN, len(frame) - PURGE, DECISION_STEP))
    if len(decision_indices) < MIN_DECISIONS:
        raise RuntimeError(f"insufficient external decisions={len(decision_indices)}")
    fold_indices = [list(map(int, part)) for part in np.array_split(np.asarray(decision_indices), FOLDS)]

    decisions: list[dict] = []
    per_symbol_selected: dict[str, list[float]] = {symbol: [] for symbol in EXTERNAL}
    per_symbol_counts: dict[str, int] = {symbol: 0 for symbol in EXTERNAL}

    for fold_no, fold_signals in enumerate(fold_indices, start=1):
        if not fold_signals:
            continue
        first_signal = fold_signals[0]
        train = training[training.signal_i < first_signal - PURGE].copy()
        model = fit_model(train)

        for signal_i in fold_signals:
            feature_rows = pd.DataFrame(
                [{"symbol": symbol, **feature_vector(frame, symbol, signal_i)} for symbol in EXTERNAL]
            )
            predictions = model.predict(feature_rows[list(FEATURES)].to_numpy(float))
            candidates = sorted(
                [
                    (float(pred), str(symbol))
                    for pred, symbol in zip(predictions, feature_rows["symbol"], strict=True)
                    if float(pred) > 0.0
                ],
                key=lambda item: (-item[0], item[1]),
            )
            selected = [symbol for _, symbol in candidates[:MAX_TILT_NAMES]]

            external_returns = {symbol: future_ret(frame[symbol], signal_i) for symbol in EXTERNAL}
            baseline_gross = float(np.mean(list(external_returns.values())))
            baseline_net = baseline_gross - COMMON_REBALANCE_BPS / 10000.0

            if selected:
                selected_gross = float(np.mean([external_returns[symbol] for symbol in selected]))
                conservative_peer_excess_bps = (
                    selected_gross - baseline_gross
                ) * 10000.0 - SWITCH_HURDLE_BPS
                overlay_net = baseline_net + TILT_WEIGHT * (
                    selected_gross - baseline_gross - SWITCH_HURDLE_BPS / 10000.0
                )
                for symbol in selected:
                    symbol_excess_bps = (
                        external_returns[symbol] - baseline_gross
                    ) * 10000.0 - SWITCH_HURDLE_BPS
                    per_symbol_selected[symbol].append(float(symbol_excess_bps))
                    per_symbol_counts[symbol] += 1
            else:
                selected_gross = None
                conservative_peer_excess_bps = None
                overlay_net = baseline_net

            entry_i = signal_i + DELAY
            exit_i = entry_i + HOLD
            decisions.append(
                {
                    "fold": fold_no,
                    "signal_i": signal_i,
                    "signal_date": frame.index[signal_i].isoformat(),
                    "entry_date": frame.index[entry_i].isoformat(),
                    "exit_date": frame.index[exit_i].isoformat(),
                    "train_rows": int(len(train)),
                    "predictions_bps": {
                        str(symbol): float(pred)
                        for pred, symbol in zip(predictions, feature_rows["symbol"], strict=True)
                    },
                    "selected": selected,
                    "baseline_equal_external_net": baseline_net,
                    "overlay_75core_25tilt_net": overlay_net,
                    "incremental_overlay_bps": float((overlay_net - baseline_net) * 10000.0),
                    "selected_gross_return": selected_gross,
                    "conservative_selected_minus_equal_peer_bps": conservative_peer_excess_bps,
                    "itb_gross_return": future_ret(frame["ITB"], signal_i),
                }
            )

    incremental = [float(row["incremental_overlay_bps"]) for row in decisions]
    baseline_returns = [float(row["baseline_equal_external_net"]) for row in decisions]
    overlay_returns = [float(row["overlay_75core_25tilt_net"]) for row in decisions]
    selected_excess = [
        float(row["conservative_selected_minus_equal_peer_bps"])
        for row in decisions
        if row["conservative_selected_minus_equal_peer_bps"] is not None
    ]
    tilt_decisions = sum(bool(row["selected"]) for row in decisions)

    fold_rows = []
    for fold_no in range(1, FOLDS + 1):
        rows = [row for row in decisions if row["fold"] == fold_no]
        vals = [float(row["incremental_overlay_bps"]) for row in rows]
        selected_vals = [
            float(row["conservative_selected_minus_equal_peer_bps"])
            for row in rows
            if row["conservative_selected_minus_equal_peer_bps"] is not None
        ]
        fold_rows.append(
            {
                "fold": fold_no,
                "decisions": len(rows),
                "tilt_decisions": sum(bool(row["selected"]) for row in rows),
                "mean_incremental_overlay_bps": fold_mean(vals),
                "mean_selected_peer_excess_after50_bps": fold_mean(selected_vals),
            }
        )

    symbol_rows = []
    symbol_passes = 0
    for symbol in EXTERNAL:
        vals = per_symbol_selected[symbol]
        mean_bps = fold_mean(vals)
        passed = len(vals) >= MIN_SYMBOL_EVENTS and mean_bps is not None and mean_bps > 0.0
        symbol_passes += int(passed)
        symbol_rows.append(
            {
                "symbol": symbol,
                "selected_events": len(vals),
                "mean_conservative_peer_excess_bps": mean_bps,
                "pass": passed,
            }
        )

    positive_increment_folds = sum(
        row["mean_incremental_overlay_bps"] is not None
        and row["mean_incremental_overlay_bps"] > 0.0
        for row in fold_rows
    )
    selected_mean = fold_mean(selected_excess)
    baseline_ann = annualize_periodic(baseline_returns)
    overlay_ann = annualize_periodic(overlay_returns)
    annualized_increment = (
        None if baseline_ann is None or overlay_ann is None else overlay_ann - baseline_ann
    )

    gate = (
        len(decisions) >= MIN_DECISIONS
        and tilt_decisions >= MIN_TILT_DECISIONS
        and annualized_increment is not None
        and annualized_increment > 0.0
        and positive_increment_folds >= 4
        and selected_mean is not None
        and selected_mean > 0.0
        and symbol_passes >= 3
    )
    decision = (
        "HOMEBUILDER_PEER_RELATIVE_MARGINAL_TILT_PASSES_EXTERNAL_GATE"
        if gate
        else "HOMEBUILDER_PEER_RELATIVE_MARGINAL_TILT_REJECTED_AS_SPECIFIED"
    )

    output = {
        "schema": "public_research.homebuilder_peer_relative_alpha_r1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim": (
            "A ticker-agnostic shared Homebuilder state model can identify marginal component "
            "tilts that add value over an equal-weight Homebuilder core, rather than merely "
            "outperforming ITB."
        ),
        "source": {
            "provider": "Yahoo adjusted daily via fixed HTTPS endpoint",
            "start": START,
            "end_exclusive": END_EXCLUSIVE,
            "source_last_timestamp": source_last,
            "common_first": frame.index[0].isoformat(),
            "common_last": frame.index[-1].isoformat(),
            "common_sessions": int(len(frame)),
        },
        "contract": {
            "development_symbols": list(DEV),
            "external_symbols_target_excluded": list(EXTERNAL),
            "context": list(CONTEXT),
            "model": "StandardScaler + Ridge(alpha=10)",
            "ticker_identity_feature": False,
            "features": list(FEATURES),
            "training_target": (
                "future +1/fixed20 component gross return minus equal-weight other-development-"
                "Homebuilders gross return minus 50 bps switching hurdle"
            ),
            "train_step_sessions": TRAIN_STEP,
            "decision_step_sessions": DECISION_STEP,
            "delay_sessions": DELAY,
            "hold_sessions": HOLD,
            "purge_sessions": PURGE,
            "candidate_rule": "predicted peer-relative after-50bps value > 0",
            "ranking": "descending predicted peer-relative value among positive candidates",
            "max_tilt_names": MAX_TILT_NAMES,
            "portfolio": "75% equal-weight external Homebuilder core + 25% marginal selected tilt",
            "common_rebalance_cost_bps": COMMON_REBALANCE_BPS,
            "marginal_switch_hurdle_bps": SWITCH_HURDLE_BPS,
            "hyperparameter_search": False,
            "threshold_search": False,
            "holdout_target_training": False,
        },
        "acceptance_gate": {
            "minimum_decisions": MIN_DECISIONS,
            "minimum_tilt_decisions": MIN_TILT_DECISIONS,
            "annualized_increment_over_equal_core_gt_zero": True,
            "positive_incremental_folds_required": 4,
            "aggregate_selected_peer_excess_after50_bps_gt_zero": True,
            "external_symbols_passing_required": 3,
            "minimum_selected_events_per_symbol": MIN_SYMBOL_EVENTS,
        },
        "metrics": {
            "decisions": len(decisions),
            "tilt_decisions": tilt_decisions,
            "baseline_equal_external_annualized": baseline_ann,
            "overlay_75core_25tilt_annualized": overlay_ann,
            "annualized_increment": annualized_increment,
            "mean_incremental_overlay_bps_per_decision": fold_mean(incremental),
            "mean_selected_peer_excess_after50_bps": selected_mean,
            "positive_incremental_folds": positive_increment_folds,
            "external_symbol_passes": symbol_passes,
        },
        "folds": fold_rows,
        "external_symbols": symbol_rows,
        "decision": decision,
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "promotion_authority": False,
            "strategy_spec_mutation": False,
            "runtime_mutation": False,
            "broker_authority": False,
            "live_trading_change": False,
        },
        "decisions": decisions,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print("HOMEBUILDER_PEER_RELATIVE_ALPHA=" + json.dumps(output, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
