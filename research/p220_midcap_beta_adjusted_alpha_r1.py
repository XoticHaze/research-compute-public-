import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['XMMO','MDY','SPY']; W={'2006':'2006-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; B=10

def cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def ols_alpha(y,x):
 y=np.asarray(y,float); x=np.asarray(x,float); X=np.column_stack([np.ones(len(x)),x]); coef=np.linalg.lstsq(X,y,rcond=None)[0]; pred=X@coef; resid=y-pred; a=float(coef[0]); beta=float(coef[1]); ann=float((1+a)**12-1); r2=float(1-np.sum(resid**2)/np.sum((y-y.mean())**2)) if np.sum((y-y.mean())**2)>0 else None; return {'monthly_alpha':a,'annualized_alpha':ann,'beta':beta,'r2':r2,'residual_vol_annualized':float(np.std(resid,ddof=0)*12**.5)}
def ev(d):
 y=cost(d['XMMO']); m=cost(d['MDY']); s=cost(d['SPY']); full_m=ols_alpha(y,m); full_s=ols_alpha(y,s); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(y)),5),1): folds.append({'fold':i,'alpha_vs_mdy':ols_alpha(y.iloc[ix],m.iloc[ix])['annualized_alpha'],'alpha_vs_spy':ols_alpha(y.iloc[ix],s.iloc[ix])['annualized_alpha']})
 return {'vs_mdy':full_m,'vs_spy':full_s,'positive_mdy_alpha_folds':sum(x['alpha_vs_mdy']>0 for x in folds),'positive_spy_alpha_folds':sum(x['alpha_vs_spy']>0 for x in folds),'folds':folds}
raw=yf.download(A,start='2005-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c,d=(tests[k] for k in ['2006','2010','2015','2020']); decision='P220_MIDCAP_BETA_ADJUSTED_ALPHA_SUPPORT' if all(x['vs_mdy']['annualized_alpha']>0 and x['vs_spy']['annualized_alpha']>0 for x in (a,b,c,d)) and b['positive_mdy_alpha_folds']>=4 and b['positive_spy_alpha_folds']>=4 else 'P220_MIDCAP_BETA_ADJUSTED_ALPHA_NOT_ROBUST'; out={'schema':'research.p220_midcap_beta_adjusted_alpha_r1','parent':'P220','hypothesis':'P217/P219 XMMO excess remains positive after beta adjustment to independent mid-cap MDY and broad SPY, rather than arising only from systematic exposure magnitude.','contract':{'candidate':'XMMO','matched_factor':'MDY','broad_factor':'SPY','model':'monthly OLS candidate_return = alpha + beta*control_return','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit_applied_to_each_series':B,'gate':'positive annualized alpha versus MDY and SPY every window; >=4/5 positive fold alphas versus each from 2010','no_window_model_factor_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p220_midcap_beta_adjusted_alpha_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
