from __future__ import annotations

"""Bounded pre-scorer FNSPID next-session arrival-state ablation.

This is intentionally narrower than the full frozen P11 news-state experiment:
- it uses only the fixed AMAT/AMD/AVGO bounded-prefix materialization;
- FNSPID timestamps are NEVER admitted intraday;
- each article becomes eligible only on the first trading session strictly after
  its RECORDED calendar date;
- news features are arrival/intensity/source-diversity only (no sentiment/LLM);
- the exact generic price-state Ridge lineage remains target-excluded, trained
  only on CAT/JPM/UNH/XOM/COST/MSFT;
- one prior-only Ridge residual learner asks whether news adds information beyond
  that frozen price prediction on AMAT/AMD/AVGO;
- a training-block-permuted news residual arm is the negative control.

A pass here is only bounded-subset evidence. It cannot grant full Semiconductor
news-state admission, scorer admission, StrategySpec/runtime/broker authority, or
live-trading authority.
"""

import argparse
import bisect
import csv
import hashlib
import json
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRAIN = ("CAT", "JPM", "UNH", "XOM", "COST", "MSFT")
TEST = ("AMAT", "AMD", "AVGO")
CONTEXT = ("QQQ", "SMH")
PRICE_FEATURES = (
    "mom5", "mom20", "mom60", "mom100", "mom20_z252", "mom20_accel5",
    "vol20", "vol20_z252", "distance_high60", "rs_qqq20", "rs_qqq60",
    "qqq_mom20", "qqq_mom100",
)
NEWS_FEATURES = (
    "log_news_count_1d", "log_news_count_5d", "log_news_count_20d",
    "news_arrival_surprise", "log_publisher_diversity_5d",
    "subset_news_breadth_1d", "subset_news_breadth_5d",
)
START = "2014-01-01"
END = "2024-03-01"
DELAY = 1
HOLD = 20
COST_BPS = 25.0
FOLDS = 6
EVAL_FIRST_FOLD = 2
MIN_TRAIN = 756
PURGE = 22
MIN_NEWS_ROWS_PER_SYMBOL = 300
MIN_SUPPORTED_YEARS = 5
MIN_ROWS_PER_SUPPORTED_YEAR = 20
MAX_SINGLE_YEAR_SHARE = 0.50
MAX_SINGLE_PUBLISHER_SHARE = 0.80
BLOCK_SESSIONS = 20
NEGATIVE_CONTROL_SEED = 20260906
MIN_RESIDUAL_TRAIN_ROWS = 300
MIN_RESIDUAL_TRAIN_ROWS_PER_SYMBOL = 50
MIN_FOLD_EVAL_ROWS = 30
MATERIAL_MAE_RATIO = 0.99  # >=1% aggregate MAE improvement, frozen pre-outcome


