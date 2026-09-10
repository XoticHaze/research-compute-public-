from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
from numpy.linalg import lstsq
SYMS=['SPMO','SPY','XLK','QQQ']; START='2017-01-01'; END='2026-09-11'; WINDOWS={'2017':'2017-01-01','2020':'2020-01-01','2023':'2023-01-01'}
def nw_tstat(y,X,lags=3):
 n=len(y); beta=lstsq(X,y,rcond=None)[0]; u=y-X@beta; xu=X*u[:,None]; S=xu.T@xu
 for l in range(1,min(lags,n-1)+1):
  w=1-l/(lags+1); G=xu[l:].T@xu[:-l]; S += w*(G+G.T)
 XXi=np.linalg.pinv(X.T@X); cov=XXi@S@XXi; se=np.sqrt(np.clip(np.diag(cov),0,None)); return beta, np.divide(beta,se,out=np.full_like(beta,np.nan),where=se>0)
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for name,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)].dropna(); y=(z.SPMO-z.SPY).to_numpy(); tech=(z.XLK-z.SPY).to_numpy(); growth=(z.QQQ-z.SPY).to_numpy(); X=np.column_stack([np.ones(len(z)),tech,growth]); b,t=nw_tstat(y,X,3); results[name]={'months':len(z),'annualized_residual_alpha':float(b[0]*12),'nw_tstat_alpha':float(t[0]),'beta_tech_minus_spy':float(b[1]),'beta_qqq_minus_spy':float(b[2]),'raw_spmo_minus_spy_annualized_mean':float(y.mean()*12)}
p=results['2017']; q=results['2020']; s=results['2023']; ok=p['annualized_residual_alpha']>0 and q['annualized_residual_alpha']>0 and s['annualized_residual_alpha']>=0 and p['nw_tstat_alpha']>=1.0
out={'schema':'research.spmo_tech_attribution_r1','workload_id':'SPMO_TECH_ATTRIBUTION_R1','parent_context':'SPMO_SURVIVOR','claim':'Test whether SPMO broad-market excess is fully explained by static exposure to technology and growth leadership, using unchanged monthly returns and a fixed regression of SPMO-SPY on XLK-SPY and QQQ-SPY.','parameters':{'windows':WINDOWS,'regressors':['intercept','XLK-SPY','QQQ-SPY'],'newey_west_lags':3,'no_regressor_or_window_search':True},'results':results,'decision_rule':'Residual-evidence support requires positive annualized intercept in 2017+ and 2020+, nonnegative 2023+ intercept, and 2017+ Newey-West alpha t-stat >=1.0. Failure narrows the SPMO claim toward tech/growth exposure; it does not kill prior matched-return evidence by itself.','decision':'SPMO_EXCESS_NOT_FULLY_EXPLAINED_BY_TECH_GROWTH' if ok else 'SPMO_EXCESS_TECH_GROWTH_ATTRIBUTION_NOT_REJECTED','limitations':['attribution is linear and monthly; it does not identify holdings-level security selection','QQQ and XLK are investable exposure proxies rather than exhaustive factor models','scientific attribution only; no portfolio-ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/spmo_tech_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
