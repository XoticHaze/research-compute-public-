from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CROSS=("VTI","VEA","IEF","IAU","GSG"); IND=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); ALL=tuple(dict.fromkeys((*CROSS,*IND,"SPY","QQQ"))); START="2007-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':m}
def build():
 d=yf.download(list(ALL),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(ALL)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pc={s:0. for s in CROSS}; pi={s:0. for s in IND}; rows=[]
 for dt in m.index:
  bc=pd.DataFrame({'mom6':mom.loc[dt,list(CROSS)],'trend200':trend.loc[dt,list(CROSS)],'drawdown6':dd.loc[dt,list(CROSS)]},index=list(CROSS)); bi=pd.DataFrame({'mom6':mom.loc[dt,list(IND)],'trend200':trend.loc[dt,list(IND)],'low_vol6':-vol.loc[dt,list(IND)],'drawdown6':dd.loc[dt,list(IND)]},index=list(IND))
  if bc.isna().any().any() or bi.isna().any().any() or pd.isna(mom.loc[dt,'SPY']): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if r.isna().any(): continue
  cc=bc.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; ci=bi.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(3).index; wc={s:(.5 if s in cc else 0.) for s in CROSS}; wi={s:(1/3 if s in ci else 0.) for s in IND}; tc=.5*sum(abs(wc[s]-pc[s]) for s in CROSS); ti=.5*sum(abs(wi[s]-pi[s]) for s in IND); rows.append({'date':nxt,'cross_gross':sum(wc[s]*float(r[s]) for s in CROSS),'industry_gross':sum(wi[s]*float(r[s]) for s in IND),'cross_turn':tc,'industry_turn':ti,'control':.5*float(r.loc[list(CROSS)].mean())+.5*float(r.loc[list(IND)].mean()),'spy':float(r['SPY']),'qqq':float(r['QQQ']),'state':'risk_on' if float(mom.loc[dt,'SPY'])>0 else 'risk_off'}); pc,pi=wc,wi
 return pd.DataFrame(rows).set_index('date')
def main():
 f=build(); tests={}
 for bps in (25,50):
  ens=.5*(f.cross_gross-f.cross_turn*bps/10000)+.5*(f.industry_gross-f.industry_turn*bps/10000); ctrl=f.control; ex=ens-ctrl; strongest=ex.nlargest(5); trimmed=ex.drop(strongest.index); states={}
  for state,gidx in f.groupby('state').groups.items():
   e=ens.loc[gidx]; c=ctrl.loc[gidx]; states[state]={'months':len(gidx),'annualized_mean_excess':float((e-c).mean()*12),'strategy':metrics(e),'control':metrics(c),'positive_relative_month_fraction':float((e>c).mean())}
  tests[str(bps)]={'ensemble':metrics(ens),'control':metrics(ctrl),'excess_cagr_vs_control':metrics(ens)['cagr']-metrics(ctrl)['cagr'],'states':states,'five_strongest_removed_annualized_mean_excess':float(trimmed.mean()*12),'five_strongest_months':{str(k.date()):float(v) for k,v in strongest.items()},'trimmed_positive':float(trimmed.mean()*12)>0}
 p=tests['25']; p50=tests['50']; ok=p['five_strongest_removed_annualized_mean_excess']>0 and p50['five_strongest_removed_annualized_mean_excess']>0 and p['states']['risk_on']['annualized_mean_excess']>0 and p['states']['risk_off']['annualized_mean_excess']>0
 out={'schema':'research.p99_p96_concentration_state_r1','parent_ids':['P47','P87','P96','P98','P99'],'contract':{'ensemble':'frozen 50/50 P87/P47','state':'prior SPY 6m return sign','concentration':'remove five strongest ensemble-minus-exact-control months','costs_bps':[25,50],'no_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':tests,'decision':'P96_EDGE_BROAD_ACROSS_STATES_AND_NOT_EXTREME_MONTH_DEPENDENT' if ok else 'P96_EDGE_CONCENTRATED_OR_STATE_DEPENDENT_RESEARCH_CAUTION'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p99_p96_concentration_state_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':{'excess':p['excess_cagr_vs_control'],'states':p['states'],'trimmed':p['five_strongest_removed_annualized_mean_excess']},'50':{'excess':p50['excess_cagr_vs_control'],'states':p50['states'],'trimmed':p50['five_strongest_removed_annualized_mean_excess']}},sort_keys=True))
if __name__=='__main__': main()
