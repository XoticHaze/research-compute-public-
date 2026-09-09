from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p13_semiconductor_stock_specific_residual as p13
import p13_twofactor_residual_r1 as tf

BP=50

def cagr(x):
    x=np.asarray(x,float); return float(np.prod(1+x)**(12/len(x))-1)

def main():
    close,volume=p13.download(); pos=p13.month_end_indices(close.index); rows=[]
    for j in range(len(pos)-1):
        sig,nxt=pos[j],pos[j+1]; entry,exit_=sig+1,nxt+1
        if sig<p13.LOOKBACK or exit_>=len(close) or close.index[entry]<pd.Timestamp('2019-01-01'): continue
        scores={n:tf.score_twofactor(close,n,sig) for n in p13.UNIVERSE}; scores={n:s for n,s in scores.items() if np.isfinite(s)}
        if len(scores)<8: continue
        chosen=sorted(scores,key=lambda n:scores[n],reverse=True)[:p13.TOP_N]
        realized={n:p13.asset_return(close,n,entry,exit_) for n in scores}
        if not all(np.isfinite(v) for v in realized.values()): continue
        rows.append({'entry':close.index[entry],'chosen':chosen,'realized':realized,'ew':float(np.mean(list(realized.values()))),'smh':p13.asset_return(close,'SMH',entry,exit_)})
    def eval_lag(rr,lag):
        vals=[]; ew=[]; smh=[]
        for i in range(lag,len(rr)):
            picks=rr[i-lag]['chosen']; cur=rr[i]
            if not all(n in cur['realized'] for n in picks): continue
            vals.append(float(np.mean([cur['realized'][n] for n in picks]))-BP/10000); ew.append(cur['ew']); smh.append(cur['smh'])
        return {'months':len(vals),'candidate_cagr':cagr(vals),'ew_cagr':cagr(ew),'smh_cagr':cagr(smh),'excess_vs_ew':cagr(vals)-cagr(ew),'excess_vs_smh':cagr(vals)-cagr(smh)}
    tests={}
    for lab,rr in [('full',rows),('2022_forward',[r for r in rows if r['entry']>=pd.Timestamp('2022-01-01')])]: tests[lab]={str(l):eval_lag(rr,l) for l in (0,1,2,3)}
    r=tests['2022_forward']; margin=r['0']['excess_vs_smh']; place=max(r[str(l)]['excess_vs_smh'] for l in (1,2,3)); state='P13_TWOFACTOR_TIMING_SPECIFICITY_SUPPORTED' if margin>0 and place < margin*0.5 else 'P13_TWOFACTOR_TIMING_SPECIFICITY_WEAK'
    out={'schema':'research.p13_twofactor_signal_lag_placebo_r1','parent':'P13','scientific_contract':{'candidate':'prior-only 126-session SMH+QQQ residual top-3 monthly','placebo':'apply rankings delayed by 1,2,3 months to later realized returns','cost_bps':BP,'comparators':['same-window equal weight','SMH'],'known_current-name_survivorship_risk_preserved':True,'no_parameter_search':True},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_twofactor_signal_lag_placebo_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