def _epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def _load_price(symbol: str) -> pd.Series:
    query = urlencode({
        "period1": _epoch(START), "period2": _epoch(END), "interval": "1d",
        "events": "history", "includeAdjustedClose": "true",
    })
    req = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}",
        headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"},
    )
    with urlopen(req, timeout=45) as response:  # noqa: S310 fixed HTTPS host
        payload = json.loads(response.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no chart result")
    ts = result.get("timestamp") or []
    ind = result.get("indicators", {})
    adjusted = (ind.get("adjclose") or [{}])[0].get("adjclose")
    close = adjusted or (ind.get("quote") or [{}])[0].get("close")
    s = pd.Series(
        pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(float),
        index=pd.DatetimeIndex(pd.to_datetime(ts, unit="s", utc=True)),
        name=symbol,
        dtype=float,
    ).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if len(s) < 1500 or (s <= 0).any():
        raise RuntimeError(f"{symbol}: invalid price history rows={len(s)}")
    return s


def _folds(n: int) -> list[tuple[int, int]]:
    edges = np.linspace(MIN_TRAIN, n - (HOLD + DELAY + 1), FOLDS + 1, dtype=int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(FOLDS)]


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 3 or np.std(a) <= 0 or np.std(b) <= 0:
        return None
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


def _price_state(prices: dict[str, pd.Series], calendar: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for symbol, price in prices.items():
        c = price.reindex(calendar)
        if c.isna().any():
            raise RuntimeError(f"{symbol}: missing common-calendar prices")
        df = pd.DataFrame({"timestamp": calendar, "price": c.to_numpy(float)})
        df["ret1"] = df.price.pct_change()
        for n in (5, 20, 60, 100):
            df[f"mom{n}"] = df.price.pct_change(n)
        df["vol20"] = df.ret1.rolling(20, min_periods=20).std(ddof=0)
        prior_mom = df.mom20.shift(1)
        pm = prior_mom.rolling(252, min_periods=126).mean()
        ps = prior_mom.rolling(252, min_periods=126).std(ddof=0).replace(0, np.nan)
        prior_vol = df.vol20.shift(1)
        vm = prior_vol.rolling(252, min_periods=126).mean()
        vs = prior_vol.rolling(252, min_periods=126).std(ddof=0).replace(0, np.nan)
        df["mom20_z252"] = (df.mom20 - pm) / ps
        df["vol20_z252"] = (df.vol20 - vm) / vs
        df["mom20_accel5"] = df.mom20 - df.mom20.shift(5)
        df["distance_high60"] = df.price / df.price.rolling(60, min_periods=60).max() - 1.0
        out[symbol] = df

    qqq = out["QQQ"]
    smh = out["SMH"]
    for symbol in (*TRAIN, *TEST):
        df = out[symbol]
        df["rs_qqq20"] = df.mom20 - qqq.mom20
        df["rs_qqq60"] = df.mom60 - qqq.mom60
        df["qqq_mom20"] = qqq.mom20
        df["qqq_mom100"] = qqq.mom100
        df["stock_gross_bps"] = (
            df.price.shift(-(DELAY + HOLD)) / df.price.shift(-DELAY) - 1.0
        ) * 10000.0
        df["target_net25_bps"] = df.stock_gross_bps - COST_BPS
        df["smh_gross_bps"] = (
            smh.price.shift(-(DELAY + HOLD)) / smh.price.shift(-DELAY) - 1.0
        ) * 10000.0
        df["conservative_smh_substitution_bps"] = df.stock_gross_bps - df.smh_gross_bps - 50.0
    return out


def _parse_day(text: str) -> date | None:
    text = str(text or "").strip()
    if len(text) < 10:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _load_news(path: Path, trading_days: list[date]) -> tuple[dict[str, dict[int, list[str]]], dict]:
    by_symbol: dict[str, dict[int, list[str]]] = {s: defaultdict(list) for s in TEST}
    raw_counts = Counter()
    years = defaultdict(Counter)
    publishers = Counter()
    min_day: dict[str, date] = {}
    max_day: dict[str, date] = {}
    source_rows = 0
    rejected_bad_date = 0
    rejected_after_calendar = 0
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        required = {"Date", "Stock_symbol", "Publisher"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"unexpected bounded news schema: {reader.fieldnames}")
        for row in reader:
            symbol = str(row.get("Stock_symbol") or "").strip().upper()
            if symbol not in TEST:
                continue
            source_rows += 1
            d = _parse_day(row.get("Date") or "")
            if d is None:
                rejected_bad_date += 1
                continue
            # STRICT causality rule: first trading session strictly AFTER recorded date.
            pos = bisect.bisect_right(trading_days, d)
            if pos >= len(trading_days):
                rejected_after_calendar += 1
                continue
            publisher = str(row.get("Publisher") or "").strip() or "<missing>"
            by_symbol[symbol][pos].append(publisher)
            raw_counts[symbol] += 1
            years[symbol][str(d.year)] += 1
            publishers[publisher] += 1
            min_day[symbol] = min(min_day.get(symbol, d), d)
            max_day[symbol] = max(max_day.get(symbol, d), d)

    coverage = {}
    coverage_pass = True
    for symbol in TEST:
        n = raw_counts[symbol]
        supported_years = [y for y, c in years[symbol].items() if c >= MIN_ROWS_PER_SUPPORTED_YEAR]
        year_share = max(years[symbol].values(), default=0) / max(n, 1)
        passed = bool(
            n >= MIN_NEWS_ROWS_PER_SYMBOL
            and len(supported_years) >= MIN_SUPPORTED_YEARS
            and year_share <= MAX_SINGLE_YEAR_SHARE
        )
        coverage_pass &= passed
        coverage[symbol] = {
            "rows": int(n),
            "supported_years_ge20": sorted(supported_years),
            "supported_year_count": len(supported_years),
            "max_single_year_share": float(year_share),
            "min_recorded_date": None if symbol not in min_day else min_day[symbol].isoformat(),
            "max_recorded_date": None if symbol not in max_day else max_day[symbol].isoformat(),
            "coverage_gate": passed,
        }
    publisher_share = max(publishers.values(), default=0) / max(sum(publishers.values()), 1)
    publisher_gate = publisher_share <= MAX_SINGLE_PUBLISHER_SHARE
    coverage_pass &= publisher_gate
    audit = {
        "source_rows": source_rows,
        "eligible_rows": int(sum(raw_counts.values())),
        "rejected_bad_date": rejected_bad_date,
        "rejected_after_price_calendar": rejected_after_calendar,
        "coverage": coverage,
        "publisher_count": len(publishers),
        "top_publishers": publishers.most_common(10),
        "max_single_publisher_share": float(publisher_share),
        "publisher_gate": publisher_gate,
        "coverage_gate": bool(coverage_pass),
        "gate_contract": {
            "min_rows_per_symbol": MIN_NEWS_ROWS_PER_SYMBOL,
            "min_supported_years": MIN_SUPPORTED_YEARS,
            "min_rows_per_supported_year": MIN_ROWS_PER_SUPPORTED_YEAR,
            "max_single_year_share": MAX_SINGLE_YEAR_SHARE,
            "max_single_publisher_share": MAX_SINGLE_PUBLISHER_SHARE,
        },
    }
    return by_symbol, audit


def _news_state(by_symbol: dict[str, dict[int, list[str]]], n: int) -> dict[str, pd.DataFrame]:
    counts = {s: np.zeros(n, dtype=float) for s in TEST}
    diversity5 = {s: np.zeros(n, dtype=float) for s in TEST}
    for s in TEST:
        for i, pubs in by_symbol[s].items():
            if i < n:
                counts[s][i] = len(pubs)
        window: deque[list[str]] = deque()
        pub_counter = Counter()
        for i in range(n):
            pubs = list(by_symbol[s].get(i, []))
            window.append(pubs)
            pub_counter.update(pubs)
            if len(window) > 5:
                old = window.popleft()
                for p in old:
                    pub_counter[p] -= 1
                    if pub_counter[p] <= 0:
                        del pub_counter[p]
            diversity5[s][i] = len(pub_counter)

    roll5 = {s: pd.Series(counts[s]).rolling(5, min_periods=1).sum().to_numpy() for s in TEST}
    roll20 = {s: pd.Series(counts[s]).rolling(20, min_periods=1).sum().to_numpy() for s in TEST}
    breadth1 = np.mean(np.vstack([counts[s] > 0 for s in TEST]), axis=0)
    breadth5 = np.mean(np.vstack([roll5[s] > 0 for s in TEST]), axis=0)

    out = {}
    for s in TEST:
        one = pd.Series(np.log1p(counts[s]))
        prior_mean = one.shift(1).expanding(min_periods=60).mean()
        prior_std = one.shift(1).expanding(min_periods=60).std(ddof=0).replace(0, np.nan)
        df = pd.DataFrame({
            "log_news_count_1d": np.log1p(counts[s]),
            "log_news_count_5d": np.log1p(roll5[s]),
            "log_news_count_20d": np.log1p(roll20[s]),
            "news_arrival_surprise": (one - prior_mean) / prior_std,
            "log_publisher_diversity_5d": np.log1p(diversity5[s]),
            "subset_news_breadth_1d": breadth1,
            "subset_news_breadth_5d": breadth5,
        })
        out[s] = df.replace([np.inf, -np.inf], np.nan)
    return out


def _fit_ridge(x: np.ndarray, y: np.ndarray) -> Pipeline:
    model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=10.0))])
    model.fit(x, y)
    return model


