from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

CFTC_DATASET = "gpe5-46if"
CFTC_CODE = "209742"
CFTC_URL = f"https://publicreporting.cftc.gov/resource/{CFTC_DATASET}.csv"
PRICE_START = "2009-01-01"
PRICE_END_EXCLUSIVE = "2026-09-08"
CHANGE_REPORTS = 13
COSTS_BPS_PER_SIDE = (10.0, 25.0, 50.0)
PRIMARY_COST_BPS = 25.0
OUT = Path("p19-asset-manager-position-change-result.json")


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 research-compute-p19/2.0", "Accept": "*/*"})
    with urlopen(req, timeout=90) as response:
        raw = response.read()
    if not raw:
        raise RuntimeError(f"empty response: {url}")
    return raw


def pick(columns: list[str], *aliases: str) -> str:
    normalized = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for column in columns:
        low = column.lower().strip()
        if any(alias in low for alias in aliases):
            return column
    raise KeyError(f"required aliases absent aliases={aliases} columns={columns}")


def load_cftc() -> tuple[pd.DataFrame, dict]:
    params = {
        "$limit": "5000",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$where": f"cftc_contract_market_code='{CFTC_CODE}'",
    }
    url = CFTC_URL + "?" + urlencode(params)
    raw = fetch_bytes(url)
    src = pd.read_csv(io.BytesIO(raw))
    columns = list(src.columns)
    date_col = pick(columns, "report_date_as_yyyy_mm_dd", "report_date")
    oi_col = pick(columns, "open_interest_all", "open_interest")
    long_col = pick(columns, "asset_mgr_positions_long_all", "asset_mgr_positions_long")
    short_col = pick(columns, "asset_mgr_positions_short_all", "asset_mgr_positions_short")
    code_col = pick(columns, "cftc_contract_market_code")
    frame = pd.DataFrame(
        {
            "report_date": pd.to_datetime(src[date_col], utc=True, errors="coerce").dt.tz_localize(None),
            "open_interest": pd.to_numeric(src[oi_col], errors="coerce"),
            "asset_mgr_long": pd.to_numeric(src[long_col], errors="coerce"),
            "asset_mgr_short": pd.to_numeric(src[short_col], errors="coerce"),
            "code": src[code_col].astype(str).str.strip(),
        }
    ).dropna()
    frame = frame[frame.open_interest > 0].sort_values("report_date").drop_duplicates("report_date", keep="last")
    frame["asset_mgr_net_share"] = (frame.asset_mgr_long - frame.asset_mgr_short) / frame.open_interest
    frame["asset_mgr_net_share_change_13r"] = frame.asset_mgr_net_share - frame.asset_mgr_net_share.shift(CHANGE_REPORTS)
    frame = frame.dropna(subset=["asset_mgr_net_share_change_13r"]).reset_index(drop=True)
    if len(frame) < 500:
        raise RuntimeError(f"insufficient CFTC observations after change warmup: {len(frame)}")
    return frame, {
        "provider": "CFTC Public Reporting Environment",
        "dataset": CFTC_DATASET,
        "contract_market_code": CFTC_CODE,
        "url": url,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "rows_raw": int(len(src)),
        "rows_usable": int(len(frame)),
        "first_report": frame.report_date.min().date().isoformat(),
        "last_report": frame.report_date.max().date().isoformat(),
        "selected_columns": {
            "open_interest": oi_col,
            "asset_manager_long": long_col,
            "asset_manager_short": short_col,
        },
    }


def unix(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def load_price(symbol: str) -> tuple[pd.Series, dict]:
    query = urlencode(
        {
            "period1": str(unix(PRICE_START)),
            "period2": str(unix(PRICE_END_EXCLUSIVE)),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    raw = fetch_bytes(url)
    payload = json.loads(raw.decode("utf-8"))
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart missing result for {symbol}")
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    adj = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    close = adj or (indicators.get("quote") or [{}])[0].get("close") or []
    if len(timestamps) != len(close):
        raise RuntimeError(f"Yahoo chart shape mismatch for {symbol}")
    index = pd.to_datetime(pd.Series(timestamps), unit="s", utc=True, errors="coerce").dt.tz_localize(None)
    series = pd.Series(pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(), index=pd.DatetimeIndex(index), name=symbol).dropna().sort_index()
    series = series[~series.index.duplicated(keep="last")]
    if len(series) < 4000:
        raise RuntimeError(f"insufficient price rows for {symbol}: {len(series)}")
    return series, {
        "provider": "Yahoo chart JSON",
        "url": url,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "rows": int(len(series)),
        "first": series.index.min().date().isoformat(),
        "last": series.index.max().date().isoformat(),
    }


def effective_session(report_date: pd.Timestamp, sessions: pd.DatetimeIndex) -> pd.Timestamp | None:
    publication_boundary = report_date.normalize() + pd.Timedelta(days=3)
    position = sessions.searchsorted(publication_boundary, side="right")
    return None if position >= len(sessions) else sessions[position]


def build_intervals(cftc: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    signals = []
    for row in cftc.itertuples(index=False):
        effective = effective_session(row.report_date, prices.index)
        if effective is None:
            continue
        signals.append(
            {
                "report_date": row.report_date,
                "effective_date": effective,
                "change": float(row.asset_mgr_net_share_change_13r),
            }
        )
    signal_frame = pd.DataFrame(signals).drop_duplicates("effective_date", keep="last").sort_values("effective_date")
    records = []
    rows = signal_frame.to_dict("records")
    for current, nxt in zip(rows[:-1], rows[1:]):
        d0, d1 = current["effective_date"], nxt["effective_date"]
        if d0 not in prices.index or d1 not in prices.index or d1 <= d0:
            continue
        qqq = float(prices.at[d1, "QQQ"] / prices.at[d0, "QQQ"] - 1.0)
        spy = float(prices.at[d1, "SPY"] / prices.at[d0, "SPY"] - 1.0)
        asset = "QQQ" if float(current["change"]) >= 0.0 else "SPY"
        records.append(
            {
                "report_date": current["report_date"],
                "start": d0,
                "end": d1,
                "asset_manager_change_13r": float(current["change"]),
                "asset": asset,
                "qqq_return": qqq,
                "spy_return": spy,
                "half_return": 0.5 * qqq + 0.5 * spy,
                "gross_return": qqq if asset == "QQQ" else spy,
            }
        )
    frame = pd.DataFrame(records)
    if len(frame) < 800:
        raise RuntimeError(f"insufficient matched intervals: {len(frame)}")
    return frame


def strategy_returns(frame: pd.DataFrame, bps: float) -> pd.Series:
    cost = bps / 10000.0
    previous = None
    returns = []
    for asset, gross in zip(frame.asset, frame.gross_return):
        sides = 1 if previous is None else (2 if asset != previous else 0)
        returns.append((1.0 + float(gross)) * (1.0 - cost * sides) - 1.0)
        previous = asset
    return pd.Series(returns, index=frame.index)


def static_returns(frame: pd.DataFrame, column: str, bps: float, initial_sides: int = 1) -> pd.Series:
    returns = frame[column].astype(float).copy()
    returns.iloc[0] = (1.0 + returns.iloc[0]) * (1.0 - bps / 10000.0 * initial_sides) - 1.0
    return returns


def metrics(returns: pd.Series, frame: pd.DataFrame) -> dict:
    r = returns.reset_index(drop=True).astype(float)
    wealth = (1.0 + r).cumprod()
    years = max(1.0 / 365.2425, (pd.Timestamp(frame.end.iloc[-1]) - pd.Timestamp(frame.start.iloc[0])).days / 365.2425)
    drawdown = wealth / wealth.cummax() - 1.0
    return {
        "intervals": int(len(r)),
        "total_return": float(wealth.iloc[-1] - 1.0),
        "cagr": float(wealth.iloc[-1] ** (1.0 / years) - 1.0),
        "max_drawdown": float(drawdown.min()),
        "annualized_weekly_vol": float(r.std(ddof=1) * math.sqrt(52.0)),
    }


def folds(frame: pd.DataFrame, strategy: pd.Series, qqq: pd.Series) -> list[dict]:
    output = []
    for number, indexes in enumerate(np.array_split(np.arange(len(frame)), 5), start=1):
        sr = float((1.0 + strategy.iloc[indexes]).prod() - 1.0)
        qr = float((1.0 + qqq.iloc[indexes]).prod() - 1.0)
        output.append(
            {
                "fold": number,
                "start": pd.Timestamp(frame.iloc[indexes[0]].start).date().isoformat(),
                "end": pd.Timestamp(frame.iloc[indexes[-1]].end).date().isoformat(),
                "strategy_total_return": sr,
                "qqq_total_return": qr,
                "excess": sr - qr,
                "positive_excess": sr > qr,
            }
        )
    return output


def full_years(frame: pd.DataFrame, strategy: pd.Series, qqq: pd.Series) -> list[dict]:
    temp = pd.DataFrame({"end": pd.to_datetime(frame.end), "strategy": strategy, "qqq": qqq})
    temp["year"] = temp.end.dt.year
    output = []
    for year, group in temp.groupby("year"):
        if len(group) < 40:
            continue
        sr = float((1.0 + group.strategy).prod() - 1.0)
        qr = float((1.0 + group.qqq).prod() - 1.0)
        output.append({"year": int(year), "strategy": sr, "qqq": qr, "excess": sr - qr, "beat": sr > qr})
    return output


def main() -> int:
    cftc, cftc_provenance = load_cftc()
    qqq, qqq_provenance = load_price("QQQ")
    spy, spy_provenance = load_price("SPY")
    prices = pd.concat([qqq, spy], axis=1, join="inner").dropna().sort_index()
    frame = build_intervals(cftc, prices)

    cost_results = {}
    for bps in COSTS_BPS_PER_SIDE:
        strategy = strategy_returns(frame, bps)
        qqq_ret = static_returns(frame, "qqq_return", bps)
        spy_ret = static_returns(frame, "spy_return", bps)
        half_ret = static_returns(frame, "half_return", bps, initial_sides=2)
        sm, qm, pm, hm = metrics(strategy, frame), metrics(qqq_ret, frame), metrics(spy_ret, frame), metrics(half_ret, frame)
        cost_results[str(int(bps))] = {
            "strategy": sm,
            "qqq": qm,
            "spy": pm,
            "half": hm,
            "cagr_excess_vs_qqq": sm["cagr"] - qm["cagr"],
            "cagr_excess_vs_spy": sm["cagr"] - pm["cagr"],
            "cagr_excess_vs_half": sm["cagr"] - hm["cagr"],
        }

    strategy_primary = strategy_returns(frame, PRIMARY_COST_BPS)
    qqq_primary = static_returns(frame, "qqq_return", PRIMARY_COST_BPS)
    fold_rows = folds(frame, strategy_primary, qqq_primary)
    year_rows = full_years(frame, strategy_primary, qqq_primary)
    positive_folds = sum(int(row["positive_excess"]) for row in fold_rows)
    positive_years = sum(int(row["beat"]) for row in year_rows)
    primary_excess = cost_results[str(int(PRIMARY_COST_BPS))]["cagr_excess_vs_qqq"]
    year_fraction = positive_years / len(year_rows) if year_rows else 0.0
    supported = bool(primary_excess > 0.0 and positive_folds >= 3 and year_fraction >= 0.5)

    receipt = {
        "schema": "public_research.p19_asset_manager_position_change.v1",
        "status": "PASS",
        "decision": "P19_ASSET_MANAGER_POSITION_CHANGE_SUPPORTED" if supported else "P19_ASSET_MANAGER_POSITION_CHANGE_NOT_SUPPORTED",
        "parent_id": "P19",
        "frozen_before_execution": True,
        "hypothesis": "A deterioration in publication-lagged Nasdaq Mini Asset Manager net positioning over the prior 13 reports identifies relative QQQ weakness versus SPY.",
        "frozen_contract": {
            "cftc_dataset": CFTC_DATASET,
            "contract_market_code": CFTC_CODE,
            "trader_class": "Asset Manager/Institutional",
            "position_measure": "(asset_manager_long-asset_manager_short)/open_interest",
            "state_transform": "current net share minus net share 13 reports earlier",
            "allocation": "QQQ when 13-report change >= 0; SPY when 13-report change < 0",
            "publication_boundary": "first market session strictly after report_date+3 calendar days",
            "primary_cost_bps_per_traded_side": PRIMARY_COST_BPS,
            "cost_grid_bps_per_traded_side": list(COSTS_BPS_PER_SIDE),
            "support_gate": "positive primary CAGR excess vs QQQ AND >=3/5 positive chronological folds vs QQQ AND >=50% full calendar years beating QQQ",
            "parameter_search": False,
        },
        "matched_window": {
            "start": pd.Timestamp(frame.start.iloc[0]).date().isoformat(),
            "end": pd.Timestamp(frame.end.iloc[-1]).date().isoformat(),
            "weekly_intervals": int(len(frame)),
            "spy_state_fraction": float((frame.asset == "SPY").mean()),
            "switch_count": int((frame.asset != frame.asset.shift()).sum() - 1),
        },
        "cost_results": cost_results,
        "chronological_folds_vs_qqq": fold_rows,
        "positive_fold_count_vs_qqq": int(positive_folds),
        "full_calendar_years_vs_qqq": year_rows,
        "full_calendar_years_beating_qqq": int(positive_years),
        "source_provenance": {"cftc": cftc_provenance, "qqq": qqq_provenance, "spy": spy_provenance},
        "parent_context": {
            "prior_child": "P19-C-CFTC-NASDAQ-CROWDING",
            "prior_child_result": "NOT_SUPPORTED",
            "mechanism_change": "different trader class (Asset Manager vs Leveraged Money) and change-state representation (13-report delta sign vs 52-report crowding z-level)",
            "after_this_child": "rerank P19 if unsupported; do not tune 13-report horizon, sign threshold, costs, lag, or years",
        },
        "safety": {
            "public_data_only": True,
            "canonical_mm_semantics_claim": False,
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "broker_submission": False,
            "allocation_authority_change": False,
            "live_trading_change": False,
        },
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("P19_ASSET_MANAGER_POSITION_CHANGE=" + json.dumps(receipt, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
