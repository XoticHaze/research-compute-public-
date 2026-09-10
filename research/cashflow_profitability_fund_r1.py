from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
PAIRS={'COWZ_vs_IWB':('COWZ','IWB'),'CALF_vs_IJR':('CALF','IJR')}; CONTROLS=['SPY','QQQ']; START='2017-06-01'; END='2026-09-11'; COST=10.0; WINDOWS={'2018':'2018-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; ann=float(q.mean()*12) if n else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(ann/vol) if vol else None}
def ep(r):
 q=pd.Series(r,dtype=float).dropna().copy(); f=COST/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for positions in np.array_split(np.arange(len(z)),5):
  c=z.iloc[positions]
  if len(c)>=12: out.append(metric(ep(c.a))['cagr']-metric(ep(c.b))['cagr'])
 return out
syms=sorted(set(sum(([a,b] for a,b in PAIRS.values()),[])+CONTROLS)); raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for w,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]; wr={}
 for name,(cand,base) in PAIRS.items():
  cm=metric(ep(z[cand])); bm=metric(ep(z[base])); fm=folds(z[cand],z[base]); spy=metric(ep(z.SPY)); qqq=metric(ep(z.QQQ)); wr[name]={'candidate':cand,'matched':base,'candidate_metrics':cm,'matched_metrics':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in fm),'fold_count':len(fm),'fold_excess_cagr':fm,'vs_SPY_cagr':cm['cagr']-spy['cagr'],'vs_QQQ_cagr':cm['cagr']-qqq['cagr']}
 results[w]=wr
p=results['2018']; q=results['2020']; s=results['2022']; each={k:(p[k]['matched_excess_cagr']>0 and p[k]['positive_matched_folds']>=3 and p[k]['candidate_metrics']['maxdd']>=p[k]['matched_metrics']['maxdd']-.05 and q[k]['matched_excess_cagr']>0 and s[k]['matched_excess_cagr']>0) for k in PAIRS}; passes=sum(each.values()); decision='CASHFLOW_PROFITABILITY_CROSS_CAP_SUPPORTED' if passes==2 else ('CASHFLOW_PROFITABILITY_SINGLE_CAP_SUPPORTED' if passes==1 else 'CASHFLOW_PROFITABILITY_NOT_SUPPORTED')
out={'schema':'research.cashflow_profitability_fund_r1','workload_id':'CASHFLOW_PROFITABILITY_FUND_R1','claim':'Test whether a fixed investable free-cash-flow profitability-plus-valuation architecture earns persistent after-cost matched excess in both large-cap and small-cap implementations, without timing, weight, product, or threshold search.','parameters':{'pairs':PAIRS,'entry_exit_bps':COST,'windows':WINDOWS,'no_tuning':True},'results':results,'implementation_support':each,'decision_rule':'Each implementation passes only with positive 2018+ matched excess, >=3/5 positive chronology folds, no >5pp max-drawdown penalty versus its matched capitalization control, and positive matched excess in both 2020+ and 2022+. Two passes support cross-cap transport; one is single-cap evidence only; zero rejects the architecture. SPY/QQQ are opportunity context, not matched gates.','decision':decision,'limitations':['ETF methodology/fees are embedded in adjusted fund returns','history begins in 2017 and cannot adjudicate pre-2018 regimes','this is a distinct free-cash-flow profitability+valuation architecture and must not be used to rescue failed static quality/value ETF claims','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/cashflow_profitability_fund_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
