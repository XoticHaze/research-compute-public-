import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=[10,25,50]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; PC=25

def cagr(r):
 r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def maxdd(r):
 e=(1+pd.Series(r).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def sharpe(r):
 r=pd.Series(r).dropna(); s=r.std(ddof=1); return float(np.sqrt(12)*r.mean()/s) if s>0 else float('nan')
def met(r): return {'cagr':cagr(r),'maxdd':maxdd(r),'sharpe':sharpe(r)}
def ev(z,c):
 p=z.pos; cand=p*z.SPY_ret+(1-p)*z.BIL_ret-p.diff().abs().fillna(0)*c/10000; ex=float(p.mean()); matched=ex*z.SPY_ret+(1-ex)*z.BIL_ret; spy=z.SPY_ret
 return {'candidate':met(cand),'matched':met(matched),'spy':met(spy),'excess_matched':cagr(cand)-cagr(matched),'excess_spy':cagr(cand)-cagr(spy),'mean_spy_exposure':ex,'months':int(len(z))}
def folds(z,c):
 out=[]
 for i,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  x=ev(z.iloc[idx],c); out.append({'fold':i,'matched_excess':x['excess_matched'],'spy_excess':x['excess_spy']})
 return out
raw=yf.download(['SPY','BIL'],start='2007-01-01',end='2026-09-01',auto_adjust=True,progress=False,group_by='column'); close=raw['Close'][['SPY','BIL']] if isinstance(raw.columns,pd.MultiIndex) else raw[['SPY','BIL']]; close=close.dropna(how='all').ffill().dropna(); m=close.resample('ME').last(); ret=m.pct_change(); # month return labeled month-end; own SPY Nov-Apr
pos=pd.Series([1.0 if d.month in (11,12,1,2,3,4) else 0.0 for d in ret.index],index=ret.index); z=pd.DataFrame({'SPY_ret':ret.SPY,'BIL_ret':ret.BIL,'pos':pos}).dropna(); sha=hashlib.sha256(close.to_csv().encode()).hexdigest()
r={'schema':'research.p180_halloween_seasonality_r1','parent':'P180','hypothesis':'A fixed November-through-April equity seasonality produces durable after-cost excess beyond static SPY exposure matched to the same average equity allocation.','contract':{'position':'SPY during November-April monthly return periods, BIL May-October; calendar known ex ante','cost_bps':COSTS,'primary_cost_bps':PC,'windows':WINDOWS,'folds':5,'matched':'static SPY/BIL at evaluated mean SPY exposure','opportunity_control':'SPY','predeclared_gate':'2015+ at 25 bps positive matched CAGR excess, >=3/5 positive matched folds, and non-inferior max drawdown','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(m.index[-1].date()),'panel_sha256':sha},'tests':{}}
for c in COSTS:
 r['tests'][str(c)]={}
 for k,s in WINDOWS.items():
  q=z.loc[pd.Timestamp(s):]; x=ev(q,c); fs=folds(q,c); x['folds']=fs; x['positive_matched_folds']=sum(a['matched_excess']>0 for a in fs); x['positive_spy_folds']=sum(a['spy_excess']>0 for a in fs); r['tests'][str(c)][k]=x
p=r['tests'][str(PC)]['2015']; r['decision']='P180_HALLOWEEN_SEASONALITY_SURVIVOR' if p['excess_matched']>0 and p['positive_matched_folds']>=3 and p['candidate']['maxdd']>=p['matched']['maxdd'] else 'P180_HALLOWEEN_SEASONALITY_REJECT'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p180_halloween_seasonality_r1.json').write_text(json.dumps(r,sort_keys=True,indent=2)); print(json.dumps(r,sort_keys=True))
