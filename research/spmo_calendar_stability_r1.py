from __future__ import annotations
import json,math
from pathlib import Path
import pandas as pd,yfinance as yf
SYMS=['SPMO','SPY','QQQ']; START='2017-01-01'; END='2026-09-11'; COST=10.; BLOCKS={'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_present':('2023-01-01','2026-09-11')}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def ep(r):
 q=pd.Series(r,dtype=float).dropna().copy(); f=COST/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for name,(a,b) in BLOCKS.items():
 z=r.loc[(r.index>=pd.Timestamp(a))&(r.index<=pd.Timestamp(b))]; sm=metric(ep(z.SPMO)); sp=metric(ep(z.SPY)); qq=metric(ep(z.QQQ)); results[name]={'SPMO':sm,'SPY':sp,'QQQ':qq,'excess_vs_SPY_cagr':sm['cagr']-sp['cagr'],'excess_vs_QQQ_cagr':sm['cagr']-qq['cagr']}
positive_spy=sum(v['excess_vs_SPY_cagr']>0 for v in results.values()); positive_qqq=sum(v['excess_vs_QQQ_cagr']>0 for v in results.values()); recent_spy=results['2020_2022']['excess_vs_SPY_cagr']>0 and results['2023_present']['excess_vs_SPY_cagr']>0; ok=positive_spy==3 and positive_qqq>=2 and recent_spy
out={'schema':'research.spmo_calendar_stability_r1','workload_id':'SPMO_CALENDAR_STABILITY_R1','parent_context':'STOCK_MOMENTUM_INDEPENDENT_TRANSPORT_R2','claim':'Orthogonally falsify the unchanged SPMO survivor by requiring after-cost excess to persist across fixed non-overlapping calendar blocks rather than nested windows.','parameters':{'blocks':BLOCKS,'entry_exit_bps':COST,'no_tuning':True},'results':results,'decision_rule':'Calendar stability passes only if SPMO beats SPY in all three non-overlapping blocks, beats QQQ in at least two blocks, and beats SPY in both post-2020 blocks. No block, product, or threshold selection is allowed.','decision':'SPMO_CALENDAR_STABILITY_SUPPORTED' if ok else 'SPMO_CALENDAR_STABILITY_NOT_SUPPORTED','limitations':['calendar-block test does not establish holdings/sector attribution or factor-adjusted alpha','Yahoo adjusted fund returns are research-only','scientific evidence only; no portfolio-ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/spmo_calendar_stability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
