from __future__ import annotations
import json,math
from pathlib import Path
import pandas as pd,yfinance as yf
PAIRS={'SPMO_vs_SPY':('SPMO','SPY'),'CALF_vs_IJR':('CALF','IJR')}; START='2018-01-01'; END='2026-09-10'; COST=10/10000
BLOCKS={'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_present':('2025-01-01','2026-09-10')}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def endpoint(r):
 q=pd.Series(r,dtype=float).dropna().copy()
 if len(q): q.iloc[0]-=COST; q.iloc[-1]-=COST
 return q
syms=sorted({x for p in PAIRS.values() for x in p}); raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for n,(a,b) in BLOCKS.items():
 ix=(r.index>=pd.Timestamp(a))&(r.index<=pd.Timestamp(b)); br={}
 for label,(cand,base) in PAIRS.items():
  cm=metric(endpoint(r.loc[ix,cand])); bm=metric(endpoint(r.loc[ix,base])); br[label]={'candidate':cm,'matched':bm,'matched_excess_cagr':cm['cagr']-bm['cagr']}
 results[n]=br
counts={k:sum(results[b][k]['matched_excess_cagr']>0 for b in BLOCKS) for k in PAIRS}; both=sum(all(results[b][k]['matched_excess_cagr']>0 for k in PAIRS) for b in BLOCKS)
decision='P293_BOTH_COMPONENTS_CONTRIBUTE_ACROSS_ALL_BLOCKS' if both==3 else ('P293_COMPONENT_CONTRIBUTION_MIXED' if all(v>=1 for v in counts.values()) else 'P293_ONE_COMPONENT_NOT_PERSISTENT')
out={'schema':'research.p293_spmo_calf_attribution_r1','parent':'P293','claim':'Attribute the fixed SPMO+CALF combination without optimizing it: test whether each sleeve independently earns positive excess versus its own matched control in the same non-overlapping calendar blocks used for the combination confirmation.','pairs':PAIRS,'blocks':BLOCKS,'endpoint_cost_bps':10,'results':results,'summary':{'positive_blocks_by_component':counts,'blocks_both_positive':both},'decision_rule':'Strong contribution support only if SPMO>SPY and CALF>IJR in all three fixed blocks. Mixed attribution preserves P290/P291 combination evidence but narrows claims about persistent contribution; it does not trigger weight or component rescue.','decision':decision,'limitations':['component endpoint-cost model differs from combination drift-turnover cost because each sleeve is held independently','same adjusted-price provider as prior tests','scientific attribution only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p293_spmo_calf_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
