from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
RNG=np.random.default_rng(20260909)
REPS={'p87':("VTI","VEA","IEF","IAU","GSG"),'original':("SPY","QQQ","TLT","GLD","DBC")}; START='2006-01-01'
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; return float(e.iloc[-1]**(1/y)-1)
def roll(a,b,w):
 x=[]
 for i in range(w-1,len(a)): x.append(metrics(a.iloc[i-w+1:i+1])-metrics(b.iloc[i-w+1:i+1]))
 return np.array(x,float)
def boot(x,block=12,n=5000):
 x=np.asarray(x,float); z=[]
 for _ in range(n):
  o=[]
  while len(o)<len(x):
   s=int(RNG.integers(0,max(1,len(x)-block+1))); o.extend(x[s:s+block])
  z.append(float(np.mean(o[:len(x)])*12))
 q=np.quantile(z,[.025,.975]); return {'annualized_mean_incremental':float(np.mean(x)*12),'bootstrap_95pct':[float(q[0]),float(q[1])],'p_incremental_le_zero':float(np.mean(np.asarray(z)<=0))}
def frame(syms):
 req=tuple(dict.fromkeys((*syms,'SPY','QQQ'))); d=yf.download(list(req),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(req)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pa={s:0. for s in syms}; ph={s:0. for s in syms}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(syms)],'trend200':trend.loc[dt,list(syms)],'drawdown6':dd.loc[dt,list(syms)]},index=list(syms))
  if b.isna().any().any() or pd.isna(mom.loc[dt,'SPY']): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(req)]/m.loc[dt,list(req)]-1
  if r.isna().any(): continue
  chosen=b.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; wa={s:(.5 if s in chosen else 0.) for s in syms}; wh=wa if float(mom.loc[dt,'SPY'])>0 else {s:1/len(syms) for s in syms}; ta=.5*sum(abs(wa[s]-pa[s]) for s in syms); th=.5*sum(abs(wh[s]-ph[s]) for s in syms); rows.append({'date':nxt,'base_gross':sum(wa[s]*float(r[s]) for s in syms),'hybrid_gross':sum(wh[s]*float(r[s]) for s in syms),'base_turn':ta,'hybrid_turn':th}); pa,ph=wa,wh
 return pd.DataFrame(rows).set_index('date')
def main():
 out={'schema':'research.p100_p95_incremental_serial_r1','parent_ids':['P95','P97','P100'],'contract':{'mutation':'P95 risk-off equal-weight deactivation versus same frozen three-factor base','representations':REPS,'rolling_months':[36,60],'block_months':12,'bootstrap_draws':5000,'costs_bps':[25,50],'no_tuning':True},'results':{}}
 strong=0
 for name,syms in REPS.items():
  f=frame(syms); out['results'][name]={'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)}}
  for bps in (25,50):
   base=f.base_gross-f.base_turn*bps/10000; hy=f.hybrid_gross-f.hybrid_turn*bps/10000; inc=hy-base; rec={'full_incremental_cagr':metrics(hy)-metrics(base),'bootstrap':boot(inc)}
   for w in (36,60):
    rr=roll(hy,base,w); rec[f'rolling{w}_positive_fraction']=float(np.mean(rr>0)); rec[f'rolling{w}_median_incremental_cagr']=float(np.median(rr))
   out['results'][name][str(bps)]=rec
  r=out['results'][name]['25']; strong+=r['rolling60_positive_fraction']>=.75 and r['bootstrap']['p_incremental_le_zero']<=.1 and r['full_incremental_cagr']>=.001
 out['decision']='P95_INCREMENTAL_EDGE_SERIAL_SUPPORT_ACROSS_REPRESENTATIONS' if strong==2 else 'P95_INCREMENTAL_EDGE_TOO_THIN_OR_UNSTABLE_PARK_MUTATION'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p100_p95_incremental_serial_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'results':out['results']},sort_keys=True))
if __name__=='__main__': main()
