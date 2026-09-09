from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("VTI","VEA","IEF","IAU","GSG"); REQ=(*SYMS,"SPY","QQQ"); START="2007-01-01"; HOLDOUT=pd.Timestamp('2022-01-01')
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else float('nan')}
def folds(c,b):
 z=[]
 for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
  x,y=metrics(c.iloc[idx]),metrics(b.iloc[idx]); z.append({'fold':n,'excess_cagr':x['cagr']-y['cagr']})
 return sum(a['excess_cagr']>0 for a in z),z
def main():
 d=yf.download(list(REQ),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(REQ)].dropna(how='all').astype(float); m=close.resample('ME').last(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); tr=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); p3={s:0. for s in SYMS}; p4={s:0. for s in SYMS}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':tr.loc[dt,list(SYMS)],'low_vol6':-vol.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(REQ)]/m.loc[dt,list(REQ)]-1
  if r.isna().any(): continue
  s4=b.rank(axis=0,pct=True,method='average').mean(axis=1); s3=b[['mom6','trend200','drawdown6']].rank(axis=0,pct=True,method='average').mean(axis=1); c4=s4.sort_values(ascending=False).head(2).index; c3=s3.sort_values(ascending=False).head(2).index; w4={s:(.5 if s in c4 else 0.) for s in SYMS}; w3={s:(.5 if s in c3 else 0.) for s in SYMS}; t4=.5*sum(abs(w4[s]-p4[s]) for s in SYMS); t3=.5*sum(abs(w3[s]-p3[s]) for s in SYMS); rows.append({'date':nxt,'g3':sum(w3[s]*float(r[s]) for s in SYMS),'g4':sum(w4[s]*float(r[s]) for s in SYMS),'t3':t3,'t4':t4,'ew':float(r.loc[list(SYMS)].mean()),'spy':float(r.SPY),'qqq':float(r.QQQ)}); p3,p4=w3,w4
 f=pd.DataFrame(rows).set_index('date'); f=f.loc[f.index>=HOLDOUT]; costs={}
 for bps in (25,50,100):
  c3=f.g3-f.t3*bps/10000; c4=f.g4-f.t4*bps/10000; m3,m4,me=metrics(c3),metrics(c4),metrics(f.ew); pe,fe=folds(c3,f.ew); p4c,f4=folds(c3,c4); costs[str(bps)]={'three_factor':m3,'four_factor':m4,'matched_equal_weight':me,'spy':metrics(f.spy),'qqq':metrics(f.qqq),'excess_cagr_vs_equal_weight':m3['cagr']-me['cagr'],'excess_cagr_vs_four_factor':m3['cagr']-m4['cagr'],'excess_cagr_vs_spy':m3['cagr']-metrics(f.spy)['cagr'],'excess_cagr_vs_qqq':m3['cagr']-metrics(f.qqq)['cagr'],'positive_folds_vs_equal_weight':pe,'positive_folds_vs_four_factor':p4c,'folds_vs_equal_weight':fe,'folds_vs_four_factor':f4}
 c50=costs['50']; c100=costs['100']; ok=c50['excess_cagr_vs_equal_weight']>0 and c50['excess_cagr_vs_four_factor']>0 and c50['positive_folds_vs_equal_weight']>=3 and c100['excess_cagr_vs_equal_weight']>0
 out={'schema':'research.p87_2022_forward_holdout_r1','parent_ids':['P46','P87'],'scientific_contract':{'holdout':'2022-forward','representation':list(SYMS),'three_factor':'6m momentum + SMA200 trend + 6m drawdown rank','four_factor_comparator':'same representation with original low-vol included','matched_control':'same-universe equal weight','costs_bps':[25,50,100],'no_parameter_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'costs':costs,'decision':'P87_RECENT_HOLDOUT_SUPPORTED' if ok else 'P87_RECENT_HOLDOUT_REQUIRES_CAUTION'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p87_2022_forward_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print('P87_2022_FORWARD='+json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
