from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("SPY","QQQ","TLT","GLD","DBC"); START="2006-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':m}
def folds(c,b):
 out=[]
 for idx in np.array_split(np.arange(len(c)),5): out.append(metrics(c.iloc[idx])['cagr']-metrics(b.iloc[idx])['cagr'])
 return sum(x>0 for x in out),out
def main():
 d=yf.download(list(SYMS),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(SYMS)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pa={s:0. for s in SYMS}; ph={s:0. for s in SYMS}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any() or pd.isna(mom.loc[dt,'SPY']): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1
  if r.isna().any(): continue
  chosen=b.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; wa={s:(.5 if s in chosen else 0.) for s in SYMS}; risk_on=float(mom.loc[dt,'SPY'])>0; wh=wa if risk_on else {s:.2 for s in SYMS}; ta=.5*sum(abs(wa[s]-pa[s]) for s in SYMS); th=.5*sum(abs(wh[s]-ph[s]) for s in SYMS); rows.append({'date':nxt,'active':sum(wa[s]*float(r[s]) for s in SYMS),'hybrid':sum(wh[s]*float(r[s]) for s in SYMS),'ta':ta,'th':th,'ew':float(r.mean()),'spy':float(r['SPY']),'qqq':float(r['QQQ'])}); pa,ph=wa,wh
 f=pd.DataFrame(rows).set_index('date'); tests={}
 for bps in (25,50):
  a=f.active-f.ta*bps/10000; h=f.hybrid-f.th*bps/10000; ew=f.ew; hm,am,em=metrics(h),metrics(a),metrics(ew); p,fs=folds(h,a); tests[str(bps)]={'hybrid':hm,'base_three_factor':am,'matched_ew':em,'excess_cagr_vs_base':hm['cagr']-am['cagr'],'excess_cagr_vs_ew':hm['cagr']-em['cagr'],'positive_folds_vs_base':p,'folds_vs_base':fs,'spy':metrics(f.spy),'qqq':metrics(f.qqq)}
 p=tests['25']; p50=tests['50']; ok=p['excess_cagr_vs_base']>0 and p['positive_folds_vs_base']>=3 and p50['excess_cagr_vs_ew']>0
 out={'schema':'research.p97_p95_original_replication_r1','parent_ids':['P46','P87','P95','P97'],'contract':{'representation':SYMS,'mutation':'same P95 prior-SPY-6m risk-off deactivation to exact equal weight','costs_bps':[25,50],'no_parameter_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':tests,'decision':'SUPPORTED_P95_MUTATION_IN_ORIGINAL_REPRESENTATION' if ok else 'P95_MUTATION_NOT_REPLICATED_KEEP_AS_RESEARCH_ONLY'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p97_p95_original_replication_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':{'excess_vs_base':p['excess_cagr_vs_base'],'excess_vs_ew':p['excess_cagr_vs_ew'],'folds':p['positive_folds_vs_base'],'hybrid':p['hybrid'],'base':p['base_three_factor']},'50':{'excess_vs_base':p50['excess_cagr_vs_base'],'excess_vs_ew':p50['excess_cagr_vs_ew']}},sort_keys=True))
if __name__=='__main__': main()
