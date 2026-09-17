from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SPMO','IJS','SPY','IJR','DBMF','BIL']; COST=0.0025
x=yf.download(T,start='2020-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
m=c[T].resample('ME').last().dropna(); r=m.pct_change().dropna()
# P305 sleeve and exact matched control, plus P380 DBMF residual versus BIL.
p305=.5*r.SPMO+.5*r.IJS; p305_ctl=.5*r.SPY+.5*r.IJR
dbmf=r.DBMF; cash=r.BIL
# Endpoint cost only at sample entry/exit for fixed buy/hold sleeves.
def endpoint_cost(s):
 y=s.copy();
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
p305=endpoint_cost(p305); p305_ctl=endpoint_cost(p305_ctl); dbmf=endpoint_cost(dbmf); cash=endpoint_cost(cash)
idx=p305.index.intersection(dbmf.index); p305,p305_ctl,dbmf,cash=[z.reindex(idx).dropna() for z in (p305,p305_ctl,dbmf,cash)]
idx=p305.index.intersection(p305_ctl.index).intersection(dbmf.index).intersection(cash.index); p305,p305_ctl,dbmf,cash=[z.reindex(idx) for z in (p305,p305_ctl,dbmf,cash)]
e1=p305-p305_ctl; e2=dbmf-cash
def corr(a,b): return float(a.corr(b))
def cagr(s): return float((1+s).prod()**(12/len(s))-1)
def sh(s): return float(np.sqrt(12)*s.mean()/s.std(ddof=1))
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min())
blocks=[('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]
block=[]
for a,b in blocks:
 z=e1.loc[a:b].index.intersection(e2.loc[a:b].index); block.append({'start':a,'end':b,'months':len(z),'corr':corr(e1.reindex(z),e2.reindex(z))})
blend=.5*p305+.5*dbmf; ctl=.5*p305_ctl+.5*cash
metrics={'blend_cagr':cagr(blend),'control_cagr':cagr(ctl),'matched_excess_pp':100*(cagr(blend)-cagr(ctl)),'blend_sharpe':sh(blend),'p305_sharpe':sh(p305),'blend_max_drawdown':dd(blend),'p305_max_drawdown':dd(p305),'dbmf_max_drawdown':dd(dbmf)}
overall=corr(e1,e2); pass_corr=abs(overall)<.35 and sum(abs(b['corr'])<.4 for b in block)>=2
pass_econ=metrics['matched_excess_pp']>0 and metrics['blend_sharpe']>=metrics['p305_sharpe'] and metrics['blend_max_drawdown']>metrics['p305_max_drawdown']
pass_gate=pass_corr and pass_econ
out={'schema':'research.p384_p305_dbmf_complementarity.v1','workload_id':'P384_P305_DBMF_COMPLEMENTARITY_R1','claim':'Test whether DBMF-specific P380 evidence contributes an orthogonal return source to the frozen P305 momentum+small-value sleeve without treating broad managed-futures transport as supported.','p305':'50% SPMO + 50% IJS','p305_control':'50% SPY + 50% IJR','dbmf_control':'BIL','cost_bps_each_endpoint':25,'overall_residual_corr':overall,'blocks':block,'metrics':metrics,'decision_rule':'SUPPORTED only if |overall residual corr|<0.35, >=2/3 blocks |corr|<0.40, fixed 50/50 blend has positive matched excess, Sharpe >= P305 alone, and max drawdown improves versus P305. No weights/products/windows/costs tuned.','decision':'P305_DBMF_COMPLEMENTARITY_SUPPORTED' if pass_gate else 'P305_DBMF_COMPLEMENTARITY_NOT_SUPPORTED','scientific_consequence':('DBMF-specific survivor earns orthogonal combination evidence with P305; broad managed-futures family remains unsupported and portfolio allocation remains Coordinator authority.' if pass_gate else 'Reject only this fixed complementarity claim; preserve P305 and DBMF-specific passing evidence within prior scopes and do not tune blend weights.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p384_p305_dbmf_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'overall_corr':round(overall,3),'metrics':metrics},sort_keys=True))
