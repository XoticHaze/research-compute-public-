from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = "1999-01-01"
END = "2026-09-08"
PRICE_SYMBOLS = ["SMH", "QQQ", "SPY"]
OAS_SERIES = "BAMLH0A0HYM2"
OAS_ARCHIVE_COMMIT = "bf64e83fa4c2a6e72c37d3883476dc81bd9d2e31"
OAS_ARCHIVE_URL = f"https://raw.githubusercontent.com/maaurocp/Trading_Protocol/{OAS_ARCHIVE_COMMIT}/data/raw/fred_BAMLH0A0HYM2.csv"
OAS_TAIL_URL = "https://convextrade.com/metrics/bamlh0a0hym2/data.csv"
OAS_MA_OBS = 252
OAS_DELTA_OBS = 63
PUBLICATION_LAG_DAYS = 7
COSTS_BPS = [10.0, 25.0, 50.0]
PRIMARY_COST_BPS = 25.0
OUT = "p17-credit-oas-semiconductor-switch-receipt.json"


def epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def fetch_bytes(url: str, timeout: int = 45) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"})
    with urlopen(req, timeout=timeout) as response:
        raw = response.read()
    if not raw:
        raise RuntimeError(f"empty response from {url}")
    return raw


def load_price(symbol: str) -> pd.Series:
    query = urlencode({"period1": epoch(START), "period2": epoch(END), "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    req = Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}", headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"})
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no Yahoo chart result")
    timestamps = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True)
    indicators = result.get("indicators", {})
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    close = adjusted or (indicators.get("quote") or [{}])[0].get("close")
    series = pd.Series(pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(), index=timestamps, name=symbol).dropna()
    if len(series) < 1000:
        raise RuntimeError(f"{symbol}: insufficient price rows {len(series)}")
    return series[~series.index.duplicated(keep="last")].sort_index()


def parse_archive(raw: bytes) -> pd.Series:
    frame = pd.read_csv(io.BytesIO(raw), na_values=[".", ""])
    date_col = "date" if "date" in frame.columns else "DATE"
    value_col = OAS_SERIES
    if date_col not in frame.columns or value_col not in frame.columns:
        raise RuntimeError(f"unexpected archive columns: {list(frame.columns)}")
    idx = pd.to_datetime(frame[date_col], utc=True, errors="coerce")
    values = pd.to_numeric(frame[value_col], errors="coerce")
    series = pd.Series(values.to_numpy(), index=idx, name=OAS_SERIES).dropna().sort_index()
    return series[~series.index.duplicated(keep="last")]


def parse_tail(raw: bytes) -> tuple[pd.Series, int]:
    text = raw.decode("utf-8-sig", errors="strict")
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        tokens = [token.strip().strip('"').lower() for token in line.split(",")]
        if "date" in tokens and any(token in {"value", "value_bps", OAS_SERIES.lower(), "close"} for token in tokens):
            header_index = index
            break
    if header_index is None:
        raise RuntimeError(f"OAS tail has no recognized CSV header; first_lines={lines[:8]!r}")
    frame = pd.read_csv(io.StringIO("\n".join(lines[header_index:]) + "\n"))
    lowered = {str(column).strip().lower(): column for column in frame.columns}
    date_col = lowered.get("date") or lowered.get("observation_date") or lowered.get("timestamp")
    value_col = lowered.get("value") or lowered.get("value_bps") or lowered.get(OAS_SERIES.lower()) or lowered.get("close")
    if date_col is None or value_col is None:
        raise RuntimeError(f"unexpected OAS tail columns: {list(frame.columns)}")
    idx = pd.to_datetime(frame[date_col], utc=True, errors="coerce")
    values = pd.to_numeric(frame[value_col], errors="coerce")
    series = pd.Series(values.to_numpy(), index=idx, name=OAS_SERIES).dropna().sort_index()
    series = series[~series.index.duplicated(keep="last")]
    if float(series.median()) > 50.0:
        series = series / 100.0
    return series, int(header_index)


def load_oas() -> tuple[pd.Series, str, dict[str, object]]:
    archive_raw = fetch_bytes(OAS_ARCHIVE_URL)
    tail_raw = fetch_bytes(OAS_TAIL_URL)
    archive = parse_archive(archive_raw)
    tail, preamble_lines = parse_tail(tail_raw)
    if archive.index.min() > pd.Timestamp("1997-01-02", tz="UTC") or archive.index.max() < pd.Timestamp("2026-02-01", tz="UTC"):
        raise RuntimeError(f"archive date span unexpected: {archive.index.min()} -> {archive.index.max()}")
    if tail.index.min() > pd.Timestamp("2021-09-15", tz="UTC"):
        raise RuntimeError(f"tail starts too late for overlap validation: {tail.index.min()}")

    overlap_idx = archive.index.intersection(tail.index)
    overlap = pd.DataFrame({"archive": archive.reindex(overlap_idx), "tail": tail.reindex(overlap_idx)}).dropna()
    if len(overlap) < 500:
        raise RuntimeError(f"insufficient OAS overlap rows: {len(overlap)}")
    abs_diff = (overlap["archive"] - overlap["tail"]).abs()
    median_abs_diff = float(abs_diff.median())
    p99_abs_diff = float(abs_diff.quantile(0.99))
    if median_abs_diff > 0.011 or p99_abs_diff > 0.051:
        raise RuntimeError(f"OAS overlap mismatch: rows={len(overlap)} median_abs={median_abs_diff} p99_abs={p99_abs_diff}")

    tail_only = tail.loc[tail.index > archive.index.max()]
    series = pd.concat([archive, tail_only]).sort_index()
    series = series[~series.index.duplicated(keep="last")]
    if len(series) < 7000:
        raise RuntimeError(f"stitched OAS history too short: {len(series)}")
    anchor_date = pd.Timestamp("2026-09-03", tz="UTC")
    anchor = series.loc[series.index == anchor_date]
    if anchor.empty or abs(float(anchor.iloc[-1]) - 2.65) > 0.011:
        raise RuntimeError(f"stitched OAS failed FRED anchor 2026-09-03=2.65; observed={None if anchor.empty else float(anchor.iloc[-1])}")

    archive_sha256 = hashlib.sha256(archive_raw).hexdigest()
    tail_sha256 = hashlib.sha256(tail_raw).hexdigest()
    stitched_identity = hashlib.sha256(pd.util.hash_pandas_object(series, index=True).values.tobytes()).hexdigest()
    provenance = {
        "authority_series": OAS_SERIES,
        "archive": {
            "provider": "maaurocp/Trading_Protocol public FRED archive",
            "commit": OAS_ARCHIVE_COMMIT,
            "url": OAS_ARCHIVE_URL,
            "sha256": archive_sha256,
            "rows": int(len(archive)),
            "first_timestamp": archive.index.min().isoformat(),
            "last_timestamp": archive.index.max().isoformat(),
        },
        "current_tail": {
            "provider": "Convex mirror of FRED BAMLH0A0HYM2",
            "url": OAS_TAIL_URL,
            "sha256": tail_sha256,
            "rows": int(len(tail)),
            "first_timestamp": tail.index.min().isoformat(),
            "last_timestamp": tail.index.max().isoformat(),
            "metadata_preamble_lines": preamble_lines,
        },
        "overlap_validation": {
            "rows": int(len(overlap)),
            "median_abs_difference_percent": median_abs_diff,
            "p99_abs_difference_percent": p99_abs_diff,
            "accepted": True,
        },
        "fred_anchor": {"date": "2026-09-03", "value_percent": 2.65, "validated": True},
        "stitched_rows": int(len(series)),
        "stitched_first_timestamp": series.index.min().isoformat(),
        "stitched_last_timestamp": series.index.max().isoformat(),
        "stitched_content_identity": stitched_identity,
    }
    return series, stitched_identity, provenance


def month_end_indices(frame: pd.DataFrame) -> list[int]:
    return [i for i in range(len(frame) - 1) if frame.index[i].month != frame.index[i + 1].month]


def turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    names = set(previous) | set(current)
    return 0.5 * sum(abs(current.get(name, 0.0) - previous.get(name, 0.0)) for name in names)


def summary(rows: list[tuple[pd.Timestamp, float]]) -> dict[str, object]:
    if not rows:
        raise RuntimeError("empty return stream")
    equity = [1.0]
    years: dict[str, float] = {}
    for date, ret in rows:
        equity.append(equity[-1] * (1.0 + ret))
        years[str(date.year)] = years.get(str(date.year), 1.0) * (1.0 + ret)
    span = max((rows[-1][0] - rows[0][0]).days / 365.25, 1.0 / 12.0)
    peak = equity[0]
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0)
    periodic = np.array([ret for _, ret in rows], dtype=float)
    ann_vol = float(np.std(periodic, ddof=1) * math.sqrt(12.0)) if len(periodic) > 1 else 0.0
    cagr = equity[-1] ** (1.0 / span) - 1.0
    return {"periods": len(rows), "total_return": equity[-1] - 1.0, "cagr": cagr, "max_drawdown": max_drawdown, "annualized_volatility": ann_vol, "return_over_volatility": None if ann_vol <= 0 else cagr / ann_vol, "year_returns": {year: value - 1.0 for year, value in sorted(years.items())}}


