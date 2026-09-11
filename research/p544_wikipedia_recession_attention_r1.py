from __future__ import annotations
import json, math
from pathlib import Path
import requests
import pandas as pd
import yfinance as yf

API='https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Recession/monthly/2015070100/2026090100'
START='2015-08-01'; COST_BPS=10.0
FOLDS=[('2015-08-01','2018-12-31'),('2019-01-01','2022-12-31'),('2023-01-01','2026-12-31')]

def attention():
 r=requests.get(API,headers={'User-Agent':'XoticHaze-Research/1.0 contact=github.com/XoticHaze'},timeout=45); r.raise_for_status(); items=r.json()['items']
 x=pd.DataFrame({'date':[pd.Timestamp(i['timestamp'][:6]+'01') for i in items],'views':[float(i['views']) for i in items]}).set_index('date').sort_index()
 x['yoy']=x['views'].pct_change(12)
 # Monthly pageviews are known only after month end; use the signal from the prior completed month.
 x['risk_off']=(x['yoy']>0).astype(float).shift(1)
 x.index=x.index.to_period('M').to_timestamp('M')
 return x['risk_off'].dropna()

def cagr(r):
 if len(r)<2:return None
 years=(r.index[-1]-r.index[0]).days/365.25; total=(1+r).prod()
 return float(total**(1/years)-1) if years>0 and total>0 else None

def mdd(r):
 e=(1+r).cumprod(); return float((e/e.cummax()-1).min())

def stats(r): return {'cagr':cagr(r),'max_drawdown':mdd(r),'months':int(len(r)),'vol':float(r.std()*math.sqrt(12))}

def evaluate(df,a,b):
 z=df.loc[a:b].copy(); w=float(z['spy_w'].mean()); z['matched_control']=w*z['SPY_ret']+(1-w)*z['BIL_ret']; s=z['strategy']; c=z['matched_control']
 return {'strategy':stats(s),'matched_control':stats(c),'spy':stats(z['SPY_ret']),'bil':stats(z['BIL_ret']),'matched_excess_cagr':cagr(s)-cagr(c),'switches':int(z['switch'].sum()),'spy_weight_mean':w}

def main():
 sig=attention(); px=yf.download(['SPY','BIL'],start=START,auto_adjust=True,progress=False,group_by='column')['Close'].dropna(); m=px.resample('ME').last(); r=m.pct_change().dropna(); d=r.join(sig.rename('risk_off').reindex(r.index,method='ffill')).dropna(); d['spy_w']=1-d['risk_off']; d['switch']=d['spy_w'].diff().abs().fillna(0); d['SPY_ret']=d['SPY']; d['BIL_ret']=d['BIL']; d['strategy']=d['spy_w']*d['SPY_ret']+(1-d['spy_w'])*d['BIL_ret']-d['switch']*(COST_BPS/10000.0)
 overall=evaluate(d,START,'2026-12-31'); folds=[evaluate(d,a,b) for a,b in FOLDS]; pos=sum(1 for f in folds if f['matched_excess_cagr']>0)
 decision='P544_SUPPORTED' if overall['matched_excess_cagr']>0 and pos>=2 else 'P544_NOT_SUPPORTED'
 out={'schema':'research.p544_wikipedia_recession_attention_r1','parent':'P544','claim':'Causally lagged public recession-attention growth can time equity risk with durable after-cost excess over an exposure-matched SPY/BIL control.','frozen_contract':{'source':'Wikimedia monthly pageviews for en.wikipedia/Recession','availability':'prior completed month only','signal':'hold BIL when YoY Recession pageviews growth > 0 else SPY','cost_bps_per_switch':COST_BPS,'control':'static SPY/BIL mix matched to strategy mean SPY exposure within each evaluation window','folds':FOLDS},'overall':overall,'folds':folds,'positive_fold_count':pos,'decision':decision,'attention_months':int(len(sig)),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p544_wikipedia_recession_attention_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
