from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

WORKLOAD_ID = "CFTC_TFF_RELATIVE_ALPHA_R1"
SOURCE_WORKLOAD_ID = "CFTC_TFF_SOURCE_R1"
BASE = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CODES = {"ES": "13874A", "NQ": "209742"}
START = "2010-01-01"
COST = 0.001
RIDGE = 1.0
MIN_TRAIN = 104
MIN_ALL_OBS = 100
MIN_RECENT_OBS = 52
WINDOWS = {"all": "2012-01-01", "recent": "2020-01-01"}
PRICE_COLS = ["rel4", "rel13"]
POSITION_COLS = ["am_diff", "lm_diff", "am_chg13", "lm_chg13"]
ARMS = ["price", "positioning", "combined", "permuted"]


def fetch(code: str) -> pd.DataFrame:
    query = urlencode(
        {
            "$where": f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd >= '{START}T00:00:00.000'",
            "$order": "report_date_as_yyyy_mm_dd ASC",
            "$limit": "5000",
        }
    )
    req = Request(BASE + "?" + query, headers={"User-Agent": "XoticHaze-Research/1.0"})
    with urlopen(req, timeout=45) as response:
        rows = json.loads(response.read().decode())
    out = []
    for row in rows:
        oi = float(row["open_interest_all"])
        date = pd.Timestamp(row["report_date_as_yyyy_mm_dd"]).tz_localize(None)
        out.append(
            (
                date,
                (float(row["asset_mgr_positions_long"]) - float(row["asset_mgr_positions_short"])) / oi,
                (float(row["lev_money_positions_long"]) - float(row["lev_money_positions_short"])) / oi,
            )
        )
    return (
        pd.DataFrame(out, columns=["report_date", "am", "lm"])
        .drop_duplicates("report_date")
        .set_index("report_date")
        .sort_index()
    )


def metrics(returns: pd.Series) -> dict:
    q = pd.Series(returns, dtype=float).dropna()
    n = len(q)
    if not n:
        return {"weeks": 0, "cagr": None, "maxdd": None, "sharpe_rf0": None}
    equity = (1 + q).cumprod()
    cagr = float(equity.iloc[-1] ** (52 / n) - 1)
    maxdd = float((equity / equity.cummax() - 1).min())
    if n < 2:
        sharpe = None
    else:
        vol = float(q.std(ddof=1) * math.sqrt(52))
        sharpe = float(q.mean() * 52 / vol) if vol else None
    return {"weeks": int(n), "cagr": cagr, "maxdd": maxdd, "sharpe_rf0": sharpe}


def ridge_pred(X, y, x) -> float:
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-12] = 1
    z = (X - mu) / sd
    zx = (x - mu) / sd
    A = np.column_stack([np.ones(len(z)), z])
    penalty = np.eye(A.shape[1])
    penalty[0, 0] = 0
    beta = np.linalg.solve(A.T @ A + RIDGE * penalty, A.T @ y)
    return float(np.r_[1, zx] @ beta)


def causal_permutation(values: np.ndarray) -> np.ndarray:
    """Deterministic past-only negative control; never reads row i or the future."""
    a = np.asarray(values, float)
    out = np.full_like(a, np.nan)
    for i in range(1, len(a)):
        # LCG-style index. Unlike the legacy i*37 expression, this does not
        # algebraically collapse to one constant historical row.
        j = ((1103515245 * (i + 1) + 12345) & 0x7FFFFFFF) % i
        out[i] = a[j]
    return out


def arm_metrics(df: pd.DataFrame, pred_col: str) -> tuple[dict, pd.Series]:
    q = df.dropna(subset=[pred_col, "qqq_fwd", "spy_fwd"]).copy()
    if q.empty:
        return {
            "weeks": 0,
            "cagr": None,
            "maxdd": None,
            "sharpe_rf0": None,
            "matched_excess_cagr": None,
            "vs_spy_cagr": None,
            "vs_qqq_cagr": None,
            "switch_fraction": None,
            "benchmark_cagr": None,
        }, pd.Series(dtype=float)
    choose = (q[pred_col] > 0).astype(int)
    gross = pd.Series(np.where(choose.to_numpy() == 1, q.qqq_fwd, q.spy_fwd), index=q.index)
    turnover = choose.ne(choose.shift()).astype(float)
    turnover.iloc[0] = 1.0
    net = gross - COST * turnover
    benchmark = 0.5 * q.qqq_fwd + 0.5 * q.spy_fwd
    result = metrics(net)
    matched = metrics(benchmark)
    spy = metrics(q.spy_fwd)
    qqq = metrics(q.qqq_fwd)
    result.update(
        {
            "matched_excess_cagr": result["cagr"] - matched["cagr"],
            "vs_spy_cagr": result["cagr"] - spy["cagr"],
            "vs_qqq_cagr": result["cagr"] - qqq["cagr"],
            "switch_fraction": float(turnover.mean()),
            "benchmark_cagr": matched["cagr"],
        }
    )
    return result, net