def main() -> None:
    prices = {symbol: load_price(symbol) for symbol in PRICE_SYMBOLS}
    common = pd.DatetimeIndex(sorted(set.intersection(*[set(series.index) for series in prices.values()])))
    frame = pd.DataFrame({symbol: series.reindex(common) for symbol, series in prices.items()}).dropna()
    oas, oas_identity, oas_provenance = load_oas()
    month_ends = month_end_indices(frame)
    decisions = []
    for n, i in enumerate(month_ends[:-1]):
        j = month_ends[n + 1]
        decision_date = frame.index[i]
        cutoff = decision_date - pd.Timedelta(days=PUBLICATION_LAG_DAYS)
        available = oas.loc[oas.index <= cutoff]
        if len(available) <= max(OAS_MA_OBS, OAS_DELTA_OBS):
            continue
        current_oas = float(available.iloc[-1])
        mean_oas = float(available.iloc[-OAS_MA_OBS:].mean())
        delta_oas = current_oas - float(available.iloc[-1 - OAS_DELTA_OBS])
        selected = "SMH" if current_oas <= mean_oas and delta_oas <= 0.0 else "QQQ"
        decisions.append({"i": i, "j": j, "date": decision_date, "macro_cutoff": available.index[-1], "oas": current_oas, "oas_mean": mean_oas, "oas_delta": delta_oas, "selected": selected})
    if len(decisions) < 120:
        raise RuntimeError(f"insufficient monthly decisions {len(decisions)}")

    policy = {cost: [] for cost in COSTS_BPS}
    baselines = {"SMH": [], "QQQ": [], "SPY": [], "equal_SMH_QQQ": []}
    previous: dict[str, float] = {}
    turns: list[float] = []
    smh_months = 0
    for row in decisions:
        i, j, selected = int(row["i"]), int(row["j"]), str(row["selected"])
        smh_months += int(selected == "SMH")
        weights = {selected: 1.0}
        one_way_turnover = turnover(previous, weights)
        turns.append(one_way_turnover)
        gross = float(frame[selected].iloc[j] / frame[selected].iloc[i] - 1.0)
        for cost in COSTS_BPS:
            policy[cost].append((frame.index[j], gross - one_way_turnover * cost / 10000.0))
        previous = weights
        for symbol in ["SMH", "QQQ", "SPY"]:
            baselines[symbol].append((frame.index[j], float(frame[symbol].iloc[j] / frame[symbol].iloc[i] - 1.0)))
        baselines["equal_SMH_QQQ"].append((frame.index[j], 0.5 * float(frame["SMH"].iloc[j] / frame["SMH"].iloc[i] - 1.0) + 0.5 * float(frame["QQQ"].iloc[j] / frame["QQQ"].iloc[i] - 1.0)))

    summaries = {"credit_switch": {str(int(cost)): summary(policy[cost]) for cost in COSTS_BPS}, **{name: summary(rows) for name, rows in baselines.items()}}
    primary = summaries["credit_switch"][str(int(PRIMARY_COST_BPS))]
    smh, qqq, spy, equal = summaries["SMH"], summaries["QQQ"], summaries["SPY"], summaries["equal_SMH_QQQ"]
    common_years = sorted(set(primary["year_returns"]) & set(smh["year_returns"]) & set(qqq["year_returns"]) & set(spy["year_returns"]))
    first_year = str(frame.index[int(decisions[0]["i"])].year)
    last_year = str(frame.index[int(decisions[-1]["j"])].year)
    full_years = [year for year in common_years if year not in {first_year, last_year}]
    yearly = {year: {"vs_SMH": primary["year_returns"][year] - smh["year_returns"][year], "vs_QQQ": primary["year_returns"][year] - qqq["year_returns"][year], "vs_SPY": primary["year_returns"][year] - spy["year_returns"][year]} for year in full_years}
    wins_smh = sum(value["vs_SMH"] > 0 for value in yearly.values())
    wins_qqq = sum(value["vs_QQQ"] > 0 for value in yearly.values())
    cost_robust = all(summaries["credit_switch"][str(int(cost))]["cagr"] > summaries["QQQ"]["cagr"] for cost in COSTS_BPS)
    supported = primary["cagr"] > smh["cagr"] and primary["cagr"] > qqq["cagr"] and primary["cagr"] > equal["cagr"] and primary["max_drawdown"] >= smh["max_drawdown"] and len(full_years) >= 10 and wins_smh / len(full_years) >= 0.50 and wins_qqq / len(full_years) >= 0.60 and cost_robust

    output = {
        "schema": "public_research.p17_credit_oas_semiconductor_switch.v1",
        "research_only": True,
        "frozen_hypothesis": "At each month-end, use only ICE BofA US High Yield OAS observations at least seven calendar days old. Hold SMH for the next month when OAS is at or below its trailing 252-observation mean and has not risen over 63 observations; otherwise hold QQQ. Independent credit-state information should improve after-cost return versus SMH, QQQ, SPY and a static 50/50 SMH-QQQ opportunity set without using future macro observations.",
        "sources": {"prices": {"provider": "Yahoo chart adjusted close", "query_host": "query1.finance.yahoo.com"}, "macro": {"authority_series": OAS_SERIES, "meaning": "ICE BofA US High Yield Index Option-Adjusted Spread", "materialization": oas_provenance, "runtime_identity": oas_identity}},
        "causality": {"publication_lag_days": PUBLICATION_LAG_DAYS, "macro_cutoff_rule": "latest OAS observation timestamp <= price decision timestamp minus seven calendar days", "trade_rule": "signal at month-end close, measure return to next month-end close"},
        "parameters": {"oas_mean_observations": OAS_MA_OBS, "oas_delta_observations": OAS_DELTA_OBS, "costs_bps": COSTS_BPS, "primary_cost_bps": PRIMARY_COST_BPS},
        "matched_window": {"signal_start": frame.index[int(decisions[0]["i"])].isoformat(), "return_end": frame.index[int(decisions[-1]["j"])].isoformat(), "common_price_rows": len(frame), "monthly_decisions": len(decisions)},
        "deployment": {"SMH_months": smh_months, "QQQ_months": len(decisions) - smh_months, "SMH_fraction": smh_months / len(decisions), "mean_one_way_turnover": float(np.mean(turns)), "median_one_way_turnover": float(np.median(turns))},
        "summaries": summaries,
        "primary_25bps_excess": {"cagr_vs_SMH": primary["cagr"] - smh["cagr"], "cagr_vs_QQQ": primary["cagr"] - qqq["cagr"], "cagr_vs_SPY": primary["cagr"] - spy["cagr"], "cagr_vs_equal_SMH_QQQ": primary["cagr"] - equal["cagr"], "max_drawdown_improvement_vs_SMH": primary["max_drawdown"] - smh["max_drawdown"], "full_years": len(full_years), "positive_years_vs_SMH": wins_smh, "positive_years_vs_QQQ": wins_qqq, "year_excess": yearly},
        "cost_robust_vs_QQQ": cost_robust,
        "decision": "P17_CREDIT_OAS_SWITCH_SUPPORTED" if supported else "P17_CREDIT_OAS_SWITCH_NOT_SUPPORTED",
        "allocation_authority": False, "promotion_authority": False, "runtime_authority": False, "broker_authority": False, "live_trading_change": False,
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(output, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print("P17_RESULT=" + json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
