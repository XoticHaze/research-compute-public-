from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("VTI","VEA","IEF","IAU","GSG"); REQ=(*SYMS,"SPY","QQQ"); START="2007-01-01"
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else float('nan')}
def rolling(c,b,w):
 a=np.asarray([cagr(c.iloc[i-w:i])-cagr(b.iloc[i-w:i]) for i in range(w,len(c)+1)]); return {'windows':len(a),'positive_fraction':float((a>0).mean()),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1)),'p90_excess_cagr':float(np.quantile(a,.9))}
def bootstrap(c,b,n=5000,block=12):
 x=(c-b).to_numpy(); rng=np.random.default_rng(20260909); vals=[]; L=len(x)
 for _ in range(n):
  pieces=[]
  while sum(len(z) for z in pieces)<L:
   s=int(rng.integers(0,max(1,L-block+1))); pieces.append(x[s:s+block])
  vals.append(float(np.concatenate(pieces)[:L].mean()*12))
 a=np.asarray(vals); return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float((a<=0).mean()),'block_months':block,'replicates':n}
def build():
 d=yf.download(list(REQ),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(REQ)].dropna(how='all').astype(float); m=close.resample('ME').last(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); p3={s:0. for s in SYMS}; p4={s:0. for s in SYMS}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)],'low_vol6':-vol.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(REQ)]/m.loc[dt,list(REQ)]-1
  if r.isna().any(): continue
  s3=b[['mom6','trend200','drawdown6']].rank(axis=0,pct=True,method='average').mean(axis=1); s4=b.rank(axis=0,pct=True,method='average').mean(axis=1); c3=s3.sort_values(ascending=False).head(2).index; c4=s4.sort_values(ascending=False).head(2).index; w3={s:(.5 if s in c3 else 0.) for s in SYMS}; w4={s:(.5 if s in c4 else 0.) for s in SYMS}; t3=.5*sum(abs(w3[s]-p3[s]) for s in SYMS); t4=.5*sum(abs(w4[s]-p4[s]) for s in SYMS); rows.append({'date':nxt,'g3':sum(w3[s]*float(r[s]) for s in SYMS),'g4':sum(w4[s]*float(r[s]) for s in SYMS),'t3':t3,'t4':t4,'ew':float(r.loc[list(SYMS)].mean())}); p3,p4=w3,w4
 return pd.DataFrame(rows).set_index('date')
def main():
 f=build(); tests={}
 for bps in (25,50):
  c3=f.g3-f.t3*bps/10000; c4=f.g4-f.t4*bps/10000; ew=f.ew; tests[str(bps)]={'three_factor':metrics(c3),'four_factor':metrics(c4),'matched_equal_weight':metrics(ew),'vs_equal_weight':{'rolling36':rolling(c3,ew,36),'rolling60':rolling(c3,ew,60),'bootstrap':bootstrap(c3,ew)},'vs_four_factor':{'rolling36':rolling(c3,c4,36),'rolling60':rolling(c3,c4,60),'bootstrap':bootstrap(c3,c4)}}
 p=tests['25']; p50=tests['50']; supported=p['vs_equal_weight']['rolling60']['positive_fraction']>=.6 and p['vs_equal_weight']['bootstrap']['p_excess_le_zero']<=.2 and p['vs_four_factor']['rolling60']['positive_fraction']>=.6 and p50['vs_equal_weight']['bootstrap']['annualized_mean_excess']>0
 out={'schema':'research.p91_p87_serial_persistence_r1','parent_ids':['P46','P87','P91'],'scientific_contract':{'mechanism':'frozen P87 momentum+trend+drawdown top2 on VTI/VEA/IEF/IAU/GSG','comparators':['same representation four-factor P46','exact equal weight'],'costs_bps':[25,50],'rolling_windows_months':[36,60],'bootstrap':'12m moving block 5000 reps deterministic seed','no_parameter_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':tests,'decision':'SUPPORTED_PARSIMONIOUS_THREE_FACTOR_PERSISTENCE' if supported else 'THREE_FACTOR_INCREMENT_NOT_SERIAL_PARK_REDUCTION'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p91_p87_serial_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'25_vs_ew':p['vs_equal_weight'],'25_vs_four':p['vs_four_factor'],'50_vs_ew':p50['vs_equal_weight'],'window':out['window']},sort_keys=True))
if __name__=='__main__': main()
