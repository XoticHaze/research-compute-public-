from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

START = dt.datetime(2014, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 9, 18, tzinfo=dt.timezone.utc)
TRAIN = ("CAT", "JPM", "UNH", "XOM", "COST", "MSFT")
TEST = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI", "NVDA", "AMD", "MU", "AVGO", "MRVL", "MCHP")
CONTEXT = ("QQQ", "SMH")
FEATURES = (
    "mom5", "mom20", "mom60", "mom100", "mom20_z252", "mom20_accel5",
    "vol20", "vol20_z252", "distance_high60", "rs_qqq20", "rs_qqq60",
    "qqq_mom20", "qqq_mom100",
)
DELAY = 1
HOLD = 20
COST_BPS = 25.0
FOLDS = 6
MIN_TRAIN = 756
PURGE = 22
EVAL_FIRST_FOLD = 2
RISK_Q = 0.80
OUTPUT = Path("research/results/b_survivor_mae_abstention_r1.json")


def load(symbol: str) -> pd.Series:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "period1": int(START.timestamp()),
        "period2": int(END.timestamp()),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    r = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    ts = pd.to_datetime(result["timestamp"], unit="s", utc=True)
    adj = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    close = adj or result["indicators"]["quote"][0]["close"]
    s = pd.Series(pd.to_numeric(close, errors="coerce"), index=ts, name=symbol).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def folds(n: int) -> list[tuple[int, int]]:
    edges = np.linspace(MIN_TRAIN, n - (HOLD + DELAY + 1), FOLDS + 1, dtype=int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(FOLDS)]


def engineer(prices: dict[str, pd.Series], calendar: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for symbol, s in prices.items():
        p = s.reindex(calendar)
        df = pd.DataFrame({"timestamp": calendar, "price": p.to_numpy(float)})
        df["ret1"] = df.price.pct_change()
        for n in (5, 20, 60, 100):
            df[f"mom{n}"] = df.price.pct_change(n)
        df["vol20"] = df.ret1.rolling(20, min_periods=20).std(ddof=0)
        pm = df.mom20.shift(1)
        pv = df.vol20.shift(1)
        mm = pm.rolling(252, min_periods=126).mean()
        ms = pm.rolling(252, min_periods=126).std(ddof=0).replace(0, np.nan)
        vm = pv.rolling(252, min_periods=126).mean()
        vs = pv.rolling(252, min_periods=126).std(ddof=0).replace(0, np.nan)
        df["mom20_z252"] = (df.mom20 - mm) / ms
        df["vol20_z252"] = (df.vol20 - vm) / vs
        df["mom20_accel5"] = df.mom20 - df.mom20.shift(5)
        df["distance_high60"] = df.price / df.price.rolling(60, min_periods=60).max() - 1.0
        out[symbol] = df

    qqq = out["QQQ"]
    smh = out["SMH"].price.to_numpy(float)
    for symbol in (*TRAIN, *TEST):
        df = out[symbol]
        df["rs_qqq20"] = df.mom20 - qqq.mom20
        df["rs_qqq60"] = df.mom60 - qqq.mom60
        df["qqq_mom20"] = qqq.mom20
        df["qqq_mom100"] = qqq.mom100
        df["enter20_after25_bps"] = (df.price.shift(-(DELAY + HOLD)) / df.price.shift(-DELAY) - 1.0) * 10000.0 - COST_BPS
        mae = np.full(len(df), np.nan)
        smhret = np.full(len(df), np.nan)
        p = df.price.to_numpy(float)
        for i in range(len(df)):
            e = i + DELAY
            x = e + HOLD
            if x >= len(df):
                continue
            path = p[e:x + 1] / p[e] - 1.0
            mae[i] = max(0.0, -float(np.min(path)) * 10000.0)
            smhret[i] = float((smh[x] / smh[e] - 1.0) * 10000.0)
        df["mae_loss_bps"] = mae
        df["smh_gross_bps"] = smhret
    return out


def frame(symbols: tuple[str, ...], data: dict[str, pd.DataFrame], fs: list[tuple[int, int]]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        df = data[symbol].copy()
        df["symbol"] = symbol
        df["signal_i"] = np.arange(len(df), dtype=int)
        fc = np.zeros(len(df), dtype=int)
        for fold, (start, stop) in enumerate(fs, 1):
            fc[start:max(start, stop - DELAY - HOLD)] = fold
        df["fold"] = fc
        rows.append(df[df.fold > 0][["symbol", "signal_i", "fold", "timestamp", *FEATURES, "enter20_after25_bps", "mae_loss_bps", "smh_gross_bps"]])
    out = pd.concat(rows, ignore_index=True).replace([np.inf, -np.inf], np.nan)
    return out.dropna(subset=[*FEATURES, "enter20_after25_bps", "mae_loss_bps", "smh_gross_bps"])


def model() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=10.0))])


