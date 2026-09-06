from __future__ import annotations

"""Development-only risk/regime representation audit after the MFE breadth falsifier.

PR #34 established that MFE20 information is broad across all seven development names and
survives every leave-one-symbol-out aggregate. This child changes only the information
representation. The learner, targets, chronology, costs and original seven-symbol domain
remain fixed. No external semiconductor panel is loaded.

The exact current 19-feature representation is the control. Three economically motivated,
causal price-state information families are added separately and together:
- market_risk: SMH/QQQ volatility, drawdown and relative market state;
- cross_section_risk: semiconductor breadth60, dispersion and rolling correlation;
- own_risk: each stock's longer volatility and rolling beta/correlation to SMH/QQQ.

The purpose is not to select a trading policy. It asks whether richer state information
preserves/improves the already-broad MFE signal and, more importantly, unlocks the two path
quantities the current representation failed to learn: adverse excursion and terminal
realization. Family ablations are diagnostics only; only the predeclared FULL arm can earn
the next architecture step.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import research.semiconductor_path_head_predictability_20260905 as ph

OUT = Path('semiconductor_risk_regime_representation_20260906.json')

MARKET_RISK = [
    'smh_vol20_risk', 'smh_vol60_risk', 'qqq_vol20_risk', 'qqq_vol60_risk',
    'smh_drawdown60', 'qqq_drawdown60', 'smh_qqq_rs20_risk', 'smh_qqq_rs60_risk',
]
CROSS_SECTION_RISK = [
    'survivor_breadth_positive60', 'survivor_dispersion_mom20',
    'survivor_dispersion_ret1', 'survivor_avg_corr60',
]
OWN_RISK = [
    'own_vol60_risk', 'own_corr_smh60', 'own_beta_smh60',
    'own_corr_qqq60', 'own_beta_qqq60', 'own_minus_smh_vol20',
]
NEW = [*MARKET_RISK, *CROSS_SECTION_RISK, *OWN_RISK]
TARGETS = ph.TARGETS


def rolling_avg_corr(frame: pd.DataFrame, window: int = 60) -> pd.Series:
    a = frame.to_numpy(float)
    out = np.full(len(frame), np.nan, float)
    tri = np.triu_indices(frame.shape[1], 1)
    for i in range(window - 1, len(frame)):
        x = a[i - window + 1:i + 1]
        if not np.isfinite(x).all():
            continue
        c = np.corrcoef(x, rowvar=False)
        vals = c[tri]
        if np.isfinite(vals).all():
            out[i] = float(np.mean(vals))
    return pd.Series(out, index=frame.index)


def enrich(data: dict[str, pd.DataFrame]) -> None:
    base = ph.base
    smh, qqq = data['SMH'], data['QQQ']
    smh_vol20 = smh.ret1.rolling(20, min_periods=20).std(ddof=0)
    smh_vol60 = smh.ret1.rolling(60, min_periods=60).std(ddof=0)
    qqq_vol20 = qqq.ret1.rolling(20, min_periods=20).std(ddof=0)
    qqq_vol60 = qqq.ret1.rolling(60, min_periods=60).std(ddof=0)
    smh_dd60 = smh.price / smh.price.rolling(60, min_periods=60).max() - 1.0
    qqq_dd60 = qqq.price / qqq.price.rolling(60, min_periods=60).max() - 1.0

    ret1 = pd.DataFrame({s: data[s].ret1 for s in base.TRAIN})
    mom20 = pd.DataFrame({s: data[s].mom20 for s in base.TRAIN})
    mom60 = pd.DataFrame({s: data[s].mom60 for s in base.TRAIN})
    breadth60 = (mom60 > 0).mean(axis=1)
    dispersion20 = mom20.std(axis=1, ddof=0)
    dispersion1 = ret1.std(axis=1, ddof=0)
    avg_corr60 = rolling_avg_corr(ret1, 60)

    smh_var60 = smh.ret1.rolling(60, min_periods=60).var(ddof=0).replace(0, np.nan)
    qqq_var60 = qqq.ret1.rolling(60, min_periods=60).var(ddof=0).replace(0, np.nan)

    for s in base.TRAIN:
        d = data[s]
        d['smh_vol20_risk'] = smh_vol20
        d['smh_vol60_risk'] = smh_vol60
        d['qqq_vol20_risk'] = qqq_vol20
        d['qqq_vol60_risk'] = qqq_vol60
        d['smh_drawdown60'] = smh_dd60
        d['qqq_drawdown60'] = qqq_dd60
        d['smh_qqq_rs20_risk'] = smh.mom20 - qqq.mom20
        d['smh_qqq_rs60_risk'] = smh.mom60 - qqq.mom60
        d['survivor_breadth_positive60'] = breadth60
        d['survivor_dispersion_mom20'] = dispersion20
        d['survivor_dispersion_ret1'] = dispersion1
        d['survivor_avg_corr60'] = avg_corr60
        d['own_vol60_risk'] = d.ret1.rolling(60, min_periods=60).std(ddof=0)
        d['own_corr_smh60'] = d.ret1.rolling(60, min_periods=60).corr(smh.ret1)
        d['own_beta_smh60'] = d.ret1.rolling(60, min_periods=60).cov(smh.ret1) / smh_var60
        d['own_corr_qqq60'] = d.ret1.rolling(60, min_periods=60).corr(qqq.ret1)
        d['own_beta_qqq60'] = d.ret1.rolling(60, min_periods=60).cov(qqq.ret1) / qqq_var60
        d['own_minus_smh_vol20'] = d.vol20 - smh_vol20


def build_rows(data, prices, cal, folds, all_features):
    base = ph.base
    rows = []
    for symbol in base.TRAIN:
        for fold, (start, stop) in enumerate(folds, start=1):
            safe = max(start, stop - (ph.DELAY + ph.HOLD))
            for i in range(start, safe):
                vals = data[symbol].loc[i, all_features].to_numpy(float)
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
                row.update({f: float(v) for f, v in zip(all_features, vals)})
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
        aggregate[target]['positive_spearman_folds'] = sum(
            int((row[target]['spearman'] if row[target]['spearman'] is not None else -1.0) > 0)
            for row in fold_results
        )
        aggregate[target]['mae_better_folds'] = sum(
            int(row[target]['mae_improvement_vs_median'] > 0) for row in fold_results
        )
    return {'aggregate': aggregate, 'folds': fold_results}


def fold_improvement_count(control, challenger, target: str, key: str, higher: bool) -> int:
    n = 0
    for c, h in zip(control['folds'], challenger['folds']):
        cv = c[target][key]
        hv = h[target][key]
        if cv is None or hv is None:
            continue
        if (hv > cv) if higher else (hv < cv):
            n += 1
    return n


def target_comparison(control, arm, target: str) -> dict:
    c = control['aggregate'][target]
    a = arm['aggregate'][target]
    return {
        'control': c,
        'challenger': a,
        'spearman_delta': None if c['spearman'] is None or a['spearman'] is None else float(a['spearman'] - c['spearman']),
        'mae_delta': float(a['mae'] - c['mae']),
        'spearman_improvement_folds': fold_improvement_count(control, arm, target, 'spearman', True),
        'mae_improvement_vs_control_folds': fold_improvement_count(control, arm, target, 'mae', False),
    }


def main():
    base = ph.base
    symbols = (*base.TRAIN, *base.CONTEXT)
    raw = {s: base.load(s) for s in symbols}
    cutoff = min(d.iloc[-1].timestamp for d in raw.values())
    sets = [set(d.loc[d.timestamp <= cutoff, 'timestamp']) for d in raw.values()]
    cal = pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal) < 1500:
        raise RuntimeError(f'insufficient calendar={len(cal)}')
    prices = {s: raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()):
        raise RuntimeError('missing common-calendar price')

    old = base.FRESH
    base.FRESH = ()
    try:
        data = base.engineer(prices, cal)
    finally:
        base.FRESH = old
    enrich(data)
    folds = base.folds(len(cal))
    all_features = [*base.FULL, *NEW]
    frame = build_rows(data, prices, cal, folds, all_features)

    arms = {
        'control_19': list(base.FULL),
        'plus_market_risk': [*base.FULL, *MARKET_RISK],
        'plus_cross_section_risk': [*base.FULL, *CROSS_SECTION_RISK],
        'plus_own_risk': [*base.FULL, *OWN_RISK],
        'full_risk_regime': all_features,
    }
    results = {name: evaluate(frame, folds, features) for name, features in arms.items()}
    control = results['control_19']
    full = results['full_risk_regime']

    comparisons = {
        arm: {target: target_comparison(control, result, target) for target in TARGETS}
        for arm, result in results.items() if arm != 'control_19'
    }

    full_mfe = full['aggregate']['mfe20_bps']
    control_mfe = control['aggregate']['mfe20_bps']
    mfe_preserved = bool(
        full_mfe['spearman'] is not None and control_mfe['spearman'] is not None
        and full_mfe['spearman'] >= control_mfe['spearman']
        and full_mfe['positive_spearman_folds'] >= control_mfe['positive_spearman_folds']
        and comparisons['full_risk_regime']['mfe20_bps']['spearman_improvement_folds'] >= 3
    )

    unlocked = []
    for target in ('adverse_excursion20_bps', 'terminal_net200_bps'):
        a = full['aggregate'][target]
        if bool(
            a['spearman'] is not None and a['spearman'] > 0
            and a['mae_improvement_vs_median'] > 0
            and a['positive_spearman_folds'] >= 3
            and a['mae_better_folds'] >= 3
            and comparisons['full_risk_regime'][target]['spearman_improvement_folds'] >= 3
        ):
            unlocked.append(target)

    if mfe_preserved and unlocked:
        decision = 'RISK_REGIME_REPRESENTATION_ADDS_PATH_INFORMATION'
    elif mfe_preserved:
        decision = 'MFE_PRESERVED_BUT_PATH_RISK_NOT_UNLOCKED'
    else:
        decision = 'RISK_REGIME_REPRESENTATION_NOT_JUSTIFIED'

    out = {
        'schema': 'public_compute.semiconductor_risk_regime_representation.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_parent': {'pr': 34, 'head': '3df70a0afc4286dc3da8d190aa1b972714672723'},
        'development_universe': list(base.TRAIN),
        'external_panels_loaded': False,
        'common_cutoff': cutoff.isoformat(),
        'common_calendar_rows': len(cal),
        'control_features': list(base.FULL),
        'added_information_families': {
            'market_risk': MARKET_RISK,
            'cross_section_risk': CROSS_SECTION_RISK,
            'own_risk': OWN_RISK,
        },
        'learner': 'exact fixed shallow HistGradientBoostingRegressor from PR31/PR34; no sweep',
        'targets': list(TARGETS),
        'results': results,
        'comparisons_vs_control': comparisons,
        'gate': {
            'full_mfe_preserved_or_improved': mfe_preserved,
            'previously_failed_targets_unlocked': unlocked,
            'only_full_arm_can_authorize_next_architecture': True,
        },
        'decision': decision,
        'family_ablations_are_diagnostic_only': True,
        'policy_or_trading_utility_defined': False,
        'next_boundary': 'only RISK_REGIME_REPRESENTATION_ADDS_PATH_INFORMATION justifies a frozen multi-head risk/duration child; otherwise do not tune this representation post hoc',
        'research_only': True,
        'promotion_authority': False,
        'runtime_mutation': False,
        'broker_action': False,
        'live_trading_change': False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + '\n')
    print('SEMICONDUCTOR_RISK_REGIME_REPRESENTATION=' + json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()
