from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['GDX','GLD','USO']; START='2011-01-01'; END='2026-09-18'; COST=.0025
OUT=Path('research/artifacts/mr_gold_miner_dual_confirmation_b3_20260918.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px[T].resample('ME').last().dropna(); r=m.pct_change(fill_method=None)
# Frozen B3: surviving parent is generic six-month oil trend. Challenger adds independent miner-price confirmation.
parent=(m.USO.pct_change(6,fill_method=None)<0).shift(1)
challenger=((m.USO.pct_change(6,fill_method=None)<0) & (m.GDX.pct_change(6,fill_method=None)>0)).shift(1)

def eval_signal(sig,start,end=None):
 q=pd.DataFrame({'gdx':r.GDX,'gld':r.GLD,'sig':sig}).loc[start:end].dropna().copy()
 if len(q)<18:return {'months':int(len(q))}
 w=q.sig.astype(float); switches=w.diff().abs().fillna(w.abs()); cand=w*q.gdx+(1-w)*q.gld-COST*switches
 p=float(w.mean()); ctl=p*q.gdx+(1-p)*q.gld
 if len(ctl): ctl.iloc[0]-=COST
 def met(x):
  eq=(1+x).cumprod(); years=len(x)/12
  return {'cagr_pct':100*float(eq.iloc[-1]**(1/years)-1),'max_drawdown_pct':100*float((eq/eq.cummax()-1).min())}
 cm,bm=met(cand),met(ctl)
 return {'months':len(q),'gdx_participation':p,'switches':float(switches.sum()),'candidate':cm,'matched_control':bm,'excess_cagr_pp':cm['cagr_pct']-bm['cagr_pct']}

windows={'2013+':('2013-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2013_2015':('2013-01-01','2015-12-31'),'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
R={name:{'windows':{k:eval_signal(sig,*v) for k,v in windows.items()},'blocks':{k:eval_signal(sig,*v) for k,v in blocks.items()}} for name,sig in {'raw_oil_parent':parent,'dual_confirmation':challenger}.items()}
p=R['raw_oil_parent']; c=R['dual_confirmation']
long_delta=c['windows']['2013+']['excess_cagr_pp']-p['windows']['2013+']['excess_cagr_pp']
window_wins=sum(c['windows'][k]['excess_cagr_pp']>p['windows'][k]['excess_cagr_pp'] for k in windows)
block_wins=sum(c['blocks'][k]['excess_cagr_pp']>p['blocks'][k]['excess_cagr_pp'] for k in blocks)
dd_delta=c['windows']['2013+']['candidate']['max_drawdown_pct']-p['windows']['2013+']['candidate']['max_drawdown_pct']
passed=long_delta>=1.0 and window_wins>=3 and block_wins>=3 and c['windows']['2022+']['excess_cagr_pp']>=p['windows']['2022+']['excess_cagr_pp'] and dd_delta>=-5.0
out={'schema':'research.mr_gold_miner_dual_confirmation_b3_20260918.v1','parent':'GENERIC_OIL_TREND_EXPLANATION_SURVIVES','question':'Does requiring positive six-month GDX trend when raw six-month oil trend is negative improve the supported GDX/GLD timing survivor?','non_alpha_explanation':'The added miner-price confirmation merely reduces participation after the fact and does not add stable predictive information beyond generic oil trend.','frozen':{'lookback_months':6,'thresholds':{'USO_return_lt':0,'GDX_return_gt':0},'candidate_assets':['GDX','GLD'],'cost_bps_one_way':25,'parent_signal':'prior completed-month 6m USO change < 0','challenger_signal':'prior completed-month 6m USO change < 0 AND prior completed-month 6m GDX change > 0','control':'each signal against its own static GDX/GLD mixture with identical realized GDX participation','windows':windows,'blocks':blocks,'no_rescue':'no lookback/threshold/ticker/date/cost/control changes'},'results':R,'incremental_long_excess_pp':long_delta,'challenger_wins_windows':window_wins,'challenger_wins_blocks':block_wins,'long_candidate_drawdown_delta_pp':dd_delta,'decision_rule':'FRONTIER_IMPROVED iff challenger adds >=1pp long-window excess, wins >=3/4 windows and >=3/5 blocks, preserves/improves 2022+ excess, and long-window max drawdown is no more than 5pp worse; else HOLD_GENERIC_OIL_SURVIVOR.','decision':'FRONTIER_IMPROVED' if passed else 'HOLD_GENERIC_OIL_SURVIVOR','boundaries':{'scientific_authority':True,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'long_delta':round(long_delta,3),'window_wins':window_wins,'block_wins':block_wins,'challenger_2022':round(c['windows']['2022+']['excess_cagr_pp'],3),'parent_2022':round(p['windows']['2022+']['excess_cagr_pp'],3),'dd_delta':round(dd_delta,3)},sort_keys=True))