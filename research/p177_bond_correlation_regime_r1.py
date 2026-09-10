import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPY','TLT','BIL']; COSTS=[10,25,50]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; PC=25

def cagr(r):
 r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def maxdd(r):
 e=(1+pd.Series(r).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def sharpe(r):
 r=pd.Series(r).dropna(); s=r.std(ddof=1); return float(np.sqrt(12)*r.mean()/s) if s>0 else float('nan')
def met(r): return {'cagr':cagr(r),'maxdd':maxdd(r),'sharpe':sharpe(r)}
def ev(z,c):
 bond=z.bond_on; gross=.6*z.SPY_ret+.4*(bond*z.TLT_ret+(1-bond)*z.BIL_ret); turn=.4*bond.diff().abs().fillna(0); cand=gross-turn*c/10000; static=.6*z.SPY_ret+.4*z.TLT_ret
 return {'candidate':met(cand),'static_60_40':met(static),'excess_60_40':cagr(cand)-cagr(static),'mean_tlt_weight':float(.4*bond.mean()),'months':int(len(z))}
def folds(z,c):
 out=[]
 for i,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  x=ev(z.iloc[idx],c); out.append({'fold':i,'excess_60_40':x['excess_60_40']})
 return out
raw=yf.download(T,start='2007-01-01',end='2026-09-01',auto_adjust=True,progress=False,group_by='column'); close=raw['Close'][T] if isinstance(raw.columns,pd.MultiIndex) else raw[T]; close=close.dropna(how='all').ffill().dropna(); dr=close.pct_change(); corr=dr.SPY.rolling(63,min_periods=63).corr(dr.TLT); m=close.resample('ME').last(); mr=m.pct_change(); cm=corr.resample('ME').last(); bond=(cm<0).astype(float).shift(1); z=pd.DataFrame({'SPY_ret':mr.SPY,'TLT_ret':mr.TLT,'BIL_ret':mr.BIL,'bond_on':bond}).dropna(); sha=hashlib.sha256(close.to_csv().encode()).hexdigest()
r={'schema':'research.p177_bond_correlation_regime_r1','parent':'P177','hypothesis':'A fixed ex-ante stock/bond correlation regime can improve a 60/40 fund by replacing the 40% bond sleeve with T-bills when bonds cease to diversify equities.','contract':{'base':'60% SPY + 40% TLT','signal':'completed-month trailing 63-session SPY/TLT daily-return correlation <0 keeps TLT; otherwise replace 40% TLT with BIL next month','cost_bps':COSTS,'primary_cost_bps':PC,'windows':WINDOWS,'folds':5,'matched':'static 60/40 SPY/TLT','predeclared_gate':'2015+ at 25 bps positive CAGR excess vs static 60/40, >=3/5 positive folds, and non-inferior max drawdown','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(m.index[-1].date()),'panel_sha256':sha},'tests':{}}
for c in COSTS:
 r['tests'][str(c)]={}
 for k,s in WINDOWS.items():
  q=z.loc[pd.Timestamp(s):]; x=ev(q,c); fs=folds(q,c); x['folds']=fs; x['positive_folds']=sum(a['excess_60_40']>0 for a in fs); r['tests'][str(c)][k]=x
p=r['tests'][str(PC)]['2015']; r['decision']='P177_BOND_CORRELATION_REGIME_SURVIVOR' if p['excess_60_40']>0 and p['positive_folds']>=3 and p['candidate']['maxdd']>=p['static_60_40']['maxdd'] else 'P177_BOND_CORRELATION_REGIME_REJECT'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p177_bond_correlation_regime_r1.json').write_text(json.dumps(r,sort_keys=True,indent=2)); print(json.dumps(r,sort_keys=True))
