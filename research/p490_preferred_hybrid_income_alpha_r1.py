import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p490_preferred_hybrid_income_alpha_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['PFF','PGX','XLF','AGG','SPY'];C=.001
px=yf.download(T,start='2010-01-01',end='2026-09-01',auto_adjust=True,progress=False)['Close'].ffill().dropna();r=px.pct_change().dropna();r['CTRL']=0.5*r.XLF+0.5*r.AGG
def st(x):
 n=len(x);y=n/252;t=float((1+x).prod());cg=t**(1/y)-1;w=(1+x).cumprod();dd=w/w.cummax()-1;return {'cagr':cg,'sharpe':float(x.mean()/x.std(ddof=1)*math.sqrt(252)),'max_drawdown':float(dd.min()),'n':n}
def ba(y,x):
 X=np.c_[np.ones(len(x)),np.asarray(x,float)];c=np.linalg.lstsq(X,np.asarray(y,float),rcond=None)[0];return float(c[1]),float(c[0]*252)
def ev(sym,a,b=None):
 q=r.loc[a:b];s=st(q[sym]);ctrl=st(q.CTRL);sp=st(q.SPY);yrs=len(q)/252;drag=(1-C)**(1/yrs)-1;ca=s['cagr']+drag;beta,alpha=ba(q[sym],q.CTRL);return {'symbol':sym,'start':a,'end':b,'after_cost_cagr':ca,'control_cagr':ctrl['cagr'],'spy_cagr':sp['cagr'],'excess_vs_control':ca-ctrl['cagr'],'excess_vs_spy':ca-sp['cagr'],'beta_vs_control':beta,'alpha_vs_control_ann':alpha,'sharpe':s['sharpe'],'max_drawdown':s['max_drawdown']}
windows=[ev(s,a) for a in ['2012-01-01','2015-01-01','2020-01-01'] for s in ['PFF','PGX']]
blocks=[]
for a,b in [('2012-01-01','2015-12-31'),('2016-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01','2026-09-01')]:
 rows=[ev(s,a,b) for s in ['PFF','PGX']];blocks.append({'start':a,'end':b,'rows':rows,'mean_excess_vs_control':float(np.mean([x['excess_vs_control'] for x in rows])),'mean_alpha_vs_control_ann':float(np.mean([x['alpha_vs_control_ann'] for x in rows]))})
pos=sum(1 for b in blocks if b['mean_excess_vs_control']>0 and b['mean_alpha_vs_control_ann']>0);sup=all(x['excess_vs_control']>0 and x['alpha_vs_control_ann']>0 for x in windows) and pos>=3
dec='PREFERRED_HYBRID_INCOME_ALPHA_SUPPORTED' if sup else 'PREFERRED_HYBRID_INCOME_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p490_preferred_hybrid_income_alpha_r1.v1','hypothesis':'Preferred-stock income exposure through two implementations PFF and PGX delivers durable after-cost alpha versus a fixed 50% XLF + 50% AGG hybrid financial-credit control, with SPY opportunity-cost context.','source':'Yahoo Finance via yfinance adjusted fund returns; research-only dynamic source','entry_cost':C,'control':'daily 50% XLF + 50% AGG return','windows':windows,'chronology_blocks':blocks,'positive_mean_blocks':pos,'acceptance':'both implementations positive after-cost excess and beta-adjusted alpha versus fixed hybrid control in every window and implementation-mean positive in >=3/4 blocks; no product/date/control-weight/cost rescue','decision':dec};OUT.write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out))