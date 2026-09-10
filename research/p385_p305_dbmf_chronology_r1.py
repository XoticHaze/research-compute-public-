from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SPMO','IJS','SPY','IJR','DBMF','BIL']; COST=0.0025
x=yf.download(T,start='2020-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
m=c[T].resample('ME').last().dropna(); r=m.pct_change().dropna()
base=.5*(.5*r.SPMO+.5*r.IJS)+.5*r.DBMF
ctl=.5*(.5*r.SPY+.5*r.IJR)+.5*r.BIL
idx=base.index.intersection(ctl.index); base=base.reindex(idx); ctl=ctl.reindex(idx)

def with_endpoint_cost(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s):
 return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def maxdd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
def sharpe(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
blocks=[('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]
rows=[]
for a,b in blocks:
 s=with_endpoint_cost(base.loc[a:b]); q=with_endpoint_cost(ctl.loc[a:b])
 rows.append({'start':a,'end':b,'months':int(len(s)),'blend_cagr':cagr(s),'control_cagr':cagr(q),'matched_excess_pp':100*(cagr(s)-cagr(q)),'blend_sharpe':sharpe(s),'control_sharpe':sharpe(q),'blend_max_drawdown':maxdd(s),'control_max_drawdown':maxdd(q),'positive_matched':bool(cagr(s)>cagr(q))})
# Independent rolling chronology diagnostic. Apply no synthetic endpoint charge inside each overlapping window; both fixed sleeves were already defined as buy/hold endpoint-cost contracts.
# To avoid cost omission, charge each 12m diagnostic an equal 25 bp at both ends to blend and matched control.
rolling=[]
for i in range(11,len(base)):
 s=with_endpoint_cost(base.iloc[i-11:i+1]); q=with_endpoint_cost(ctl.iloc[i-11:i+1])
 rolling.append({'end':str(s.index[-1].date()),'matched_excess_pp':100*(cagr(s)-cagr(q))})
positive_roll=sum(z['matched_excess_pp']>0 for z in rolling); roll_rate=positive_roll/len(rolling) if rolling else 0
worst=min((z['matched_excess_pp'] for z in rolling),default=float('nan'))
median=float(np.median([z['matched_excess_pp'] for z in rolling])) if rolling else float('nan')
pass_gate=sum(z['positive_matched'] for z in rows)==3 and roll_rate>=0.65 and median>0
out={'schema':'research.p385_p305_dbmf_chronology.v1','workload_id':'P385_P305_DBMF_CHRONOLOGY_R1','claim':'Orthogonally test chronology persistence of the unchanged P384 fixed 50/50 P305+DBMF combination against its exact combined matched control without changing products, weights, costs, or dates after observation.','blend':'50% P305 (50% SPMO + 50% IJS) + 50% DBMF','control':'50% P305 control (50% SPY + 50% IJR) + 50% BIL','cost_bps_each_endpoint':25,'blocks':rows,'positive_blocks':sum(z['positive_matched'] for z in rows),'rolling_12m_count':len(rolling),'rolling_12m_positive_count':positive_roll,'rolling_12m_positive_rate':roll_rate,'rolling_12m_median_excess_pp':median,'rolling_12m_worst_excess_pp':worst,'decision_rule':'SUPPORTED only if all 3 fixed non-overlapping blocks have positive matched excess, >=65% of fixed rolling 12-month windows have positive matched excess after equal endpoint costs, and median rolling matched excess is positive. No weight/product/window/cost search.','decision':'P305_DBMF_CHRONOLOGY_SUPPORTED' if pass_gate else 'P305_DBMF_CHRONOLOGY_NOT_SUPPORTED','scientific_consequence':('Chronology evidence independently supports P384 combination persistence within the DBMF-specific scope; no broad managed-futures or portfolio-allocation authority follows.' if pass_gate else 'Record chronology weakness for the combination claim only; preserve P305 and DBMF-specific prior passing evidence independently and do not parameter-rescue the blend.'),'rolling_sample':rolling,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p385_p305_dbmf_chronology_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_blocks':out['positive_blocks'],'rolling_positive_rate':round(roll_rate,3),'rolling_median_excess_pp':round(median,3),'rolling_worst_excess_pp':round(worst,3)},sort_keys=True))