def fold_delta(left: pd.Series, right: pd.Series) -> list[dict]:
    pair = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if pair.empty:
        return []
    out = []
    for fold, positions in enumerate(np.array_split(np.arange(len(pair)), 5), 1):
        if len(positions) == 0:
            continue
        lm = metrics(pair.left.iloc[positions])
        rm = metrics(pair.right.iloc[positions])
        out.append({"fold": fold, "weeks": len(positions), "cagr_delta": lm["cagr"] - rm["cagr"]})
    return out


def gt(a, b) -> bool:
    return a is not None and b is not None and a > b


es = fetch(CODES["ES"]).rename(columns={"am": "es_am", "lm": "es_lm"})
nq = fetch(CODES["NQ"]).rename(columns={"am": "nq_am", "lm": "nq_lm"})
cot = es.join(nq, how="inner").sort_index()
cot["release_date"] = cot.index + pd.Timedelta(days=3)
cot["am_diff"] = cot.nq_am - cot.es_am
cot["lm_diff"] = cot.nq_lm - cot.es_lm
cot["am_chg13"] = cot.am_diff - cot.am_diff.shift(13)
cot["lm_chg13"] = cot.lm_diff - cot.lm_diff.shift(13)

raw = yf.download(
    ["QQQ", "SPY"],
    start=START,
    end=(pd.Timestamp.utcnow() + pd.Timedelta(days=1)).date().isoformat(),
    auto_adjust=True,
    progress=False,
    threads=False,
)
close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
close = close[["QQQ", "SPY"]].dropna()
rows = []
for report_date, row in cot.iterrows():
    ix = close.index.searchsorted(row.release_date)
    if ix >= len(close):
        continue
    signal_date = close.index[ix]
    rows.append(
        (
            report_date,
            signal_date,
            row.am_diff,
            row.lm_diff,
            row.am_chg13,
            row.lm_chg13,
            float(close.loc[signal_date, "QQQ"]),
            float(close.loc[signal_date, "SPY"]),
        )
    )

d = (
    pd.DataFrame(rows, columns=["report_date", "signal_date", *POSITION_COLS, "qqq", "spy"])
    .drop_duplicates("signal_date")
    .set_index("signal_date")
    .sort_index()
)
relative = d.qqq / d.spy
d["rel4"] = relative.pct_change(4)
d["rel13"] = relative.pct_change(13)
d["qqq_fwd"] = d.qqq.shift(-1) / d.qqq - 1
d["spy_fwd"] = d.spy.shift(-1) / d.spy - 1
d["target"] = d.qqq_fwd - d.spy_fwd
permuted_positions = causal_permutation(d[POSITION_COLS].to_numpy())

predictions = {arm: [] for arm in ARMS}
for i in range(len(d)):
    row = d.iloc[i]
    common_train = d.iloc[:i].dropna(subset=PRICE_COLS + POSITION_COLS + ["target"])
    enough = len(common_train) >= MIN_TRAIN
    valid_current = not row[PRICE_COLS + POSITION_COLS].isna().any()
    if not enough or not valid_current:
        for arm in ARMS:
            predictions[arm].append(np.nan)
        continue

    target = common_train.target.to_numpy()
    predictions["price"].append(ridge_pred(common_train[PRICE_COLS], target, row[PRICE_COLS]))
    predictions["positioning"].append(ridge_pred(common_train[POSITION_COLS], target, row[POSITION_COLS]))
    predictions["combined"].append(
        ridge_pred(common_train[PRICE_COLS + POSITION_COLS], target, row[PRICE_COLS + POSITION_COLS])
    )

    train_ix = d.index.get_indexer(common_train.index)
    perm_train = permuted_positions[train_ix]
    good = np.isfinite(perm_train).all(axis=1)
    current_perm = permuted_positions[i]
    if good.sum() >= MIN_TRAIN and np.isfinite(current_perm).all():
        X = np.column_stack([common_train[PRICE_COLS].to_numpy()[good], perm_train[good]])
        x = np.r_[row[PRICE_COLS].to_numpy(float), current_perm]
        predictions["permuted"].append(ridge_pred(X, target[good], x))
    else:
        predictions["permuted"].append(np.nan)

for arm, values in predictions.items():
    d[f"{arm}_pred"] = values

prediction_diagnostics = {}
for arm in ARMS:
    valid = d[f"{arm}_pred"].dropna()
    prediction_diagnostics[arm] = {
        "count": int(len(valid)),
        "first": valid.index.min().date().isoformat() if len(valid) else None,
        "last": valid.index.max().date().isoformat() if len(valid) else None,
    }

