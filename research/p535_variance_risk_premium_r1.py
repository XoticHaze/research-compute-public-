from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path('research/artifacts/p535_variance_risk_premium_r1.json')
OUT.parent.mkdir(parents=True, exist_ok=True)
COST = 0.0010
RV_DAYS = 21
WINDOWS = {'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS = {
    '2010_2013':('2010-01-04','2013-12-31'),
    '2014_2017':('2014-01-02','2017-12-29'),
    '2018_2021':('2018-01-02','2021-12-31'),
    '2022_plus':('2022-01-03',None),
}

px = yf.download(['SPY','^VIX'], start='2008-01-01', end='2026-09-12', auto_adjust=True, progress=False, threads=False)
close = (px['Close'] if isinstance(px.columns, pd.MultiIndex) else px)[['SPY','^VIX']].dropna()
spy_r = close['SPY'].pct_change(fill_method=None)
rv = spy_r.rolling(RV_DAYS).std(ddof=1) * np.sqrt(252) * 100.0
# Causal signal: yesterday's VIX-implied vol minus yesterday's trailing realized vol.
vrp = (close['^VIX'] - rv).shift(1)
exposure = (vrp > 0).astype(float).reindex(spy_r.index).fillna(0.0)
turnover = exposure.diff().abs().fillna(exposure.abs())
strategy = exposure * spy_r - turnover * COST
f = pd.DataFrame({'strategy': strategy, 'SPY': spy_r, 'exposure': exposure, 'turnover': turnover, 'vrp': vrp}).dropna()

def perf(x: pd.Series) -> dict:
    rr = x.to_numpy()
    wealth = np.cumprod(1 + rr)
    yrs = len(rr) / 252.0
    peak = np.maximum.accumulate(wealth)
    dd = wealth / peak - 1
    av = float(np.std(rr, ddof=1) * np.sqrt(252)) if len(rr) > 1 else 0.0
    ar = float(np.mean(rr) * 252)
    return {
        'cagr': float(wealth[-1] ** (1 / yrs) - 1),
        'max_drawdown': float(dd.min()),
        'annualized_vol': av,
        'simple_sharpe': ar / av if av > 0 else None,
    }

def stats(start: str, end: str | None = None) -> dict:
    x = f.loc[f.index >= pd.Timestamp(start)].copy()
    if end is not None:
        x = x.loc[x.index <= pd.Timestamp(end)].copy()
    avg_exp = float(x['exposure'].mean())
    control = avg_exp * x['SPY']
    ps = perf(x['strategy'])
    pc = perf(control)
    pp = perf(x['SPY'])
    y = x['strategy'].to_numpy()
    X = np.column_stack([np.ones(len(x)), x['SPY'].to_numpy()])
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    return {
        'days': len(x),
        'strategy': ps,
        'exposure_matched_spy': pc,
        'spy': pp,
        'excess_vs_exposure_matched_spy_cagr': ps['cagr'] - pc['cagr'],
        'annualized_beta_adjusted_alpha': float(coef[0] * 252),
        'spy_beta': float(coef[1]),
        'average_exposure': avg_exp,
        'mean_daily_turnover': float(x['turnover'].mean()),
        'mean_vrp_vol_points': float(x['vrp'].mean()),
    }

windows = {k: stats(v) for k, v in WINDOWS.items()}
blocks = {k: stats(a, z) for k, (a, z) in BLOCKS.items()}
summary = {
    'positive_matched_excess_windows': sum(v['excess_vs_exposure_matched_spy_cagr'] > 0 for v in windows.values()),
    'positive_alpha_windows': sum(v['annualized_beta_adjusted_alpha'] > 0 for v in windows.values()),
    'positive_matched_excess_blocks': sum(v['excess_vs_exposure_matched_spy_cagr'] > 0 for v in blocks.values()),
    'positive_alpha_blocks': sum(v['annualized_beta_adjusted_alpha'] > 0 for v in blocks.values()),
}
ok = (
    summary['positive_matched_excess_windows'] == 3
    and summary['positive_alpha_windows'] == 3
    and summary['positive_matched_excess_blocks'] >= 3
    and summary['positive_alpha_blocks'] >= 3
)
decision = 'VARIANCE_RISK_PREMIUM_TIMING_ALPHA_SUPPORTED' if ok else 'VARIANCE_RISK_PREMIUM_TIMING_ALPHA_NOT_SUPPORTED'
out = {
    'schema': 'research.p535_variance_risk_premium_r1.v1',
    'workload_id': 'P535_VARIANCE_RISK_PREMIUM_R1',
    'parent': 'OPTIONS_IMPLIED_RISK_PREMIUM',
    'claim': 'A frozen causal long-SPY/cash rule based on lagged positive VIX-implied minus trailing-realized volatility can create durable after-cost alpha beyond static SPY exposure matched to its capital usage.',
    'contract': {
        'asset': 'SPY',
        'implied_volatility_source': '^VIX prior close',
        'realized_volatility': '21-trading-day annualized SPY close-to-close volatility',
        'signal': 'long SPY when yesterday VIX minus yesterday trailing realized vol > 0; otherwise cash',
        'cost_bps_per_exposure_turnover': 10,
        'windows': WINDOWS,
        'blocks': BLOCKS,
        'support_rule': 'positive matched-control CAGR excess and beta-adjusted alpha in 3/3 fixed windows and >=3/4 chronology blocks',
        'no_threshold_window_asset_cost_or_weight_search': True,
    },
    'windows': windows,
    'blocks': blocks,
    'summary': summary,
    'decision': decision,
    'boundaries': {
        'scientific_authority': True,
        'portfolio_ranking': False,
        'allocation_authority': False,
        'runtime': False,
        'broker': False,
        'live_trading': False,
    },
}
OUT.write_text(json.dumps(out, indent=2, sort_keys=True))
print(json.dumps({
    'decision': decision,
    'summary': summary,
    'windows': {k: {
        'strategy_cagr_pct': round(v['strategy']['cagr'] * 100, 3),
        'matched_excess_pp': round(v['excess_vs_exposure_matched_spy_cagr'] * 100, 3),
        'alpha_pp': round(v['annualized_beta_adjusted_alpha'] * 100, 3),
        'avg_exposure': round(v['average_exposure'], 3),
        'maxdd_pct': round(v['strategy']['max_drawdown'] * 100, 3),
    } for k, v in windows.items()},
    'blocks': {k: {
        'matched_excess_pp': round(v['excess_vs_exposure_matched_spy_cagr'] * 100, 3),
        'alpha_pp': round(v['annualized_beta_adjusted_alpha'] * 100, 3),
    } for k, v in blocks.items()},
}, sort_keys=True))
