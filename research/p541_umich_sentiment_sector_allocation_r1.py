from __future__ import annotations
import io, json, math
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd
import yfinance as yf

FRED_URL='https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT'
START='2005-01-01'; COST_BPS=10.0
FOLDS=[('2005-01-01','2009-12-31'),('2010-01-01','2014-12-31'),('2015-01-01','2019-12-31'),('2020-01-01','2026-12-31')]

def get_sent():
 req=Request(FRED_URL,headers={'User-Agent':'XoticHaze-Research/1.0'})
 with urlopen(req,timeout=30) as r: raw=r.read()
 x=pd.read_csv(io.BytesIO(raw)); x.columns=['date','sent']; x['date']=pd.to_datetime(x['date']); x['sent']=pd.to_numeric(x['sent'],errors='coerce'); x=x.dropna().set_index('date')
 # conservative monthly availability: use each observation only from next month-end onward
 x['yoy']=x['sent'].pct_change(12); x['signal']=(x['yoy']>0).astype(float)
 x['available']=x.index.to_period('M').to_timestamp('M')+pd.offsets.MonthEnd(1)
 return x.set_index('available')['signal'].dropna()

def cagr(r):
 if len(r)<2:return None
 years=(r.index[-1]-r.index[0]).days/365.25
 total=(1+r).prod(); return float(total**(1/years)-1) if years>0 and total>0 else None

def mdd(r):
 e=(1+r).cumprod(); return float((e/e.cummax()-1).min())

def stats(r): return {'cagr':cagr(r),'max_drawdown':mdd(r),'days':int(len(r)),'vol':float(r.std()*math.sqrt(252))}

def evaluate(df,a,b):
 z=df.loc[a:b]; s=z['strategy']; c=z['control']; xly=z['XLY']; xlp=z['XLP']
 return {'strategy':stats(s),'control':stats(c),'xly':stats(xly),'xlp':stats(xlp),'matched_excess_cagr':cagr(s)-cagr(c),'switches':int(z['switch'].sum()),'xly_weight_mean':float(z['xly_w'].mean())}

def main():
 sig=get_sent(); px=yf.download(['XLY','XLP'],start=START,auto_adjust=True,progress=False,group_by='column')['Close'].dropna(); r=px.pct_change().dropna(); d=r.join(sig.rename('xly_w').reindex(r.index,method='ffill')).dropna(); d['xlp_w']=1-d['xly_w']; d['switch']=d['xly_w'].diff().abs().fillna(0); d['strategy']=d['xly_w']*d['XLY']+d['xlp_w']*d['XLP']-d['switch']*(COST_BPS/10000.0); d['control']=0.5*d['XLY']+0.5*d['XLP']
 overall=evaluate(d,'2005-01-01','2026-12-31'); folds=[evaluate(d,a,b) for a,b in FOLDS]; pos=sum(1 for f in folds if f['matched_excess_cagr']>0)
 decision='P541_SUPPORTED' if overall['matched_excess_cagr']>0 and pos>=3 else 'P541_NOT_SUPPORTED'
 out={'schema':'research.p541_umich_sentiment_sector_allocation_r1','parent':'P541','claim':'Publication-lagged year-over-year direction in University of Michigan consumer sentiment can allocate between consumer discretionary and staples with durable after-cost excess over a static 50/50 matched sector control.','frozen_contract':{'source':'FRED UMCSENT','availability':'monthly observation admitted only from following month-end','signal':'XLY when UMCSENT YoY change > 0 else XLP','cost_bps_per_switch':COST_BPS,'control':'static 50/50 XLY/XLP','folds':FOLDS},'overall':overall,'folds':folds,'positive_fold_count':pos,'decision':decision,'sentiment_points':int(len(sig)),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p541_umich_sentiment_sector_allocation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
