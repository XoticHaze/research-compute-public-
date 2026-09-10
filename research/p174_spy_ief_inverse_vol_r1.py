import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPY','IEF']; COSTS=[10,25,50]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; PC=25

def cagr(r):
 r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def maxdd(r):
 e=(1+pd.Series(r).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def sharpe(r):
 r=pd.Series(r).dropna(); s=r.std(ddof=1); return float(np.sqrt(12)*r.mean()/s) if s>0 else float('nan')
def metrics(r): return {'cagr':cagr(r),'maxdd':maxdd(r),'sharpe':sharpe(r)}

def evalz(z,cost):
 w=z[['w_spy','w_ief']]; gross=(w.shift(1)*z[['SPY_ret','IEF_ret']].values).sum(axis=1)
 turn=w.diff().abs().sum(axis=1).fillna(0)/2; cand=gross-turn*cost/10000
 matched=.5*z.SPY_ret+.5*z.IEF_ret; s6040=.6*z.SPY_ret+.4*z.IEF_ret; spy=z.SPY_ret
 return {'candidate':metrics(cand),'matched':metrics(matched),'sixty_forty':metrics(s6040),'spy':metrics(spy),'excess_matched':cagr(cand)-cagr(matched),'excess_6040':cagr(cand)-cagr(s6040),'excess_spy':cagr(cand)-cagr(spy),'mean_spy_weight':float(w.w_spy.mean()),'months':int(len(z))}

def folds(z,cost):
 out=[]
 for i,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  x=evalz(z.iloc[idx],cost); out.append({'fold':i,'matched_excess':x['excess_matched'],'excess_6040':x['excess_6040'],'spy_excess':x['excess_spy']})
 return out
raw=yf.download(T,start='2003-01-01',end='2026-09-01',auto_adjust=True,progress=False,group_by='column')
close=raw['Close'][T] if isinstance(raw.columns,pd.MultiIndex) else raw[T]; close=close.dropna(how='all').ffill().dropna()
dr=close.pct_change(); vol=dr.rolling(63,min_periods=63).std()*np.sqrt(252); inv=1/vol; wd=inv.div(inv.sum(axis=1),axis=0)
wm=wd.resample('ME').last(); mr=close.resample('ME').last().pct_change(); z=pd.DataFrame({'SPY_ret':mr.SPY,'IEF_ret':mr.IEF,'w_spy':wm.SPY,'w_ief':wm.IEF}).dropna()
sha=hashlib.sha256(close.to_csv().encode()).hexdigest(); r={'schema':'research.p174_spy_ief_inverse_vol_r1','parent':'P174','hypothesis':'Fixed stock/bond inverse-volatility weighting improves after-cost return quality beyond static same-universe allocations without forecasting direction.','contract':{'universe':T,'signal':'inverse trailing 63-session realized volatility, sampled at completed month-end, applied next month','cost_bps':COSTS,'primary_cost_bps':PC,'windows':WINDOWS,'folds':5,'matched':'static 50/50 SPY/IEF','opportunity_controls':['static 60/40 SPY/IEF','SPY'],'predeclared_gate':'2015+ at 25 bps positive excess vs 50/50 and 60/40, >=3/5 positive matched folds, and candidate max drawdown no worse than 50/50','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(close.resample('ME').last().index[-1].date()),'panel_sha256':sha},'tests':{}}
for c in COSTS:
 r['tests'][str(c)]={}
 for k,s in WINDOWS.items():
  q=z.loc[pd.Timestamp(s):]; x=evalz(q,c); fs=folds(q,c); x['folds']=fs; x['positive_matched_folds']=sum(v['matched_excess']>0 for v in fs); x['positive_6040_folds']=sum(v['excess_6040']>0 for v in fs); r['tests'][str(c)][k]=x
p=r['tests'][str(PC)]['2015']; r['decision']='P174_SPY_IEF_INVOL_SURVIVOR' if (p['excess_matched']>0 and p['excess_6040']>0 and p['positive_matched_folds']>=3 and p['candidate']['maxdd']>=p['matched']['maxdd']) else 'P174_SPY_IEF_INVOL_REJECT'
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p174_spy_ief_inverse_vol_r1.json').write_text(json.dumps(r,sort_keys=True,indent=2)); print(json.dumps(r,sort_keys=True))
