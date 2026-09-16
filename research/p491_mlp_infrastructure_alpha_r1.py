import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p491_mlp_infrastructure_alpha_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['AMLP','MLPA','XLE','SPY'];C=.001
px=yf.download(T,start='2014-01-01',end='2026-09-01',auto_adjust=True,progress=False)['Close'].ffill().dropna();r=px.pct_change().dropna()
def st(x):
 n=len(x);y=n/252;t=float((1+x).prod());cg=t**(1/y)-1;w=(1+x).cumprod();dd=w/w.cummax()-1;return {'cagr':cg,'sharpe':float(x.mean()/x.std(ddof=1)*math.sqrt(252)),'max_drawdown':float(dd.min()),'n':n}
def ba(y,x):
 X=np.c_[np.ones(len(x)),np.asarray(x,float)];c=np.linalg.lstsq(X,np.asarray(y,float),rcond=None)[0];return float(c[1]),float(c[0]*252)
def ev(sym,a,b=None):
 q=r.loc[a:b];s=st(q[sym]);x=st(q.XLE);p=st(q.SPY);yrs=len(q)/252;drag=(1-C)**(1/yrs)-1;ca=s['cagr']+drag;beta,alpha=ba(q[sym],q.XLE);return {'symbol':sym,'start':a,'end':b,'after_cost_cagr':ca,'xle_cagr':x['cagr'],'spy_cagr':p['cagr'],'excess_vs_xle':ca-x['cagr'],'excess_vs_spy':ca-p['cagr'],'beta_vs_xle':beta,'alpha_vs_xle_ann':alpha,'sharpe':s['sharpe'],'max_drawdown':s['max_drawdown']}
windows=[ev(s,a) for a in ['2015-01-01','2018-01-01','2020-01-01'] for s in ['AMLP','MLPA']]
blocks=[]
for a,b in [('2015-01-01','2017-12-31'),('2018-01-01','2020-12-31'),('2021-01-01','2023-12-31'),('2024-01-01','2026-09-01')]:
 rows=[ev(s,a,b) for s in ['AMLP','MLPA']];blocks.append({'start':a,'end':b,'rows':rows,'mean_excess_vs_xle':float(np.mean([x['excess_vs_xle'] for x in rows])),'mean_alpha_vs_xle_ann':float(np.mean([x['alpha_vs_xle_ann'] for x in rows]))})
pos=sum(1 for b in blocks if b['mean_excess_vs_xle']>0 and b['mean_alpha_vs_xle_ann']>0);sup=all(x['excess_vs_xle']>0 and x['alpha_vs_xle_ann']>0 for x in windows) and pos>=3
dec='MLP_INFRASTRUCTURE_ALPHA_SUPPORTED' if sup else 'MLP_INFRASTRUCTURE_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p491_mlp_infrastructure_alpha_r1.v1','hypothesis':'Two MLP/pipeline infrastructure implementations AMLP and MLPA deliver durable after-cost alpha versus matched energy-sector XLE, with SPY opportunity-cost context.','source':'Yahoo Finance via yfinance adjusted fund returns; research-only dynamic source','entry_cost':C,'windows':windows,'chronology_blocks':blocks,'positive_mean_blocks':pos,'acceptance':'both implementations positive after-cost excess and beta-adjusted alpha versus XLE in all windows and implementation-mean positive in >=3/4 blocks; no product/date/cost rescue','decision':dec};OUT.write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out))