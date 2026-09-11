from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
OUT=Path('research/artifacts/p521_yield_curve_size_selection_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
WINDOWS={'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2010_2013':('2010-01-04','2013-12-31'),'2014_2017':('2014-01-02','2017-12-29'),'2018_2021':('2018-01-02','2021-12-31'),'2022_plus':('2022-01-03',None)}
px=yf.download(['SPY','IWM'],start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
close=(px['Close'] if isinstance(px.columns,pd.MultiIndex) else px)[['SPY','IWM']].resample('ME').last().dropna()
yc=pd.read_csv('https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y'); dc='DATE' if 'DATE' in yc.columns else ('observation_date' if 'observation_date' in yc.columns else yc.columns[0]); yc[dc]=pd.to_datetime(yc[dc]); yc['T10Y2Y']=pd.to_numeric(yc['T10Y2Y'],errors='coerce'); yc=yc.dropna().set_index(dc)['T10Y2Y'].resample('ME').last()
# Fixed economic claim: positive 10y-2y slope favors small caps; inversion favors large caps. Completed month, one-month lag.
sig=(yc>0).astype(float).shift(1); r=close.pct_change(fill_method=None); f=r.join(sig.rename('small'),how='inner').dropna(); f['strategy']=f['small']*f['IWM']+(1-f['small'])*f['SPY']; f['switch']=f['small'].diff().abs().fillna(0); f['strategy_net']=f['strategy']-f['switch']*COST

def stats(start,end=None):
 x=f.loc[f.index>=pd.Timestamp(start)]; x=x if end is None else x.loc[x.index<=pd.Timestamp(end)]; w=float(x['small'].mean()); x=x.copy(); x['matched']=w*x['IWM']+(1-w)*x['SPY']
 def perf(c):
  rr=x[c].to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/12; peak=np.maximum.accumulate(wealth); dd=wealth/peak-1; return {'cagr':float(wealth[-1]**(1/yrs)-1),'max_drawdown':float(dd.min())}
 ps,pm,pp=perf('strategy_net'),perf('matched'),perf('SPY'); return {'months':len(x),'mean_small_weight':w,'strategy':ps,'matched':pm,'spy':pp,'excess_vs_matched_cagr':ps['cagr']-pm['cagr'],'excess_vs_spy_cagr':ps['cagr']-pp['cagr'],'drawdown_improvement_vs_spy':ps['max_drawdown']-pp['max_drawdown']}
w={k:stats(v) for k,v in WINDOWS.items()}; b={k:stats(a,z) for k,(a,z) in BLOCKS.items()}; s={'positive_vs_matched_windows':sum(v['excess_vs_matched_cagr']>0 for v in w.values()),'positive_vs_spy_windows':sum(v['excess_vs_spy_cagr']>0 for v in w.values()),'positive_vs_matched_blocks':sum(v['excess_vs_matched_cagr']>0 for v in b.values())}; ok=s['positive_vs_matched_windows']==3 and s['positive_vs_spy_windows']>=2 and s['positive_vs_matched_blocks']>=3; d='YIELD_CURVE_SIZE_ALPHA_SUPPORTED' if ok else 'YIELD_CURVE_SIZE_ALPHA_NOT_SUPPORTED'; out={'schema':'research.p521_yield_curve_size_selection_r1.v1','workload_id':'P521_YIELD_CURVE_SIZE_SELECTION_R1','parent':'YIELD_CURVE_CROSS_SECTIONAL_SIZE','claim':'A causal yield-curve sign state can add after-cost value by selecting small-cap IWM versus large-cap SPY beyond a matched static size exposure.','contract':{'signal':'IWM iff completed-month T10Y2Y > 0, else SPY; one-month lag','cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive vs matched 3/3, positive vs SPY >=2/3, positive vs matched >=3/4 blocks','no_threshold_lag_asset_window_cost_or_weight_search':True},'windows':w,'blocks':b,'summary':s,'decision':d,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':d,'summary':s,'windows':{k:{'vs_matched_pp':round(v['excess_vs_matched_cagr']*100,3),'vs_spy_pp':round(v['excess_vs_spy_cagr']*100,3),'small':round(v['mean_small_weight'],3)} for k,v in w.items()},'blocks':{k:round(v['excess_vs_matched_cagr']*100,3) for k,v in b.items()}},sort_keys=True))