import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
OUT=Path('research/artifacts/p486_homebuilders_industry_alpha_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['ITB','XHB','XLY','SPY']; COST=0.001
px=yf.download(T,start='2009-01-01',end='2026-09-01',auto_adjust=True,progress=False)['Close'].ffill().dropna(); r=px.pct_change().dropna()
def stats(x):
 n=len(x); y=n/252; total=float((1+x).prod()); c=total**(1/y)-1; vol=float(x.std(ddof=1)*math.sqrt(252)); sh=float(x.mean()/x.std(ddof=1)*math.sqrt(252)); w=(1+x).cumprod(); dd=w/w.cummax()-1; return {'cagr':c,'vol':vol,'sharpe':sh,'max_drawdown':float(dd.min()),'n':n}
def ba(y,x):
 X=np.column_stack([np.ones(len(x)),np.asarray(x,float)]); c=np.linalg.lstsq(X,np.asarray(y,float),rcond=None)[0]; return float(c[1]),float(c[0]*252)
def one(sym,start,end=None):
 q=r.loc[start:end]; a=stats(q[sym]); b=stats(q['XLY']); s=stats(q['SPY']); yrs=len(q)/252; drag=(1-COST)**(1/yrs)-1; ac=a['cagr']+drag; beta,alpha=ba(q[sym],q['XLY']); return {'symbol':sym,'start':start,'end':end,'after_cost_cagr':ac,'xly_cagr':b['cagr'],'spy_cagr':s['cagr'],'excess_vs_xly':ac-b['cagr'],'excess_vs_spy':ac-s['cagr'],'beta_vs_xly':beta,'alpha_vs_xly_ann':alpha,'max_drawdown':a['max_drawdown'],'sharpe':a['sharpe']}
windows=[]
for st in ['2010-01-01','2015-01-01','2020-01-01']:
 for sym in ['ITB','XHB']: windows.append(one(sym,st))
blocks=[]
for a,b in [('2010-01-01','2013-12-31'),('2014-01-01','2017-12-31'),('2018-01-01','2021-12-31'),('2022-01-01','2026-09-01')]:
 rows=[one(sym,a,b) for sym in ['ITB','XHB']]; blocks.append({'start':a,'end':b,'rows':rows,'mean_excess_vs_xly':float(np.mean([x['excess_vs_xly'] for x in rows])),'mean_alpha_vs_xly_ann':float(np.mean([x['alpha_vs_xly_ann'] for x in rows]))})
pass_windows=all(x['excess_vs_xly']>0 and x['alpha_vs_xly_ann']>0 for x in windows); pos=sum(1 for b in blocks if b['mean_excess_vs_xly']>0 and b['mean_alpha_vs_xly_ann']>0)
dec='HOMEBUILDERS_INDUSTRY_ALPHA_SUPPORTED' if pass_windows and pos>=3 else 'HOMEBUILDERS_INDUSTRY_ALPHA_NOT_SUPPORTED'
res={'schema':'research.p486_homebuilders_industry_alpha_r1.v1','hypothesis':'Two differently weighted homebuilder implementations ITB and XHB deliver durable after-cost alpha versus matched consumer-discretionary XLY, with SPY as opportunity-cost context.','source':'Yahoo Finance via yfinance adjusted returns; research-only dynamic source','entry_cost':COST,'windows':windows,'chronology_blocks':blocks,'positive_mean_blocks':pos,'acceptance':'both implementations positive after-cost excess and positive beta-adjusted alpha versus XLY in every fixed window; implementation-mean excess and alpha positive in >=3/4 chronology blocks; no date/product/cost rescue','decision':dec}
OUT.write_text(json.dumps(res,indent=2,sort_keys=True)); print(json.dumps(res))