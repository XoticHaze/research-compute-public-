from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("VTI","VEA","IEF","IAU","GSG"); REQ=(*SYMS,"SPY","QQQ"); START="2007-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else None}
def folds(c,b):
 out=[]
 for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
  x=metrics(c.iloc[idx]); y=metrics(b.iloc[idx]); out.append({'fold':n,'excess_cagr':x['cagr']-y['cagr']})
 return sum(x['excess_cagr']>0 for x in out),out
def build():
 d=yf.download(list(REQ),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(REQ)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pa={s:0. for s in SYMS}; ph={s:0. for s in SYMS}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any() or pd.isna(mom.loc[dt,'SPY']): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(REQ)]/m.loc[dt,list(REQ)]-1
  if r.isna().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); chosen=score.sort_values(ascending=False).head(2).index; wa={s:(.5 if s in chosen else 0.) for s in SYMS}; risk_on=float(mom.loc[dt,'SPY'])>0; wh=wa if risk_on else {s:1/len(SYMS) for s in SYMS}; ta=.5*sum(abs(wa[s]-pa[s]) for s in SYMS); th=.5*sum(abs(wh[s]-ph[s]) for s in SYMS); rows.append({'date':nxt,'active_gross':sum(wa[s]*float(r[s]) for s in SYMS),'hybrid_gross':sum(wh[s]*float(r[s]) for s in SYMS),'active_turn':ta,'hybrid_turn':th,'ew':float(r.loc[list(SYMS)].mean()),'spy':float(r['SPY']),'qqq':float(r['QQQ']),'state':'risk_on' if risk_on else 'risk_off'}); pa,ph=wa,wh
 return pd.DataFrame(rows).set_index('date')
def main():
 f=build(); tests={}
 for bps in (25,50):
  active=f.active_gross-f.active_turn*bps/10000; hybrid=f.hybrid_gross-f.hybrid_turn*bps/10000; ew=f.ew; hm=metrics(hybrid); am=metrics(active); em=metrics(ew); p,fs=folds(hybrid,active); pe,fe=folds(hybrid,ew); tests[str(bps)]={'hybrid':hm,'original_p87':am,'matched_equal_weight':em,'spy':metrics(f.spy),'qqq':metrics(f.qqq),'excess_cagr_vs_p87':hm['cagr']-am['cagr'],'excess_cagr_vs_ew':hm['cagr']-em['cagr'],'positive_folds_vs_p87':p,'folds_vs_p87':fs,'positive_folds_vs_ew':pe,'folds_vs_ew':fe,'annual_turnover_hybrid':float(f.hybrid_turn.mean()*12),'annual_turnover_p87':float(f.active_turn.mean()*12)}
 p=tests['25']; p50=tests['50']; supported=p['excess_cagr_vs_p87']>0 and p['positive_folds_vs_p87']>=3 and p['excess_cagr_vs_ew']>0 and p50['excess_cagr_vs_ew']>0
 out={'schema':'research.p95_p87_riskoff_deactivation_r1','parent_ids':['P46','P87','P91','P92','P95'],'contract':{'mechanism':'P87 unchanged in prior-SPY-6m-positive months; exact same-universe equal weight in non-positive months','trigger_origin':'predeclared P92 state attribution, itself inherited from established P46 regime definition','costs_bps':[25,50],'no_factor_horizon_topk_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'state_months':{k:int(v) for k,v in f.state.value_counts().items()},'tests':tests,'decision':'SUPPORTED_P87_RISKOFF_DEACTIVATION_MUTATION_REQUIRES_INDEPENDENT_CONFIRMATION' if supported else 'P87_RISKOFF_DEACTIVATION_NOT_INCREMENTAL_KEEP_FROZEN_P87'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p95_p87_riskoff_deactivation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'states':out['state_months'],'25':{'excess_vs_p87':p['excess_cagr_vs_p87'],'excess_vs_ew':p['excess_cagr_vs_ew'],'folds_vs_p87':p['positive_folds_vs_p87'],'hybrid':p['hybrid'],'p87':p['original_p87'],'turn_hybrid':p['annual_turnover_hybrid'],'turn_p87':p['annual_turnover_p87']},'50':{'excess_vs_ew':p50['excess_cagr_vs_ew'],'excess_vs_p87':p50['excess_cagr_vs_p87']}},sort_keys=True))
if __name__=='__main__': main()
