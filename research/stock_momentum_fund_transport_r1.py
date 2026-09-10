from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
PAIRS={'MTUM_vs_IWB':('MTUM','IWB'),'PDP_vs_SPY':('PDP','SPY')}; CONTROL='QQQ'; START='2014-01-01'; END='2026-09-11'; COST=10.; WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def ep(r):
 q=pd.Series(r,dtype=float).dropna().copy(); f=COST/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for pos in np.array_split(np.arange(len(z)),5):
  c=z.iloc[pos]
  if len(c)>=12: out.append(metric(ep(c.a))['cagr']-metric(ep(c.b))['cagr'])
 return out
syms=sorted(set(sum(([a,b] for a,b in PAIRS.values()),[])+[CONTROL])); raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for w,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]; wr={}
 for name,(cand,base) in PAIRS.items():
  cm=metric(ep(z[cand])); bm=metric(ep(z[base])); fm=folds(z[cand],z[base]); qm=metric(ep(z[CONTROL])); wr[name]={'candidate':cand,'matched':base,'candidate_metrics':cm,'matched_metrics':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in fm),'fold_count':len(fm),'fold_excess_cagr':fm,'vs_QQQ_cagr':cm['cagr']-qm['cagr']}
 results[w]=wr
p=results['2015']; q=results['2020']; s=results['2022']; support={k:(p[k]['matched_excess_cagr']>0 and p[k]['positive_matched_folds']>=3 and p[k]['candidate_metrics']['maxdd']>=p[k]['matched_metrics']['maxdd']-.05 and q[k]['matched_excess_cagr']>0 and s[k]['matched_excess_cagr']>0) for k in PAIRS}; n=sum(support.values()); decision='STOCK_MOMENTUM_FUND_TRANSPORT_SUPPORTED' if n==2 else ('STOCK_MOMENTUM_FUND_SINGLE_IMPLEMENTATION_SUPPORTED' if n==1 else 'STOCK_MOMENTUM_FUND_NOT_SUPPORTED')
out={'schema':'research.stock_momentum_fund_transport_r1','workload_id':'STOCK_MOMENTUM_FUND_TRANSPORT_R1','claim':'Test whether cross-sectional stock momentum transports into two independent investable fund implementations with persistent after-cost matched excess, without timing, product, threshold, weight, or window optimization.','parameters':{'pairs':PAIRS,'entry_exit_bps':COST,'windows':WINDOWS,'no_tuning':True},'results':results,'implementation_support':support,'decision_rule':'Each implementation passes with positive 2015+ matched excess, >=3/5 positive chronological folds, no >5pp max-drawdown penalty, and positive matched excess in both 2020+ and 2022+. Both must pass for transported fund-model support. QQQ is opportunity context, not the matched control.','decision':decision,'limitations':['MTUM and PDP implement different momentum methodologies, so agreement is transport evidence rather than identical-mechanism replication','fund fees/methodologies are embedded in adjusted returns','scientific evidence only; no portfolio-ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/stock_momentum_fund_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
