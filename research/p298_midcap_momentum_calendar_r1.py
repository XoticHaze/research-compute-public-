from __future__ import annotations
import json
from pathlib import Path
import pandas as pd,yfinance as yf
CAND='XMMO'; BASE='IJH'; START='2014-01-01'; END='2026-09-10'; COST=10/10000
BLOCKS={'2015_2018':('2015-01-01','2018-12-31'),'2019_2022':('2019-01-01','2022-12-31'),'2023_present':('2023-01-01','2026-09-10')}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None}
def ep(r):
 q=pd.Series(r,dtype=float).dropna().copy()
 if len(q): q.iloc[0]-=COST; q.iloc[-1]-=COST
 return q
raw=yf.download([CAND,BASE],start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[[CAND,BASE]].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for n,(a,b) in BLOCKS.items():
 z=r.loc[(r.index>=pd.Timestamp(a))&(r.index<=pd.Timestamp(b))]; cm=metric(ep(z[CAND])); bm=metric(ep(z[BASE])); results[n]={'candidate':cm,'matched':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'drawdown_delta':cm['maxdd']-bm['maxdd']}
pos=sum(v['matched_excess_cagr']>0 for v in results.values()); dd=sum(v['drawdown_delta']>=-0.05 for v in results.values()); decision='P298_XMMO_INDEPENDENT_CALENDAR_CONFIRMATION' if pos==3 and dd==3 else ('P298_XMMO_REGIME_CONDITIONAL' if pos>=1 else 'P298_XMMO_CALENDAR_FAILURE')
out={'schema':'research.p298_midcap_momentum_calendar_r1','parent':'P298/P297','claim':'Independently confirm unchanged XMMO-vs-IJH matched momentum excess using fixed non-overlapping calendar blocks after P297 support, with no product, parameter, cost, or window search.','parameters':{'candidate':CAND,'matched':BASE,'endpoint_cost_bps':10,'blocks':BLOCKS,'no_search':True},'results':results,'summary':{'positive_matched_blocks':pos,'no_gt5pp_drawdown_penalty_blocks':dd},'decision_rule':'Independent confirmation requires positive matched excess and no >5pp drawdown penalty in all three fixed blocks. Partial block support narrows scope without killing P297.','decision':decision,'limitations':['same adjusted-price provider as P297, so temporal-structure confirmation not source-independent replication','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p298_midcap_momentum_calendar_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
