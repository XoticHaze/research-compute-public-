from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path('research/artifacts/p532_vol_managed_spy_r1.json')
OUT.parent.mkdir(parents=True, exist_ok=True)
COST = 0.0010
TARGET_VOL = 0.10
MAX_EXPOSURE = 1.50
WINDOWS = {'2005_plus':'2005-01-03','2010_plus':'2010-01-04','2015_plus':'2015-01-02'}
BLOCKS = {
    '2005_2009':('2005-01-03','2009-12-31'),
    '2010_2014':('2010-01-04','2014-12-31'),
    '2015_2019':('2015-01-02','2019-12-31'),
    '2020_plus':('2020-01-02',None),
}

px = yf.download('SPY', start='2003-01-01', end='2026-09-11', auto_adjust=True, progress=False, threads=False)
close = px['Close'] if 'Close' in px else px
if isinstance(close, pd.DataFrame): close = close.iloc[:,0]
daily = close.pct_change(fill_method=None).dropna()
# Completed-month realized vol only; exposure is applied to the following month.
monthly_ret = close.resample('ME').last().pct_change(fill_method=None)
monthly_rv = daily.groupby(daily.index.to_period('M')).std() * np.sqrt(252.0)
monthly_rv.index = monthly_rv.index.to_timestamp('M')
exposure = (TARGET_VOL / monthly_rv).clip(lower=0.0, upper=MAX_EXPOSURE).shift(1)
f = pd.concat([monthly_ret.rename('SPY'), exposure.rename('exposure')], axis=1).dropna()
f['turnover'] = f['exposure'].diff().abs().fillna(f['exposure'])
f['strategy_net'] = f['exposure'] * f['SPY'] - f['turnover'] * COST

def perf(x: pd.Series) -> dict:
    rr = x.to_numpy(); wealth = np.cumprod(1.0 + rr); yrs = len(rr)/12.0
    peak = np.maximum.accumulate(wealth); dd = wealth/peak - 1.0
    ann_vol = float(np.std(rr, ddof=1) * np.sqrt(12.0)) if len(rr) > 1 else 0.0
    ann_ret = float(np.mean(rr) * 12.0)
    return {'cagr': float(wealth[-1]**(1.0/yrs)-1.0), 'max_drawdown': float(dd.min()), 'annualized_vol': ann_vol, 'simple_sharpe': ann_ret/ann_vol if ann_vol > 0 else None}

def stats(start: str, end: str | None = None) -> dict:
    x = f.loc[f.index >= pd.Timestamp(start)]
    if end is not None: x = x.loc[x.index <= pd.Timestamp(end)]
    avg_exp = float(x['exposure'].mean())
    x = x.copy(); x['matched_static'] = avg_exp * x['SPY']
    ps, pm, pp = perf(x['strategy_net']), perf(x['matched_static']), perf(x['SPY'])
    return {
        'months': int(len(x)), 'mean_exposure': avg_exp, 'mean_monthly_turnover': float(x['turnover'].mean()),
        'strategy': ps, 'matched_static_exposure': pm, 'spy': pp,
        'excess_vs_matched_cagr': ps['cagr']-pm['cagr'],
        'excess_vs_spy_cagr': ps['cagr']-pp['cagr'],
        'drawdown_improvement_vs_spy': ps['max_drawdown']-pp['max_drawdown'],
        'sharpe_improvement_vs_matched': (ps['simple_sharpe']-pm['simple_sharpe']) if ps['simple_sharpe'] is not None and pm['simple_sharpe'] is not None else None,
    }

windows = {k:stats(v) for k,v in WINDOWS.items()}; blocks = {k:stats(a,z) for k,(a,z) in BLOCKS.items()}
summary = {
    'positive_vs_matched_windows': sum(v['excess_vs_matched_cagr'] > 0 for v in windows.values()),
    'positive_vs_matched_blocks': sum(v['excess_vs_matched_cagr'] > 0 for v in blocks.values()),
    'sharpe_improved_windows': sum((v['sharpe_improvement_vs_matched'] or -999) > 0 for v in windows.values()),
    'drawdown_improved_windows': sum(v['drawdown_improvement_vs_spy'] > 0 for v in windows.values()),
}
supported = summary['positive_vs_matched_windows'] == 3 and summary['positive_vs_matched_blocks'] >= 3 and summary['sharpe_improved_windows'] == 3
decision = 'VOL_MANAGED_EQUITY_ALPHA_SUPPORTED' if supported else 'VOL_MANAGED_EQUITY_ALPHA_NOT_SUPPORTED'
out = {
    'schema':'research.p532_vol_managed_spy_r1.v1','workload_id':'P532_VOL_MANAGED_SPY_R1','parent':'VOLATILITY_MANAGED_EQUITY',
    'claim':'A causal inverse-realized-vol SPY exposure rule can add after-cost timing alpha beyond a static SPY exposure matched to the strategy average beta.',
    'contract':{'asset':'SPY','realized_vol':'completed-calendar-month daily return standard deviation annualized','target_vol':TARGET_VOL,'max_exposure':MAX_EXPOSURE,'signal_lag':'one month','cost_bps_per_exposure_turnover':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive excess vs exposure-matched static SPY 3/3 windows and >=3/4 blocks, Sharpe improvement 3/3 windows','no_target_cap_window_cost_or_vol_estimator_search':True},
    'windows':windows,'blocks':blocks,'summary':summary,'decision':decision,
    'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True))
print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{'vs_matched_pp':round(v['excess_vs_matched_cagr']*100,3),'vs_spy_pp':round(v['excess_vs_spy_cagr']*100,3),'dd_pp':round(v['drawdown_improvement_vs_spy']*100,3),'mean_exp':round(v['mean_exposure'],3),'sharpe_delta':None if v['sharpe_improvement_vs_matched'] is None else round(v['sharpe_improvement_vs_matched'],3)} for k,v in windows.items()},'blocks_vs_matched_pp':{k:round(v['excess_vs_matched_cagr']*100,3) for k,v in blocks.items()}},sort_keys=True))