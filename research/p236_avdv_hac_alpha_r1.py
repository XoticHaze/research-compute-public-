import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['AVDV','VSS']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; L=3; B=10
def nw(y,x,lag=L):
 d=pd.concat([y.rename('y'),x.rename('x')],axis=1).dropna(); yy=d.y.to_numpy(float); xx=d.x.to_numpy(float); X=np.column_stack([np.ones(len(d)),xx]); inv=np.linalg.pinv(X.T@X); beta=inv@(X.T@yy); u=yy-X@beta; S=np.zeros((2,2))
 for t in range(len(d)): S += u[t]**2*np.outer(X[t],X[t])
 for l in range(1,min(lag,len(d)-1)+1):
  w=1-l/(lag+1); G=np.zeros((2,2))
  for t in range(l,len(d)): G += u[t]*u[t-l]*np.outer(X[t],X[t-l])
  S += w*(G+G.T)
 cov=inv@S@inv; se=float(np.sqrt(max(cov[0,0],0))); return {'rows':len(d),'alpha_ann':float(beta[0]*12),'alpha_t_hac':float(beta[0]/se) if se else None,'beta':float(beta[1]),'nw_lag':lag}
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={}
for k,s in W.items():
 d=r.loc[pd.Timestamp(s):].copy(); d.iloc[0]-=B/10000; d.iloc[-1]-=B/10000; tests[k]=nw(d.AVDV,d.VSS)
ok=all(tests[k]['alpha_ann']>0 for k in W) and tests['2020']['alpha_t_hac']>=1.5
out={'schema':'research.p236_avdv_hac_alpha_r1','parent':'P233/P234','claim':'AVDV matched ex-US small-cap alpha survives predeclared HAC autocorrelation correction','contract':{'candidate':'AVDV','factor':'VSS','windows':W,'monthly_ols':True,'newey_west_lag':L,'cost_bps':B,'fixed_test':True,'no_parameter_search':True},'tests':tests,'decision':'P236_SUPPORT' if ok else 'P236_NOT_SUPPORTED','limitations':['single-factor attribution remains incomplete','short AVDV live history'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p236_avdv_hac_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))