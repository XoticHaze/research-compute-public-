import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['AVDV','VSS','IEFA','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ols(y,x):
 d=pd.concat([y.rename('y'),x.rename('x')],axis=1).dropna(); yy=d.y.to_numpy(float); xx=d.x.to_numpy(float); X=np.column_stack([np.ones(len(d)),xx]); b,*_=np.linalg.lstsq(X,yy,rcond=None); resid=yy-X@b; dof=max(len(d)-2,1); s2=float(resid@resid/dof); cov=s2*np.linalg.pinv(X.T@X); se=float(np.sqrt(max(cov[0,0],0))); t=float(b[0]/se) if se else None; return {'rows':len(d),'alpha_ann':float(b[0]*12),'alpha_t_iid':t,'beta':float(b[1])}
def ev(d):
 regs={b:ols(c(d['AVDV']),c(d[b])) for b in ['VSS','IEFA','SPY']}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; z=ols(c(q['AVDV']),c(q['VSS'])); fs.append({'fold':i,'vss_alpha_ann':z['alpha_ann'],'beta':z['beta']})
 return {'regressions':regs,'positive_vss_alpha_folds':sum(x['vss_alpha_ann']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['regressions']['VSS']['alpha_ann']>0 for k in W) and t['2020']['positive_vss_alpha_folds']>=4 and t['2020']['regressions']['VSS']['alpha_t_iid']>=1.5; out={'schema':'research.p234_avdv_beta_attribution_r1','parent':'P234','claim':'P233 matched small-value excess survives simple beta attribution to ex-US small-cap','contract':{'candidate':'AVDV','primary_factor':'VSS','references':['IEFA','SPY'],'windows':W,'folds':5,'cost_bps':B,'fixed_test':True,'regression':'monthly OLS candidate=alpha+beta*factor'},'tests':t,'decision':'P234_SUPPORT' if ok else 'P234_NOT_SUPPORTED','limitations':['IID alpha t-stat descriptive, not HAC','single-factor attribution is not a full factor model'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p234_avdv_beta_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))