from __future__ import annotations

import io
import json
import math
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

WORKLOAD_ID = "FF5_FACTOR_PERSISTENCE_R1"
URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
FACTORS = ["HML", "RMW", "CMA"]
WINDOWS = {"2010": "2010-01-01", "2015": "2015-01-01", "2020": "2020-01-01"}


def load_monthly() -> pd.DataFrame:
    req = urllib.request.Request(URL, headers={"User-Agent": "XoticHaze-Research/1.0"})
    raw = urllib.request.urlopen(req, timeout=45).read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = z.namelist()[0]
        text = z.read(name).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(",Mkt-RF"))
    data = []
    for line in lines[start + 1 :]:
        parts = [x.strip() for x in line.split(",")]
        if not parts or not parts[0].isdigit() or len(parts[0]) != 6:
            if data:
                break
            continue
        data.append(parts[:7])
    cols = ["date", "Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
    df = pd.DataFrame(data, columns=cols)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m") + pd.offsets.MonthEnd(0)
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
    return df.set_index("date").sort_index()


def stats(series: pd.Series) -> dict:
    q = pd.Series(series, dtype=float).dropna()
    n = len(q)
    mean_month = float(q.mean()) if n else None
    ann_mean = mean_month * 12 if mean_month is not None else None
    ann_vol = float(q.std(ddof=1) * math.sqrt(12)) if n > 1 else None
    tstat = float(q.mean() / (q.std(ddof=1) / math.sqrt(n))) if n > 1 and q.std(ddof=1) else None
    positive_fraction = float((q > 0).mean()) if n else None
    return {
        "months": n,
        "annualized_arithmetic_mean": ann_mean,
        "annualized_volatility": ann_vol,
        "tstat_monthly_mean": tstat,
        "positive_month_fraction": positive_fraction,
    }


def fold_means(series: pd.Series) -> list[float]:
    q = pd.Series(series, dtype=float).dropna()
    out = []
    for positions in np.array_split(np.arange(len(q)), 5):
        if len(positions) >= 12:
            out.append(float(q.iloc[positions].mean() * 12))
    return out


def main() -> None:
    df = load_monthly()
    results = {}
    support = {}
    for factor in FACTORS:
        results[factor] = {}
        for name, start in WINDOWS.items():
            q = df.loc[df.index >= pd.Timestamp(start), factor]
            f = fold_means(q)
            s = stats(q)
            s["fold_annualized_means"] = f
            s["positive_folds"] = sum(x > 0 for x in f)
            s["fold_count"] = len(f)
            results[factor][name] = s
        long = results[factor]["2010"]
        recent = results[factor]["2020"]
        support[factor] = bool(
            long["annualized_arithmetic_mean"] is not None
            and long["annualized_arithmetic_mean"] > 0
            and long["positive_folds"] >= 3
            and recent["annualized_arithmetic_mean"] is not None
            and recent["annualized_arithmetic_mean"] > 0
        )

    decision = (
        "FF5_ECONOMIC_PREMISE_PERSISTS_FOR_AT_LEAST_ONE_FACTOR"
        if any(support.values())
        else "FF5_ECONOMIC_PREMISE_NOT_PERSISTENT_IN_TESTED_FACTORS"
    )
    out = {
        "schema": "research.ff5_factor_persistence_r1",
        "workload_id": WORKLOAD_ID,
        "claim": "Determine whether the underlying academic value, profitability and investment premia retain positive chronology-broad economic evidence after 2010 and after 2020, to distinguish factor-economic decay from investable ETF implementation failure.",
        "source": URL,
        "factors": FACTORS,
        "windows": WINDOWS,
        "results": results,
        "factor_support": support,
        "decision_rule": "A factor retains an economic-premise prior only if its 2010+ annualized arithmetic mean is positive, at least 3/5 non-overlapping chronological folds are positive, and its 2020+ annualized arithmetic mean is positive. This is not investable alpha and cannot override failed matched ETF evidence.",
        "decision": decision,
        "limitations": [
            "Fama-French factors are academic long-short research portfolios, not directly investable funds and do not include realistic implementation costs for a fund product.",
            "Positive factor-premium evidence only justifies searching for a chronology-safe investable implementation; it does not rescue any failed ETF candidate.",
            "No factor, window, weighting, or threshold search is performed.",
        ],
        "boundaries": {
            "scientific_authority": True,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("research/artifacts").mkdir(parents=True, exist_ok=True)
    Path("research/artifacts/ff5_factor_persistence_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
