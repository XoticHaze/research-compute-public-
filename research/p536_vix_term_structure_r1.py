from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
OUT=Path('research/artifacts/p536_vix_term_structure_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
WINDOWS={'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2010_2013':('2010-01-04','2013-12-31'),'2014_2017':('2014-01-02','2017-12-29'),'2018_2021':('2018-01-02','2021-12-31'),'2022_plus':('2022-01-03',None)}
px=yf.download(['SPY','^VIX','^VIX3M'],start='2009-01-01',end='2026-09-12',auto_adjust=True,progress=False,threads=False)
close=(px['Close'] if isinstance(px.columns,pd.MultiIndex) else px)[['SPY','^VIX','^VIX3M']].dropna(); r=close['SPY'].pct_change(fill_method=None)
# Causal prior-close term structure: normal upward slope when 30d VIX < 3m VIX.
exp=(close['^VIX'].shift(1)<close['^VIX3M'].shift(1)).astype(float).reindex(r.index).fillna(0.0)
turn=exp.diff().abs().fillna(exp.abs()); strat=exp*r-turn*COST
f=pd.DataFrame({'strategy':strat,'SPY':r,'exposure':exp,'turnover':turn}).dropna()
def perf(s):
 a=s.to_numpy(); w=np.cumprod(1+a); yrs=len(a)/252; peak=np.maximum.accumulate(w); dd=w/peak-1; vol=float(np.std(a,ddof=1)*np.sqrt(252)); return {'cagr':float(w[-1]**(1/yrs)-1),'max_drawdown':float(dd.min()),'annualized_vol':vol}
def stats(a,z=None):
 x=f.loc[f.index>=pd.Timestamp(a)].copy(); x=x if z is None else x.loc[x.index<=pd.Timestamp(z)].copy(); ae=float(x.exposure.mean()); ctl=ae*x.SPY; ps,pc,pp=perf(x.strategy),perf(ctl),perf(x.SPY); X=np.column_stack([np.ones(len(x)),x.SPY.to_numpy()]); b=np.linalg.lstsq(X,x.strategy.to_numpy(),rcond=None)[0]; return {'days':len(x),'strategy':ps,'exposure_matched_spy':pc,'spy':pp,'excess_vs_exposure_matched_spy_cagr':ps['cagr']-pc['cagr'],'annualized_beta_adjusted_alpha':float(b[0]*252),'spy_beta':float(b[1]),'average_exposure':ae,'mean_daily_turnover':float(x.turnover.mean())}
w={k:stats(v) for k,v in WINDOWS.items()}; b={k:stats(a,z) for k,(a,z) in BLOCKS.items()}; s={'positive_matched_excess_windows':sum(v['excess_vs_exposure_matched_spy_cagr']>0 for v in w.values()),'positive_alpha_windows':sum(v['annualized_beta_adjusted_alpha']>0 for v in w.values()),'positive_matched_excess_blocks':sum(v['excess_vs_exposure_matched_spy_cagr']>0 for v in b.values()),'positive_alpha_blocks':sum(v['annualized_beta_adjusted_alpha']>0 for v in b.values())}; ok=s['positive_matched_excess_windows']==3 and s['positive_alpha_windows']==3 and s['positive_matched_excess_blocks']>=3 and s['positive_alpha_blocks']>=3; d='VIX_TERM_STRUCTURE_TIMING_ALPHA_SUPPORTED' if ok else 'VIX_TERM_STRUCTURE_TIMING_ALPHA_NOT_SUPPORTED'; out={'schema':'research.p536_vix_term_structure_r1.v1','workload_id':'P536_VIX_TERM_STRUCTURE_R1','parent':'OPTIONS_TERM_STRUCTURE_RISK_PREMIUM','claim':'A frozen causal SPY/cash rule using the prior-close VIX versus VIX3M term-structure slope can create durable after-cost alpha beyond static SPY exposure matched to capital usage.','contract':{'signal':'long SPY when prior close VIX < prior close VIX3M; otherwise cash','cost_bps_per_exposure_turnover':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive matched-control CAGR excess and beta-adjusted alpha 3/3 windows and >=3/4 blocks','no_threshold_window_asset_cost_or_weight_search':True},'windows':w,'blocks':b,'summary':s,'decision':d,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':d,'summary':s,'windows':{k:{'cagr_pct':round(v['strategy']['cagr']*100,3),'matched_excess_pp':round(v['excess_vs_exposure_matched_spy_cagr']*100,3),'alpha_pp':round(v['annualized_beta_adjusted_alpha']*100,3),'avg_exp':round(v['average_exposure'],3)} for k,v in w.items()},'blocks':{k:{'matched_excess_pp':round(v['excess_vs_exposure_matched_spy_cagr']*100,3),'alpha_pp':round(v['annualized_beta_adjusted_alpha']*100,3)} for k,v in b.items()}},sort_keys=True))
