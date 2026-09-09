from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CROSS=("VTI","VEA","IEF","IAU","GSG"); IND=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); ALL=tuple(dict.fromkeys((*CROSS,*IND,"SPY","QQQ"))); START="2007-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else None}
def folds(a,b,n=3):
 out=[]
 for k,idx in enumerate(np.array_split(np.arange(len(a)),n),1):
  if len(idx)==0: continue
  am,bm=metrics(a.iloc[idx]),metrics(b.iloc[idx]); out.append({'fold':k,'excess_cagr':am['cagr']-bm['cagr']})
 return sum(x['excess_cagr']>0 for x in out),out
def build():
 d=yf.download(list(ALL),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(ALL)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pc={s:0. for s in CROSS}; pi={s:0. for s in IND}; rows=[]
 for dt in m.index:
  bc=pd.DataFrame({'mom6':mom.loc[dt,list(CROSS)],'trend200':trend.loc[dt,list(CROSS)],'drawdown6':dd.loc[dt,list(CROSS)]},index=list(CROSS)); bi=pd.DataFrame({'mom6':mom.loc[dt,list(IND)],'trend200':trend.loc[dt,list(IND)],'low_vol6':-vol.loc[dt,list(IND)],'drawdown6':dd.loc[dt,list(IND)]},index=list(IND))
  if bc.isna().any().any() or bi.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if r.isna().any(): continue
  cc=bc.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; ci=bi.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(3).index; wc={s:(.5 if s in cc else 0.) for s in CROSS}; wi={s:(1/3 if s in ci else 0.) for s in IND}; tc=.5*sum(abs(wc[s]-pc[s]) for s in CROSS); ti=.5*sum(abs(wi[s]-pi[s]) for s in IND); rows.append({'date':nxt,'cross_gross':sum(wc[s]*float(r[s]) for s in CROSS),'industry_gross':sum(wi[s]*float(r[s]) for s in IND),'cross_turn':tc,'industry_turn':ti,'combined_control':.5*float(r.loc[list(CROSS)].mean())+.5*float(r.loc[list(IND)].mean()),'spy':float(r['SPY']),'qqq':float(r['QQQ'])}); pc,pi=wc,wi
 return pd.DataFrame(rows).set_index('date')
def main():
 f=build(); out={'schema':'research.p103_p96_late_era_holdout_r1','parent_ids':['P47','P87','P96','P98','P99','P102','P103'],'contract':{'ensemble':'frozen 50/50 P87/P47','holdouts':['2015-01-31','2020-01-31'],'costs_bps':[25,50],'matched_control':'frozen 50/50 exact representation equal weights','comparators':['P87','P47','SPY','QQQ'],'chronological_folds_per_holdout':3,'no_factor_horizon_topk_weight_tuning':True},'results':{}}
 for start in ('2015-01-31','2020-01-31'):
  g=f.loc[f.index>=pd.Timestamp(start)].copy(); rec={'window':{'start':str(g.index.min().date()),'end':str(g.index.max().date()),'months':len(g)}}
  for bps in (25,50):
   p87=g.cross_gross-g.cross_turn*bps/10000; p47=g.industry_gross-g.industry_turn*bps/10000; ens=.5*p87+.5*p47; ctrl=g.combined_control; em,cm,rm,im=metrics(ens),metrics(ctrl),metrics(p87),metrics(p47); pc,fc=folds(ens,ctrl); pr,fr=folds(ens,p87); rec[str(bps)]={'ensemble':em,'combined_control':cm,'p87':rm,'p47':im,'spy':metrics(g.spy),'qqq':metrics(g.qqq),'excess_cagr_vs_control':em['cagr']-cm['cagr'],'incremental_cagr_vs_p87':em['cagr']-rm['cagr'],'incremental_cagr_vs_p47':em['cagr']-im['cagr'],'positive_folds_vs_control':pc,'folds_vs_control':fc,'positive_folds_vs_p87':pr,'folds_vs_p87':fr}
  out['results'][start]=rec
 a=out['results']['2015-01-31']; b=out['results']['2020-01-31']; ok=all(x[c]['excess_cagr_vs_control']>0 and x[c]['incremental_cagr_vs_p87']>0 for x in (a,b) for c in ('25','50')) and a['25']['positive_folds_vs_control']>=2 and b['25']['positive_folds_vs_control']>=2
 out['decision']='P96_LATE_ERA_INCREMENTAL_DIVERSIFICATION_CONFIRMED_RESEARCH_ONLY' if ok else 'P96_LATE_ERA_SUPPORT_MIXED_PARK_FOR_INDEPENDENT_SOURCE_OR_TRUE_OOS'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p103_p96_late_era_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'results':{k:{'window':v['window'],'25':{'excess_vs_control':v['25']['excess_cagr_vs_control'],'incremental_vs_p87':v['25']['incremental_cagr_vs_p87'],'folds_vs_control':v['25']['positive_folds_vs_control'],'ensemble':v['25']['ensemble']},'50':{'excess_vs_control':v['50']['excess_cagr_vs_control'],'incremental_vs_p87':v['50']['incremental_cagr_vs_p87']}} for k,v in out['results'].items()}},sort_keys=True))
if __name__=='__main__': main()
