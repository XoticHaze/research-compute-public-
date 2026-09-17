from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['XSMO','AVUV','IJR','SPY']; COST=0.0025
x=yf.download(T,start='2019-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna().loc['2020-01-01':]
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
combo=0.5*r.XSMO+0.5*r.AVUV
blocks=[]
for a,b in [('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 q=charge(combo.loc[a:b]); ctl=charge(r.IJR.loc[a:b]); spy=charge(r.SPY.loc[a:b]); blocks.append({'start':a,'end':b,'months':len(q),'combo_ijr_excess_pp':100*(cagr(q)-cagr(ctl)),'combo_spy_excess_pp':100*(cagr(q)-cagr(spy))})
roll=[]
for i in range(11,len(r)):
 q=charge(combo.iloc[i-11:i+1]); ctl=charge(r.IJR.iloc[i-11:i+1]); roll.append(100*(cagr(q)-cagr(ctl)))
positive=sum(v>0 for v in roll); hit=positive/len(roll) if roll else 0.0
full_q=charge(combo); full_ctl=charge(r.IJR); full_spy=charge(r.SPY)
full_ex=100*(cagr(full_q)-cagr(full_ctl)); full_spy_ex=100*(cagr(full_q)-cagr(full_spy))
passed=all(b['combo_ijr_excess_pp']>0 for b in blocks) and hit>=0.70 and full_ex>0
out={'schema':'research.p420_xsmo_avuv_chronology.v1','workload_id':'P420_XSMO_AVUV_CHRONOLOGY_R1','parent':'SMALL_CAP_FACTOR_COMPLEMENTARITY','claim':'The unchanged frozen 50/50 XSMO+AVUV scientific diagnostic from P417 has persistent after-cost matched excess over IJR across fixed chronology blocks and rolling 12-month windows. This tests persistence only and does not select or recommend portfolio weights.','cost_bps_each_endpoint':25,'fixed_weight_each':0.5,'blocks':blocks,'rolling_12m_count':len(roll),'rolling_12m_positive_count':positive,'rolling_12m_positive_rate':hit,'rolling_12m_median_excess_pp':float(np.median(roll)) if roll else None,'rolling_12m_worst_excess_pp':float(np.min(roll)) if roll else None,'full_matched_excess_pp':full_ex,'full_spy_excess_pp':full_spy_ex,'decision_rule':'PERSISTENCE_SUPPORTED only if every fixed 2020-21/2022-23/2024+ block has positive combo-IJR after-cost excess, >=70% rolling 12-month windows are positive, and full-history matched excess is positive. No weight/product/window optimization.','decision':'SMALL_CAP_FACTOR_COMBINATION_PERSISTENCE_SUPPORTED' if passed else 'SMALL_CAP_FACTOR_COMBINATION_PERSISTENCE_NOT_SUPPORTED','scientific_consequence':('P417 complementarity gains independent chronology support; portfolio sizing/ranking remains outside Market Research.' if passed else 'Narrow P417: low residual correlation may exist without sufficiently persistent combined matched excess. Preserve individual survivor evidence and do not parameter-rescue weights/windows.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p420_xsmo_avuv_chronology_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'block_excess_pp':[round(b['combo_ijr_excess_pp'],3) for b in blocks],'rolling_positive_rate':round(hit,3),'median_roll_pp':round(out['rolling_12m_median_excess_pp'],3),'worst_roll_pp':round(out['rolling_12m_worst_excess_pp'],3),'full_excess_pp':round(full_ex,3)},sort_keys=True))