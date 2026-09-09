from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd
import p47_deep_robustness_r2 as p47
SYMS=p47.BASE; FACTORS=('mom6','trend200')
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def rolling(c,b,n):
 a=np.array([cagr(c.iloc[i-n:i])-cagr(b.iloc[i-n:i]) for i in range(n,len(c)+1)]); return {'windows':len(a),'positive_fraction':float((a>0).mean()),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1))}
def boot(c,b,reps=5000,block=12):
 x=(c-b).dropna().to_numpy(); n=len(x); rng=np.random.default_rng(520052); vals=[]
 for _ in range(reps):
  s=[]
  while len(s)<n:
   i=int(rng.integers(0,max(1,n-block+1))); s.extend(x[i:i+block])
  vals.append(float(np.mean(s[:n])*12))
 a=np.array(vals); return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float((a<=0).mean())}
def main():
 fr,close=p47.run(SYMS,FACTORS,0); ctr=p47.base.load(('SPY','QQQ')); tests={}
 for bp in (25,50,100):
  c=fr.gross-fr.turnover*bp/10000; controls={'matched_equal_weight':fr.ew}
  for s in ('SPY','QQQ'): controls[s]=ctr[s].resample('ME').last().pct_change().reindex(fr.index)
  tests[str(bp)]={k:{'rolling36':rolling(c,b,36),'rolling60':rolling(c,b,60),'bootstrap':boot(c,b)} for k,b in controls.items()}
 p=tests['25']['matched_equal_weight']; q=tests['50']['matched_equal_weight']; supported=p['rolling60']['positive_fraction']>=.6 and p['bootstrap']['p_excess_le_zero']<=.2 and q['bootstrap']['annualized_mean_excess']>0
 out={'schema':'research.p52_serial_persistence_r2','parent':'P52','scientific_contract':{'economics':'unchanged momentum+trend industry top-3 monthly','costs_bps':[25,50,100],'rolling_windows_months':[36,60],'bootstrap':'12m moving block 5000 reps','comparators':['same-universe equal weight','SPY','QQQ'],'no_parameter_tuning':True},'source':{'industry_panel_sha256':p47.base.source_hash(close),'control_panel_sha256':p47.base.source_hash(ctr)},'window':{'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'months':len(fr)},'tests':tests,'decision':'P52_SERIAL_PERSISTENCE_SUPPORTED' if supported else 'P52_SERIAL_PERSISTENCE_NOT_SUPPORTED'}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p52_serial_persistence_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'25_matched':p,'50_matched':q,'25_QQQ':tests['25']['QQQ']},sort_keys=True))
if __name__=='__main__': main()
