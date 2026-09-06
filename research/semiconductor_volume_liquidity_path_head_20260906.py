from __future__ import annotations

"""Development-only target-specific volume/liquidity information-value test.

PR #36 proved complete causal source coverage for a frozen six-feature volume/liquidity
family. This child keeps the exact PR31/PR34 19-feature path-head control and exact fixed
shallow HGB learner. Each target independently compares control_19 against control_19 plus
the predeclared volume/liquidity family. This is intentional multi-head architecture:
features need not help every target to be useful, and no trading utility is defined here.

No external semiconductor panel is loaded. No hyperparameter, target, threshold, cost,
admission, ranking, duration, sizing or policy sweep is performed.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import research.semiconductor_path_head_predictability_20260905 as ph
import research.semiconductor_volume_liquidity_preflight_20260906 as vl

OUT = Path('semiconductor_volume_liquidity_path_head_20260906.json')
VOLUME_FEATURES = list(vl.FEATURES)
TARGETS = ph.TARGETS


def add_volume_features(data: dict[str, pd.DataFrame], source: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex) -> None:
    base = ph.base
    surprise = {}
    per_symbol = {}
    for symbol in (*base.TRAIN, *base.CONTEXT):
        f = source[symbol].set_index('timestamp').reindex(calendar)
        log_volume = np.log(f.volume.astype(float))
        dollar_volume = f.raw_close.astype(float) * f.volume.astype(float)
        log_dollar = np.log(dollar_volume)
        adj_ret1 = f.adj_close.astype(float).pct_change()
        s = vl.z_against_prior(log_volume)
        part = pd.DataFrame(index=calendar)
        part['volume_surprise252'] = s
        part['volume_ratio20_60'] = np.log(
            f.volume.astype(float).rolling(20, min_periods=20).mean()
            / f.volume.astype(float).rolling(60, min_periods=60).mean()
        )
        part['dollar_volume_surprise252'] = vl.z_against_prior(log_dollar)
        illiq = (adj_ret1.abs() / dollar_volume.replace(0, np.nan)) * 1e9
        part['amihud20'] = illiq.rolling(20, min_periods=20).mean()
        surprise[symbol] = s
        per_symbol[symbol] = part

    sector = pd.DataFrame({s: surprise[s] for s in base.TRAIN}, index=calendar)
    breadth = (sector > 0).mean(axis=1)
    dispersion = sector.std(axis=1, ddof=0)
    for symbol in base.TRAIN:
        per_symbol[symbol]['sector_volume_surprise_breadth'] = breadth
        per_symbol[symbol]['sector_volume_surprise_dispersion'] = dispersion
        for feature in VOLUME_FEATURES:
            data[symbol][feature] = per_symbol[symbol][feature].to_numpy(float)


def build_rows(data, prices, cal, folds, features):
    base = ph.base
    rows = []
    for symbol in base.TRAIN:
        for fold, (start, stop) in enumerate(folds, start=1):
            safe = max(start, stop - (ph.DELAY + ph.HOLD))
            for i in range(start, safe):
                vals = data[symbol].loc[i, features].to_numpy(float)
                if not np.isfinite(vals).all():
                    continue
                ei = i + ph.DELAY
                xi = ei + ph.HOLD
                entry = float(prices[symbol].iloc[ei])
                path = prices[symbol].iloc[ei:xi + 1].to_numpy(float) / entry - 1.0
                row = {
                    'symbol': symbol,
                    'fold': fold,
                    'signal_i': i,
                    'terminal_net200_bps': float(path[-1] * 10000.0 - 200.0),
                    'mfe20_bps': float(np.max(path) * 10000.0),
                    'adverse_excursion20_bps': float(max(0.0, -np.min(path) * 10000.0)),
                }
                row.update({f: float(v) for f, v in zip(features, vals)})
                rows.append(row)
    return pd.DataFrame(rows)


def metric(pred, truth, baseline):
    pred = np.asarray(pred, float)
    truth = np.asarray(truth, float)
    baseline = np.asarray(baseline, float)
    return {
        'rows': int(len(truth)),
        'spearman': ph.sp(pred, truth),
        'mae': float(np.mean(np.abs(pred - truth))),
        'median_baseline_mae': float(np.mean(np.abs(baseline - truth))),
        'mae_improvement_vs_median': float(np.mean(np.abs(baseline - truth)) - np.mean(np.abs(pred - truth))),
    }


def evaluate(frame: pd.DataFrame, folds, features: list[str]) -> dict:
    fold_results = []
    all_truth = {t: [] for t in TARGETS}
    all_pred = {t: [] for t in TARGETS}
    all_base = {t: [] for t in TARGETS}
    for fold in range(2, 7):
        start, _ = folds[fold - 1]
        train = frame[frame.signal_i < start - (ph.DELAY + ph.HOLD)].copy()
        test = frame[frame.fold == fold].copy()
        if len(train) < 1000 or len(test) < 100:
            raise RuntimeError(f'fold {fold}: support train={len(train)} test={len(test)}')
        fr = {'fold': fold}
        for target in TARGETS:
            m = ph.model()
            m.fit(train[features].to_numpy(float), train[target].to_numpy(float))
            pred = m.predict(test[features].to_numpy(float))
            truth = test[target].to_numpy(float)
            med = float(np.median(train[target]))
            baseline = np.full(len(test), med, float)
            fr[target] = metric(pred, truth, baseline)
            all_truth[target].extend(truth.tolist())
            all_pred[target].extend(pred.tolist())
            all_base[target].extend(baseline.tolist())
        fold_results.append(fr)
    aggregate = {}
    for target in TARGETS:
        aggregate[target] = metric(all_pred[target], all_truth[target], all_base[target])
        aggregate[target]['positive_spearman_folds'] = sum(int((r[target]['spearman'] or -1.0) > 0) for r in fold_results)
        aggregate[target]['mae_better_folds'] = sum(int(r[target]['mae_improvement_vs_median'] > 0) for r in fold_results)
    return {'aggregate': aggregate, 'folds': fold_results}


def comparison(control, challenger, target: str) -> dict:
    c = control['aggregate'][target]
    h = challenger['aggregate'][target]
    spearman_better_folds = 0
    mae_better_folds = 0
    for cf, hf in zip(control['folds'], challenger['folds']):
        cs, hs = cf[target]['spearman'], hf[target]['spearman']
        if cs is not None and hs is not None and hs > cs:
            spearman_better_folds += 1
        if hf[target]['mae'] < cf[target]['mae']:
            mae_better_folds += 1
    robust = bool(
        h['spearman'] is not None and c['spearman'] is not None
        and h['spearman'] > 0
        and h['spearman'] > c['spearman']
        and h['mae'] < c['mae']
        and h['mae_improvement_vs_median'] > 0
        and h['positive_spearman_folds'] >= 3
        and h['mae_better_folds'] >= 3
        and spearman_better_folds >= 3
        and mae_better_folds >= 3
    )
    return {
        'control': c,
        'plus_volume_liquidity': h,
        'spearman_delta': None if c['spearman'] is None or h['spearman'] is None else float(h['spearman'] - c['spearman']),
        'mae_delta': float(h['mae'] - c['mae']),
        'spearman_improvement_folds_vs_control': spearman_better_folds,
        'mae_improvement_folds_vs_control': mae_better_folds,
        'robust_information_increment': robust,
    }


def main():
    base = ph.base
    symbols = (*base.TRAIN, *base.CONTEXT)
    source = {s: vl.load(s) for s in symbols}
    cutoff = min(f.iloc[-1].timestamp for f in source.values())
    sets = []
    for f in source.values():
        b = f.loc[f.timestamp <= cutoff]
        u = b[b.raw_close.notna() & b.adj_close.notna() & b.volume.notna() & (b.raw_close > 0) & (b.adj_close > 0) & (b.volume > 0)]
        sets.append(set(u.timestamp))
    cal = pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal) < 3000:
        raise RuntimeError(f'insufficient common source calendar={len(cal)}')
    prices = {s: source[s].set_index('timestamp').adj_close.reindex(cal).astype(float) for s in symbols}

    old = base.FRESH
    base.FRESH = ()
    try:
        data = base.engineer(prices, cal)
    finally:
        base.FRESH = old
    add_volume_features(data, source, cal)
    folds = base.folds(len(cal))
    control_features = list(base.FULL)
    challenger_features = [*control_features, *VOLUME_FEATURES]
    frame = build_rows(data, prices, cal, folds, challenger_features)
    control = evaluate(frame, folds, control_features)
    challenger = evaluate(frame, folds, challenger_features)
    comparisons = {target: comparison(control, challenger, target) for target in TARGETS}

    unlocked = [t for t in ('adverse_excursion20_bps','terminal_net200_bps') if comparisons[t]['robust_information_increment']]
    mfe_improved = comparisons['mfe20_bps']['robust_information_increment']
    if unlocked:
        decision = 'VOLUME_LIQUIDITY_ADDS_PATH_RISK_INFORMATION'
    elif mfe_improved:
        decision = 'VOLUME_LIQUIDITY_IMPROVES_MFE_ONLY'
    else:
        decision = 'VOLUME_LIQUIDITY_INFORMATION_NOT_JUSTIFIED_FOR_PATH_HEADS'

    out = {
        'schema': 'public_compute.semiconductor_volume_liquidity_path_head.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_preflight_pr': 36,
        'development_universe': list(base.TRAIN),
        'external_panels_loaded': False,
        'common_cutoff': cutoff.isoformat(),
        'common_calendar_rows': int(len(cal)),
        'control_features': control_features,
        'added_volume_liquidity_features': VOLUME_FEATURES,
        'architecture': 'target-specific path heads; each head independently chooses whether the frozen information family adds value',
        'learner': 'exact fixed shallow HistGradientBoostingRegressor from PR31/PR34; no sweep',
        'control': control,
        'plus_volume_liquidity': challenger,
        'comparisons': comparisons,
        'previously_failed_targets_unlocked': unlocked,
        'mfe_information_robustly_improved': mfe_improved,
        'decision': decision,
        'next_boundary': 'only a robust target-specific information increment justifies carrying this modality into a separately frozen multi-head architecture; no trading utility is authorized here',
        'policy_or_trading_utility_defined': False,
        'research_only': True,
        'promotion_authority': False,
        'runtime_mutation': False,
        'broker_action': False,
        'live_trading_change': False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + '\n')
    print('SEMICONDUCTOR_VOLUME_LIQUIDITY_PATH_HEAD=' + json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()
