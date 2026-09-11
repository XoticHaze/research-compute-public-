from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
ACCOUNT = "Treasury General Account (TGA) Closing Balance"
END = "2026-09-11"
COST_BPS = 10.0
FOLDS = [
    ("2016-01-01", "2018-12-31"),
    ("2019-01-01", "2021-12-31"),
    ("2022-01-01", END),
]


def cagr(r: pd.Series) -> float | None:
    if len(r) < 2:
        return None
    years = (r.index[-1] - r.index[0]).days / 365.25
    total = float((1 + r).prod())
    return None if years <= 0 or total <= 0 else total ** (1 / years) - 1


def mdd(r: pd.Series) -> float:
    e = (1 + r).cumprod()
    return float((e / e.cummax() - 1).min())


def stats(r: pd.Series) -> dict:
    return {
        "cagr": cagr(r),
        "max_drawdown": mdd(r),
        "vol": float(r.std() * math.sqrt(252)),
        "days": int(len(r)),
    }


def fetch_tga() -> pd.Series:
    params = {
        "format": "json",
        "fields": "record_date,account_type,close_today_bal",
        "filter": f"account_type:eq:{ACCOUNT}",
        "sort": "record_date",
        "page[size]": "10000",
    }
    r = requests.get(API, params=params, headers={"User-Agent": "XoticHaze-Research/1.0"}, timeout=(15, 60))
    r.raise_for_status()
    j = r.json()
    d = pd.DataFrame(j.get("data", []))
    if d.empty:
        raise RuntimeError("No TGA closing-balance records returned")
    d["record_date"] = pd.to_datetime(d["record_date"], errors="coerce")
    d["balance"] = pd.to_numeric(d["close_today_bal"], errors="coerce")
    d = d.dropna(subset=["record_date", "balance"]).sort_values("record_date")
    s = d.set_index("record_date")["balance"].resample("ME").last().dropna()
    s.attrs["raw_rows"] = int(len(d))
    s.attrs["api_meta"] = j.get("meta", {})
    return s


def evaluate(d: pd.DataFrame, a: str, b: str) -> dict:
    z = d.loc[a:b]
    return {
        "strategy": stats(z["strategy"]),
        "control": stats(z["control"]),
        "IWM": stats(z["IWM"]),
        "SPY": stats(z["SPY"]),
        "matched_excess_cagr": cagr(z["strategy"]) - cagr(z["control"]),
        "spy_excess_cagr": cagr(z["strategy"]) - cagr(z["SPY"]),
        "switches": int(z["switch"].sum()),
        "iwm_weight_mean": float(z["iwm_w"].mean()),
    }


def main() -> None:
    tga = fetch_tga()
    # Frozen before performance inspection: use the sign of the completed
    # month-end 3-month TGA balance change. Falling TGA is treated as a
    # liquidity-release state and selects IWM; otherwise select SPY.
    signal = (tga.pct_change(3) < 0).astype(float).shift(1).dropna().rename("iwm_w")
    first_signal = signal.index.min()
    if pd.isna(first_signal) or len(signal) < 36:
        out = {
            "schema": "research.p552_tga_smallcap_liquidity_r1",
            "parent": "P552",
            "decision": "P552_SOURCE_COVERAGE_NOT_READY",
            "source_diagnostics": {
                "raw_rows": tga.attrs.get("raw_rows", 0),
                "monthly_points": int(len(tga)),
                "first_month": str(tga.index.min().date()),
                "last_month": str(tga.index.max().date()),
            },
            "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
        }
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/p552_tga_smallcap_liquidity_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
        print(json.dumps(out, sort_keys=True))
        return

    raw = yf.download(["IWM", "SPY"], start="2015-01-01", end="2026-09-12", auto_adjust=True, progress=False, group_by="column")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    r = close[["IWM", "SPY"]].dropna(how="any").pct_change().dropna()
    d = r.join(signal.reindex(r.index, method="ffill")).dropna()
    d["spy_w"] = 1 - d["iwm_w"]
    d["switch"] = d["iwm_w"].diff().abs().fillna(0.0)
    d["strategy"] = d["iwm_w"] * d["IWM"] + d["spy_w"] * d["SPY"] - d["switch"] * (COST_BPS / 10000.0)
    d["control"] = 0.5 * d["IWM"] + 0.5 * d["SPY"]
    start = max(pd.Timestamp("2016-01-01"), d.index.min())
    overall = evaluate(d, str(start.date()), END)
    folds = [evaluate(d, a, b) for a, b in FOLDS if pd.Timestamp(b) >= start]
    positive = sum(1 for f in folds if f["matched_excess_cagr"] > 0)
    required = max(2, len(folds) - 1)
    decision = "P552_SUPPORTED" if overall["matched_excess_cagr"] > 0 and positive >= required else "P552_NOT_SUPPORTED_NO_RESCUE"
    out = {
        "schema": "research.p552_tga_smallcap_liquidity_r1",
        "parent": "P552",
        "claim": "Completed-month Treasury General Account contraction can causally select small caps over large caps with durable after-cost excess versus a static IWM/SPY mix.",
        "frozen_contract": {
            "source": API,
            "account_type": ACCOUNT,
            "feature": "completed month-end TGA closing balance 3-month percent change",
            "signal": "negative 3-month TGA change => IWM; otherwise SPY; decision applied the following month",
            "control": "static 50/50 IWM/SPY",
            "opportunity_controls": ["IWM", "SPY"],
            "cost_bps_per_full_switch": COST_BPS,
            "folds": FOLDS,
            "no_parameter_rescue": True,
        },
        "overall": overall,
        "folds": folds,
        "positive_fold_count": positive,
        "required_positive_folds": required,
        "decision": decision,
        "source_diagnostics": {
            "raw_rows": tga.attrs.get("raw_rows", 0),
            "monthly_points": int(len(tga)),
            "first_month": str(tga.index.min().date()),
            "last_month": str(tga.index.max().date()),
        },
        "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p552_tga_smallcap_liquidity_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
