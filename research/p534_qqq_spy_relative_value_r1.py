from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p534_qqq_spy_relative_value_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
LOOKBACK=60; ENTRY_Z=2.0; COST=.0010
WINDOWS={'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2010_2013':('2010-01-04','2013-12-31'),'2014_2017':('2014-01-02','2017-12-29'),'2018_2021':('2018-01-02','2021-12-31'),'2022_plus':('2022-01-03',None)}
px=yf.download(['QQQ','SPY'],start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
close=(px['Close'] if isinstance(px.columns,pd.MultiIndex) else px)[['QQQ','SPY']].dropna(); r=close.pct_change(fill_method=None).dropna()
ratio=np.log(close['QQQ']/close['SPY']); mu=ratio.rolling(LOOKBACK).mean(); sd=ratio.rolling(LOOKBACK).std(); z=((ratio-mu)/sd).shift(1).reindex(r.index)
pos=[]; state=0
for v in z:
    if np.isnan(v): state=0
    elif state==0:
        if v>=ENTRY_Z: state=-1
        elif v<=-ENTRY_Z: state=1
    elif state==1 and v>=0: state=0
    elif state==-1 and v<=0: state=0
    pos.append(state)
pdpos=pd.Series(pos,index=r.index,dtype=float)
wq=.5*pdpos; ws=-.5*pdpos
turnover=(wq.diff().abs()+ws.diff().abs()).fillna(wq.abs()+ws.abs())
strategy=wq*r['QQQ']+ws*r['SPY']-turnover*COST
f=pd.DataFrame({'strategy':strategy,'SPY':r['SPY'],'position':pdpos,'turnover':turnover}).dropna()

def perf(x):
 rr=x.to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/252; peak=np.maximum.accumulate(wealth); dd=wealth/peak-1; av=float(np.std(rr,ddof=1)*np.sqrt(252)) if len(rr)>1 else 0; ar=float(np.mean(rr)*252); return {'cagr':float(wealth[-1]**(1/yrs)-1),'max_drawdown':float(dd.min()),'annualized_vol':av,'simple_sharpe':ar/av if av>0 else None}

def stats(start,end=None):
 x=f.loc[f.index>=pd.Timestamp(start)].copy(); x=x if end is None else x.loc[x.index<=pd.Timestamp(end)].copy(); ps=perf(x['strategy']); pp=perf(x['SPY']); Y=x['strategy'].to_numpy(); X=np.column_stack([np.ones(len(x)),x['SPY'].to_numpy()]); coef=np.linalg.lstsq(X,Y,rcond=None)[0]; return {'days':len(x),'strategy':ps,'spy':pp,'annualized_beta_adjusted_alpha':float(coef[0]*252),'spy_beta':float(coef[1]),'active_fraction':float((x['position']!=0).mean()),'mean_daily_turnover':float(x['turnover'].mean())}
w={k:stats(v) for k,v in WINDOWS.items()}; b={k:stats(a,z) for k,(a,z) in BLOCKS.items()}; s={'positive_cagr_windows':sum(v['strategy']['cagr']>0 for v in w.values()),'positive_alpha_windows':sum(v['annualized_beta_adjusted_alpha']>0 for v in w.values()),'positive_cagr_blocks':sum(v['strategy']['cagr']>0 for v in b.values()),'positive_alpha_blocks':sum(v['annualized_beta_adjusted_alpha']>0 for v in b.values())}; ok=s['positive_cagr_windows']==3 and s['positive_alpha_windows']==3 and s['positive_cagr_blocks']>=3 and s['positive_alpha_blocks']>=3; d='QQQ_SPY_RELATIVE_VALUE_ALPHA_SUPPORTED' if ok else 'QQQ_SPY_RELATIVE_VALUE_ALPHA_NOT_SUPPORTED'; out={'schema':'research.p534_qqq_spy_relative_value_r1.v1','workload_id':'P534_QQQ_SPY_RELATIVE_VALUE_R1','parent':'STATISTICAL_RELATIVE_VALUE','claim':'A fixed dollar-neutral QQQ/SPY log-ratio mean-reversion rule can create after-cost return with positive beta-adjusted alpha.','contract':{'pair':['QQQ','SPY'],'lookback_days':LOOKBACK,'entry_abs_z':ENTRY_Z,'exit':'z crosses zero','gross_exposure_when_active':1.0,'cost_bps_per_gross_turnover':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive CAGR and beta-adjusted alpha 3/3 fixed windows and >=3/4 chronology blocks','no_pair_lookback_threshold_exit_window_cost_or_weight_search':True},'windows':w,'blocks':b,'summary':s,'decision':d,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':d,'summary':s,'windows':{k:{'cagr_pct':round(v['strategy']['cagr']*100,3),'alpha_pp':round(v['annualized_beta_adjusted_alpha']*100,3),'beta':round(v['spy_beta'],3),'active':round(v['active_fraction'],3),'maxdd_pct':round(v['strategy']['max_drawdown']*100,3)} for k,v in w.items()},'blocks':{k:{'cagr_pct':round(v['strategy']['cagr']*100,3),'alpha_pp':round(v['annualized_beta_adjusted_alpha']*100,3)} for k,v in b.items()}},sort_keys=True))