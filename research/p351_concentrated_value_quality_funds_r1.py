from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SYMS=['QVAL','IWB','IVAL','IEFA','SPY','QQQ']; START='2014-10-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS]; r=px.resample('ME').last().pct_change()
def net_endpoint(s):
 x=s.dropna().copy(); x.iloc[0]-=COST_BPS/10000; x.iloc[-1]-=COST_BPS/10000; return x
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
specs={'QVAL':'IWB','IVAL':'IEFA'}; reps={}
for fund,bench in specs.items():
 res={}
 for name,start in {'2015_plus':'2015-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01'}.items():
  q=r.loc[start:,[fund,bench,'SPY','QQQ']].dropna(); a,b,sp,nq=[stats(net_endpoint(q[c])) for c in [fund,bench,'SPY','QQQ']]; res[name]={'fund':a,'matched':b,'spy':sp,'qqq_context':nq,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_gap_cagr':a['cagr']-sp['cagr'],'qqq_gap_cagr':a['cagr']-nq['cagr']}
 z=r.loc['2015-01-01':,[fund,bench]].dropna(); folds=[stats(net_endpoint(f[fund]))['cagr']-stats(net_endpoint(f[bench]))['cagr'] for f in np.array_split(z,5)]; passed=len(z)>=120 and all(v['matched_excess_cagr']>0 for v in res.values()) and sum(v>0 for v in folds)>=3
 reps[fund]={'benchmark':bench,'months_available':int(len(z)),'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(v>0 for v in folds),'passes':passed}
family_pass=all(v['passes'] for v in reps.values()); decision='P351_CONCENTRATED_VALUE_QUALITY_FAMILY_SUPPORTED' if family_pass else 'P351_CONCENTRATED_VALUE_QUALITY_FAMILY_NOT_SUPPORTED'
out={'schema':'research.p351_concentrated_value_quality_funds_r1','parent':'P351','claim':'Prospectively frozen cross-geography concentrated value-quality fund discriminator: QVAL versus IWB in the US and IVAL versus IEFA ex-US. Buy/hold only, 10bp entry plus 10bp terminal friction, fixed 2015+/2018+/2020+ windows and five chronology folds. No fund, geography, valuation metric, quality screen, timing, weight, date, or cost search.','cost_bps_each_endpoint':COST_BPS,'representations':reps,'decision_rule':'Support the broad concentrated value-quality fund family only if BOTH geography implementations have >=120 months, positive after-cost matched excess in every fixed window, and >=3/5 positive chronology folds. Failure preserves any passing representation but rejects broad-family support without rescue.','decision':decision,'limitations':['fund methodologies share a systematic value-with-quality philosophy but invest in different geographies','adjusted prices include fund expenses/distributions but not investor taxes','SPY/QQQ are opportunity context, not ex-US matched controls','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p351_concentrated_value_quality_funds_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))