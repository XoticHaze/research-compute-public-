import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
RISK=['SPY','IEF','GLD','DBC']; ALL=RISK+['BIL']; COSTS=[10,25,50]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; PC=25

def cagr(r):
 r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def maxdd(r):
 e=(1+pd.Series(r).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def sharpe(r):
 r=pd.Series(r).dropna(); s=r.std(ddof=1); return float(np.sqrt(12)*r.mean()/s) if s>0 else float('nan')
def met(r): return {'cagr':cagr(r),'maxdd':maxdd(r),'sharpe':sharpe(r)}
def ev(z,c):
 cand=z.gross-z.turn*c/10000; static=z.static; spy=z.SPY_ret
 return {'candidate':met(cand),'static_equal_weight':met(static),'spy':met(spy),'excess_static':cagr(cand)-cagr(static),'excess_spy':cagr(cand)-cagr(spy),'months':int(len(z))}
def folds(z,c):
 out=[]
 for i,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  x=ev(z.iloc[idx],c); out.append({'fold':i,'static_excess':x['excess_static'],'spy_excess':x['excess_spy']})
 return out
raw=yf.download(ALL,start='2007-01-01',end='2026-09-01',auto_adjust=True,progress=False,group_by='column'); close=raw['Close'][ALL] if isinstance(raw.columns,pd.MultiIndex) else raw[ALL]; close=close.dropna(how='all').ffill().dropna(); m=close.resample('ME').last(); ret=m.pct_change(); mom=m[RISK].pct_change(12); rows=[]; prev=None
for i in range(12,len(m.index)-1):
 dt,nxt=m.index[i],m.index[i+1]; sig=(mom.loc[dt]>0).astype(float); w=sig/len(RISK); bil=1-float(w.sum()); r=ret.loc[nxt]; gross=float((w*r[RISK]).sum()+bil*r.BIL); static=float(r[RISK].mean()); vec=np.r_[w.values,bil]; turn=0 if prev is None else float(np.abs(vec-prev).sum()/2); rows.append({'date':nxt,'gross':gross,'turn':turn,'static':static,'SPY_ret':float(r.SPY)}); prev=vec
z=pd.DataFrame(rows).set_index('date'); sha=hashlib.sha256(close.to_csv().encode()).hexdigest(); out={'schema':'research.p182_crossasset_tsmom_r1','parent':'P182','hypothesis':'A fixed diversified 12-month absolute time-series momentum overlay across equities, Treasuries, gold and commodities creates durable after-cost excess versus static equal-weight exposure to the same four risk sleeves.','contract':{'universe':RISK,'signal':'each sleeve receives fixed 25% weight next month only when its completed-month trailing 12-month return is positive; inactive sleeve capital goes to BIL','cost_bps':COSTS,'primary_cost_bps':PC,'windows':WINDOWS,'folds':5,'matched':'static equal-weight SPY/IEF/GLD/DBC','opportunity_control':'SPY','predeclared_gate':'2015+ at 25 bps positive excess vs static equal-weight, >=3/5 positive static folds, and non-inferior max drawdown','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(m.index[-1].date()),'panel_sha256':sha},'tests':{}}
for c in COSTS:
 out['tests'][str(c)]={}
 for k,s in WINDOWS.items():
  q=z.loc[pd.Timestamp(s):]; x=ev(q,c); fs=folds(q,c); x['folds']=fs; x['positive_static_folds']=sum(a['static_excess']>0 for a in fs); out['tests'][str(c)][k]=x
p=out['tests'][str(PC)]['2015']; out['decision']='P182_CROSSASSET_TSMOM_SURVIVOR' if p['excess_static']>0 and p['positive_static_folds']>=3 and p['candidate']['maxdd']>=p['static_equal_weight']['maxdd'] else 'P182_CROSSASSET_TSMOM_REJECT'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p182_crossasset_tsmom_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
