from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SYMS=['COWZ','SYLD','IWB','SPY','QQQ']; START='2016-12-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); r=px.resample('ME').last().pct_change().dropna()
def net_endpoint(s):
 x=s.copy(); x.iloc[0]-=COST_BPS/10000; x.iloc[-1]-=COST_BPS/10000; return x
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
windows={'2017_plus':'2017-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}; reps={}
for fund in ['COWZ','SYLD']:
 res={}
 for name,start in windows.items():
  q=r.loc[start:]; a=stats(net_endpoint(q[fund])); b=stats(net_endpoint(q.IWB)); sp=stats(net_endpoint(q.SPY)); nq=stats(net_endpoint(q.QQQ)); res[name]={'fund':a,'iwb_matched':b,'spy':sp,'qqq_context':nq,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_gap_cagr':a['cagr']-sp['cagr'],'qqq_gap_cagr':a['cagr']-nq['cagr']}
 z=r.loc['2017-01-01':,[fund,'IWB']].dropna(); folds=[]
 for f in np.array_split(z,5):
  folds.append(stats(net_endpoint(f[fund]))['cagr']-stats(net_endpoint(f.IWB))['cagr'])
 passed=all(v['matched_excess_cagr']>0 for v in res.values()) and sum(v>0 for v in folds)>=3
 reps[fund]={'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(v>0 for v in folds),'passes':passed}
family_pass=all(v['passes'] for v in reps.values()); decision='P344_YIELD_FACTOR_FUND_FAMILY_SUPPORTED' if family_pass else 'P344_YIELD_FACTOR_FUND_FAMILY_NOT_SUPPORTED'
out={'schema':'research.p344_shareholder_cashflow_yield_funds_r1','parent':'P344','claim':'Prospectively frozen investable-fund discriminator for shareholder/free-cash-flow yield exposure. Test two independent constructions, COWZ and SYLD, each against IWB matched broad-US exposure with SPY and QQQ opportunity-cost context. Buy/hold only, 10bp entry plus 10bp terminal friction, fixed 2017+/2020+/2022+ windows and five chronology folds. No fund substitution, timing, weighting, threshold, window, or cost tuning.','cost_bps_each_endpoint':COST_BPS,'representations':reps,'decision_rule':'Support the broad yield-factor fund family only if BOTH independent fund constructions have positive after-cost matched excess in every fixed window and >=3/5 positive chronology folds. A one-representation failure preserves any passing fund evidence but rejects broad-family support without parameter rescue.','decision':decision,'limitations':['fund methodologies are related economically but not identical','ETF adjusted prices include fund expenses/distributions but not investor tax effects','QQQ is opportunity-cost context, not matched control','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p344_shareholder_cashflow_yield_funds_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))