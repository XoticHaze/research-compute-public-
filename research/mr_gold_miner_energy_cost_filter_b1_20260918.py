from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['GDX','GLD','USO']; START='2011-01-01'; END='2026-09-18'; COST=.0025
OUT=Path('research/artifacts/mr_gold_miner_energy_cost_filter_b1_20260918.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px[T].resample('ME').last().dropna()
r=m.pct_change(fill_method=None)
# Frozen causal signal: at completed month t, favorable miner input-cost state iff
# six-month USO/GLD relative-price change is negative. Hold GDX next month if favorable, else GLD.
rel=(m.USO/m.GLD).pct_change(6,fill_method=None)
sig=(rel<0).shift(1).reindex(r.index).fillna(False)

def eval_window(start,end=None):
    q=pd.DataFrame({'gdx':r.GDX,'gld':r.GLD,'sig':sig}).loc[start:end].dropna().copy()
    if len(q)<18:return {'months':int(len(q))}
    w=q.sig.astype(float)
    gross=w*q.gdx+(1-w)*q.gld
    switches=w.diff().abs().fillna(w.abs())
    cand=gross-COST*switches
    p=float(w.mean())
    control=p*q.gdx+(1-p)*q.gld
    # Endpoint friction on the static matched-participation control.
    if len(control): control.iloc[0]-=COST
    def metrics(x):
        eq=(1+x).cumprod(); years=len(x)/12
        cagr=float(eq.iloc[-1]**(1/years)-1) if years>0 else float('nan')
        dd=float((eq/eq.cummax()-1).min())
        return {'cagr_pct':100*cagr,'max_drawdown_pct':100*dd}
    cm, bm=metrics(cand), metrics(control)
    return {'months':int(len(q)),'gdx_participation':p,'switches':float(switches.sum()),'candidate':cm,'matched_control':bm,'excess_cagr_pp':cm['cagr_pct']-bm['cagr_pct']}

windows={'2013+':('2013-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2013_2015':('2013-01-01','2015-12-31'),'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
W={k:eval_window(*v) for k,v in windows.items()}; B={k:eval_window(*v) for k,v in blocks.items()}
posw=sum(v.get('excess_cagr_pp',-999)>0 for v in W.values()); posb=sum(v.get('excess_cagr_pp',-999)>0 for v in B.values())
coverage=all(v.get('months',0)>=18 for v in B.values())
long=W['2013+']; dd_guard=long.get('candidate',{}).get('max_drawdown_pct',-999) >= long.get('matched_control',{}).get('max_drawdown_pct',0)-5
passed=coverage and posw>=3 and posb>=3 and W['2022+'].get('excess_cagr_pp',-999)>0 and dd_guard
out={'schema':'research.mr_gold_miner_energy_cost_filter_b1_20260918.v1','workload_id':'MR_GOLD_MINER_ENERGY_COST_FILTER_B1_20260918','parent':'GOLD_MINER_INDEPENDENT_ALPHA_SUPPORTED','claim':'A completed-month decline in the 6-month USO/GLD relative price identifies lower energy-input-cost pressure for gold miners and should improve next-month GDX-vs-GLD selection beyond an equal-participation static GDX/GLD control after costs.','non_alpha_explanation':'Any apparent gain is generic time-varying gold beta or chance commodity co-movement rather than miner margin information.','contract':{'signal':'prior completed-month 6m change in USO/GLD < 0','candidate':'GDX when favorable else GLD','matched_control':'static GDX/GLD mixture with identical realized GDX participation','switch_cost_bps_one_way':25,'windows':windows,'blocks':blocks,'minimum_block_months':18,'protected_boundary':'no threshold/lookback/ticker/date/cost/control rescue'},'windows':W,'blocks':B,'positive_excess_windows':posw,'positive_excess_blocks':posb,'coverage_ready':coverage,'drawdown_guard':dd_guard,'decision_rule':'FRONTIER_IMPROVED only if >=3/4 windows and >=3/5 blocks have positive excess, 2022+ excess is positive, every block has >=18 months, and long-window drawdown is no worse than matched control by >5pp. Otherwise HOLD_CURRENT_SURVIVOR.','decision':('FRONTIER_IMPROVED' if passed else ('INCONCLUSIVE_COVERAGE' if not coverage else 'HOLD_CURRENT_SURVIVOR')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'windows':{k:round(v.get('excess_cagr_pp',-999),3) for k,v in W.items()},'blocks':{k:round(v.get('excess_cagr_pp',-999),3) for k,v in B.items()},'long':long},sort_keys=True))