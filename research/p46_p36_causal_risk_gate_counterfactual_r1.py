from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_p36_causal_temporal_holdout_r1 as causal


def cagr(x):
    x = pd.Series(x, dtype=float).dropna()
    return float((1 + x).prod() ** (12 / len(x)) - 1)


def sharpe(x):
    x = pd.Series(x, dtype=float).dropna()
    return float(np.sqrt(12) * x.mean() / x.std(ddof=1)) if len(x) > 1 and x.std(ddof=1) > 0 else 0.0


def maxdd(x):
    eq = (1 + pd.Series(x, dtype=float).fillna(0)).cumprod()
    return float((eq / eq.cummax() - 1).min())


def folds(a, b):
    pos = 0
    for ids in np.array_split(np.arange(len(a)), min(5, len(a))):
        pos += cagr(a.iloc[ids]) - cagr(b.iloc[ids]) > 0
    return int(pos)


def main():
    close = base.load(causal.ALL)
    month_start = pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close = close.loc[close.index < month_start]
    monthly_spy = close['SPY'].resample('ME').last()
    trend = monthly_spy / monthly_spy.rolling(10, min_periods=10).mean() - 1
    tests = {}
    for bp in (25, 50, 100):
        f = causal.build(close, bp, 1).copy()
        f['signal_month'] = pd.DatetimeIndex(f.index).to_period('M').to_timestamp('M') - pd.offsets.MonthEnd(2)
        f['gate'] = [1.0 if (not pd.isna(trend.asof(d)) and trend.asof(d) >= 0) else 0.0 for d in f['signal_month']]
        prev = f['gate'].shift(1).fillna(0.0)
        gate_turn = (f['gate'] - prev).abs()
        gate_cost = gate_turn * bp / 10000.0
        f['gated_candidate'] = f['gate'] * f['candidate'] - gate_cost
        f['gated_matched'] = f['gate'] * f['matched'] - gate_cost
        f['gated_qqq'] = f['gate'] * f['qqq'] - gate_cost
        t = {
            'months': int(len(f)),
            'risk_on_fraction': float(f['gate'].mean()),
            'gate_transitions': int((gate_turn > 0).sum()),
            'gated_candidate_cagr': cagr(f['gated_candidate']),
            'gated_matched_cagr': cagr(f['gated_matched']),
            'gated_qqq_cagr': cagr(f['gated_qqq']),
            'all_in_candidate_cagr': cagr(f['candidate']),
            'all_in_qqq_cagr': cagr(f['qqq']),
            'excess_vs_gated_matched_cagr': cagr(f['gated_candidate']) - cagr(f['gated_matched']),
            'excess_vs_gated_qqq_cagr': cagr(f['gated_candidate']) - cagr(f['gated_qqq']),
            'excess_vs_all_in_qqq_cagr': cagr(f['gated_candidate']) - cagr(f['qqq']),
            'gated_candidate_sharpe': sharpe(f['gated_candidate']),
            'all_in_candidate_sharpe': sharpe(f['candidate']),
            'gated_candidate_max_drawdown': maxdd(f['gated_candidate']),
            'all_in_candidate_max_drawdown': maxdd(f['candidate']),
            'positive_folds_vs_gated_matched': folds(f['gated_candidate'], f['gated_matched']),
            'positive_folds_vs_gated_qqq': folds(f['gated_candidate'], f['gated_qqq']),
        }
        tests[str(bp)] = t
    t50 = tests['50']
    if (t50['excess_vs_gated_matched_cagr'] > 0 and t50['positive_folds_vs_gated_matched'] >= 3 and
        t50['gated_candidate_max_drawdown'] > t50['all_in_candidate_max_drawdown']):
        state = 'CAUSAL_RISK_GATE_IMPROVES_CAPITAL_EFFICIENCY_REQUIRES_INDEPENDENT_HOLDOUT'
    else:
        state = 'CAUSAL_RISK_GATE_NOT_SUPPORTED'
    out = {
        'schema': 'research.p46_p36_causal_risk_gate_counterfactual_r1',
        'parents': ['P46', 'P36'],
        'scientific_contract': {
            'base_implementation': 'fixed one-trading-day delayed entry',
            'counterfactual_gate': 'cash when completed signal-month SPY close is below trailing 10-month SMA; otherwise unchanged candidate',
            'gate_threshold_predeclared_from_prior_regime_attribution': True,
            'costs_bps': [25, 50, 100],
            'comparators': ['same gate applied to exact matched blend', 'same gate applied to QQQ', 'all-in QQQ'],
            'gate_transition_cost_charged': True,
            'no_factor_weight_lookback_topk_cadence_or_threshold_tuning': True,
            'research_counterfactual_only': True,
        },
        'source': {'normalized_complete_month_price_panel_sha256': base.source_hash(close)},
        'tests': tests,
        'decision': state,
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p46_p36_causal_risk_gate_counterfactual_r1.json').write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()
