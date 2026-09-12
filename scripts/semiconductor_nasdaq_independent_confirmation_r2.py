from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRAIN = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")
EXTERNAL = ("NVDA", "AMD", "MU", "AVGO", "MRVL", "MCHP")
CONTEXT = ("SMH", "QQQ")
ALL = (*TRAIN, *EXTERNAL, *CONTEXT)
START = "2014-01-01"
HOLD = 20
DELAY = 1
FOLDS = 6
MIN_TRAIN = 756
PURGE = 22
EVAL_FIRST_FOLD = 2
COST_BPS = (25.0, 50.0, 100.0, 150.0, 200.0)
TAIL = 0.30
JUMP_GUARD = 0.35
MIN_COMMON_ROWS = 1500
OUT = Path("results/semiconductor_nasdaq_independent_confirmation_r2.json")

FEATURES = [
    "mom5", "mom20", "mom60", "mom100", "mom20_z252", "mom20_accel5",
    "vol20", "vol20_z252", "distance_high60", "rs_smh20", "rs_smh60",
    "rs_qqq20", "rs_qqq60", "smh_mom20", "smh_mom100", "qqq_mom20",
    "qqq_mom100", "survivor_breadth_positive20", "survivor_cross_section_mom20_pct",
]


def _parse_date(value: str) -> date:
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(text)


def _price(value: object) -> float:
    return float(str(value or "").strip().replace("$", "").replace(",", ""))


def _load(symbol: str) -> pd.Series:
    asset_class = "etf" if symbol in CONTEXT else "stocks"
    query = urlencode({
        "assetclass": asset_class,
        "fromdate": START,
        "todate": (date.today() + timedelta(days=2)).isoformat(),
        "limit": 5000,
    })
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical?{query}"
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://www.nasdaq.com/market-activity/{asset_class}/{symbol.lower()}/historical",
        "Origin": "https://www.nasdaq.com",
    })
    with urlopen(req, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    vals = sorted({_parse_date(r["date"]): _price(r["close"]) for r in rows}.items())
    if len(vals) < MIN_COMMON_ROWS:
        raise RuntimeError(f"{symbol}: insufficient Nasdaq rows={len(vals)}")
    if any(v <= 0 for _, v in vals):
        raise RuntimeError(f"{symbol}: non-positive close")
    return pd.Series(
        [v for _, v in vals],
        index=pd.DatetimeIndex(pd.to_datetime([d for d, _ in vals], utc=True)),
        name=symbol,
        dtype=float,
    )


def _guard(price: pd.Series) -> np.ndarray:
    ret = price.pct_change().to_numpy(float)
    disc = np.isfinite(ret) & (np.abs(ret) > JUMP_GUARD)
    n = len(price)
    ok = np.ones(n, dtype=bool)
    for i in range(n):
        lo = max(1, i - 100)
        hi = min(n, i + DELAY + HOLD + 1)
        if disc[lo:hi].any():
            ok[i] = False
    return ok


def _folds(n: int) -> list[tuple[int, int]]:
    edges = np.linspace(MIN_TRAIN, n - (HOLD + DELAY + 1), FOLDS + 1, dtype=int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(FOLDS)]


def _engineer(prices: dict[str, pd.Series], calendar: pd.DatetimeIndex):
    data: dict[str, pd.DataFrame] = {}
    guards = {s: _guard(prices[s]) for s in ALL}
    shared_guard = np.logical_and.reduce([guards[s] for s in (*TRAIN, *CONTEXT)])
    for symbol in ALL:
        p = prices[symbol]
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
        df["guard_ok"] = shared_guard & guards[symbol]
        data[symbol] = df
    smh, qqq = data["SMH"], data["QQQ"]
    surv = pd.DataFrame({s: data[s].mom20 for s in TRAIN})
    breadth = (surv > 0).mean(axis=1)
    survivor_rank = surv.rank(axis=1, pct=True, method="average")
    for symbol in (*TRAIN, *EXTERNAL):
        df = data[symbol]
        df["rs_smh20"] = df.mom20 - smh.mom20
        df["rs_smh60"] = df.mom60 - smh.mom60
        df["rs_qqq20"] = df.mom20 - qqq.mom20
        df["rs_qqq60"] = df.mom60 - qqq.mom60
        df["smh_mom20"] = smh.mom20
        df["smh_mom100"] = smh.mom100
        df["qqq_mom20"] = qqq.mom20
        df["qqq_mom100"] = qqq.mom100
        df["survivor_breadth_positive20"] = breadth
        if symbol in TRAIN:
            df["survivor_cross_section_mom20_pct"] = survivor_rank[symbol]
        else:
            df["survivor_cross_section_mom20_pct"] = pd.Series(
                [np.nan if pd.isna(v) else float((surv.iloc[i] <= v).mean()) for i, v in enumerate(df.mom20)],
                index=df.index,
            )
        df["enter20_after25_bps"] = (
            df.price.shift(-(DELAY + HOLD)) / df.price.shift(-DELAY) - 1.0
        ) * 10000.0 - 25.0
        df["smh20_gross_bps"] = (
            smh.price.shift(-(DELAY + HOLD)) / smh.price.shift(-DELAY) - 1.0
        ) * 10000.0
    return data


def _frame(symbols, data, folds):
    rows = []
    for symbol in symbols:
        df = data[symbol].copy()
        df["symbol"] = symbol
        df["signal_i"] = np.arange(len(df), dtype=int)
        fc = np.zeros(len(df), dtype=int)
        for fold, (start, stop) in enumerate(folds, 1):
            fc[start:max(start, stop - (DELAY + HOLD))] = fold
        df["fold"] = fc
        columns = ["symbol", "signal_i", "fold", *FEATURES, "enter20_after25_bps", "smh20_gross_bps"]
        use = df[(df.fold > 0) & df.guard_ok][columns]
        rows.append(use)
    return pd.concat(rows, ignore_index=True).replace([np.inf, -np.inf], np.nan).dropna(
        subset=FEATURES + ["enter20_after25_bps", "smh20_gross_bps"]
    )


def _fit(train: pd.DataFrame):
    model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=10.0))])
    model.fit(train[FEATURES].to_numpy(float), train.enter20_after25_bps.to_numpy(float))
    return model


