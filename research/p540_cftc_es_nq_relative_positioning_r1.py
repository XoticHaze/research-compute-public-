from __future__ import annotations
import json, math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
import yfinance as yf

DATASET='gpe5-46if'; BASE=f'https://publicreporting.cftc.gov/resource/{DATASET}.json'
CONTRACTS={'ES':'13874A','NQ':'209742'}
START='2014-01-01'; COST_BPS=10.0
FOLDS=[('2014-01-01','2017-12-31'),('2018-01-01','2021-12-31'),('2022-01-01','2026-12-31')]

def fetch(code):
 q=urlencode({'$where':f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd >= '{START}T00:00:00.000'",'$order':'report_date_as_yyyy_mm_dd ASC','$limit':'5000'})
 r=Request(BASE+'?'+q,headers={'User-Agent':'XoticHaze-Research/1.0'})
 with urlopen(r,timeout=60) as x: return json.loads(x.read().decode())

def series(code):
 rows=fetch(code); out=[]
 for r in rows:
  try:
   oi=float(r['open_interest_all']); am=float(r['asset_mgr_positions_long'])-float(r['asset_mgr_positions_short']); lv=float(r['lev_money_positions_long'])-float(r['lev_money_positions_short'])
   d=pd.Timestamp(r['report_date_as_yyyy_mm_dd']).tz_localize(None)
   pub=d+pd.offsets.Day(3); trad=pub+pd.offsets.BDay(1)
   out.append((trad,(am-lv)/oi))
  except Exception: pass
 s=pd.Series(dict(out)).sort_index(); s.name='x'; return s[~s.index.duplicated(keep='last')]

def cagr(r):
 if len(r)<2:return None
 years=(r.index[-1]-r.index[0]).days/365.25
 return float((1+r).prod()**(1/years)-1) if years>0 and (1+r).prod()>0 else None

def mdd(r):
 e=(1+r).cumprod(); return float((e/e.cummax()-1).min())

def stats(r): return {'cagr':cagr(r),'max_drawdown':mdd(r),'days':int(len(r)),'vol':float(r.std()*math.sqrt(252))}

def eval_slice(df,a,b):
 z=df.loc[a:b].copy(); s=z['strategy']; ctrl=z['control']; spy=z['SPY']; qqq=z['QQQ']
 ex=(cagr(s)-cagr(ctrl)) if cagr(s) is not None and cagr(ctrl) is not None else None
 return {'strategy':stats(s),'control':stats(ctrl),'spy':stats(spy),'qqq':stats(qqq),'matched_excess_cagr':ex,'switches':int(z['switch'].sum()),'nq_weight_mean':float(z['nq_w'].mean())}

def main():
 es=series(CONTRACTS['ES']); nq=series(CONTRACTS['NQ']); w=pd.concat([es.rename('es'),nq.rename('nq')],axis=1).dropna(); w['rel']=w['nq']-w['es']
 w['med']=w['rel'].expanding(min_periods=26).median().shift(1); w['nq_w']=(w['rel']>w['med']).astype(float); w=w.dropna()
 px=yf.download(['SPY','QQQ'],start=START,auto_adjust=True,progress=False,group_by='column')['Close'].dropna(); rets=px.pct_change().dropna(); d=rets.join(w['nq_w'].reindex(rets.index,method='ffill')).dropna(); d['spy_w']=1-d['nq_w']; d['switch']=d['nq_w'].diff().abs().fillna(0); d['strategy']=d['nq_w']*d['QQQ']+d['spy_w']*d['SPY']-d['switch']*(COST_BPS/10000.0); d['control']=0.5*d['QQQ']+0.5*d['SPY']
 overall=eval_slice(d,'2014-01-01','2026-12-31'); folds=[eval_slice(d,a,b) for a,b in FOLDS]; pos=sum(1 for x in folds if x['matched_excess_cagr'] is not None and x['matched_excess_cagr']>0)
 decision='P540_SUPPORTED' if overall['matched_excess_cagr'] and overall['matched_excess_cagr']>0 and pos>=2 else 'P540_NOT_SUPPORTED'
 out={'schema':'research.p540_cftc_es_nq_relative_positioning_r1','parent':'P540','claim':'Causally lagged relative ES-vs-NQ institutional-minus-leveraged positioning can improve a weekly SPY/QQQ allocation over a static 50/50 matched-risk control after 10bp switching costs.','frozen_contract':{'source':DATASET,'contracts':CONTRACTS,'availability':'Tuesday report first tradable Monday after Friday publication','signal':'(AM_net-LevMoney_net)/OI NQ minus ES; choose QQQ when above expanding prior median else SPY','cost_bps_per_switch':COST_BPS,'control':'static 50/50 SPY/QQQ','folds':FOLDS},'overall':overall,'folds':folds,'positive_fold_count':pos,'decision':decision,'source_rows':{'ES':int(len(es)),'NQ':int(len(nq)),'common':int(len(w))},'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p540_cftc_es_nq_relative_positioning_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
