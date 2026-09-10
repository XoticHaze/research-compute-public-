from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
CONTROLS=['SPY','QQQ']; START='2004-01-01'; END='2026-09-10'; LOOKBACK=252; TOP=3
COSTS=[10.0,25.0,50.0]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}

def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
 if not n:return {'months':0,'cagr':None,'maxdd':None,'sharpe_rf0':None}
 vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; ann=float(q.mean()*12)
 return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}
def turn(a,b): return .5*sum(abs(b.get(s,0)-a.get(s,0)) for s in set(a)|set(b))
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for c in np.array_split(z,5):
  if len(c)>=12: out.append(metric(c.a)['cagr']-metric(c.b)['cagr'])
 return out
raw=yf.download(SECTORS+CONTROLS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SECTORS+CONTROLS].dropna().sort_index(); dr=px.pct_change()
monthends=[i for i in range(LOOKBACK,len(px)-1) if px.index[i].month!=px.index[i+1].month]
rows=[]; prev={}
for n,i in enumerate(monthends[:-1]):
 j=monthends[n+1]; win=dr.iloc[i-LOOKBACK+1:i+1]; v=float(win.SPY.var())
 if not v or not np.isfinite(v): continue
 beta={s:float(win[s].cov(win.SPY)/v) for s in SECTORS}; sel=sorted(SECTORS,key=lambda s:(beta[s],s))[:TOP]; w={s:1/TOP for s in sel}; t=turn(prev,w); prev=w
 gross=sum(wt*float(px[s].iloc[j]/px[s].iloc[i]-1) for s,wt in w.items()); ew=float(np.mean([px[s].iloc[j]/px[s].iloc[i]-1 for s in SECTORS]))
 rows.append({'date':px.index[j],**{f'model_{int(c)}':gross-t*c/10000 for c in COSTS},'matched':ew,'SPY':float(px.SPY.iloc[j]/px.SPY.iloc[i]-1),'QQQ':float(px.QQQ.iloc[j]/px.QQQ.iloc[i]-1),'turnover':t,'selected':','.join(sel)})
r=pd.DataFrame(rows).set_index('date'); outres={}
for name,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]; m=metric(z.model_25); b=metric(z.matched); spy=metric(z.SPY); qqq=metric(z.QQQ); f=folds(z.model_25,z.matched)
 outres[name]={'model_25bps':m,'matched_equal_sector':b,'SPY':spy,'QQQ':qqq,'matched_excess_cagr':m['cagr']-b['cagr'],'vs_SPY_cagr':m['cagr']-spy['cagr'],'vs_QQQ_cagr':m['cagr']-qqq['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'matched_excess_10bps':metric(z.model_10)['cagr']-b['cagr'],'matched_excess_50bps':metric(z.model_50)['cagr']-b['cagr'],'mean_monthly_turnover':float(z.turnover.mean())}
p=outres['2015']; q=outres['2020']; s=outres['2022']; ok=p['matched_excess_cagr']>=.01 and p['positive_matched_folds']>=4 and p['matched_excess_50bps']>0 and q['matched_excess_cagr']>0 and q['positive_matched_folds']>=3 and s['matched_excess_cagr']>0 and p['model_25bps']['maxdd']>=p['matched_equal_sector']['maxdd']-.05
res={'schema':'research.p281_sector_lowbeta_r1','parent':'P281','hypothesis':'A prospectively fixed monthly selector owning the three lowest trailing-252-session beta US sectors earns durable after-cost excess versus equal-weight exposure to the exact same sector universe.','parameters':{'sectors':SECTORS,'beta_market':'SPY','lookback_sessions':LOOKBACK,'top_n_low_beta':TOP,'costs_bps_per_one_way_turnover':COSTS,'primary_cost_bps':25.0,'windows':WINDOWS},'results':outres,'decision_rule':'SUPPORTED_CANDIDATE only if 2015+ matched excess >=1pp CAGR, >=4/5 positive folds, positive at 50bps, positive 2020+ with >=3/5 folds, positive 2022+, and max drawdown no more than 5pp worse than matched. Otherwise reject the frozen formulation without lookback/top-k/universe/weight rescue.','decision':'P281_SECTOR_LOWBETA_SUPPORTED_CANDIDATE' if ok else 'P281_SECTOR_LOWBETA_NOT_SUPPORTED','limitations':['Yahoo adjusted-price research data','fixed nine-sector long-history universe','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p281_sector_lowbeta_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
