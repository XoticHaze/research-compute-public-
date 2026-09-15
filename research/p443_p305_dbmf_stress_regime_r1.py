from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd
INPUT=Path('research/inputs/p423_exact/p423_p305_dbmf_monthly_prices.csv'); OUT=Path('research/artifacts/p443_p305_dbmf_stress_regime_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
START='2019-06-30'; END='2026-09-30'; LB=24; EP=.0025; DD=-.10
m=pd.read_csv(INPUT,index_col='date',parse_dates=True); r=m.pct_change(fill_method=None)
p305=.5*(r.SPMO+r.IJS); ctl=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
 w=r[['HYG','SHY','SRLN']].iloc[max(0,i-LB):i].dropna()
 if len(w)<LB: bs.append((np.nan,np.nan)); continue
 b=np.clip(np.linalg.lstsq(w[['HYG','SHY']].values,w.SRLN.values,rcond=None)[0],0,1); b=b/b.sum() if b.sum()>1 else b; bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1); loanctl=b.hyg*r.HYG+b.shy*r.SHY
q=pd.DataFrame({'challenger':.5*p305+.5*r.DBMF,'matched_control':.5*ctl+.5*r.BIL,'core':.5*p305+.5*r.SRLN,'spy':r.SPY}).dropna().loc[START:END]
if len(q)!=88: raise SystemExit(f'P423_SAMPLE_MISMATCH {len(q)}')
spy_px=(1+q.spy).cumprod(); dd=spy_px/spy_px.cummax()-1; stress=dd<=DD

def stats(z):
 n=len(z)
 if not n:return {'months':0}
 def geo(x): return float(np.prod(1+np.asarray(x))**(12/n)-1)
 return {'months':n,'challenger_cagr':geo(z.challenger),'matched_control_cagr':geo(z.matched_control),'core_cagr':geo(z.core),'matched_excess_cagr':geo(z.challenger)-geo(z.matched_control),'core_advantage_cagr':geo(z.challenger)-geo(z.core),'challenger_hit_rate':float((z.challenger>0).mean()),'challenger_mean_monthly':float(z.challenger.mean())}
s=stats(q.loc[stress]); normal=stats(q.loc[~stress]); supported=s.get('months',0)>=6 and s['matched_excess_cagr']>0 and s['core_advantage_cagr']>0
out={'schema':'research.p443_p305_dbmf_stress_regime_r1.v1','workload_id':'P443_P305_DBMF_STRESS_REGIME_R1','parent':'P305_DBMF_COMPLEMENTARITY','claim':'The fixed 50/50 P305+DBMF formulation should add economically useful protection relative to both its matched control and frozen P305+SRLN core specifically during broad-equity drawdown stress, providing orthogonal crisis-regime evidence rather than another full-sample bootstrap.','input_provenance':{'p423_artifact_id':10168949628,'p423_artifact_sha256':'1e66a243355e69b295a8324800b91edb237b028d2fe5f5f0c7a12cbad7393faf','fresh_market_redownload':False},'sample':{'start':START,'end':END,'months':len(q)},'regime_contract':{'stress_definition':'SPY cumulative drawdown from running peak <= -10% within admitted sample','threshold':DD,'parameter_search':False,'endpoint_cost_bps_each':25,'note':'No threshold/date/weight rescue after observation.'},'stress':s,'normal':normal,'decision':'P305_DBMF_STRESS_COMPLEMENTARITY_SUPPORTED' if supported else 'P305_DBMF_STRESS_COMPLEMENTARITY_NOT_SUPPORTED','scientific_consequence':('Adds orthogonal crisis-regime support to the matched-alpha survivor while leaving Coordinator ranking/allocation authority unchanged.' if supported else 'Crisis-regime complementarity is not established for the frozen formulation; retain prior matched-alpha evidence but do not rescue this stress test with nearby thresholds.'),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'stress':s,'normal':normal},sort_keys=True))
