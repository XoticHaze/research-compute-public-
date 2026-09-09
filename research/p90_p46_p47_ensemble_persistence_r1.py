from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CROSS=("SPY","QQQ","TLT","GLD","DBC"); IND=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); ALL=tuple(dict.fromkeys((*CROSS,*IND))); START="2006-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else float('nan')}
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
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
 d=yf.download(list(ALL),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(ALL)].dropna(how='all').astype(float); m=close.resample('ME').last(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pc={s:0. for s in CROSS}; pi={s:0. for s in IND}; rows=[]
 for dt in m.index:
  bc=pd.DataFrame({'mom6':mom.loc[dt,list(CROSS)],'trend200':trend.loc[dt,list(CROSS)],'low_vol6':-vol.loc[dt,list(CROSS)],'drawdown6':dd.loc[dt,list(CROSS)]},index=list(CROSS)); bi=pd.DataFrame({'mom6':mom.loc[dt,list(IND)],'trend200':trend.loc[dt,list(IND)],'low_vol6':-vol.loc[dt,list(IND)],'drawdown6':dd.loc[dt,list(IND)]},index=list(IND))
  if bc.isna().any().any() or bi.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if r.isna().any(): continue
  cc=bc.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; ci=bi.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(3).index; wc={s:(.5 if s in cc else 0.) for s in CROSS}; wi={s:(1/3 if s in ci else 0.) for s in IND}; tc=.5*sum(abs(wc[s]-pc[s]) for s in CROSS); ti=.5*sum(abs(wi[s]-pi[s]) for s in IND); gc=sum(wc[s]*float(r[s]) for s in CROSS); gi=sum(wi[s]*float(r[s]) for s in IND); rows.append({'date':nxt,'cross_gross':gc,'industry_gross':gi,'cross_turnover':tc,'industry_turnover':ti,'control':.5*float(r.loc[list(CROSS)].mean())+.5*float(r.loc[list(IND)].mean())}); pc,pi=wc,wi
 return pd.DataFrame(rows).set_index('date')
def main():
 f=build(); tests={}
 for bps in (25,50):
  cross=f.cross_gross-f.cross_turnover*bps/10000; industry=f.industry_gross-f.industry_turnover*bps/10000; ensemble=.5*cross+.5*industry; ctrl=f.control; tests[str(bps)]={'ensemble':metrics(ensemble),'cross_parent':metrics(cross),'matched_combined_control':metrics(ctrl),'vs_control':{'rolling36':rolling(ensemble,ctrl,36),'rolling60':rolling(ensemble,ctrl,60),'bootstrap':bootstrap(ensemble,ctrl)},'vs_cross_parent':{'rolling36':rolling(ensemble,cross,36),'rolling60':rolling(ensemble,cross,60),'bootstrap':bootstrap(ensemble,cross)}}
 p=tests['25']; p50=tests['50']; supported=p['vs_control']['rolling60']['positive_fraction']>=.6 and p['vs_control']['bootstrap']['p_excess_le_zero']<=.2 and p50['vs_control']['bootstrap']['annualized_mean_excess']>0 and p['vs_cross_parent']['rolling60']['positive_fraction']>=.5
 out={'schema':'research.p90_p46_p47_ensemble_persistence_r1','parent_ids':['P46','P47','P89','P90'],'scientific_contract':{'ensemble':'frozen research-only 50/50 P46/P47 net return streams','comparators':['exact combined equal-weight control','P46 alone'],'costs_bps':[25,50],'rolling_windows_months':[36,60],'bootstrap':'12m moving block 5000 reps deterministic seed','no_allocation_weight_tuning':True,'no_portfolio_authority':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':tests,'decision':'SUPPORTED_ENSEMBLE_SERIAL_PERSISTENCE_RESEARCH_ONLY' if supported else 'ENSEMBLE_PERSISTENCE_INSUFFICIENT_KEEP_P46_PRIMARY'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p90_p46_p47_ensemble_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'25_vs_control':p['vs_control'],'25_vs_cross':p['vs_cross_parent'],'50_vs_control':p50['vs_control'],'window':out['window']},sort_keys=True))
if __name__=='__main__': main()
