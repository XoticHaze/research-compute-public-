from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
import statsmodels.api as sm
U=('SPY','QQQ','TLT','GLD','DBC'); BP=50

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def build():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cutoff]; m=d.resample('ME').last(); dr=d.pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0. for s in U}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  b=pd.DataFrame({'mom6':mom.loc[dt,list(U)],'trend200':trend.loc[dt,list(U)],'low_vol6':-vol.loc[dt,list(U)],'drawdown6':dd.loc[dt,list(U)]},index=list(U))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); chosen=list(score.sort_values(ascending=False,kind='mergesort').head(2).index); nxt=m.index[i+1]; rr=m.loc[nxt,list(U)]/m.loc[dt,list(U)]-1
  if rr.isna().any(): continue
  w={s:(.5 if s in chosen else 0.) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); net=sum(w[s]*float(rr[s]) for s in U)-turn*BP/10000; ew=float(rr.mean()); rows.append({'date':nxt,'p46':net,'ew':ew,'excess':net-ew,'qqq':float(rr.QQQ),'spy':float(rr.SPY)}); prev=w
 return pd.DataFrame(rows).set_index('date'),d,cutoff
def fit(q,market):
 y=q.excess.astype(float); x=sm.add_constant(q[market].astype(float)); r=sm.OLS(y,x).fit(cov_type='HAC',cov_kwds={'maxlags':6}); alpha=float(r.params['const']); beta=float(r.params[market]); ap=float((1+alpha)**12-1) if alpha>-1 else None
 down=q[q[market]<0]; up=q[q[market]>=0]
 return {'months':len(q),'p46_cagr':cagr(q.p46),'equal_weight_cagr':cagr(q.ew),'raw_excess_cagr':cagr(q.p46)-cagr(q.ew),'market_cagr':cagr(q[market]),'monthly_alpha':alpha,'annualized_alpha_compound':ap,'alpha_hac_t':float(r.tvalues['const']),'alpha_hac_p':float(r.pvalues['const']),'beta':beta,'r2':float(r.rsquared),'mean_excess_down_market':float(down.excess.mean()) if len(down) else None,'mean_excess_up_market':float(up.excess.mean()) if len(up) else None,'positive_excess_month_fraction':float((q.excess>0).mean())}
def main():
 q,d,cut=build(); windows={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; tests={w:{m:fit(q.loc[pd.Timestamp(s):],m) for m in ('qqq','spy')} for w,s in windows.items()}; a=tests['2015']['qqq']; b=tests['2020']['qqq']; decision='P46_MATCHED_EXCESS_RETAINS_POSITIVE_MARKET_CONDITIONAL_ALPHA' if a['monthly_alpha']>0 and b['monthly_alpha']>0 and a['alpha_hac_t']>1.0 and b['alpha_hac_t']>1.0 else 'P46_MARKET_CONDITIONAL_ALPHA_NOT_ESTABLISHED'
 out={'schema':'research.p46_market_beta_attribution_r1','parent':'P46','hypothesis':'P46 after-cost excess over the same-universe equal-weight control retains a positive intercept after linear conditioning on QQQ/SPY monthly returns.','contract':{'p46':'original four-factor cross-asset top-2 monthly selector','cost_bps_turnover':BP,'dependent_variable':'P46 net monthly return minus same-universe equal-weight monthly return','market_controls':['QQQ','SPY'],'estimator':'OLS with Newey-West/HAC 6-month covariance','windows':list(windows),'no_signal_parameter_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_market_beta_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
