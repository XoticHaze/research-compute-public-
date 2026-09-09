from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC'); BP=50; REPS=5000; BLOCK=6; SEED=460131

def build():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]; m=d.resample('ME').last(); dr=d.pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0. for s in U}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  b=pd.DataFrame({'mom6':mom.loc[dt,list(U)],'trend200':trend.loc[dt,list(U)],'low_vol6':-vol.loc[dt,list(U)],'drawdown6':dd.loc[dt,list(U)]},index=list(U))
  if b.isna().any().any(): continue
  chosen=list(b.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False,kind='mergesort').head(2).index); nxt=m.index[i+1]; rr=m.loc[nxt,list(U)]/m.loc[dt,list(U)]-1
  if rr.isna().any(): continue
  w={s:(.5 if s in chosen else 0.) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); net=sum(w[s]*float(rr[s]) for s in U)-turn*BP/10000; rows.append({'date':nxt,'excess':net-float(rr.mean()),'qqq':float(rr.QQQ),'spy':float(rr.SPY)}); prev=w
 return pd.DataFrame(rows).set_index('date'),d,cut
def alpha(y,x):
 X=np.column_stack([np.ones(len(x)),x]); return float(np.linalg.lstsq(X,y,rcond=None)[0][0])
def boot(q,market):
 a=q[['excess',market]].to_numpy(float); n=len(a); rng=np.random.default_rng(SEED+(1 if market=='spy' else 0)+n); starts=np.arange(0,n-BLOCK+1); vals=[]; means=[]
 for _ in range(REPS):
  ix=[]
  while len(ix)<n:
   s=int(rng.choice(starts)); ix.extend(range(s,s+BLOCK))
  z=a[np.array(ix[:n])]; vals.append(alpha(z[:,0],z[:,1])); means.append(float(z[:,0].mean()))
 vals=np.array(vals); means=np.array(means); obs=alpha(a[:,0],a[:,1]); return {'months':n,'observed_monthly_alpha':obs,'annualized_alpha_compound':float((1+obs)**12-1),'p_alpha_le_zero':float((vals<=0).mean()),'alpha_p05':float(np.quantile(vals,.05)),'alpha_p50':float(np.quantile(vals,.5)),'alpha_p95':float(np.quantile(vals,.95)),'p_mean_matched_excess_le_zero':float((means<=0).mean()),'mean_excess_p05':float(np.quantile(means,.05)),'block_months':BLOCK,'replications':REPS}
def main():
 q,d,cut=build(); tests={w:{m:boot(q.loc[pd.Timestamp(s):],m) for m in ('qqq','spy')} for w,s in {'2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['qqq']; b=tests['2020']['qqq']; decision='P46_MARKET_CONDITIONAL_ALPHA_BOOTSTRAP_SUPPORTED' if a['p_alpha_le_zero']<.10 and b['p_alpha_le_zero']<.10 and a['p_mean_matched_excess_le_zero']<.10 and b['p_mean_matched_excess_le_zero']<.10 else 'P46_MARKET_CONDITIONAL_ALPHA_BOOTSTRAP_INCONCLUSIVE'
 out={'schema':'research.p46_alpha_block_bootstrap_r1','parent':'P46','hypothesis':'Positive P46 matched-excess intercept under QQQ/SPY conditioning survives joint moving-block resampling of monthly observations.','contract':{'block_months':BLOCK,'replications':REPS,'seed':SEED,'windows':['2015','2020'],'controls':['QQQ','SPY'],'cost_bps_turnover':BP,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_alpha_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