results = {}
for window_name, start in WINDOWS.items():
    window = d.loc[d.index >= pd.Timestamp(start)].copy()
    arms = {}
    nets = {}
    for arm in ARMS:
        arms[arm], nets[arm] = arm_metrics(window, f"{arm}_pred")
    price_folds = fold_delta(nets["combined"], nets["price"])
    permuted_folds = fold_delta(nets["combined"], nets["permuted"])
    results[window_name] = {
        "start": start,
        "end": window.index.max().date().isoformat() if len(window) else None,
        "raw_window_rows": int(len(window)),
        "arms": arms,
        "combined_minus_price_folds": price_folds,
        "combined_minus_permuted_folds": permuted_folds,
        "positive_combined_minus_price_folds": sum(row["cagr_delta"] > 0 for row in price_folds),
        "positive_combined_minus_permuted_folds": sum(row["cagr_delta"] > 0 for row in permuted_folds),
    }

all_window = results["all"]
recent = results["recent"]
all_combined = all_window["arms"]["combined"]
recent_combined = recent["arms"]["combined"]
all_price = all_window["arms"]["price"]
recent_price = recent["arms"]["price"]
all_permuted = all_window["arms"]["permuted"]
recent_permuted = recent["arms"]["permuted"]

sample_ok = all_combined["weeks"] >= MIN_ALL_OBS and recent_combined["weeks"] >= MIN_RECENT_OBS
incremental_gate = bool(
    sample_ok
    and gt(all_combined["matched_excess_cagr"], 0)
    and gt(recent_combined["matched_excess_cagr"], 0)
    and gt(all_combined["cagr"], all_price["cagr"])
    and gt(recent_combined["cagr"], recent_price["cagr"])
    and all_window["positive_combined_minus_price_folds"] >= 3
    and recent["positive_combined_minus_price_folds"] >= 3
    and gt(all_combined["cagr"], all_permuted["cagr"])
    and gt(recent_combined["cagr"], recent_permuted["cagr"])
    and all_window["positive_combined_minus_permuted_folds"] >= 3
)

out = {
    "schema": "research.cftc_tff_relative_alpha_r1",
    "workload_id": WORKLOAD_ID,
    "source_workload_id": SOURCE_WORKLOAD_ID,
    "claim": "Test whether causally lagged NQ-versus-ES TFF positioning adds incremental information to a fixed QQQ-versus-SPY relative-selection model beyond price state alone.",
    "contract": {
        "target": "next COT-to-COT QQQ minus SPY return",
        "price_features": ["4-week QQQ/SPY relative return", "13-week QQQ/SPY relative return"],
        "positioning_features": ["NQ-ES asset-manager net/OI", "NQ-ES leveraged-money net/OI", "13-week change of each"],
        "models": "expanding fixed ridge lambda=1; minimum 104 training weeks",
        "arms": ["PRICE_STATE_CONTROL", "POSITIONING_ONLY", "PRICE_PLUS_POSITIONING", "CAUSAL_PERMUTED_POSITIONING_NEGATIVE_CONTROL"],
        "decision_rule": "choose QQQ when predicted relative return >0 else SPY",
        "switch_cost_bps": 10,
        "publication_lag": "Tuesday COT observation available no earlier than Friday; signal price is first market close on/after Friday release",
        "windows": WINDOWS,
        "gate": "combined requires sufficient sample, positive matched excess in both windows, beats price control in both with >=3/5 positive chronology folds, and beats causal permuted control in both without parameter search",
        "no_feature_window_lambda_threshold_or_cost_search": True,
    },
    "source": {
        "dataset": "gpe5-46if",
        "ES_code": CODES["ES"],
        "NQ_code": CODES["NQ"],
        "source_admission_run": 34451989568,
        "source_admission_artifact": 10141899576,
        "source_release_commit": "46efe787ae2a766de330741a877b9255457af409",
    },
    "diagnostics": {
        "cftc_es_rows": int(len(es)),
        "cftc_nq_rows": int(len(nq)),
        "joined_cot_rows": int(len(cot)),
        "aligned_signal_rows": int(len(d)),
        "prediction_counts": prediction_diagnostics,
        "minimum_observations": {"all": MIN_ALL_OBS, "recent": MIN_RECENT_OBS},
        "sample_gate_pass": sample_ok,
        "negative_control": "deterministic LCG-indexed past-only positioning rows; current/future rows are impossible",
    },
    "tests": results,
    "decision": "CFTC_TFF_POSITIONING_INCREMENTAL_EVIDENCE" if incremental_gate else "CFTC_TFF_POSITIONING_NOT_INCREMENTAL",
    "limitations": [
        "Yahoo adjusted ETF prices are research-only",
        "COT release-date rule uses the standard Friday publication schedule",
        "This is a relative QQQ/SPY consumer and does not establish ticker-level alpha",
    ],
    "identity_note": "Earlier branch/PR/run names used local alias P282 before a concurrent fleet parent collision was discovered. P282 is not this workload's canonical parent identity.",
    "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
}
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/cftc_tff_relative_alpha_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
print(json.dumps(out, sort_keys=True))
