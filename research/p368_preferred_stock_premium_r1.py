from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
FUND='PFF'; C=['HYG','IEF','SPY']; ALL=[FUND]+C; START='2008-01-01'; END='2026-09-10'; LB=24; COST=10
W={'2011_plus':'2011-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False); close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()
def m(q):
 q=pd.Series(q,dtype=float).dropna();n=len(q)
 if n<2:return {'months':n,'cagr':None,'maxdd':None,'sharpe_rf0':None}
 e=(1+q).cumprod();v=q.std(ddof=1)*math.sqrt(12);return {'months':n,'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/v) if v else None}
bs=[]
for i in range(len(r)):
 if i<LB:bs.append((np.nan,)*3);continue
 b=np.linalg.lstsq(r[C].iloc[i-LB:i].values,r[FUND].iloc[i-LB:i].values,rcond=None)[0];b=np.clip(b,0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['b_hyg','b_ief','b_spy']).shift(1); bench=b.b_hyg*r.HYG+b.b_ief*r.IEF+b.b_spy*r.SPY
x=pd.concat([r[FUND].rename('fund'),bench.rename('bench'),r[C],b],axis=1).dropna();f=COST/10000
if len(x):x.iloc[0,x.columns.get_loc('fund')]-=f;x.iloc[-1,x.columns.get_loc('fund')]-=f
rows={}
for n,s in W.items():
 q=x.loc[x.index>=pd.Timestamp(s)];fm,bm=m(q.fund),m(q.bench);fold=[]
 for ix in np.array_split(np.arange(len(q)),5):
  z=q.iloc[ix]
  if len(z)>=2:fold.append(m(z.fund)['cagr']-m(z.bench)['cagr'])
 rows[n]={'fund':fm,'matched':bm,'HYG':m(q.HYG),'IEF':m(q.IEF),'SPY':m(q.SPY),'matched_excess_cagr':fm['cagr']-bm['cagr'],'positive_matched_folds':sum(v>0 for v in fold),'fold_excess_cagr':fold}
passes=sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in rows.values());dd=all(v['fund']['maxdd']>=v['matched']['maxdd']-0.05 for v in rows.values());supported=passes==len(W) and dd
res={'schema':'research.p368_preferred_stock_premium_r1','parent':'PREFERRED_STOCK_HYBRID_PREMIUM','claim':'Fixed PFF preferred-stock hybrid exposure versus causal lagged 24-month HYG+IEF+SPY matched control at 10bp endpoint friction. No product/control/beta-window/cost/date/allocation/threshold search.','contract':{'fund':FUND,'control':'lagged 24m OLS HYG+IEF+SPY clipped [0,1], normalize if sum>1','windows':W,'gate':'positive matched excess and >=3/5 folds every window; maxdd no worse by >5pp'},'results':rows,'window_pass_count':passes,'drawdown_guard_pass':dd,'decision':'P368_PREFERRED_STOCK_PREMIUM_SUPPORTED' if supported else 'P368_PREFERRED_STOCK_PREMIUM_NOT_SUPPORTED','scientific_consequence':'Pass requires independent preferred implementation. Failure rejects this fixed formulation without rescue and rotates.','limitations':['single PFF representation','Yahoo adjusted-price representation','control approximates credit/rate/equity factors but omits callability and issuer-specific capital structure'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p368_preferred_stock_premium_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(res,sort_keys=True))
