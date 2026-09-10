import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
A=['AVUV','AVDV','IJR','VSS','IJS','DLS','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10; L=3

def cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def metrics(r):
 q=pd.Series(r).dropna(); e=(1+q).cumprod(); n=len(q); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}

def nw(y,x1,x2,lag=L):
 d=pd.concat([y.rename('y'),x1.rename('x1'),x2.rename('x2')],axis=1).dropna(); yy=d.y.to_numpy(float); X=np.column_stack([np.ones(len(d)),d.x1.to_numpy(float),d.x2.to_numpy(float)]); inv=np.linalg.pinv(X.T@X); beta=inv@(X.T@yy); u=yy-X@beta; S=np.zeros((3,3))
 for t in range(len(d)): S += u[t]**2*np.outer(X[t],X[t])
 for l in range(1,min(lag,len(d)-1)+1):
  w=1-l/(lag+1); G=np.zeros((3,3))
  for t in range(l,len(d)): G += u[t]*u[t-l]*np.outer(X[t],X[t-l])
  S += w*(G+G.T)
 cov=inv@S@inv; se=float(np.sqrt(max(cov[0,0],0))); return {'rows':len(d),'alpha_ann':float(beta[0]*12),'alpha_t_hac':float(beta[0]/se) if se else None,'beta_matched':float(beta[1]),'beta_value_spread':float(beta[2]),'nw_lag':lag}

r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={}
for k,s in W.items():
 d=r.loc[pd.Timestamp(s):]; cand=.5*d.AVUV+.5*d.AVDV; matched=.5*d.IJR+.5*d.VSS; value=.5*d.IJS+.5*d.DLS; spread=value-matched; c=cost(cand); m=cost(matched); sp=cost(d.SPY); tests[k]={'candidate':metrics(c),'matched_control':metrics(m),'spy':metrics(sp),'vs_matched':metrics(c)['cagr']-metrics(m)['cagr'],'vs_spy':metrics(c)['cagr']-metrics(sp)['cagr'],'attribution':nw(c,m,spread)}
ok=all(tests[k]['vs_matched']>0 and tests[k]['attribution']['alpha_ann']>0 for k in W) and tests['2020']['attribution']['alpha_t_hac']>=1.5
out={'schema':'research.p241_smallvalue_combination_factor_attribution_r1','parent':'P239/P240','claim':'fixed AVUV/AVDV combination matched excess survives size/value attribution using ex-ante investable references','contract':{'candidate_weights':{'AVUV':0.5,'AVDV':0.5},'matched_control_weights':{'IJR':0.5,'VSS':0.5},'value_reference_weights':{'IJS':0.5,'DLS':0.5},'regression':'candidate = alpha + beta_matched*matched + beta_value_spread*(value_reference-matched)','windows':W,'cost_bps':B,'newey_west_lag':L,'fixed_test':True,'no_weight_window_fund_or_parameter_search':True},'tests':tests,'decision':'P241_SUPPORT' if ok else 'P241_ATTRIBUTION_NOT_SUPPORTED','limitations':['live-history boundary constrained by AVUV/AVDV inception','investable references approximate size/value exposure rather than academic factor portfolios'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p241_smallvalue_combination_factor_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
