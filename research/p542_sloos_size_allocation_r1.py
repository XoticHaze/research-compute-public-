from __future__ import annotations
import io, json, math, time
from pathlib import Path
import requests
import pandas as pd
import yfinance as yf

SERIES='DRTSCILM'
FRED_URL=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}'
START='2000-06-01'; COST_BPS=10.0
FOLDS=[('2000-06-01','2006-12-31'),('2007-01-01','2012-12-31'),('2013-01-01','2018-12-31'),('2019-01-01','2026-12-31')]

def fetch_fred():
 raw=None; last=None
 for attempt in range(3):
  try:
   r=requests.get(FRED_URL,headers={'User-Agent':'XoticHaze-Research/1.0'},timeout=(15,90)); r.raise_for_status(); raw=r.content
   if len(raw)>500: break
  except Exception as exc:
   last=exc
   if attempt<2: time.sleep(2**attempt)
 if raw is None or len(raw)<=500: raise RuntimeError(f'FRED {SERIES} fetch failed: {last!r}')
 x=pd.read_csv(io.BytesIO(raw)); x.columns=['date','tightening']; x['date']=pd.to_datetime(x['date']); x['tightening']=pd.to_numeric(x['tightening'],errors='coerce'); x=x.dropna()
 # Conservative publication treatment: quarterly survey value becomes usable two month-ends after observation month.
 x['available']=x['date'].dt.to_period('M').dt.to_timestamp('M')+pd.offsets.MonthEnd(2)
 x['iwm_w']=(x['tightening']<=0).astype(float)
 return x.set_index('available')['iwm_w'].sort_index()

def cagr(r):
 if len(r)<2:return None
 years=(r.index[-1]-r.index[0]).days/365.25; total=(1+r).prod()
 return float(total**(1/years)-1) if years>0 and total>0 else None

def mdd(r):
 e=(1+r).cumprod(); return float((e/e.cummax()-1).min())

def stats(r): return {'cagr':cagr(r),'max_drawdown':mdd(r),'days':int(len(r)),'vol':float(r.std()*math.sqrt(252))}

def evaluate(df,a,b):
 z=df.loc[a:b]; s=z['strategy']; c=z['control']
 return {'strategy':stats(s),'control':stats(c),'iwm':stats(z['IWM']),'spy':stats(z['SPY']),'matched_excess_cagr':cagr(s)-cagr(c),'switches':int(z['switch'].sum()),'iwm_weight_mean':float(z['iwm_w'].mean())}

def main():
 sig=fetch_fred(); px=yf.download(['IWM','SPY'],start=START,auto_adjust=True,progress=False,group_by='column')['Close'].dropna(); r=px.pct_change().dropna(); d=r.join(sig.rename('iwm_w').reindex(r.index,method='ffill')).dropna(); d['spy_w']=1-d['iwm_w']; d['switch']=d['iwm_w'].diff().abs().fillna(0); d['strategy']=d['iwm_w']*d['IWM']+d['spy_w']*d['SPY']-d['switch']*(COST_BPS/10000.0); d['control']=0.5*d['IWM']+0.5*d['SPY']
 overall=evaluate(d,START,'2026-12-31'); folds=[evaluate(d,a,b) for a,b in FOLDS]; pos=sum(1 for f in folds if f['matched_excess_cagr']>0)
 decision='P542_SUPPORTED' if overall['matched_excess_cagr']>0 and pos>=3 else 'P542_NOT_SUPPORTED'
 out={'schema':'research.p542_sloos_size_allocation_r1','parent':'P542','claim':'Publication-lagged Federal Reserve bank lending standards can allocate between small- and large-cap US equities with durable after-cost excess over a static 50/50 matched control.','frozen_contract':{'source':f'FRED {SERIES}','availability':'quarterly observation usable only two month-ends after observation month','signal':'IWM when net tightening <= 0, SPY when net tightening > 0','cost_bps_per_switch':COST_BPS,'control':'static 50/50 IWM/SPY','folds':FOLDS},'overall':overall,'folds':folds,'positive_fold_count':pos,'decision':decision,'survey_points':int(len(sig)),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p542_sloos_size_allocation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
