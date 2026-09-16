from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p517_vol_term_structure_regime_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['SPY','BIL','^VIX','^VIX9D']; COST=.0010
WINDOWS={'2013_plus':'2013-01-02','2018_plus':'2018-01-02','2022_plus':'2022-01-03'}
BLOCKS={'2013_2016':('2013-01-02','2016-12-30'),'2017_2020':('2017-01-03','2020-12-31'),'2021_2023':('2021-01-04','2023-12-29'),'2024_plus':('2024-01-02',None)}
raw=yf.download(T,start='2012-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna(how='all')
# Month-end signal uses only completed-month closes. Hold SPY next month when short-horizon implied vol <= 30-day VIX (normal/contango-like state); otherwise BIL.
month=close.resample('ME').last().dropna(subset=['SPY','BIL','^VIX','^VIX9D'])
r=month[['SPY','BIL']].pct_change(fill_method=None)
sig=(month['^VIX9D']<=month['^VIX']).astype(float).shift(1)
frame=pd.DataFrame({'spy':r['SPY'],'bil':r['BIL'],'equity':sig}).dropna()
frame['strategy']=frame['equity']*frame['spy']+(1-frame['equity'])*frame['bil']
frame['switch']=frame['equity'].diff().abs().fillna(0)
frame['strategy_net']=frame['strategy']-frame['switch']*COST


def stats(start,end=None):
    x=frame.loc[frame.index>=pd.Timestamp(start)]
    if end: x=x.loc[x.index<=pd.Timestamp(end)]
    if len(x)<12: raise RuntimeError(f'insufficient rows {start} {end}: {len(x)}')
    w=float(x['equity'].mean())
    x=x.copy(); x['matched']=w*x['spy']+(1-w)*x['bil']
    def perf(col):
        rr=x[col].to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/12
        cagr=float(wealth[-1]**(1/yrs)-1)
        peak=np.maximum.accumulate(wealth); dd=wealth/peak-1
        vol=float(np.std(rr,ddof=1)*np.sqrt(12)); sharpe=float(np.mean(rr)*12/vol) if vol>0 else None
        return {'cagr':cagr,'max_drawdown':float(dd.min()),'annualized_vol':vol,'sharpe':sharpe}
    ps,pm,pp=perf('strategy_net'),perf('matched'),perf('spy')
    return {'months':int(len(x)),'mean_equity_exposure':w,'switches':int((x['switch']>0).sum()),'strategy':ps,'matched_static_exposure':pm,'spy':pp,'excess_vs_matched_cagr':ps['cagr']-pm['cagr'],'excess_vs_spy_cagr':ps['cagr']-pp['cagr'],'drawdown_improvement_vs_spy':ps['max_drawdown']-pp['max_drawdown']}

w={k:stats(v) for k,v in WINDOWS.items()}; b={k:stats(a,z) for k,(a,z) in BLOCKS.items()}
summary={'positive_vs_matched_windows':sum(v['excess_vs_matched_cagr']>0 for v in w.values()),'positive_vs_spy_windows':sum(v['excess_vs_spy_cagr']>0 for v in w.values()),'positive_vs_matched_blocks':sum(v['excess_vs_matched_cagr']>0 for v in b.values()),'drawdown_improved_windows':sum(v['drawdown_improvement_vs_spy']>0 for v in w.values())}
supported=summary['positive_vs_matched_windows']==3 and summary['positive_vs_spy_windows']>=2 and summary['positive_vs_matched_blocks']>=3 and summary['drawdown_improved_windows']==3
decision='VOL_TERM_STRUCTURE_REGIME_ALPHA_SUPPORTED' if supported else 'VOL_TERM_STRUCTURE_REGIME_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p517_vol_term_structure_regime_r1.v1','workload_id':'P517_VOL_TERM_STRUCTURE_REGIME_R1','parent':'VOLATILITY_TERM_STRUCTURE_STATE','claim':'A causal monthly volatility-term-structure state using VIX9D<=VIX to hold SPY next month, otherwise BIL, must add after-cost return beyond an equal-equity-exposure static SPY/BIL control while preserving broad-market opportunity value and improving drawdown.','contract':{'signal':'at completed month-end, equity_on iff VIX9D <= VIX; apply one-month lag','assets':['SPY','BIL'],'switch_cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive CAGR excess vs matched static exposure in 3/3 windows, positive vs SPY in >=2/3 windows, positive vs matched in >=3/4 chronology blocks, and drawdown improvement vs SPY in 3/3 windows','no_signal_threshold_window_asset_cost_or_weight_search':True},'windows':w,'blocks':b,'summary':summary,'decision':decision,'scientific_consequence':'Support only if the fixed volatility term-structure timing rule survives matched capital-exposure, chronology, costs, SPY opportunity cost, and drawdown gates. Otherwise reject this exact macro-volatility architecture without threshold or signal rescue.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{'vs_matched_pp':round(v['excess_vs_matched_cagr']*100,3),'vs_spy_pp':round(v['excess_vs_spy_cagr']*100,3),'dd_improve_pp':round(v['drawdown_improvement_vs_spy']*100,3),'equity':round(v['mean_equity_exposure'],3)} for k,v in w.items()},'blocks':{k:round(v['excess_vs_matched_cagr']*100,3) for k,v in b.items()}},sort_keys=True))
