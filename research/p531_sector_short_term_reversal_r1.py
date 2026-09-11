from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path('research/artifacts/p531_sector_short_term_reversal_r1.json')
OUT.parent.mkdir(parents=True, exist_ok=True)
SECTORS = ['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
COST = 0.0010
WINDOWS = {'2005_plus':'2005-01-03','2010_plus':'2010-01-04','2015_plus':'2015-01-02'}
BLOCKS = {
    '2005_2009':('2005-01-03','2009-12-31'),
    '2010_2014':('2010-01-04','2014-12-31'),
    '2015_2019':('2015-01-02','2019-12-31'),
    '2020_plus':('2020-01-02',None),
}

px = yf.download(SECTORS + ['SPY'], start='2003-01-01', end='2026-09-11', auto_adjust=True, progress=False, threads=False)
close = (px['Close'] if isinstance(px.columns, pd.MultiIndex) else px)[SECTORS + ['SPY']].resample('ME').last().dropna()
r = close.pct_change(fill_method=None).dropna()
# Frozen mechanism: each month hold equal-weight the three sectors with the worst immediately-prior completed-month return.
prior = r[SECTORS].shift(1)
ranks = prior.rank(axis=1, method='first', ascending=True)
w = (ranks <= 3).astype(float) / 3.0
turnover = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)) / 2.0
strategy_gross = (w * r[SECTORS]).sum(axis=1)
strategy_net = strategy_gross - turnover * COST
sector_ew = r[SECTORS].mean(axis=1)
f = pd.DataFrame({'strategy_net': strategy_net, 'sector_ew': sector_ew, 'SPY': r['SPY'], 'turnover': turnover}).dropna()

def perf(x: pd.Series) -> dict:
    rr = x.to_numpy()
    wealth = np.cumprod(1.0 + rr)
    yrs = len(rr) / 12.0
    peak = np.maximum.accumulate(wealth)
    dd = wealth / peak - 1.0
    return {'cagr': float(wealth[-1] ** (1.0 / yrs) - 1.0), 'max_drawdown': float(dd.min())}

def stats(start: str, end: str | None = None) -> dict:
    x = f.loc[f.index >= pd.Timestamp(start)]
    if end is not None:
        x = x.loc[x.index <= pd.Timestamp(end)]
    ps, pe, pp = perf(x['strategy_net']), perf(x['sector_ew']), perf(x['SPY'])
    return {
        'months': int(len(x)),
        'strategy': ps,
        'sector_equal_weight': pe,
        'spy': pp,
        'excess_vs_sector_ew_cagr': ps['cagr'] - pe['cagr'],
        'excess_vs_spy_cagr': ps['cagr'] - pp['cagr'],
        'drawdown_improvement_vs_spy': ps['max_drawdown'] - pp['max_drawdown'],
        'mean_monthly_turnover': float(x['turnover'].mean()),
    }

windows = {k: stats(v) for k, v in WINDOWS.items()}
blocks = {k: stats(a, z) for k, (a, z) in BLOCKS.items()}
summary = {
    'positive_vs_sector_ew_windows': sum(v['excess_vs_sector_ew_cagr'] > 0 for v in windows.values()),
    'positive_vs_spy_windows': sum(v['excess_vs_spy_cagr'] > 0 for v in windows.values()),
    'positive_vs_sector_ew_blocks': sum(v['excess_vs_sector_ew_cagr'] > 0 for v in blocks.values()),
    'drawdown_improved_windows': sum(v['drawdown_improvement_vs_spy'] > 0 for v in windows.values()),
}
supported = (
    summary['positive_vs_sector_ew_windows'] == 3
    and summary['positive_vs_spy_windows'] >= 2
    and summary['positive_vs_sector_ew_blocks'] >= 3
)
decision = 'SECTOR_SHORT_TERM_REVERSAL_ALPHA_SUPPORTED' if supported else 'SECTOR_SHORT_TERM_REVERSAL_ALPHA_NOT_SUPPORTED'
out = {
    'schema': 'research.p531_sector_short_term_reversal_r1.v1',
    'workload_id': 'P531_SECTOR_SHORT_TERM_REVERSAL_R1',
    'parent': 'CROSS_SECTIONAL_SECTOR_REVERSAL',
    'claim': 'A causal one-month cross-sectional sector reversal allocator can add after-cost excess return beyond static sector equal weight and SPY.',
    'contract': {
        'universe': SECTORS,
        'signal': 'equal-weight bottom 3 sectors by immediately prior completed-month total return',
        'cost_bps_per_one_way_turnover': 10,
        'windows': WINDOWS,
        'blocks': BLOCKS,
        'support_rule': 'positive vs sector equal weight 3/3 windows, positive vs SPY >=2/3 windows, positive vs sector equal weight >=3/4 chronology blocks',
        'no_lookback_topk_universe_window_cost_weight_or_threshold_search': True,
    },
    'windows': windows,
    'blocks': blocks,
    'summary': summary,
    'decision': decision,
    'boundaries': {'scientific_authority': True, 'portfolio_ranking': False, 'allocation_authority': False, 'runtime': False, 'broker': False, 'live_trading': False},
}
OUT.write_text(json.dumps(out, indent=2, sort_keys=True))
print(json.dumps({
    'decision': decision,
    'summary': summary,
    'windows': {k: {'vs_sector_ew_pp': round(v['excess_vs_sector_ew_cagr']*100,3), 'vs_spy_pp': round(v['excess_vs_spy_cagr']*100,3), 'dd_pp': round(v['drawdown_improvement_vs_spy']*100,3), 'turnover': round(v['mean_monthly_turnover'],3)} for k,v in windows.items()},
    'blocks_vs_sector_ew_pp': {k: round(v['excess_vs_sector_ew_cagr']*100,3) for k,v in blocks.items()},
}, sort_keys=True))