def select_nonoverlap(test: pd.DataFrame, ep: np.ndarray, rp: np.ndarray, cut: float, filtered: bool) -> list[dict]:
    w = test.copy().reset_index(drop=True)
    w["entry_pred"] = ep
    w["risk_pred"] = rp
    out = []
    next_exec_ok = -1
    for row in w.sort_values("signal_i").itertuples(index=False):
        exec_i = int(row.signal_i) + DELAY
        if exec_i < next_exec_ok or float(row.entry_pred) <= 0:
            continue
        if filtered and float(row.risk_pred) > cut:
            continue
        out.append({
            "symbol": str(row.symbol),
            "fold": int(row.fold),
            "entry_timestamp": row.timestamp.isoformat(),
            "after25_bps": float(row.enter20_after25_bps),
            "mae_loss_bps": float(row.mae_loss_bps),
            "matched_smh_excess_bps": float(row.enter20_after25_bps - row.smh_gross_bps),
        })
        next_exec_ok = exec_i + HOLD
    return out


def summary(rows: list[dict]) -> dict:
    if not rows:
        return {"trades": 0}
    net = np.asarray([r["after25_bps"] for r in rows])
    mae = np.asarray([r["mae_loss_bps"] for r in rows])
    exc = np.asarray([r["matched_smh_excess_bps"] for r in rows])
    return {
        "trades": len(rows),
        "mean_after25_bps": float(net.mean()),
        "median_after25_bps": float(np.median(net)),
        "median_mae_loss_bps": float(np.median(mae)),
        "mean_mae_loss_bps": float(mae.mean()),
        "mean_matched_smh_excess_bps": float(exc.mean()),
        "positive_trade_rate": float(np.mean(net > 0)),
        "cost_stress_mean_bps": {str(c): float(np.mean(net - (c - 25.0))) for c in (25, 50, 100, 200)},
    }


def concentration(rows: list[dict], mode: str) -> float:
    pos = [r for r in rows if r["after25_bps"] > 0]
    total = sum(r["after25_bps"] for r in pos)
    if total <= 0:
        return 1.0
    g: dict[str, float] = {}
    for r in pos:
        k = str(pd.Timestamp(r["entry_timestamp"]).year) if mode == "year" else r["symbol"]
        g[k] = g.get(k, 0.0) + r["after25_bps"]
    return float(max(g.values()) / total)


