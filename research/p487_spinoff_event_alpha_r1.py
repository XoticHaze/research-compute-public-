import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
OUT=Path('research/artifacts/p487_spinoff_event_alpha_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['CSD','IWB','SPY']; COST=.001
px=yf.download(T,start='2007-01-01',end='2026-09-01',auto_adjust=True,progress=False)['Close'].ffill().dropna(); r=px.pct_change().dropna()
def stats(x):
 n=len(x); y=n/252; tot=float((1+x).prod()); c=tot**(1/y)-1; vol=float(x.std(ddof=1)*math.sqrt(252)); sh=float(x.mean()/x.std(ddof=1)*math.sqrt(252)); w=(1+x).cumprod(); dd=w/w.cummax()-1; return {'cagr':c,'vol':vol,'sharpe':sh,'max_drawdown':float(dd.min()),'n':n}
def ba(y,x):
 X=np.column_stack([np.ones(len(x)),np.asarray(x,float)]); c=np.linalg.lstsq(X,np.asarray(y,float),rcond=None)[0]; return float(c[1]),float(c[0]*252)
def evalw(a,b=None):
 q=r.loc[a:b]; c=stats(q.CSD); iw=stats(q.IWB); sp=stats(q.SPY); yrs=len(q)/252; drag=(1-COST)**(1/yrs)-1; ca=c['cagr']+drag; bi,ai=ba(q.CSD,q.IWB); bs,as_=ba(q.CSD,q.SPY)
 return {'start':a,'end':b,'csd_after_cost_cagr':ca,'iwb_cagr':iw['cagr'],'spy_cagr':sp['cagr'],'excess_vs_iwb':ca-iw['cagr'],'excess_vs_spy':ca-sp['cagr'],'beta_vs_iwb':bi,'alpha_vs_iwb_ann':ai,'beta_vs_spy':bs,'alpha_vs_spy_ann':as_,'max_drawdown':c['max_drawdown'],'sharpe':c['sharpe']}
windows=[evalw(x) for x in ['2010-01-01','2015-01-01','2020-01-01']]
blocks=[evalw(a,b) for a,b in [('2010-01-01','2013-12-31'),('2014-01-01','2017-12-31'),('2018-01-01','2021-12-31'),('2022-01-01','2026-09-01')]]
pos=sum(1 for x in blocks if x['excess_vs_iwb']>0 and x['alpha_vs_iwb_ann']>0)
sup=all(x['excess_vs_iwb']>0 and x['alpha_vs_iwb_ann']>0 for x in windows) and pos>=3
dec='SPINOFF_EVENT_ALPHA_SUPPORTED' if sup else 'SPINOFF_EVENT_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p487_spinoff_event_alpha_r1.v1','hypothesis':'An investable corporate spin-off/event selection sleeve (CSD) delivers durable after-cost excess and beta-adjusted alpha versus broad-US IWB, with SPY opportunity-cost context.','source':'Yahoo Finance via yfinance adjusted fund returns; research-only dynamic source','entry_cost':COST,'windows':windows,'chronology_blocks':blocks,'positive_blocks':pos,'acceptance':'positive after-cost excess and positive beta-adjusted annual alpha versus IWB in all fixed windows and >=3/4 chronology blocks; no product/date/cost rescue','decision':dec}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out))