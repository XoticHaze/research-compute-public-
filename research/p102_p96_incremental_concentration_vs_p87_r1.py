from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CROSS=("VTI","VEA","IEF","IAU","GSG"); IND=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); ALL=tuple(dict.fromkeys((*CROSS,*IND,"SPY","QQQ"))); START="2007-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':float(d.min())}
def build():
 d=yf.download(list(ALL),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(ALL)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pc={s:0. for s in CROSS}; pi={s:0. for s in IND}; rows=[]
 for dt in m.index:
  bc=pd.DataFrame({'mom6':mom.loc[dt,list(CROSS)],'trend200':trend.loc[dt,list(CROSS)],'drawdown6':dd.loc[dt,list(CROSS)]},index=list(CROSS)); bi=pd.DataFrame({'mom6':mom.loc[dt,list(IND)],'trend200':trend.loc[dt,list(IND)],'low_vol6':-vol.loc[dt,list(IND)],'drawdown6':dd.loc[dt,list(IND)]},index=list(IND))
  if bc.isna().any().any() or bi.isna().any().any() or pd.isna(mom.loc[dt,'SPY']): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if r.isna().any(): continue
  cc=bc.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; ci=bi.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(3).index; wc={s:(.5 if s in cc else 0.) for s in CROSS}; wi={s:(1/3 if s in ci else 0.) for s in IND}; tc=.5*sum(abs(wc[s]-pc[s]) for s in CROSS); ti=.5*sum(abs(wi[s]-pi[s]) for s in IND); rows.append({'date':nxt,'cross_gross':sum(wc[s]*float(r[s]) for s in CROSS),'industry_gross':sum(wi[s]*float(r[s]) for s in IND),'cross_turn':tc,'industry_turn':ti,'state':'risk_on' if float(mom.loc[dt,'SPY'])>0 else 'risk_off'}); pc,pi=wc,wi
 return pd.DataFrame(rows).set_index('date')
def main():
 f=build(); tests={}
 for bps in (25,50):
  p87=f.cross_gross-f.cross_turn*bps/10000; p47=f.industry_gross-f.industry_turn*bps/10000; ens=.5*p87+.5*p47; inc=ens-p87; strongest=inc.nlargest(5); trimmed=inc.drop(strongest.index); states={}
  for state,idx in f.groupby('state').groups.items():
   e=ens.loc[idx]; b=p87.loc[idx]; states[state]={'months':len(idx),'annualized_mean_incremental':float((e-b).mean()*12),'ensemble':metrics(e),'p87':metrics(b),'positive_relative_month_fraction':float((e>b).mean())}
  tests[str(bps)]={'ensemble':metrics(ens),'p87':metrics(p87),'incremental_cagr_vs_p87':metrics(ens)['cagr']-metrics(p87)['cagr'],'states':states,'five_strongest_incremental_months_removed_annualized_mean':float(trimmed.mean()*12),'five_strongest_incremental_months':{str(k.date()):float(v) for k,v in strongest.items()}}
 p=tests['25']; p50=tests['50']; ok=p['five_strongest_incremental_months_removed_annualized_mean']>0 and p50['five_strongest_incremental_months_removed_annualized_mean']>0 and p['states']['risk_on']['annualized_mean_incremental']>0 and p['states']['risk_off']['annualized_mean_incremental']>0
 out={'schema':'research.p102_p96_incremental_concentration_vs_p87_r1','parent_ids':['P47','P87','P96','P98','P99','P102'],'contract':{'ensemble':'frozen 50/50 P87/P47','comparator':'frozen P87','state':'prior SPY 6m return sign','concentration':'remove five strongest ensemble-minus-P87 months','costs_bps':[25,50],'no_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':tests,'decision':'P47_ADDITION_TO_P87_BROAD_INCREMENTAL_DIVERSIFICATION' if ok else 'P47_ADDITION_INCREMENTAL_VALUE_CONCENTRATED_RESEARCH_CAUTION'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p102_p96_incremental_concentration_vs_p87_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':{'incremental_cagr':p['incremental_cagr_vs_p87'],'states':p['states'],'trimmed':p['five_strongest_incremental_months_removed_annualized_mean']},'50':{'incremental_cagr':p50['incremental_cagr_vs_p87'],'states':p50['states'],'trimmed':p50['five_strongest_incremental_months_removed_annualized_mean']}},sort_keys=True))
if __name__=='__main__': main()
