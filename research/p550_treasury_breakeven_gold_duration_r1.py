from __future__ import annotations

import io
import json
import math
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

START_YEAR = 2003
END_YEAR = 2026
START = "2005-01-01"
END = "2026-09-11"
COST_BPS = 10.0
FOLDS = [
    ("2005-01-01", "2010-12-31"),
    ("2011-01-01", "2016-12-31"),
    ("2017-01-01", "2021-12-31"),
    ("2022-01-01", END),
]
BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?_format=csv&field_tdr_date_value={year}&page=&type={kind}"


def get_year(year: int, kind: str) -> pd.DataFrame:
    url = BASE.format(year=year, kind=kind)
    r = requests.get(url, headers={"User-Agent": "XoticHaze-Research/1.0"}, timeout=(15, 60))
    r.raise_for_status()
    if len(r.content) < 100:
        raise RuntimeError(f"Treasury CSV unexpectedly small: {url}")
    x = pd.read_csv(io.BytesIO(r.content))
    date_col = next((c for c in x.columns if str(c).strip().lower() == "date"), None)
    ten_col = next((c for c in x.columns if str(c).strip().lower() in {"10 yr", "10-year", "10 year"}), None)
    if date_col is None or ten_col is None:
        raise RuntimeError(f"Treasury columns missing date/10Y for {year}/{kind}: {list(x.columns)}")
    out = x[[date_col, ten_col]].copy()
    out.columns = ["date", "ten"]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["ten"] = pd.to_numeric(out["ten"], errors="coerce")
    return out.dropna().drop_duplicates("date").sort_values("date")


def fetch_curve(kind: str) -> pd.Series:
    parts = []
    errors = []
    for year in range(START_YEAR, END_YEAR + 1):
        try:
            parts.append(get_year(year, kind))
        except Exception as exc:
            errors.append({"year": year, "error": repr(exc)})
    if not parts:
        raise RuntimeError(f"No Treasury data for {kind}: {errors}")
    x = pd.concat(parts).drop_duplicates("date").sort_values("date")
    s = x.set_index("date")["ten"]
    s.attrs["errors"] = errors
    return s


def cagr(r: pd.Series) -> float | None:
    if len(r) < 2:
        return None
    years = (r.index[-1] - r.index[0]).days / 365.25
    total = float((1 + r).prod())
    if years <= 0 or total <= 0:
        return None
    return total ** (1 / years) - 1


def mdd(r: pd.Series) -> float:
    e = (1 + r).cumprod()
    return float((e / e.cummax() - 1).min())


def stats(r: pd.Series) -> dict:
    return {"cagr": cagr(r), "max_drawdown": mdd(r), "vol": float(r.std() * math.sqrt(252)), "days": int(len(r))}


def evaluate(d: pd.DataFrame, a: str, b: str) -> dict:
    z = d.loc[a:b]
    return {
        "strategy": stats(z["strategy"]),
        "control": stats(z["control"]),
        "GLD": stats(z["GLD"]),
        "TLT": stats(z["TLT"]),
        "SPY": stats(z["SPY"]),
        "matched_excess_cagr": cagr(z["strategy"]) - cagr(z["control"]),
        "spy_excess_cagr": cagr(z["strategy"]) - cagr(z["SPY"]),
        "switches": int(z["switch"].sum()),
        "gold_weight_mean": float(z["gold_w"].mean()),
    }


def main() -> None:
    nominal = fetch_curve("daily_treasury_yield_curve")
    real = fetch_curve("daily_treasury_real_yield_curve")
    curves = pd.concat([nominal.rename("nominal10"), real.rename("real10")], axis=1).dropna()
    curves["breakeven10"] = curves["nominal10"] - curves["real10"]
    monthly = curves["breakeven10"].resample("ME").last().dropna()
    trend = monthly.rolling(12, min_periods=12).mean()
    # Frozen ex ante rule: inflation compensation above its trailing-12m level
    # selects gold; otherwise nominal long duration. Use only completed month-end
    # observations and apply the decision the following month.
    gold = (monthly > trend).astype(float).shift(1).dropna().rename("gold_w")

    raw = yf.download(["GLD", "TLT", "SPY"], start="2004-11-01", end="2026-09-12", auto_adjust=True, progress=False, group_by="column")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[["GLD", "TLT", "SPY"]].dropna(how="any")
    r = close.pct_change().dropna()
    d = r.join(gold.reindex(r.index, method="ffill")).dropna()
    d["duration_w"] = 1 - d["gold_w"]
    d["switch"] = d["gold_w"].diff().abs().fillna(0.0)
    d["strategy"] = d["gold_w"] * d["GLD"] + d["duration_w"] * d["TLT"] - d["switch"] * (COST_BPS / 10000.0)
    d["control"] = 0.5 * d["GLD"] + 0.5 * d["TLT"]

    overall = evaluate(d, START, END)
    folds = [evaluate(d, a, b) for a, b in FOLDS]
    positive = sum(1 for f in folds if f["matched_excess_cagr"] > 0)
    decision = "P550_SUPPORTED" if overall["matched_excess_cagr"] > 0 and positive >= 3 else "P550_NOT_SUPPORTED_NO_RESCUE"
    out = {
        "schema": "research.p550_treasury_breakeven_gold_duration_r1",
        "parent": "P550",
        "claim": "Official Treasury nominal-real 10Y inflation compensation can causally rotate gold versus long nominal duration with durable after-cost excess over a static matched GLD/TLT mix.",
        "frozen_contract": {
            "source": "U.S. Treasury daily nominal and real par yield curve CSV archives",
            "feature": "10Y nominal minus 10Y real yield",
            "signal": "completed month-end breakeven above trailing 12-month mean => GLD; otherwise TLT; applied following month",
            "control": "static 50/50 GLD/TLT",
            "opportunity_controls": ["GLD", "TLT", "SPY"],
            "cost_bps_per_full_switch": COST_BPS,
            "folds": FOLDS,
            "no_parameter_rescue": True,
        },
        "overall": overall,
        "folds": folds,
        "positive_fold_count": positive,
        "decision": decision,
        "source_diagnostics": {
            "nominal_points": int(len(nominal)),
            "real_points": int(len(real)),
            "joined_points": int(len(curves)),
            "nominal_year_errors": nominal.attrs.get("errors", []),
            "real_year_errors": real.attrs.get("errors", []),
        },
        "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p550_treasury_breakeven_gold_duration_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
