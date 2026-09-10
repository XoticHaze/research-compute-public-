import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPY','IEF','BIL']; COSTS=[10,25,50]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; PC=25

def cagr(r):
 r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def maxdd(r):
 e=(1+pd.Series(r).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def sharpe(r):
 r=pd.Series(r).dropna(); s=r.std(ddof=1); return float(np.sqrt(12)*r.mean()/s) if s>0 else float('nan')
def met(r): return {'cagr':cagr(r),'maxdd':maxdd(r),'sharpe':sharpe(r)}
def ev(z,c):
 cand=z.gross-z.turn*c/10000; ew=.5*z.SPY_ret+.5*z.IEF_ret; sixty=.6*z.SPY_ret+.4*z.IEF_ret
 return {'candidate':met(cand),'equal_weight':met(ew),'sixty_forty':met(sixty),'spy':met(z.SPY_ret),'excess_equal_weight':cagr(cand)-cagr(ew),'excess_60_40':cagr(cand)-cagr(sixty),'excess_spy':cagr(cand)-cagr(z.SPY_ret),'months':int(len(z))}
def folds(z,c):
 out=[]
 for i,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  x=ev(z.iloc[idx],c); out.append({'fold':i,'ew_excess':x['excess_equal_weight'],'excess_60_40':x['excess_60_40'],'spy_excess':x['excess_spy']})
 return out
raw=yf.download(T,start='2007-01-01',end='2026-09-01',auto_adjust=True,progress=False,group_by='column'); close=raw['Close'][T] if isinstance(raw.columns,pd.MultiIndex) else raw[T]; close=close.dropna(how='all').ffill().dropna(); m=close.resample('ME').last(); mom=m.pct_change(12); rows=[]; prev=None
for i in range(12,len(m.index)-1):
 dt,nxt=m.index[i],m.index[i+1]; s=mom.loc[dt,['SPY','IEF']]; bil=float(mom.loc[dt,'BIL']); winner=s.idxmax(); wret=float(s.max()); asset=winner if wret>bil else 'BIL'; r=m.loc[nxt,T]/m.loc[dt,T]-1; turn=0 if prev is None or prev==asset else 1; rows.append({'date':nxt,'gross':float(r[asset]),'turn':turn,'SPY_ret':float(r.SPY),'IEF_ret':float(r.IEF)}); prev=asset
z=pd.DataFrame(rows).set_index('date'); sha=hashlib.sha256(close.to_csv().encode()).hexdigest(); out={'schema':'research.p181_spy_ief_dual_momentum_r1','parent':'P181','hypothesis':'A fixed 12-month dual-momentum rule across US equities, intermediate Treasuries, and T-bills creates durable after-cost excess versus static stock/bond allocations.','contract':{'signal':'at completed month-end choose stronger of SPY or IEF by trailing 12-month return only if its 12-month return exceeds BIL; otherwise BIL; apply next month','cost_bps':COSTS,'primary_cost_bps':PC,'windows':WINDOWS,'folds':5,'matched_controls':['50/50 SPY/IEF','60/40 SPY/IEF'],'opportunity_control':'SPY','predeclared_gate':'2015+ at 25 bps positive excess vs both 50/50 and 60/40, >=3/5 positive 50/50 folds, and non-inferior max drawdown vs 50/50','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(m.index[-1].date()),'panel_sha256':sha},'tests':{}}
for c in COSTS:
 out['tests'][str(c)]={}
 for k,s in WINDOWS.items():
  q=z.loc[pd.Timestamp(s):]; x=ev(q,c); fs=folds(q,c); x['folds']=fs; x['positive_ew_folds']=sum(a['ew_excess']>0 for a in fs); x['positive_6040_folds']=sum(a['excess_60_40']>0 for a in fs); out['tests'][str(c)][k]=x
p=out['tests'][str(PC)]['2015']; out['decision']='P181_DUAL_MOMENTUM_SURVIVOR' if p['excess_equal_weight']>0 and p['excess_60_40']>0 and p['positive_ew_folds']>=3 and p['candidate']['maxdd']>=p['equal_weight']['maxdd'] else 'P181_DUAL_MOMENTUM_REJECT'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p181_spy_ief_dual_momentum_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