def _block_permute_training(frame: pd.DataFrame, columns: list[str], seed: int) -> np.ndarray:
    # Negative control only: all source rows here are already strictly prior to
    # the evaluation fold. Reassign 20-session blocks within each symbol; no test
    # feature or test outcome is imported into training.
    rng = np.random.default_rng(seed)
    x = frame[columns].to_numpy(float).copy()
    for symbol in TEST:
        pos = np.flatnonzero(frame.symbol.to_numpy() == symbol)
        if len(pos) < BLOCK_SESSIONS * 2:
            continue
        blocks = [pos[i:i + BLOCK_SESSIONS] for i in range(0, len(pos), BLOCK_SESSIONS)]
        order = np.arange(len(blocks))
        rng.shuffle(order)
        source = np.concatenate([blocks[i] for i in order])
        target = np.concatenate(blocks)
        # Unequal final blocks can change concatenated length only if malformed;
        # both are permutations of the same positions, so lengths must match.
        if len(source) != len(target):
            raise RuntimeError("negative-control block permutation length mismatch")
        x[target] = frame.iloc[source][columns].to_numpy(float)
    return x


def _arm_metrics(pred: np.ndarray, y: np.ndarray, smh: np.ndarray) -> dict:
    ae = np.abs(pred - y)
    selected = pred > 0.0
    return {
        "rows": int(len(y)),
        "mae_bps": float(ae.mean()),
        "spearman": _spearman(pred, y),
        "predicted_positive_rows": int(selected.sum()),
        "predicted_positive_rate": float(selected.mean()),
        "selected_mean_net25_bps": None if not selected.any() else float(y[selected].mean()),
        "selected_mean_conservative_smh_substitution_bps": None if not selected.any() else float(smh[selected].mean()),
        "top20_actual_net25_bps": float(y[pred >= np.quantile(pred, 0.8)].mean()),
    }


