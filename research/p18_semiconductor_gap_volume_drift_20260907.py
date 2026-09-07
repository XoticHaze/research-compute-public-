from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = "2004-01-01"
END = "2026-09-08"
PANEL = ["NVDA", "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "TXN", "ADI", "MCHP", "MRVL"]
BENCHMARKS = ["SMH", "QQQ", "SPY"]
GAP_MIN = 0.04
VOLUME_MULT_MIN = 1.50
VOLUME_LOOKBACK = 20
HOLD_SESSIONS = 5
COSTS_BPS = [10.0, 25.0, 50.0]
PRIMARY_COST_BPS = 25.0
OUT = "p18-semiconductor-gap-volume-drift-receipt.json"


def epoch(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


def fetch_symbol(symbol: str) -> tuple[pd.DataFrame, dict]:
    q = urlencode({
        "period1": epoch(START),
        "period2": epoch(END),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"})
    raw = urlopen(req, timeout=45).read()
    if not raw:
        raise RuntimeError(f"empty price response {symbol}")
    payload = json.loads(raw)["chart"]["result"][0]
    idx = pd.to_datetime(payload["timestamp"], unit="s", utc=True)
    quote = payload["indicators"]["quote"][0]
    adj = (payload["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    frame = pd.DataFrame({
        "open": pd.to_numeric(pd.Series(quote["open"]), errors="coerce").to_numpy(),
        "high": pd.to_numeric(pd.Series(quote["high"]), errors="coerce").to_numpy(),
        "low": pd.to_numeric(pd.Series(quote["low"]), errors="coerce").to_numpy(),
        "close": pd.to_numeric(pd.Series(quote["close"]), errors="coerce").to_numpy(),
        "volume": pd.to_numeric(pd.Series(quote["volume"]), errors="coerce").to_numpy(),
    }, index=idx)
    if adj is not None:
        frame["adjclose"] = pd.to_numeric(pd.Series(adj), errors="coerce").to_numpy()
    else:
        frame["adjclose"] = frame["close"]
    frame = frame.dropna(subset=["open", "close", "adjclose", "volume"]).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    factor = (frame["adjclose"] / frame["close"]).replace([np.inf, -np.inf], np.nan)
    frame["adjopen"] = frame["open"] * factor
    frame["adjclose"] = frame["close"] * factor
    frame = frame.dropna(subset=["adjopen", "adjclose"])
    identity = {
        "symbol": symbol,
        "url": url,
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "rows": int(len(frame)),
        "first": frame.index.min().isoformat(),
        "last": frame.index.max().isoformat(),
    }
    return frame, identity


def trade_return(frame: pd.DataFrame, event_i: int) -> tuple[pd.Timestamp, pd.Timestamp, float] | None:
    entry_i = event_i + 1
    exit_i = event_i + HOLD_SESSIONS
    if exit_i >= len(frame):
        return None
    entry = float(frame["adjopen"].iloc[entry_i])
    exit_px = float(frame["adjclose"].iloc[exit_i])
    if not np.isfinite(entry) or not np.isfinite(exit_px) or entry <= 0:
        return None
    return frame.index[entry_i], frame.index[exit_i], exit_px / entry - 1.0


def matched_return(frame: pd.DataFrame, entry_date: pd.Timestamp, exit_date: pd.Timestamp) -> float | None:
    if entry_date not in frame.index or exit_date not in frame.index:
        return None
    entry = float(frame.loc[entry_date, "adjopen"])
    exit_px = float(frame.loc[exit_date, "adjclose"])
    if not np.isfinite(entry) or not np.isfinite(exit_px) or entry <= 0:
        return None
    return exit_px / entry - 1.0


def fold_stats(events: list[dict], metric: str) -> list[dict]:
    ordered = sorted(events, key=lambda x: (x["event_date"], x["symbol"]))
    cuts = np.array_split(np.arange(len(ordered)), 5)
    out = []
    for n, ids in enumerate(cuts, start=1):
        rows = [ordered[int(i)] for i in ids]
        if not rows:
            continue
        vals = np.array([r[metric] for r in rows], dtype=float)
        out.append({
            "fold": n,
            "n": len(rows),
            "first": rows[0]["event_date"],
            "last": rows[-1]["event_date"],
            "mean": float(vals.mean()),
            "median": float(np.median(vals)),
            "positive_rate": float((vals > 0).mean()),
        })
    return out


def summarize(events: list[dict], key: str) -> dict:
    a = np.array([x[key] for x in events], dtype=float)
    return {
        "n": int(len(a)),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "positive_rate": float((a > 0).mean()),
        "p10": float(np.quantile(a, 0.10)),
        "p90": float(np.quantile(a, 0.90)),
    }


def main() -> None:
    retrieval_at = datetime.now(timezone.utc).isoformat()
    data = {}
    identities = {}
    for sym in PANEL + BENCHMARKS:
        data[sym], identities[sym] = fetch_symbol(sym)

    events = []
    for sym in PANEL:
        f = data[sym].copy()
        prior_close = f["adjclose"].shift(1)
        f["gap"] = f["adjopen"] / prior_close - 1.0
        f["prior_vol_med"] = f["volume"].shift(1).rolling(VOLUME_LOOKBACK, min_periods=VOLUME_LOOKBACK).median()
        f["volume_multiple"] = f["volume"] / f["prior_vol_med"]
        signal = (f["gap"] >= GAP_MIN) & (f["adjclose"] >= f["adjopen"]) & (f["volume_multiple"] >= VOLUME_MULT_MIN)
        for event_i in np.flatnonzero(signal.to_numpy()):
            tr = trade_return(f, int(event_i))
            if tr is None:
                continue
            entry_date, exit_date, gross = tr
            bench = {b: matched_return(data[b], entry_date, exit_date) for b in BENCHMARKS}
            panel_rets = [matched_return(data[p], entry_date, exit_date) for p in PANEL]
            panel_rets = [x for x in panel_rets if x is not None and np.isfinite(x)]
            if any(v is None for v in bench.values()) or len(panel_rets) < 6:
                continue
            events.append({
                "symbol": sym,
                "event_date": f.index[event_i].isoformat(),
                "entry_date": entry_date.isoformat(),
                "exit_date": exit_date.isoformat(),
                "gap": float(f["gap"].iloc[event_i]),
                "volume_multiple": float(f["volume_multiple"].iloc[event_i]),
                "gross": float(gross),
                "SMH": float(bench["SMH"]),
                "QQQ": float(bench["QQQ"]),
                "SPY": float(bench["SPY"]),
                "equal_panel": float(np.mean(panel_rets)),
            })

    if len(events) < 60:
        raise RuntimeError(f"insufficient frozen events: {len(events)}")

    for e in events:
        for c in COSTS_BPS:
            e[f"net_{int(c)}"] = e["gross"] - 2.0 * c / 10000.0
        e["excess_smh_25"] = e["net_25"] - e["SMH"]
        e["excess_qqq_25"] = e["net_25"] - e["QQQ"]
        e["excess_spy_25"] = e["net_25"] - e["SPY"]
        e["excess_equal_25"] = e["net_25"] - e["equal_panel"]

    years = {}
    symbols = {}
    for e in events:
        y = e["event_date"][:4]
        years.setdefault(y, []).append(e)
        symbols.setdefault(e["symbol"], []).append(e)

    fold_excess = fold_stats(events, "excess_smh_25")
    positive_folds = sum(f["mean"] > 0 for f in fold_excess)
    net50 = summarize(events, "net_50")
    ex_smh = summarize(events, "excess_smh_25")
    ex_equal = summarize(events, "excess_equal_25")
    supported = (
        len(events) >= 75
        and ex_smh["mean"] > 0.0075
        and ex_equal["mean"] > 0.0050
        and ex_smh["positive_rate"] >= 0.55
        and positive_folds >= 4
        and net50["mean"] > 0
    )

    receipt = {
        "schema": "public_compute.p18_semiconductor_gap_volume_drift.v1",
        "decision": "P18_GAP_VOLUME_DRIFT_SUPPORTED" if supported else "P18_GAP_VOLUME_DRIFT_NOT_SUPPORTED",
        "frozen_before_execution": True,
        "hypothesis_family": "event_microstructure_post_gap_abnormal_volume_continuation",
        "frozen_rule": {
            "event_information_time": "after event-day close",
            "gap_min": GAP_MIN,
            "close_confirmation": "adjusted close >= adjusted open",
            "volume_multiple_min": VOLUME_MULT_MIN,
            "volume_baseline": f"prior {VOLUME_LOOKBACK}-session median, excluding event day",
            "entry": "next-session adjusted open",
            "exit": f"event index + {HOLD_SESSIONS} session adjusted close",
            "long_only": True,
            "parameter_search": False,
        },
        "panel": PANEL,
        "matched_baselines": BENCHMARKS + ["equal_current_panel"],
        "window": {
            "requested_start": START,
            "requested_end_exclusive": END,
            "first_event": min(e["event_date"] for e in events),
            "last_event": max(e["event_date"] for e in events),
            "events": len(events),
            "years_with_events": len(years),
        },
        "provenance": {
            "source": "Yahoo Finance chart API",
            "retrieved_at": retrieval_at,
            "per_symbol_response_identity": identities,
            "note": "Mutable public source responses are admitted by exact query URL and SHA256 at retrieval time; no claim of runtime/canonical MM authority.",
        },
        "metrics": {
            "gross": summarize(events, "gross"),
            "net_by_cost_bps": {str(int(c)): summarize(events, f"net_{int(c)}") for c in COSTS_BPS},
            "benchmarks": {b: summarize(events, b) for b in BENCHMARKS},
            "equal_panel": summarize(events, "equal_panel"),
            "excess_at_25bps": {
                "vs_SMH": ex_smh,
                "vs_QQQ": summarize(events, "excess_qqq_25"),
                "vs_SPY": summarize(events, "excess_spy_25"),
                "vs_equal_panel": ex_equal,
            },
            "chronological_folds_vs_SMH_25bps": fold_excess,
            "positive_folds_vs_SMH": positive_folds,
            "by_year_vs_SMH_25bps": {
                y: {"n": len(rows), "mean_excess": float(np.mean([r["excess_smh_25"] for r in rows]))}
                for y, rows in sorted(years.items())
            },
            "by_symbol_vs_SMH_25bps": {
                s: {"n": len(rows), "mean_excess": float(np.mean([r["excess_smh_25"] for r in rows]))}
                for s, rows in sorted(symbols.items())
            },
        },
        "promotion_gate": {
            "min_events": 75,
            "mean_excess_vs_SMH_25bps_min": 0.0075,
            "mean_excess_vs_equal_panel_25bps_min": 0.0050,
            "event_win_rate_vs_SMH_min": 0.55,
            "positive_chronological_folds_vs_SMH_min": 4,
            "mean_net_50bps_must_be_positive": True,
            "passed": supported,
        },
        "capital_context": {
            "event_level_test": True,
            "portfolio_allocator_not_claimed": True,
            "overlap_not_net_portfolio_simulated": True,
            "survivorship_bias_limitation": "Current liquid semiconductor panel is fixed prospectively for this test but is not point-in-time constituent history; support would require point-in-time-universe confirmation before capital promotion.",
        },
        "safety": {
            "strategy_spec_changed": False,
            "allocation_authority_changed": False,
            "runtime_changed": False,
            "broker_submission": False,
            "live_trading_changed": False,
        },
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
