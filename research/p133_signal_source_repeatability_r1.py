from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

REPRESENTATIONS = {
    "base": ("VTI", "VEA", "IEF", "IAU", "GSG"),
    "proxy": ("SPY", "EFA", "TLT", "GLD", "DBC"),
    "industry": ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT"),
}
START = "2007-01-01"


def pull(assets: tuple[str, ...]) -> tuple[pd.DataFrame, str]:
    raw = yf.download(list(assets), start=START, auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.loc[:, list(assets)].dropna(how="all").astype(float)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    payload = close.round(10).to_csv(index=True, date_format="%Y-%m-%dT%H:%M:%S").encode()
    return close, hashlib.sha256(payload).hexdigest()


def selections(close: pd.DataFrame, assets: tuple[str, ...]) -> pd.DataFrame:
    last = pd.Timestamp(close.index.max()).normalize()
    monthly = close.resample("ME").last().loc[lambda x: x.index <= last]
    mom6 = monthly.pct_change(6)
    rows = []
    for i, dt in enumerate(monthly.index[:-1]):
        if i < 7:
            continue
        m = mom6.loc[dt, list(assets)]
        if m.isna().any():
            continue
        hist = monthly.loc[:dt, list(assets)].pct_change(fill_method=None).tail(6)
        corr_pen = hist.corr().abs().replace(1.0, np.nan).mean(axis=1).fillna(1.0)
        z = (m - m.mean()) / (m.std(ddof=0) or 1.0)
        score = z - corr_pen
        sel = tuple(sorted(score.sort_values(ascending=False).head(2).index))
        gap = float(score.sort_values(ascending=False).iloc[1] - score.sort_values(ascending=False).iloc[2]) if len(score) >= 3 else None
        rows.append({"date": dt, "selection": sel, "rank2_rank3_gap": gap})
    return pd.DataFrame(rows).set_index("date")


def compare(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    idx = a.index.intersection(b.index)
    aa, bb = a.loc[idx], b.loc[idx]
    agree = aa.selection == bb.selection
    gaps = pd.concat([aa.rank2_rank3_gap, bb.rank2_rank3_gap], axis=1).min(axis=1)
    return {
        "months_compared": int(len(idx)),
        "selection_agreement_fraction": float(agree.mean()),
        "selection_disagreement_months": [str(x.date()) for x in idx[~agree]],
        "minimum_rank2_rank3_gap": float(gaps.min()),
        "median_rank2_rank3_gap": float(gaps.median()),
        "signal_level_gate": "PASS" if float(agree.mean()) >= 0.995 else "FAIL",
    }


def main() -> None:
    out = {
        "schema": "research.p133_signal_source_repeatability_r1",
        "parent_ids": ["P109", "P117", "P125", "P133"],
        "contract": {
            "purpose": "test whether two sequential Yahoo adjusted-close pulls reproduce the frozen P109 top-2 selections despite possible byte-level source drift",
            "representations": {k: list(v) for k, v in REPRESENTATIONS.items()},
            "signal_level_gate": ">=99.5% identical monthly top-2 selections",
            "no_parameter_or_model_changes": True,
            "scientific_use": "source/feature repeatability only; not promotion or allocation authority"
        },
        "results": {},
    }
    for name, assets in REPRESENTATIONS.items():
        c1, h1 = pull(assets)
        c2, h2 = pull(assets)
        s1, s2 = selections(c1, assets), selections(c2, assets)
        rec = compare(s1, s2)
        rec["pull1_sha256"] = h1
        rec["pull2_sha256"] = h2
        rec["byte_identical"] = h1 == h2
        rec["last_date_pull1"] = str(c1.index.max().date())
        rec["last_date_pull2"] = str(c2.index.max().date())
        out["results"][name] = rec
    out["decision"] = "SIGNAL_SOURCE_REPEATABILITY_SUPPORTED" if all(x["signal_level_gate"] == "PASS" for x in out["results"].values()) else "SIGNAL_SOURCE_REPEATABILITY_NOT_ESTABLISHED"
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p133_signal_source_repeatability_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"decision": out["decision"], "results": out["results"]}, sort_keys=True))


if __name__ == "__main__":
    main()