def main():
    raw = {s: _load(s) for s in ALL}
    common = raw[ALL[0]].index
    for s in ALL[1:]:
        common = common.intersection(raw[s].index)
    common = common.sort_values()
    if len(common) < MIN_COMMON_ROWS:
        raise RuntimeError(f"insufficient strict common calendar={len(common)}")
    prices = {s: raw[s].reindex(common) for s in ALL}
    if any(v.isna().any() for v in prices.values()):
        raise RuntimeError("missing strict common-calendar price")
    fingerprint = hashlib.sha256(
        "\n".join(
            f"{d.date().isoformat()}|" + "|".join(f"{prices[s].loc[d]:.10f}" for s in ALL)
            for d in common
        ).encode()
    ).hexdigest()
    data = _engineer(prices, common)
    folds = _folds(len(common))
    train_states = _frame(TRAIN, data, folds)
    test_states = _frame(EXTERNAL, data, folds)
    per_symbol = []
    for symbol in EXTERNAL:
        fold_rows = []
        outside_all = []
        outside_excess_all = []
        for fold in range(EVAL_FIRST_FOLD, FOLDS + 1):
            start, _ = folds[fold - 1]
            train = train_states[train_states.signal_i < start - PURGE]
            test = test_states[(test_states.symbol == symbol) & (test_states.fold == fold)]
            if len(train) < 1000 or len(test) < 100:
                raise RuntimeError(f"{symbol} fold {fold}: insufficient train/test={len(train)}/{len(test)}")
            model = _fit(train)
            pred = model.predict(test[FEATURES].to_numpy(float))
            chosen = test.loc[pred > 0].copy()
            prior_df = data[symbol].iloc[: start - PURGE]
            prior = prior_df.loc[prior_df.guard_ok, "mom20"].dropna()
            if len(prior) < 100:
                raise RuntimeError(f"{symbol} fold {fold}: insufficient guarded threshold history={len(prior)}")
            threshold = float(prior.quantile(1.0 - TAIL))
            outside = chosen.loc[chosen["mom20"] < threshold].copy()
            net50 = outside.enter20_after25_bps.to_numpy(float) - 25.0
            gross = outside.enter20_after25_bps.to_numpy(float) + 25.0
            excess = gross - outside.smh20_gross_bps.to_numpy(float)
            outside_all.extend(gross.tolist())
            outside_excess_all.extend(excess.tolist())
            fold_rows.append({
                "fold": fold,
                "train_states": int(len(train)),
                "test_states": int(len(test)),
                "model_trades": int(len(chosen)),
                "outside_frozen_trades": int(len(outside)),
                "outside_net50_mean_bps": None if not len(outside) else float(net50.mean()),
                "outside_matched_smh_excess_mean_bps": None if not len(outside) else float(excess.mean()),
            })
        outside_gross = np.asarray(outside_all, float)
        outside_excess = np.asarray(outside_excess_all, float)
        cost_rows = {}
        for cost in COST_BPS:
            net = outside_gross - cost
            cost_rows[str(int(cost))] = {
                "outside_frozen_mean_bps": None if not len(net) else float(net.mean()),
                "outside_frozen_median_bps": None if not len(net) else float(np.median(net)),
                "positive_trade_fraction": None if not len(net) else float((net > 0).mean()),
            }
        pos_net50_folds = sum((r["outside_net50_mean_bps"] if r["outside_net50_mean_bps"] is not None else -1e99) > 0 for r in fold_rows)
        pos_excess_folds = sum((r["outside_matched_smh_excess_mean_bps"] if r["outside_matched_smh_excess_mean_bps"] is not None else -1e99) > 0 for r in fold_rows)
        passes50 = bool(
            len(outside_gross) >= 20
            and cost_rows["50"]["outside_frozen_mean_bps"] > 0
            and pos_net50_folds >= 3
            and len(outside_excess) > 0
            and float(outside_excess.mean()) > 0
            and pos_excess_folds >= 3
        )
        per_symbol.append({
            "symbol": symbol,
            "outside_frozen_trades": int(len(outside_gross)),
            "costs": cost_rows,
            "matched_smh_excess_mean_bps": None if not len(outside_excess) else float(outside_excess.mean()),
            "positive_net50_folds": int(pos_net50_folds),
            "positive_matched_smh_excess_folds": int(pos_excess_folds),
            "source_independent_50bps_matched_gate": passes50,
            "folds": fold_rows,
        })
    passing50 = sum(r["source_independent_50bps_matched_gate"] for r in per_symbol)
    passing200 = sum(
        r["outside_frozen_trades"] >= 20 and r["costs"]["200"]["outside_frozen_mean_bps"] > 0
        for r in per_symbol
    )
    out = {
        "schema": "research.semiconductor_nasdaq_independent_confirmation.v1",
        "experiment_id": "CC-RF-SEMICON-NASDAQ-INDEPENDENT-CONFIRM-001",
        "implementation_revision": "R2 deterministic duplicate-column fix only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Nasdaq historical API raw daily close",
        "common_start": common[0].date().isoformat(),
        "common_end": common[-1].date().isoformat(),
        "common_rows": int(len(common)),
        "source_fingerprint_sha256": fingerprint,
        "corporate_action_guard": {
            "policy": "no price transformation; quarantine candidate states if abs raw-close one-session return >35% in prior 100 through forward 21 sessions",
            "jump_threshold": JUMP_GUARD,
        },
        "frozen_contract": {
            "train": list(TRAIN), "external": list(EXTERNAL), "context": list(CONTEXT),
            "model": "StandardScaler + Ridge(alpha=10)", "features": FEATURES,
            "hold": HOLD, "delay": DELAY, "folds": FOLDS, "min_train": MIN_TRAIN,
            "purge": PURGE, "entry": "predicted fixed20 value > 0", "costs_bps": list(COST_BPS),
        },
        "per_symbol": per_symbol,
        "decision": {
            "passing_external_symbols_at_50bps_with_matched_smh_gate": int(passing50),
            "required": 4,
            "passing_external_symbols_at_200bps_absolute": int(passing200),
            "required_200bps": 4,
            "source_independent_confirmation_pass": bool(passing50 >= 4 and passing200 >= 4),
        },
        "boundaries": {"runtime_mutation": False, "allocation_authority": False, "live_trading_change": False},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
