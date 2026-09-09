from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CROSS=("VTI","VEA","IEF","IAU","GSG"); IND=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); ALL=tuple(dict.fromkeys((*CROSS,*IND,"SPY","QQQ"))); START="2007-01-01"; RNG=np.random.default_rng(20260909)
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; return float(e.iloc[-1]**(1/y)-1)
def rolling_excess(a,b,w):
 vals=[]
 for i in range(w-1,len(a)): vals.append(metrics(a.iloc[i-w+1:i+1])-metrics(b.iloc[i-w+1:i+1]))
 return np.array(vals,float)
def mb_boot(x,block=12,n=5000):
 x=np.asarray(x,float); out=[]
 for _ in range(n):
  z=[]
  while len(z)<len(x):
   s=int(RNG.integers(0,max(1,len(x)-block+1))); z.extend(x[s:s+block])
  out.append(float(np.mean(z[:len(x)])*12))
 q=np.quantile(out,[.025,.975]); return {'annualized_mean_excess':float(np.mean(x)*12),'bootstrap_95pct':[float(q[0]),float(q[1])],'bootstrap_p_excess_le_zero':float(np.mean(np.array(out)<=0))}
def build():
 d=yf.download(list(ALL),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(ALL)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pc={s:0. for s in CROSS}; pi={s:0. for s in IND}; rows=[]
 for dt in m.index:
  bc=pd.DataFrame({'mom6':mom.loc[dt,list(CROSS)],'trend200':trend.loc[dt,list(CROSS)],'drawdown6':dd.loc[dt,list(CROSS)]},index=list(CROSS)); bi=pd.DataFrame({'mom6':mom.loc[dt,list(IND)],'trend200':trend.loc[dt,list(IND)],'low_vol6':-vol.loc[dt,list(IND)],'drawdown6':dd.loc[dt,list(IND)]},index=list(IND))
  if bc.isna().any().any() or bi.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if r.isna().any(): continue
  cc=bc.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; ci=bi.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(3).index; wc={s:(.5 if s in cc else 0.) for s in CROSS}; wi={s:(1/3 if s in ci else 0.) for s in IND}; tc=.5*sum(abs(wc[s]-pc[s]) for s in CROSS); ti=.5*sum(abs(wi[s]-pi[s]) for s in IND); gc=sum(wc[s]*float(r[s]) for s in CROSS); gi=sum(wi[s]*float(r[s]) for s in IND); rows.append({'date':nxt,'cross_gross':gc,'industry_gross':gi,'cross_turn':tc,'industry_turn':ti,'control':.5*float(r.loc[list(CROSS)].mean())+.5*float(r.loc[list(IND)].mean())}); pc,pi=wc,wi
 return pd.DataFrame(rows).set_index('date')
def main():
 f=build(); out={'schema':'research.p98_p96_serial_persistence_r1','parent_ids':['P47','P87','P96','P98'],'contract':{'ensemble':'frozen 50/50 P87/P47','rolling_months':[36,60],'moving_block_months':12,'bootstrap_draws':5000,'costs_bps':[25,50],'no_weight_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':{}}
 for bps in (25,50):
  cross=f.cross_gross-f.cross_turn*bps/10000; ind=f.industry_gross-f.industry_turn*bps/10000; ens=.5*cross+.5*ind; ctrl=f.control; ex_ctrl=ens-ctrl; ex_cross=ens-cross; key=str(bps); out['tests'][key]={'vs_control':mb_boot(ex_ctrl),'vs_p87':mb_boot(ex_cross)}
  for w in (36,60):
   rc=rolling_excess(ens,ctrl,w); rp=rolling_excess(ens,cross,w); out['tests'][key][f'rolling{w}_positive_vs_control']=float(np.mean(rc>0)); out['tests'][key][f'rolling{w}_median_excess_cagr_vs_control']=float(np.median(rc)); out['tests'][key][f'rolling{w}_positive_vs_p87']=float(np.mean(rp>0)); out['tests'][key][f'rolling{w}_median_excess_cagr_vs_p87']=float(np.median(rp))
 p=out['tests']['25']; p50=out['tests']['50']; ok=p['rolling60_positive_vs_control']>=.8 and p50['rolling60_positive_vs_control']>=.7 and p['vs_control']['bootstrap_p_excess_le_zero']<=.1
 out['decision']='SUPPORTED_P96_ENSEMBLE_SERIAL_MATCHED_ALPHA_RESEARCH_ONLY' if ok else 'P96_ENSEMBLE_SERIAL_SUPPORT_WEAK_KEEP_DIVERSIFICATION_ONLY'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p98_p96_serial_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':p,'50':p50},sort_keys=True))
if __name__=='__main__': main()
