from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['GDX','GLD','USO']; START='2011-01-01'; END='2026-09-18'; COST=.0025
OUT=Path('research/artifacts/mr_gold_miner_relative_specificity_b2_20260918.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px[T].resample('ME').last().dropna(); r=m.pct_change(fill_method=None)
# Preregistered specificity test. Parent signal uses relative energy input cost; competing explanation says raw oil trend alone explains it.
sigs={'relative_uso_gld':((m.USO/m.GLD).pct_change(6,fill_method=None)<0).shift(1),'raw_uso':(m.USO.pct_change(6,fill_method=None)<0).shift(1)}

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
R={name:{'windows':{k:eval_signal(sig,*v) for k,v in windows.items()},'blocks':{k:eval_signal(sig,*v) for k,v in blocks.items()}} for name,sig in sigs.items()}
rel=R['relative_uso_gld']; rawr=R['raw_uso']
long_delta=rel['windows']['2013+']['excess_cagr_pp']-rawr['windows']['2013+']['excess_cagr_pp']
block_wins=sum(rel['blocks'][k]['excess_cagr_pp']>rawr['blocks'][k]['excess_cagr_pp'] for k in blocks)
window_wins=sum(rel['windows'][k]['excess_cagr_pp']>rawr['windows'][k]['excess_cagr_pp'] for k in windows)
# Specificity is supported only if denominator adds economically meaningful and chronologically broad incremental excess.
passed=long_delta>=1.0 and block_wins>=3 and window_wins>=3 and rel['windows']['2022+']['excess_cagr_pp']>=rawr['windows']['2022+']['excess_cagr_pp']
out={'schema':'research.mr_gold_miner_relative_specificity_b2_20260918.v1','parent':'MR_GOLD_MINER_ENERGY_COST_FILTER_B1_20260918__FRONTIER_IMPROVED','question':'Does GLD in the USO/GLD denominator add miner-margin information beyond a raw six-month USO trend?','non_alpha_explanation':'The supported parent is merely generic oil trend timing; dividing by GLD adds no distinct causal information.','frozen':{'lookback_months':6,'threshold':0,'candidate_assets':['GDX','GLD'],'cost_bps_one_way':25,'relative_signal':'prior completed-month 6m USO/GLD change < 0','competitor':'prior completed-month 6m USO change < 0','control':'each signal evaluated against its own static GDX/GLD mixture with identical realized GDX participation','windows':windows,'blocks':blocks,'no_rescue':'no lookback/threshold/ticker/date/cost/control changes'},'results':R,'incremental_long_excess_pp':long_delta,'relative_wins_windows':window_wins,'relative_wins_blocks':block_wins,'decision_rule':'SPECIFICITY_SUPPORTED iff relative minus raw long-window excess >=1pp, relative wins >=3/4 windows and >=3/5 blocks, and 2022+ relative excess >= raw excess; else GENERIC_OIL_TREND_EXPLANATION_SURVIVES.','decision':'SPECIFICITY_SUPPORTED' if passed else 'GENERIC_OIL_TREND_EXPLANATION_SURVIVES','boundaries':{'scientific_authority':True,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'long_delta':round(long_delta,3),'window_wins':window_wins,'block_wins':block_wins,'relative_2022':round(rel['windows']['2022+']['excess_cagr_pp'],3),'raw_2022':round(rawr['windows']['2022+']['excess_cagr_pp'],3)},sort_keys=True))