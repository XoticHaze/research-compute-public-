import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
A=['AVUV','AVDV','IJR','VSS','IJS','DLS','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10; L=3

def nw(y,x,lag=L):
 d=pd.concat([y.rename('y'),x.rename('x')],axis=1).dropna(); yy=d.y.to_numpy(float); xx=d.x.to_numpy(float); X=np.column_stack([np.ones(len(d)),xx]); inv=np.linalg.pinv(X.T@X); beta=inv@(X.T@yy); u=yy-X@beta; S=np.zeros((2,2))
 for t in range(len(d)): S += u[t]**2*np.outer(X[t],X[t])
 for l in range(1,min(lag,len(d)-1)+1):
  w=1-l/(lag+1); G=np.zeros((2,2))
  for t in range(l,len(d)): G += u[t]*u[t-l]*np.outer(X[t],X[t-l])
  S += w*(G+G.T)
 cov=inv@S@inv; se=float(np.sqrt(max(cov[0,0],0))); return {'rows':len(d),'alpha_ann':float(beta[0]*12),'alpha_t_hac':float(beta[0]/se) if se else None,'beta_value_spread':float(beta[1]),'nw_lag':lag}

def cagr(r):
 q=np.asarray(r,float); return float(np.prod(1+q)**(12/len(q))-1)
def endpoint_cost(r):
 q=np.asarray(r,float).copy(); f=B/10000
 if len(q): q[0]-=f; q[-1]-=f
 return q
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; r=cl.dropna(how='any').resample('ME').last().pct_change().dropna(how='any'); tests={}
for k,s in W.items():
 d=r.loc[pd.Timestamp(s):]; cand=.5*d.AVUV+.5*d.AVDV; matched=.5*d.IJR+.5*d.VSS; val=.5*d.IJS+.5*d.DLS; excess=cand-matched; value_spread=val-matched; reg=nw(excess,value_spread); tests[k]={'raw_matched_excess_cagr':cagr(endpoint_cost(cand))-cagr(endpoint_cost(matched)),'spy_excess_cagr':cagr(endpoint_cost(cand))-cagr(endpoint_cost(d.SPY)),'excess_attribution':reg}
ok=all(tests[k]['raw_matched_excess_cagr']>0 and tests[k]['excess_attribution']['alpha_ann']>0 for k in W) and tests['2020']['excess_attribution']['alpha_t_hac']>=1.5
out={'schema':'research.p243_smallvalue_excess_attribution_r1','parent':'P239/P240/P241/P242','claim':'fixed AVUV/AVDV matched excess retains positive HAC intercept after directly controlling its excess return for an ex-ante investable small-value spread','contract':{'candidate_weights':{'AVUV':0.5,'AVDV':0.5},'matched_control_weights':{'IJR':0.5,'VSS':0.5},'value_reference_weights':{'IJS':0.5,'DLS':0.5},'regression':'candidate_minus_matched = alpha + beta*(value_reference_minus_matched)','windows':W,'cost_bps':B,'newey_west_lag':L,'no_weight_window_fund_or_parameter_search':True},'tests':tests,'decision':'P243_SUPPORT' if ok else 'P243_EXCESS_ATTRIBUTION_NOT_SUPPORTED','limitations':['short common live history','investable references are factor proxies rather than academic factor portfolios'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p243_smallvalue_excess_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
