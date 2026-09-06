from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

START = "2015-01-01"
END = "2026-09-06"
LOOKBACK_MAX = 120
FORWARD = 20
DECISION_STEP = 20
DEV_FRACTION = 0.65
CRAK_COST_BPS = 50.0
ETF_COST_BPS = 10.0
MIN_INNER_TRAIN = 36
INNER_FOLDS = 4
LOW_Q = 0.30
HIGH_Q = 0.70

CORE = ["CRAK", "XLE", "SPY", "QQQ"]
ENERGY = ["XOP", "MPC", "VLO", "PSX"]
MACRO = ["IEF", "TLT", "SHY", "UUP"]
COMPLEMENTS = ["SMH", "ITB", "XLI", "XLU", "XLV", "XLF", "IYT", "XBI"]
SYMBOLS = list(dict.fromkeys(CORE + ENERGY + MACRO + COMPLEMENTS))

FAMILIES = {
    "refining_state": [
        "crak_xle_ret20", "crak_xle_ret60", "crak_xle_ret120",
        "crak_vol20", "xle_vol20",
    ],
    "energy_breadth": [
        "xop_xle_ret20", "xop_xle_ret60",
        "refiner_breadth20", "refiner_dispersion20",
    ],
    "broad_risk": [
        "spy_ret20", "spy_ret60", "spy_vol20", "spy_vol60",
        "qqq_spy_ret20", "qqq_spy_ret60",
    ],
    "rates_dollar": [
        "ief_ret20", "ief_ret60", "tlt_shy_ret20", "tlt_shy_ret60",
        "uup_ret20", "uup_ret60",
    ],
}
MODEL_MENU = {
    "refining_only": ["refining_state"],
    "refining_plus_energy": ["refining_state", "energy_breadth"],
    "refining_plus_risk": ["refining_state", "broad_risk"],
    "refining_plus_macro": ["refining_state", "rates_dollar"],
    "full_state": list(FAMILIES),
}


def epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def load(symbol: str) -> pd.DataFrame:
    params = urlencode({
        "period1": epoch(START),
        "period2": epoch(END),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    req = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}",
        headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"},
    )
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode())
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no chart result")
    ts = result.get("timestamp") or []
    ind = result.get("indicators", {})
    quote = (ind.get("quote") or [{}])[0]
    adj = (ind.get("adjclose") or [{}])[0].get("adjclose")
    close = adj or quote.get("close")
    if not ts or close is None:
        raise RuntimeError(f"{symbol}: missing timestamp/close")
    return pd.DataFrame(
        {"close": pd.to_numeric(pd.Series(close), errors="coerce").to_numpy()},
        index=pd.to_datetime(ts, unit="s", utc=True),
    ).dropna().sort_index()


def ret(series: pd.Series, n: int) -> pd.Series:
    return series.pct_change(n, fill_method=None)


def vol(series: pd.Series, n: int) -> pd.Series:
    return series.pct_change(fill_method=None).rolling(n, min_periods=n).std(ddof=0) * np.sqrt(252.0)


def rank_corr(a: np.ndarray, b: np.ndarray) -> float:
    aa = pd.Series(a).rank(method="average")
    bb = pd.Series(b).rank(method="average")
    value = aa.corr(bb)
    return float(value) if pd.notna(value) else float("nan")


def feature_columns(family_names: list[str]) -> list[str]:
    out: list[str] = []
    for family in family_names:
        out.extend(FAMILIES[family])
    return out


def make_model() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("ridge", Ridge(alpha=10.0)),
    ])


