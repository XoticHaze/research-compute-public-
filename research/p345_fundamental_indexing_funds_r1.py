from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SYMS=['PRF','FNDX','IWB','VTI','SPY','QQQ']; START='2005-12-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS]; r=px.resample('ME').last().pct_change()
def net_endpoint(s):
 x=s.dropna().copy(); x.iloc[0]-=COST_BPS/10000; x.iloc[-1]-=COST_BPS/10000; return x
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
specs={'PRF':{'bench':'IWB','windows':{'2007_plus':'2007-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}},'FNDX':{'bench':'VTI','windows':{'2014_plus':'2014-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01'}}}; reps={}
for fund,spec in specs.items():
 res={}
 for name,start in spec['windows'].items():
  q=r.loc[start:,[fund,spec['bench'],'SPY','QQQ']].dropna(); a,b,sp,nq=[stats(net_endpoint(q[c])) for c in [fund,spec['bench'],'SPY','QQQ']]; res[name]={'fund':a,'matched':b,'spy':sp,'qqq_context':nq,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_gap_cagr':a['cagr']-sp['cagr'],'qqq_gap_cagr':a['cagr']-nq['cagr']}
 first=list(spec['windows'].values())[0]; z=r.loc[first:,[fund,spec['bench']]].dropna(); folds=[stats(net_endpoint(f[fund]))['cagr']-stats(net_endpoint(f[spec['bench']]))['cagr'] for f in np.array_split(z,5)]; passed=all(v['matched_excess_cagr']>0 for v in res.values()) and sum(v>0 for v in folds)>=3
 reps[fund]={'benchmark':spec['bench'],'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(v>0 for v in folds),'passes':passed}
family_pass=all(v['passes'] for v in reps.values()); decision='P345_FUNDAMENTAL_INDEXING_FAMILY_SUPPORTED' if family_pass else 'P345_FUNDAMENTAL_INDEXING_FAMILY_NOT_SUPPORTED'
out={'schema':'research.p345_fundamental_indexing_funds_r1','parent':'P345','claim':'Prospectively frozen investable fundamental-indexing discriminator using two independent constructions: PRF versus IWB and FNDX versus VTI. Each is buy/hold with 10bp entry plus 10bp terminal friction, fixed chronology windows, five folds, SPY and QQQ opportunity-cost context, and no fund substitution, timing, weighting, threshold, window, or cost tuning.','cost_bps_each_endpoint':COST_BPS,'representations':reps,'decision_rule':'Support broad fundamental-indexing alpha only if BOTH independent constructions have positive after-cost matched excess in every fixed window and >=3/5 positive chronology folds. Failure preserves passing scope but rejects broad-family support without rescue.','decision':decision,'limitations':['fundamental index methodologies differ but both explicitly depart from cap weighting using company fundamentals','adjusted prices include fund expenses/distributions but not investor taxes','QQQ is opportunity context not matched baseline','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p345_fundamental_indexing_funds_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))