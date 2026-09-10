from __future__ import annotations
import json,math
from pathlib import Path
import pandas as pd,yfinance as yf
CAND=['SPMO','CALF']; BASE=['SPY','IJR']; CONTROL='QQQ'; START='2018-01-01'; END='2026-09-10'; COST=10/10000
BLOCKS={'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_present':('2025-01-01','2026-09-10')}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def equal_rebalanced(r,cols):
 target=pd.Series({c:1/len(cols) for c in cols},dtype=float); out=[]; turns=[]; prev_end=None
 for _,row in r[cols].iterrows():
  turnover=1.0 if prev_end is None else float((target-prev_end).abs().sum()/2)
  gross=float((target*row).sum()); out.append(gross-turnover*COST); turns.append(turnover)
  grown=target*(1+row); denom=float(grown.sum()); prev_end=(grown/denom) if denom else target.copy()
 return pd.Series(out,index=r.index,dtype=float),pd.Series(turns,index=r.index,dtype=float)
syms=CAND+BASE+[CONTROL]; raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); cand,ct=equal_rebalanced(r,CAND); base,bt=equal_rebalanced(r,BASE)
results={}
for name,(start,end) in BLOCKS.items():
 ix=(r.index>=pd.Timestamp(start))&(r.index<=pd.Timestamp(end)); a=cand.loc[ix]; b=base.loc[ix]; q=r.loc[ix,CONTROL]; am=metric(a); bm=metric(b); qm=metric(q)
 results[name]={'candidate':am,'matched_blend':bm,'matched_excess_cagr':am['cagr']-bm['cagr'],'vs_QQQ_cagr':am['cagr']-qm['cagr'],'candidate_avg_monthly_turnover':float(ct.loc[ix].mean()),'matched_avg_monthly_turnover':float(bt.loc[ix].mean())}
positive_matched=sum(v['matched_excess_cagr']>0 for v in results.values()); positive_qqq=sum(v['vs_QQQ_cagr']>0 for v in results.values()); no_drawdown_penalty=sum(v['candidate']['maxdd']>=v['matched_blend']['maxdd']-.05 for v in results.values())
ok=positive_matched==3 and no_drawdown_penalty==3
out={'schema':'research.p290_spmo_calf_calendar_r1','parent':'P290','claim':'Independently confirm the previously frozen 50/50 SPMO+CALF combination by requiring after-cost matched excess to persist across non-overlapping calendar blocks without changing components, weights, rebalance cadence, or controls.','parameters':{'candidate':CAND,'matched':BASE,'weights':[0.5,0.5],'monthly_rebalance':True,'one_way_turnover_cost_bps':10,'blocks':BLOCKS,'no_weight_component_window_search':True},'results':results,'summary':{'positive_matched_blocks':positive_matched,'positive_QQQ_blocks':positive_qqq,'no_gt5pp_drawdown_penalty_blocks':no_drawdown_penalty},'decision_rule':'Independent matched-baseline confirmation requires positive matched excess and no >5pp drawdown penalty in all three fixed non-overlapping blocks. QQQ block dominance is separately reported as opportunity-cost scope and is not required for matched confirmation.','decision':'P290_SPMO_CALF_INDEPENDENT_CALENDAR_CONFIRMATION' if ok else 'P290_SPMO_CALF_CALENDAR_WEAKNESS','limitations':['same adjusted-price provider as exploratory run, so this is temporal-structure confirmation rather than source-independent replication','2025-present block is short but prospectively fixed','scientific combination evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p290_spmo_calf_calendar_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