def build_state(close: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=close.index)
    f["crak_xle_ret20"] = ret(close.CRAK, 20) - ret(close.XLE, 20)
    f["crak_xle_ret60"] = ret(close.CRAK, 60) - ret(close.XLE, 60)
    f["crak_xle_ret120"] = ret(close.CRAK, 120) - ret(close.XLE, 120)
    f["crak_vol20"] = vol(close.CRAK, 20)
    f["xle_vol20"] = vol(close.XLE, 20)

    f["xop_xle_ret20"] = ret(close.XOP, 20) - ret(close.XLE, 20)
    f["xop_xle_ret60"] = ret(close.XOP, 60) - ret(close.XLE, 60)
    component_rel = pd.DataFrame({
        s: ret(close[s], 20) - ret(close.XLE, 20)
        for s in ["MPC", "VLO", "PSX"]
    })
    f["refiner_breadth20"] = (component_rel > 0.0).mean(axis=1)
    f["refiner_dispersion20"] = component_rel.std(axis=1, ddof=0)

    f["spy_ret20"] = ret(close.SPY, 20)
    f["spy_ret60"] = ret(close.SPY, 60)
    f["spy_vol20"] = vol(close.SPY, 20)
    f["spy_vol60"] = vol(close.SPY, 60)
    f["qqq_spy_ret20"] = ret(close.QQQ, 20) - ret(close.SPY, 20)
    f["qqq_spy_ret60"] = ret(close.QQQ, 60) - ret(close.SPY, 60)

    f["ief_ret20"] = ret(close.IEF, 20)
    f["ief_ret60"] = ret(close.IEF, 60)
    f["tlt_shy_ret20"] = ret(close.TLT, 20) - ret(close.SHY, 20)
    f["tlt_shy_ret60"] = ret(close.TLT, 60) - ret(close.SHY, 60)
    f["uup_ret20"] = ret(close.UUP, 20)
    f["uup_ret60"] = ret(close.UUP, 60)
    return f


