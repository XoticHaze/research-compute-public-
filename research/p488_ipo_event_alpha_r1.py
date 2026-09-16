import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p488_ipo_event_alpha_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['FPX','IPO','IWB','SPY'];C=.001
px=yf.download(T,start='2014-01-01',end='2026-09-01',auto_adjust=True,progress=False)['Close'].ffill();r=px.pct_change().dropna(how='all')
def st(x):
 x=x.dropna();n=len(x);y=n/252;t=float((1+x).prod());cg=t**(1/y)-1;w=(1+x).cumprod();dd=w/w.cummax()-1;return {'cagr':cg,'sharpe':float(x.mean()/x.std(ddof=1)*math.sqrt(252)),'max_drawdown':float(dd.min()),'n':n}
def ba(y,x):
 z=pd.concat([y,x],axis=1).dropna();X=np.c_[np.ones(len(z)),z.iloc[:,1].values];c=np.linalg.lstsq(X,z.iloc[:,0].values,rcond=None)[0];return float(c[1]),float(c[0]*252)
def ev(sym,a,b=None):
 q=r.loc[a:b,[sym,'IWB','SPY']].dropna();s=st(q[sym]);iw=st(q.IWB);sp=st(q.SPY);yrs=len(q)/252;drag=(1-C)**(1/yrs)-1;ca=s['cagr']+drag;beta,alpha=ba(q[sym],q.IWB);return {'symbol':sym,'start':a,'end':b,'after_cost_cagr':ca,'iwb_cagr':iw['cagr'],'spy_cagr':sp['cagr'],'excess_vs_iwb':ca-iw['cagr'],'excess_vs_spy':ca-sp['cagr'],'beta_vs_iwb':beta,'alpha_vs_iwb_ann':alpha,'sharpe':s['sharpe'],'max_drawdown':s['max_drawdown']}
windows=[ev(s,a) for a in ['2015-01-01','2018-01-01','2020-01-01'] for s in ['FPX','IPO']]
blocks=[]
for a,b in [('2015-01-01','2017-12-31'),('2018-01-01','2020-12-31'),('2021-01-01','2023-12-31'),('2024-01-01','2026-09-01')]:
 rows=[ev(s,a,b) for s in ['FPX','IPO']];blocks.append({'start':a,'end':b,'rows':rows,'mean_excess_vs_iwb':float(np.mean([x['excess_vs_iwb'] for x in rows])),'mean_alpha_vs_iwb_ann':float(np.mean([x['alpha_vs_iwb_ann'] for x in rows]))})
pos=sum(1 for b in blocks if b['mean_excess_vs_iwb']>0 and b['mean_alpha_vs_iwb_ann']>0);sup=all(x['excess_vs_iwb']>0 and x['alpha_vs_iwb_ann']>0 for x in windows) and pos>=3
dec='IPO_EVENT_ALPHA_SUPPORTED' if sup else 'IPO_EVENT_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p488_ipo_event_alpha_r1.v1','hypothesis':'Two distinct IPO/recent-listing implementations FPX and IPO deliver durable after-cost alpha versus broad-US IWB, with SPY opportunity-cost context.','source':'Yahoo Finance via yfinance adjusted fund returns; research-only dynamic source','entry_cost':C,'windows':windows,'chronology_blocks':blocks,'positive_mean_blocks':pos,'acceptance':'both implementations positive after-cost excess and beta-adjusted alpha versus IWB in all fixed windows and implementation-mean positive in >=3/4 blocks; no product/date/cost rescue','decision':dec};OUT.write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out))