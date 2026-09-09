from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CROSS=("VTI","VEA","IEF","IAU","GSG"); IND=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); ALL=tuple(dict.fromkeys((*CROSS,*IND,"SPY","QQQ"))); START="2007-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else None}
def folds(c,b):
 out=[]
 for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
  x=metrics(c.iloc[idx]); y=metrics(b.iloc[idx]); out.append({'fold':n,'excess_cagr':x['cagr']-y['cagr']})
 return sum(x['excess_cagr']>0 for x in out),out
def main():
 d=yf.download(list(ALL),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(ALL)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pc={s:0. for s in CROSS}; pi={s:0. for s in IND}; rows=[]
 for dt in m.index:
  bc=pd.DataFrame({'mom6':mom.loc[dt,list(CROSS)],'trend200':trend.loc[dt,list(CROSS)],'drawdown6':dd.loc[dt,list(CROSS)]},index=list(CROSS)); bi=pd.DataFrame({'mom6':mom.loc[dt,list(IND)],'trend200':trend.loc[dt,list(IND)],'low_vol6':-vol.loc[dt,list(IND)],'drawdown6':dd.loc[dt,list(IND)]},index=list(IND))
  if bc.isna().any().any() or bi.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if r.isna().any(): continue
  cc=bc.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; ci=bi.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(3).index; wc={s:(.5 if s in cc else 0.) for s in CROSS}; wi={s:(1/3 if s in ci else 0.) for s in IND}; tc=.5*sum(abs(wc[s]-pc[s]) for s in CROSS); ti=.5*sum(abs(wi[s]-pi[s]) for s in IND); gc=sum(wc[s]*float(r[s]) for s in CROSS); gi=sum(wi[s]*float(r[s]) for s in IND); rows.append({'date':nxt,'cross_gross':gc,'industry_gross':gi,'cross_turn':tc,'industry_turn':ti,'control':.5*float(r.loc[list(CROSS)].mean())+.5*float(r.loc[list(IND)].mean()),'spy':float(r['SPY']),'qqq':float(r['QQQ'])}); pc,pi=wc,wi
 f=pd.DataFrame(rows).set_index('date'); tests={}
 for bps in (25,50):
  cross=f.cross_gross-f.cross_turn*bps/10000; ind=f.industry_gross-f.industry_turn*bps/10000; ens=.5*cross+.5*ind; ctrl=f.control; em=metrics(ens); cm=metrics(cross); im=metrics(ind); bm=metrics(ctrl); p,fs=folds(ens,ctrl); px,fx=folds(ens,cross); tests[str(bps)]={'ensemble':em,'p87_cross_parent':cm,'p47_industry_parent':im,'matched_combined_control':bm,'spy':metrics(f.spy),'qqq':metrics(f.qqq),'excess_cagr_vs_control':em['cagr']-bm['cagr'],'excess_cagr_vs_p87':em['cagr']-cm['cagr'],'positive_folds_vs_control':p,'folds_vs_control':fs,'positive_folds_vs_p87':px,'folds_vs_p87':fx,'parent_return_correlation':float(cross.corr(ind))}
 p=tests['25']; p50=tests['50']; support=p['excess_cagr_vs_control']>0 and p['positive_folds_vs_control']>=3 and p50['excess_cagr_vs_control']>0 and p['ensemble']['max_drawdown_monthly']>=min(p['p87_cross_parent']['max_drawdown_monthly'],p['p47_industry_parent']['max_drawdown_monthly'])
 out={'schema':'research.p96_p87_p47_ensemble_r1','parent_ids':['P47','P87','P89','P90','P96'],'contract':{'scope':'research-only fixed 50/50 combination; no portfolio authority','cross_parent':'frozen P87 three-factor top2 VTI/VEA/IEF/IAU/GSG','industry_parent':'frozen P47 four-factor top3 industry','matched_control':'50/50 exact equal-weight controls of each representation','costs_bps':[25,50],'no_weight_or_parent_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':tests,'decision':'SUPPORTED_P87_P47_RESEARCH_ENSEMBLE_REQUIRES_SERIAL_TEST' if support else 'P87_P47_ENSEMBLE_NOT_ADDITIVE_KEEP_P87_PRIMARY'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p96_p87_p47_ensemble_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':{'ensemble':p['ensemble'],'p87':p['p87_cross_parent'],'p47':p['p47_industry_parent'],'excess_vs_control':p['excess_cagr_vs_control'],'excess_vs_p87':p['excess_cagr_vs_p87'],'folds_control':p['positive_folds_vs_control'],'folds_p87':p['positive_folds_vs_p87'],'correlation':p['parent_return_correlation']},'50':{'excess_vs_control':p50['excess_cagr_vs_control'],'excess_vs_p87':p50['excess_cagr_vs_p87']}},sort_keys=True))
if __name__=='__main__': main()