def decision_panel(close: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    indices = range(LOOKBACK_MAX, len(close) - FORWARD, DECISION_STEP)
    for i in indices:
        ts = close.index[i]
        row = {"date": ts, "pos": i}
        for c in features.columns:
            row[c] = features[c].iloc[i]
        crak_fwd = float(close.CRAK.iloc[i + FORWARD] / close.CRAK.iloc[i] - 1.0)
        xle_fwd = float(close.XLE.iloc[i + FORWARD] / close.XLE.iloc[i] - 1.0)
        spy_fwd = float(close.SPY.iloc[i + FORWARD] / close.SPY.iloc[i] - 1.0)
        qqq_fwd = float(close.QQQ.iloc[i + FORWARD] / close.QQQ.iloc[i] - 1.0)
        crak_net = (1.0 + crak_fwd) * (1.0 - CRAK_COST_BPS / 10000.0) - 1.0
        row.update({
            "crak_fwd": crak_fwd,
            "crak_net50": crak_net,
            "xle_fwd": xle_fwd,
            "spy_fwd": spy_fwd,
            "qqq_fwd": qqq_fwd,
            "target_crak_xle_net50": crak_net - xle_fwd,
        })
        for s in COMPLEMENTS:
            gross = float(close[s].iloc[i + FORWARD] / close[s].iloc[i] - 1.0)
            net = (1.0 + gross) * (1.0 - ETF_COST_BPS / 10000.0) - 1.0
            row[f"{s}_net10"] = net
        rows.append(row)
    panel = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    needed = list({c for cols in FAMILIES.values() for c in cols}) + ["target_crak_xle_net50"]
    return panel.dropna(subset=needed).reset_index(drop=True)


def dev_oos_scores(dev: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, list[dict]]:
    n = len(dev)
    if n < MIN_INNER_TRAIN + INNER_FOLDS * 5:
        raise RuntimeError(f"insufficient development decisions={n}")
    test_positions = np.arange(MIN_INNER_TRAIN, n)
    chunks = np.array_split(test_positions, INNER_FOLDS)
    pred = np.full(n, np.nan, dtype=float)
    fold_rows = []
    for k, chunk in enumerate(chunks, 1):
        if len(chunk) < 3:
            continue
        start = int(chunk[0])
        stop = int(chunk[-1]) + 1
        train_stop = max(0, start - 1)  # one-decision purge; spacing equals forward horizon
        train = dev.iloc[:train_stop]
        test = dev.iloc[start:stop]
        model = make_model()
        model.fit(train[cols].to_numpy(float), train.target_crak_xle_net50.to_numpy(float))
        p = model.predict(test[cols].to_numpy(float))
        pred[start:stop] = p
        fold_rows.append({
            "fold": k,
            "train_decisions": int(len(train)),
            "test_decisions": int(len(test)),
            "start": test.date.iloc[0].isoformat(),
            "end": test.date.iloc[-1].isoformat(),
            "spearman": rank_corr(p, test.target_crak_xle_net50.to_numpy(float)),
            "mean_target_bps": float(test.target_crak_xle_net50.mean() * 10000.0),
        })
    return pred, fold_rows


def summarize_state(rows: pd.DataFrame, score_name: str) -> dict:
    if rows.empty:
        return {"n": 0}
    out = {
        "n": int(len(rows)),
        "start": rows.date.iloc[0].isoformat(),
        "end": rows.date.iloc[-1].isoformat(),
        "mean_score": float(rows[score_name].mean()),
        "crak_net50_mean_pct": float(rows.crak_net50.mean() * 100.0),
        "xle_mean_pct": float(rows.xle_fwd.mean() * 100.0),
        "spy_mean_pct": float(rows.spy_fwd.mean() * 100.0),
        "qqq_mean_pct": float(rows.qqq_fwd.mean() * 100.0),
        "excess_xle_mean_bps": float((rows.crak_net50 - rows.xle_fwd).mean() * 10000.0),
        "excess_spy_mean_bps": float((rows.crak_net50 - rows.spy_fwd).mean() * 10000.0),
        "excess_qqq_mean_bps": float((rows.crak_net50 - rows.qqq_fwd).mean() * 10000.0),
        "xle_win_rate": float(((rows.crak_net50 - rows.xle_fwd) > 0).mean()),
        "spy_win_rate": float(((rows.crak_net50 - rows.spy_fwd) > 0).mean()),
        "qqq_win_rate": float(((rows.crak_net50 - rows.qqq_fwd) > 0).mean()),
    }
    return out


def chronology_blocks(rows: pd.DataFrame, value: pd.Series, blocks: int = 3) -> list[dict]:
    if rows.empty:
        return []
    chunks = np.array_split(np.arange(len(rows)), blocks)
    out = []
    for k, idx in enumerate(chunks, 1):
        if len(idx) == 0:
            continue
        v = value.iloc[idx]
        out.append({
            "block": k,
            "start": rows.date.iloc[idx[0]].isoformat(),
            "end": rows.date.iloc[idx[-1]].isoformat(),
            "n": int(len(idx)),
            "mean_bps": float(v.mean() * 10000.0),
            "win_rate": float((v > 0).mean()),
        })
    return out


def main() -> None:
    raw = {s: load(s) for s in SYMBOLS}
    close = pd.concat([raw[s].close.rename(s) for s in SYMBOLS], axis=1, join="inner").dropna().sort_index()
    features = build_state(close)
    panel = decision_panel(close, features)

    split = int(len(panel) * DEV_FRACTION)
    dev = panel.iloc[:split].copy().reset_index(drop=True)
    holdout = panel.iloc[split:].copy().reset_index(drop=True)
    if len(holdout) < 20:
        raise RuntimeError(f"insufficient holdout decisions={len(holdout)}")

    menu = {}
    menu_predictions = {}
    for name, family_names in MODEL_MENU.items():
        cols = feature_columns(family_names)
        pred, folds = dev_oos_scores(dev, cols)
        valid = np.isfinite(pred)
        spearman = rank_corr(pred[valid], dev.loc[valid, "target_crak_xle_net50"].to_numpy(float))
        positive_folds = sum(1 for f in folds if np.isfinite(f["spearman"]) and f["spearman"] > 0)
        menu[name] = {
            "families": family_names,
            "columns": cols,
            "dev_oos_spearman": spearman,
            "positive_spearman_folds": positive_folds,
            "folds": folds,
        }
        menu_predictions[name] = pred

    eligible = [n for n, r in menu.items() if r["positive_spearman_folds"] >= 3 and r["dev_oos_spearman"] > 0]
    selected_name = max(eligible, key=lambda n: menu[n]["dev_oos_spearman"]) if eligible else max(menu, key=lambda n: menu[n]["dev_oos_spearman"])
    selected = menu[selected_name]
    selected_cols = selected["columns"]
    dev_pred = menu_predictions[selected_name]
    valid_dev = np.isfinite(dev_pred)
    score_train = dev_pred[valid_dev]
    low_threshold = float(np.quantile(score_train, LOW_Q))
    high_threshold = float(np.quantile(score_train, HIGH_Q))

    final_model = make_model()
    final_model.fit(dev[selected_cols].to_numpy(float), dev.target_crak_xle_net50.to_numpy(float))
    holdout["score"] = final_model.predict(holdout[selected_cols].to_numpy(float))
    holdout_spearman = rank_corr(holdout.score.to_numpy(float), holdout.target_crak_xle_net50.to_numpy(float))

    high = holdout[holdout.score >= high_threshold].copy().reset_index(drop=True)
    low = holdout[holdout.score <= low_threshold].copy().reset_index(drop=True)
    high_summary = summarize_state(high, "score")
    low_refining_summary = summarize_state(low, "score")
    high_blocks = chronology_blocks(high, high.crak_net50 - high.xle_fwd)

    # Development-only complement discovery inside low-refining-score states.
    dev_scored = dev.loc[valid_dev].copy().reset_index(drop=True)
    dev_scored["score"] = score_train
    low_dev = dev_scored[dev_scored.score <= low_threshold].copy().reset_index(drop=True)
    complement_dev = {}
    for s in COMPLEMENTS:
        net = low_dev[f"{s}_net10"]
        ex_spy = net - low_dev.spy_fwd
        ex_qqq = net - low_dev.qqq_fwd
        complement_dev[s] = {
            "n": int(len(low_dev)),
            "mean_net_pct": float(net.mean() * 100.0),
            "excess_spy_bps": float(ex_spy.mean() * 10000.0),
            "excess_qqq_bps": float(ex_qqq.mean() * 10000.0),
            "spy_win_rate": float((ex_spy > 0).mean()),
            "qqq_win_rate": float((ex_qqq > 0).mean()),
            "selection_score_bps": float(min(ex_spy.mean(), ex_qqq.mean()) * 10000.0),
        }
    complement_symbol = max(COMPLEMENTS, key=lambda s: complement_dev[s]["selection_score_bps"])

    complement_holdout = {"symbol": complement_symbol, "n": int(len(low))}
    if len(low):
        net = low[f"{complement_symbol}_net10"]
        ex_spy = net - low.spy_fwd
        ex_qqq = net - low.qqq_fwd
        complement_holdout.update({
            "mean_net_pct": float(net.mean() * 100.0),
            "excess_spy_bps": float(ex_spy.mean() * 10000.0),
            "excess_qqq_bps": float(ex_qqq.mean() * 10000.0),
            "spy_win_rate": float((ex_spy > 0).mean()),
            "qqq_win_rate": float((ex_qqq > 0).mean()),
            "spy_blocks": chronology_blocks(low, ex_spy),
            "qqq_blocks": chronology_blocks(low, ex_qqq),
        })

    # Predeclared grouped ablations, interpreted only; holdout does not re-select the model.
    ablations = {}
    for family in FAMILIES:
        keep = [f for f in MODEL_MENU["full_state"] if f != family]
        cols = feature_columns(keep)
        model = make_model()
        model.fit(dev[cols].to_numpy(float), dev.target_crak_xle_net50.to_numpy(float))
        pred = model.predict(holdout[cols].to_numpy(float))
        ablations[family] = {
            "holdout_spearman_without_family": rank_corr(pred, holdout.target_crak_xle_net50.to_numpy(float)),
        }

    scaler = final_model.named_steps["scale"]
    ridge = final_model.named_steps["ridge"]
    coefficients = sorted(
        [{"feature": c, "standardized_coef": float(v)} for c, v in zip(selected_cols, ridge.coef_, strict=True)],
        key=lambda r: abs(r["standardized_coef"]),
        reverse=True,
    )

    high_positive_blocks = sum(1 for b in high_blocks if b["mean_bps"] > 0)
    representation_supported = bool(
        selected["positive_spearman_folds"] >= 3
        and selected["dev_oos_spearman"] > 0
        and holdout_spearman > 0
        and high_summary.get("n", 0) >= 8
        and high_summary.get("excess_xle_mean_bps", -1e9) > 0
        and high_summary.get("xle_win_rate", 0.0) >= 0.55
        and high_positive_blocks >= 2
    )

    comp_spy_blocks = complement_holdout.get("spy_blocks", [])
    comp_qqq_blocks = complement_holdout.get("qqq_blocks", [])
    complement_supported = bool(
        complement_holdout.get("n", 0) >= 8
        and complement_holdout.get("excess_spy_bps", -1e9) > 0
        and complement_holdout.get("excess_qqq_bps", -1e9) > 0
        and complement_holdout.get("spy_win_rate", 0.0) >= 0.55
        and complement_holdout.get("qqq_win_rate", 0.0) >= 0.55
        and sum(1 for b in comp_spy_blocks if b["mean_bps"] > 0) >= 2
        and sum(1 for b in comp_qqq_blocks if b["mean_bps"] > 0) >= 2
    )

    payload = {
        "schema": "research.refining_mechanism_attribution.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo adjusted daily chart endpoint; environment-independent public data",
        "shared_window": {
            "start": close.index[0].isoformat(),
            "end": close.index[-1].isoformat(),
            "rows": int(len(close)),
            "decision_step_sessions": DECISION_STEP,
            "forward_sessions": FORWARD,
            "decision_count": int(len(panel)),
            "dev_count": int(len(dev)),
            "holdout_count": int(len(holdout)),
            "dev_end": dev.date.iloc[-1].isoformat(),
            "holdout_start": holdout.date.iloc[0].isoformat(),
        },
        "frozen_contract": {
            "objective": "learn state representation for future CRAK-vs-XLE excess and independently identify a complement when refining score is weak",
            "no_high_vol_gate_promoted": True,
            "model_family": "StandardScaler + Ridge(alpha=10)",
            "model_menu": MODEL_MENU,
            "family_definitions": FAMILIES,
            "dev_fraction": DEV_FRACTION,
            "inner_oos_folds": INNER_FOLDS,
            "one_decision_purge": True,
            "state_quantiles": {"low": LOW_Q, "high": HIGH_Q},
            "crak_cost_bps": CRAK_COST_BPS,
            "complement_etf_cost_bps": ETF_COST_BPS,
            "complement_universe": COMPLEMENTS,
            "holdout_not_used_for_model_or_complement_selection": True,
        },
        "model_menu_results": menu,
        "selected_model": selected_name,
        "selected_model_eligible_on_dev": selected_name in eligible,
        "score_thresholds_from_dev_oos": {"low": low_threshold, "high": high_threshold},
        "holdout_spearman": holdout_spearman,
        "high_refining_score_holdout": high_summary,
        "high_refining_score_xle_blocks": high_blocks,
        "low_refining_score_holdout": low_refining_summary,
        "grouped_ablation_holdout_diagnostics": ablations,
        "selected_model_standardized_coefficients": coefficients,
        "complement_development_selection": complement_dev,
        "selected_complement": complement_symbol,
        "selected_complement_holdout": complement_holdout,
        "decisions": {
            "refining_state_representation": "SUPPORTED_FOR_FRESH_CONFIRMATION" if representation_supported else "NOT_SUPPORTED",
            "low_state_complement": "SUPPORTED_FOR_FRESH_CONFIRMATION" if complement_supported else "NOT_SUPPORTED",
        },
        "research_only": True,
        "allocation_authority": False,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_authority": False,
        "live_trading_change": False,
    }
    with open("refining-mechanism-attribution-20260906.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    print("REFINING_MECHANISM_ATTRIBUTION=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