def _frame_for_symbols(data: dict[str, pd.DataFrame], news: dict[str, pd.DataFrame] | None,
                       symbols: tuple[str, ...], folds: list[tuple[int, int]]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        df = data[symbol].copy()
        df["symbol"] = symbol
        df["signal_i"] = np.arange(len(df), dtype=int)
        fc = np.zeros(len(df), dtype=int)
        for fold, (start, stop) in enumerate(folds, 1):
            safe_stop = max(start, stop - (DELAY + HOLD))
            fc[start:safe_stop] = fold
        df["fold"] = fc
        if news is not None and symbol in news:
            for col in NEWS_FEATURES:
                df[col] = news[symbol][col].to_numpy(float)
        cols = ["symbol", "signal_i", "fold", *PRICE_FEATURES, "target_net25_bps",
                "conservative_smh_substitution_bps"]
        if news is not None and symbol in news:
            cols += list(NEWS_FEATURES)
        rows.append(df[df.fold > 0][cols])
    return pd.concat(rows, ignore_index=True).replace([np.inf, -np.inf], np.nan)


def run(news_csv: Path) -> dict:
    symbols = (*TRAIN, *TEST, *CONTEXT)
    raw = {s: _load_price(s) for s in symbols}
    common = raw[symbols[0]].index
    for s in symbols[1:]:
        common = common.intersection(raw[s].index)
    calendar = common.sort_values()
    if len(calendar) < 1500:
        raise RuntimeError(f"insufficient common price calendar={len(calendar)}")
    prices = {s: raw[s].reindex(calendar) for s in symbols}
    state = _price_state(prices, calendar)
    trading_days = [x.date() for x in calendar]
    news_events, coverage = _load_news(news_csv, trading_days)
    if not coverage["coverage_gate"]:
        return {
            "schema": "research.fnspid_next_session_arrival_ablation.v1",
            "classification": "FNSPID_BOUNDED_PREFIX_COVERAGE_INADEQUATE_NO_ECONOMIC_ABLATION",
            "coverage": coverage,
            "economic_ablation_executed": False,
            "causal_intraday_admission": "REJECT_UPSTREAM_UTC_CONVERSION_UNSAFE",
            "eligibility": "STRICT_NEXT_TRADING_SESSION_AFTER_RECORDED_DATE_ONLY",
            "research_only": True,
            "full_family_news_state_admission": False,
            "runtime_mutation": False,
            "broker_authority": False,
            "live_trading_change": False,
        }

    news_state = _news_state(news_events, len(calendar))
    folds = _folds(len(calendar))
    generic = _frame_for_symbols(state, None, TRAIN, folds).dropna(subset=[*PRICE_FEATURES, "target_net25_bps"])
    test = _frame_for_symbols(state, news_state, TEST, folds).dropna(
        subset=[*PRICE_FEATURES, *NEWS_FEATURES, "target_net25_bps", "conservative_smh_substitution_bps"]
    )

    fold_results = []
    row_evidence = []
    for fold in range(EVAL_FIRST_FOLD, FOLDS + 1):
        start, _ = folds[fold - 1]
        gtrain = generic[generic.signal_i < start - PURGE]
        evalf = test[test.fold == fold].copy()
        rtrain = test[test.signal_i < start - PURGE].copy()
        per_symbol_train = rtrain.groupby("symbol").size().to_dict()
        if len(gtrain) < 1000:
            raise RuntimeError(f"fold {fold}: generic train too small {len(gtrain)}")
        if len(rtrain) < MIN_RESIDUAL_TRAIN_ROWS or any(per_symbol_train.get(s, 0) < MIN_RESIDUAL_TRAIN_ROWS_PER_SYMBOL for s in TEST):
            raise RuntimeError(f"fold {fold}: residual train support insufficient total={len(rtrain)} by_symbol={per_symbol_train}")
        if len(evalf) < MIN_FOLD_EVAL_ROWS:
            raise RuntimeError(f"fold {fold}: eval support insufficient rows={len(evalf)}")

        price_model = _fit_ridge(gtrain[list(PRICE_FEATURES)].to_numpy(float), gtrain.target_net25_bps.to_numpy(float))
        price_train_pred = price_model.predict(rtrain[list(PRICE_FEATURES)].to_numpy(float))
        price_eval_pred = price_model.predict(evalf[list(PRICE_FEATURES)].to_numpy(float))
        residual = rtrain.target_net25_bps.to_numpy(float) - price_train_pred

        news_only = _fit_ridge(rtrain[list(NEWS_FEATURES)].to_numpy(float), rtrain.target_net25_bps.to_numpy(float))
        residual_model = _fit_ridge(rtrain[list(NEWS_FEATURES)].to_numpy(float), residual)
        permuted_x = _block_permute_training(rtrain, list(NEWS_FEATURES), NEGATIVE_CONTROL_SEED + fold)
        permuted_model = _fit_ridge(permuted_x, residual)

        news_x_eval = evalf[list(NEWS_FEATURES)].to_numpy(float)
        preds = {
            "PRICE_STATE_CONTROL": price_eval_pred,
            "NEWS_ONLY": news_only.predict(news_x_eval),
            "PRICE_PLUS_NEWS": price_eval_pred + residual_model.predict(news_x_eval),
            "PERMUTED_NEWS_NEGATIVE_CONTROL": price_eval_pred + permuted_model.predict(news_x_eval),
        }
        y = evalf.target_net25_bps.to_numpy(float)
        smh = evalf.conservative_smh_substitution_bps.to_numpy(float)
        arms = {k: _arm_metrics(v, y, smh) for k, v in preds.items()}
        delta = {
            "mae_improvement_bps": arms["PRICE_STATE_CONTROL"]["mae_bps"] - arms["PRICE_PLUS_NEWS"]["mae_bps"],
            "mae_improvement_ratio": 1.0 - arms["PRICE_PLUS_NEWS"]["mae_bps"] / arms["PRICE_STATE_CONTROL"]["mae_bps"],
            "selected_mean_net25_delta_bps": None,
        }
        csel = arms["PRICE_STATE_CONTROL"]["selected_mean_net25_bps"]
        nsel = arms["PRICE_PLUS_NEWS"]["selected_mean_net25_bps"]
        if csel is not None and nsel is not None:
            delta["selected_mean_net25_delta_bps"] = nsel - csel
        fold_results.append({"fold": fold, "rows": len(evalf), "arms": arms, "increment": delta})

        for j, (_, row) in enumerate(evalf.reset_index(drop=True).iterrows()):
            p0 = float(preds["PRICE_STATE_CONTROL"][j]); pn = float(preds["PRICE_PLUS_NEWS"][j]); actual = float(y[j])
            row_evidence.append({
                "fold": fold,
                "symbol": str(row.symbol),
                "signal_i": int(row.signal_i),
                "year": int(calendar[int(row.signal_i)].year),
                "actual": actual,
                "price_pred": p0,
                "plus_pred": pn,
                "abs_error_reduction": abs(p0 - actual) - abs(pn - actual),
            })

    # Aggregate exact OOS rows across folds.
    all_metrics = {}
    for arm in ("PRICE_STATE_CONTROL", "NEWS_ONLY", "PRICE_PLUS_NEWS", "PERMUTED_NEWS_NEGATIVE_CONTROL"):
        # Weighted aggregation of fold means by row count for non-decomposable selection metrics is supplemented below.
        total_rows = sum(f["arms"][arm]["rows"] for f in fold_results)
        all_metrics[arm] = {
            "rows": total_rows,
            "weighted_mae_bps": float(sum(f["arms"][arm]["mae_bps"] * f["arms"][arm]["rows"] for f in fold_results) / total_rows),
            "mean_fold_spearman": float(np.mean([f["arms"][arm]["spearman"] for f in fold_results if f["arms"][arm]["spearman"] is not None])),
            "mean_fold_selected_net25_bps": float(np.mean([f["arms"][arm]["selected_mean_net25_bps"] for f in fold_results if f["arms"][arm]["selected_mean_net25_bps"] is not None])),
            "mean_fold_selected_conservative_smh_substitution_bps": float(np.mean([f["arms"][arm]["selected_mean_conservative_smh_substitution_bps"] for f in fold_results if f["arms"][arm]["selected_mean_conservative_smh_substitution_bps"] is not None])),
        }

    control_mae = all_metrics["PRICE_STATE_CONTROL"]["weighted_mae_bps"]
    plus_mae = all_metrics["PRICE_PLUS_NEWS"]["weighted_mae_bps"]
    perm_mae = all_metrics["PERMUTED_NEWS_NEGATIVE_CONTROL"]["weighted_mae_bps"]
    positive_mae_folds = sum(f["increment"]["mae_improvement_bps"] > 0 for f in fold_results)
    positive_econ_folds = sum((f["increment"]["selected_mean_net25_delta_bps"] or -np.inf) > 0 for f in fold_results)
    permuted_positive_folds = sum(
        f["arms"]["PERMUTED_NEWS_NEGATIVE_CONTROL"]["mae_bps"] < f["arms"]["PRICE_STATE_CONTROL"]["mae_bps"]
        for f in fold_results
    )

    positive = [r for r in row_evidence if r["abs_error_reduction"] > 0]
    total_positive = sum(r["abs_error_reduction"] for r in positive)
    by_symbol = defaultdict(float); by_year = defaultdict(float)
    for r in positive:
        by_symbol[r["symbol"]] += r["abs_error_reduction"]
        by_year[str(r["year"])] += r["abs_error_reduction"]
    symbol_share = max(by_symbol.values(), default=0.0) / max(total_positive, 1e-12)
    year_share = max(by_year.values(), default=0.0) / max(total_positive, 1e-12)

    material = plus_mae <= control_mae * MATERIAL_MAE_RATIO
    permuted_reproduces = bool(perm_mae < control_mae and permuted_positive_folds >= 3)
    subset_pass = bool(
        material
        and positive_mae_folds >= 3
        and positive_econ_folds >= 3
        and not permuted_reproduces
        and symbol_share <= 0.50
        and year_share <= 0.50
    )
    news_only_better = all_metrics["NEWS_ONLY"]["weighted_mae_bps"] < control_mae
    if subset_pass:
        classification = "FNSPID_NEXT_SESSION_ARRIVAL_STATE_SUBSET_EVIDENCE"
    elif news_only_better and not material:
        classification = "FNSPID_NEXT_SESSION_NEWS_ONLY_REDUNDANT_TO_PRICE_CONTROL"
    else:
        classification = "FNSPID_NEXT_SESSION_ARRIVAL_STATE_NO_ROBUST_INCREMENTAL_EVIDENCE"

    payload = {
        "schema": "research.fnspid_next_session_arrival_ablation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classification": classification,
        "economic_ablation_executed": True,
        "scope": "bounded AMAT/AMD/AVGO FNSPID prefix only; pre-scorer arrival/intensity features",
        "full_family_news_state_admission": False,
        "causal_intraday_admission": "REJECT_UPSTREAM_UTC_CONVERSION_UNSAFE",
        "eligibility": "STRICT_NEXT_TRADING_SESSION_AFTER_RECORDED_DATE_ONLY",
        "price_control": {
            "train_universe": list(TRAIN),
            "target_excluded_test_universe": list(TEST),
            "features": list(PRICE_FEATURES),
            "model": "StandardScaler + Ridge(alpha=10)",
            "target": "fixed20 stock return after 25 bps",
            "delay_sessions": DELAY,
            "hold_sessions": HOLD,
            "folds": FOLDS,
            "evaluation_folds": "2-6",
            "min_train_sessions": MIN_TRAIN,
            "purge_sessions": PURGE,
        },
        "news_features": list(NEWS_FEATURES),
        "news_model": "prior-only Ridge(alpha=10) residual correction plus separate NEWS_ONLY Ridge",
        "negative_control": {
            "type": "20-session block permutation of TRAINING news features within symbol; evaluation news remains causally unpermuted",
            "block_sessions": BLOCK_SESSIONS,
            "seed": NEGATIVE_CONTROL_SEED,
        },
        "coverage": coverage,
        "folds": fold_results,
        "aggregate": all_metrics,
        "incremental_gate": {
            "material_mae_ratio_required": MATERIAL_MAE_RATIO,
            "actual_mae_ratio": float(plus_mae / control_mae),
            "positive_mae_folds": positive_mae_folds,
            "positive_selected_economics_folds": positive_econ_folds,
            "permuted_positive_mae_folds": permuted_positive_folds,
            "permuted_reproduces_improvement": permuted_reproduces,
            "max_positive_error_reduction_symbol_share": float(symbol_share),
            "max_positive_error_reduction_year_share": float(year_share),
            "subset_gate_pass": subset_pass,
            "note": "Even PASS is bounded-subset evidence only and cannot satisfy the full frozen P11 family/scorer gate.",
        },
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_authority": False,
        "live_trading_change": False,
    }
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--news-csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = run(args.news_csv)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FNSPID_NEXT_SESSION_ABLATION=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
