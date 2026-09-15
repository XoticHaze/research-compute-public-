import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p489_bdc_credit_equity_alpha_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['BIZD','XLF','SPY'];C=.001
px=yf.download(T,start='2014-01-01',end='2026-09-01',auto_adjust=True,progress=False)['Close'].ffill().dropna();r=px.pct_change().dropna()
def st(x):
 n=len(x);y=n/252;t=float((1+x).prod());cg=t**(1/y)-1;w=(1+x).cumprod();dd=w/w.cummax()-1;return {'cagr':cg,'sharpe':float(x.mean()/x.std(ddof=1)*math.sqrt(252)),'max_drawdown':float(dd.min()),'n':n}
def ba(y,x):
 X=np.c_[np.ones(len(x)),np.asarray(x,float)];c=np.linalg.lstsq(X,np.asarray(y,float),rcond=None)[0];return float(c[1]),float(c[0]*252)
def ev(a,b=None):
 q=r.loc[a:b];s=st(q.BIZD);x=st(q.XLF);p=st(q.SPY);yrs=len(q)/252;drag=(1-C)**(1/yrs)-1;ca=s['cagr']+drag;beta,alpha=ba(q.BIZD,q.XLF);return {'start':a,'end':b,'bizd_after_cost_cagr':ca,'xlf_cagr':x['cagr'],'spy_cagr':p['cagr'],'excess_vs_xlf':ca-x['cagr'],'excess_vs_spy':ca-p['cagr'],'beta_vs_xlf':beta,'alpha_vs_xlf_ann':alpha,'sharpe':s['sharpe'],'max_drawdown':s['max_drawdown']}
windows=[ev(a) for a in ['2015-01-01','2018-01-01','2020-01-01']];blocks=[ev(a,b) for a,b in [('2015-01-01','2017-12-31'),('2018-01-01','2020-12-31'),('2021-01-01','2023-12-31'),('2024-01-01','2026-09-01')]]
pos=sum(1 for x in blocks if x['excess_vs_xlf']>0 and x['alpha_vs_xlf_ann']>0);sup=all(x['excess_vs_xlf']>0 and x['alpha_vs_xlf_ann']>0 for x in windows) and pos>=3
dec='BDC_CREDIT_EQUITY_ALPHA_SUPPORTED' if sup else 'BDC_CREDIT_EQUITY_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p489_bdc_credit_equity_alpha_r1.v1','hypothesis':'Public business-development-company exposure via BIZD provides durable after-cost return alpha versus matched financial-sector XLF, with SPY opportunity-cost context.','source':'Yahoo Finance via yfinance adjusted fund returns; research-only dynamic source','entry_cost':C,'windows':windows,'chronology_blocks':blocks,'positive_blocks':pos,'acceptance':'positive after-cost excess and beta-adjusted alpha versus XLF in all fixed windows and >=3/4 blocks; no product/date/cost rescue','decision':dec};OUT.write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out))