def main() -> None:
    symbols = (*TRAIN, *TEST, *CONTEXT)
    raw = {s: load(s) for s in symbols}
    cutoff = min(x.index[-1] for x in raw.values())
    sets = [set(x.loc[x.index <= cutoff].index) for x in raw.values()]
    calendar = pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(calendar) < 1500:
        raise RuntimeError(f"insufficient common calendar={len(calendar)}")
    prices = {s: raw[s].reindex(calendar) for s in raw}
    if any(x.isna().any() for x in prices.values()):
        raise RuntimeError("missing common-calendar prices")
    data = engineer(prices, calendar)
    fs = folds(len(calendar))
    train = frame(TRAIN, data, fs)
    test = frame(TEST, data, fs)

    all_inc, all_fil, fold_rows = [], [], []
    for fold in range(EVAL_FIRST_FOLD, FOLDS + 1):
        start, _ = fs[fold - 1]
        tr = train[train.signal_i < start - PURGE]
        if len(tr) < 1000:
            raise RuntimeError(f"fold {fold}: insufficient train={len(tr)}")
        em = model().fit(tr[list(FEATURES)], tr.enter20_after25_bps)
        rm = model().fit(tr[list(FEATURES)], tr.mae_loss_bps)
        cut = float(np.quantile(rm.predict(tr[list(FEATURES)]), RISK_Q))
        fi, ff = [], []
        for symbol in TEST:
            te = test[(test.symbol == symbol) & (test.fold == fold)]
            x = te[list(FEATURES)]
            ep, rp = em.predict(x), rm.predict(x)
            fi += select_nonoverlap(te, ep, rp, cut, False)
            ff += select_nonoverlap(te, ep, rp, cut, True)
        si, sf = summary(fi), summary(ff)
        fold_rows.append({"fold": fold, "risk_cutoff_bps": cut, "incumbent": si, "risk_abstain": sf, "incremental_mean_after25_bps": sf["mean_after25_bps"] - si["mean_after25_bps"]})
        all_inc += fi
        all_fil += ff

    inc, fil = summary(all_inc), summary(all_fil)
    retention = fil["trades"] / inc["trades"]
    mae_imp = 1.0 - fil["median_mae_loss_bps"] / inc["median_mae_loss_bps"] if inc["median_mae_loss_bps"] > 0 else 0.0
    pos_fil_folds = sum(r["risk_abstain"]["mean_after25_bps"] > 0 for r in fold_rows)
    pos_inc_folds = sum(r["incremental_mean_after25_bps"] > 0 for r in fold_rows)
    sym_share, yr_share = concentration(all_fil, "symbol"), concentration(all_fil, "year")
    gates = {
        "retention_ge_70pct": retention >= 0.70,
        "mean_after25_not_worse": fil["mean_after25_bps"] >= inc["mean_after25_bps"],
        "median_mae_improvement_ge_10pct": mae_imp >= 0.10,
        "matched_smh_excess_not_worse": fil["mean_matched_smh_excess_bps"] >= inc["mean_matched_smh_excess_bps"],
        "positive_filtered_folds_ge_4": pos_fil_folds >= 4,
        "positive_incremental_folds_ge_3": pos_inc_folds >= 3,
        "symbol_positive_pnl_share_le_50pct": sym_share <= 0.50,
        "year_positive_pnl_share_le_50pct": yr_share <= 0.50,
    }
    supported = all(gates.values())
    eval_start = calendar[fs[EVAL_FIRST_FOLD - 1][0] + DELAY]
    eval_end = calendar[fs[-1][1] - 1]
    smh = prices["SMH"].loc[(prices["SMH"].index >= eval_start) & (prices["SMH"].index <= eval_end)]
    result = {
        "schema": "research.b_survivor_mae_abstention_r1.v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "decision": "MAE_ABSTENTION_SURVIVOR_IMPROVEMENT_SUPPORTED" if supported else "MAE_ABSTENTION_SURVIVOR_IMPROVEMENT_REJECTED",
        "common_cutoff": cutoff.isoformat(),
        "train_universe": TRAIN,
        "target_excluded_test_universe": TEST,
        "contract": {
            "entry_model": "StandardScaler+Ridge(alpha=10)",
            "entry_features": FEATURES,
            "entry_rule": "predicted fixed20 after25 value > 0",
            "risk_model": "StandardScaler+Ridge(alpha=10)",
            "risk_target": "fixed20 maximum adverse excursion loss magnitude bps",
            "risk_rule": "abstain only above prior-training 80th percentile predicted MAE risk",
            "risk_quantile": RISK_Q,
            "hold_sessions": HOLD,
            "execution_delay": DELAY,
            "test_target_history_in_training": False,
            "ticker_identity": False,
            "search": False,
        },
        "controls": {"cash_return": 0.0, "passive_smh_total_return_eval_window": float(smh.iloc[-1] / smh.iloc[0] - 1.0)},
        "incumbent": inc,
        "risk_abstain": fil,
        "trade_retention": retention,
        "median_mae_improvement_fraction": mae_imp,
        "positive_filtered_folds": pos_fil_folds,
        "positive_incremental_folds": pos_inc_folds,
        "max_positive_pnl_symbol_share": sym_share,
        "max_positive_pnl_year_share": yr_share,
        "folds": fold_rows,
        "support_gate": gates,
        "boundaries": {"research_only": True, "strategy_spec": False, "runtime": False, "broker": False, "live_trading": False},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("RESULT_JSON=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
