from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
OUT=Path('research/artifacts/p522_real_yield_gold_regime_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
WINDOWS={'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2010_2013':('2010-01-04','2013-12-31'),'2014_2017':('2014-01-02','2017-12-29'),'2018_2021':('2018-01-02','2021-12-31'),'2022_plus':('2022-01-03',None)}
px=yf.download(['SPY','GLD'],start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
close=(px['Close'] if isinstance(px.columns,pd.MultiIndex) else px)[['SPY','GLD']].resample('ME').last().dropna()
ry=pd.read_csv('https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10'); dc='DATE' if 'DATE' in ry.columns else ('observation_date' if 'observation_date' in ry.columns else ry.columns[0]); ry[dc]=pd.to_datetime(ry[dc]); ry['DFII10']=pd.to_numeric(ry['DFII10'],errors='coerce'); ry=ry.dropna().set_index(dc)['DFII10'].resample('ME').last()
# Fixed state: non-positive completed-month 10y real yield -> GLD next month, positive -> SPY. No threshold search.
sig=(ry<=0).astype(float).shift(1); r=close.pct_change(fill_method=None); f=r.join(sig.rename('gold'),how='inner').dropna(); f['strategy']=f['gold']*f['GLD']+(1-f['gold'])*f['SPY']; f['switch']=f['gold'].diff().abs().fillna(0); f['strategy_net']=f['strategy']-f['switch']*COST

def stats(start,end=None):
 x=f.loc[f.index>=pd.Timestamp(start)]; x=x if end is None else x.loc[x.index<=pd.Timestamp(end)]; w=float(x['gold'].mean()); x=x.copy(); x['matched']=w*x['GLD']+(1-w)*x['SPY']
 def perf(c):
  rr=x[c].to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/12; peak=np.maximum.accumulate(wealth); dd=wealth/peak-1; return {'cagr':float(wealth[-1]**(1/yrs)-1),'max_drawdown':float(dd.min())}
 ps,pm,pp=perf('strategy_net'),perf('matched'),perf('SPY'); return {'months':len(x),'mean_gold_weight':w,'strategy':ps,'matched':pm,'spy':pp,'excess_vs_matched_cagr':ps['cagr']-pm['cagr'],'excess_vs_spy_cagr':ps['cagr']-pp['cagr'],'drawdown_improvement_vs_spy':ps['max_drawdown']-pp['max_drawdown']}
w={k:stats(v) for k,v in WINDOWS.items()}; b={k:stats(a,z) for k,(a,z) in BLOCKS.items()}; s={'positive_vs_matched_windows':sum(v['excess_vs_matched_cagr']>0 for v in w.values()),'positive_vs_spy_windows':sum(v['excess_vs_spy_cagr']>0 for v in w.values()),'positive_vs_matched_blocks':sum(v['excess_vs_matched_cagr']>0 for v in b.values()),'drawdown_improved_windows':sum(v['drawdown_improvement_vs_spy']>0 for v in w.values())}; ok=s['positive_vs_matched_windows']==3 and s['positive_vs_spy_windows']>=2 and s['positive_vs_matched_blocks']>=3 and s['drawdown_improved_windows']>=2; d='REAL_YIELD_GOLD_ALPHA_SUPPORTED' if ok else 'REAL_YIELD_GOLD_ALPHA_NOT_SUPPORTED'; out={'schema':'research.p522_real_yield_gold_regime_r1.v1','workload_id':'P522_REAL_YIELD_GOLD_REGIME_R1','parent':'REAL_YIELD_PRECIOUS_METAL_STATE','claim':'A causal real-yield sign state can add after-cost value by selecting GLD versus SPY beyond a matched static gold exposure.','contract':{'signal':'GLD iff completed-month DFII10 <= 0, else SPY; one-month lag','cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive vs matched 3/3, positive vs SPY >=2/3, positive vs matched >=3/4 blocks, drawdown improved >=2/3','no_threshold_lag_asset_window_cost_or_weight_search':True},'windows':w,'blocks':b,'summary':s,'decision':d,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':d,'summary':s,'windows':{k:{'vs_matched_pp':round(v['excess_vs_matched_cagr']*100,3),'vs_spy_pp':round(v['excess_vs_spy_cagr']*100,3),'dd_pp':round(v['drawdown_improvement_vs_spy']*100,3),'gold':round(v['mean_gold_weight'],3)} for k,v in w.items()},'blocks':{k:round(v['excess_vs_matched_cagr']*100,3) for k,v in b.items()}},sort_keys=True))