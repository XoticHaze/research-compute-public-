from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FACTORS=['MTUM','QUAL','VLUE','USMV','SIZE']
CONTROLS=['SPY','QQQ']
START='2013-01-01'; END='2026-09-10'; LOOKBACK=252; SKIP=21; TOP=2
COSTS=[10.0,25.0,50.0]; WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}

def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
 c=float(e.iloc[-1]**(12/n)-1); dd=float((e/e.cummax()-1).min()); vol=float(q.std(ddof=1)*math.sqrt(12)); ann=float(q.mean()*12)
 return {'months':int(n),'cagr':c,'maxdd':dd,'sharpe_rf0':float(ann/vol) if vol else None}

def turnover(a,b):
 names=set(a)|set(b); return 0.5*sum(abs(b.get(s,0)-a.get(s,0)) for s in names)

def folds(a,b,k=5):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); chunks=np.array_split(z,k); out=[]
 for c in chunks:
  if len(c)<6: continue
  out.append(metric(c.a)['cagr']-metric(c.b)['cagr'])
 return out

raw=yf.download(FACTORS+CONTROLS,start=START,end=END,auto_adjust=True,progress=False,group_by='column',threads=False)
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[FACTORS+CONTROLS].dropna().sort_index()
monthends=[i for i in range(LOOKBACK,len(px)-1) if px.index[i].month!=px.index[i+1].month]
rows=[]; prev={}
for n,i in enumerate(monthends[:-1]):
 j=monthends[n+1]
 scores={s:float(px[s].iloc[i-SKIP]/px[s].iloc[i-LOOKBACK]-1) for s in FACTORS}
 sel=sorted(FACTORS,key=lambda s:(-scores[s],s))[:TOP]
 w={s:1/TOP for s in sel}; t=turnover(prev,w); prev=w
 gross=sum(wt*float(px[s].iloc[j]/px[s].iloc[i]-1) for s,wt in w.items())
 ew=float(np.mean([px[s].iloc[j]/px[s].iloc[i]-1 for s in FACTORS]))
 rows.append({'date':px.index[j],**{f'model_{int(c)}':gross-t*c/10000 for c in COSTS},'matched':ew,'SPY':float(px.SPY.iloc[j]/px.SPY.iloc[i]-1),'QQQ':float(px.QQQ.iloc[j]/px.QQQ.iloc[i]-1),'turnover':t,'selected':','.join(sel)})
r=pd.DataFrame(rows).set_index('date')
res={}
for name,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]
 m25=metric(z.model_25); match=metric(z.matched); spy=metric(z.SPY); qqq=metric(z.QQQ)
 f=folds(z.model_25,z.matched)
 res[name]={'model_25bps':m25,'matched_equal_factor':match,'SPY':spy,'QQQ':qqq,'matched_excess_cagr':m25['cagr']-match['cagr'],'vs_SPY_cagr':m25['cagr']-spy['cagr'],'vs_QQQ_cagr':m25['cagr']-qqq['cagr'],'positive_matched_folds':int(sum(x>0 for x in f)),'fold_count':len(f),'fold_excess_cagr':f,'model_10bps_cagr':metric(z.model_10)['cagr'],'model_50bps_cagr':metric(z.model_50)['cagr'],'matched_excess_50bps':metric(z.model_50)['cagr']-match['cagr'],'mean_monthly_turnover':float(z.turnover.mean())}
p=res['2020']; q=res['2022']
passed=p['matched_excess_cagr']>=0.01 and p['positive_matched_folds']>=4 and p['matched_excess_50bps']>0 and q['matched_excess_cagr']>0 and q['positive_matched_folds']>=3 and p['model_25bps']['maxdd']>=p['matched_equal_factor']['maxdd']-0.05
decision='P275_FACTOR_MOMENTUM_SUPPORTED_CANDIDATE' if passed else 'P275_FACTOR_MOMENTUM_NOT_SUPPORTED'
out={'schema':'research.p275_factor_etf_momentum_r1','parent':'P275','hypothesis':'Prospectively fixed 12-1 cross-sectional momentum among MTUM/QUAL/VLUE/USMV/SIZE, equal-weight top 2 monthly, creates after-cost excess versus the same factor ETF universe held equal-weight.','parameters':{'universe':FACTORS,'lookback_sessions':LOOKBACK,'skip_sessions':SKIP,'top_n':TOP,'rebalance':'month-end to next month-end','costs_bps':COSTS,'primary_cost_bps':25.0,'windows':WINDOWS},'results':res,'decision_rule':'SUPPORTED_CANDIDATE only if 2020+ matched excess >=1pp CAGR, >=4/5 positive matched folds, positive 50bps matched excess, 2022+ positive matched excess with >=3/5 folds, and max drawdown not >5pp worse than matched. Otherwise reject this fixed formulation without parameter rescue.','decision':decision,'limitations':['Yahoo adjusted-price public research data','ETF inception limits pre-2013 evidence','no factor weights/lookbacks/top-k were searched'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p275_factor_etf_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
