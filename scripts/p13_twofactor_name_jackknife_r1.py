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

def run(excluded=None):
    close,volume=p13.download(); pos=p13.month_end_indices(close.index); rows=[]
    names=[n for n in p13.UNIVERSE if n!=excluded]
    for j in range(len(pos)-1):
        sig,nxt=pos[j],pos[j+1]; entry,exit_=sig+1,nxt+1
        if sig<p13.LOOKBACK or exit_>=len(close) or close.index[entry]<pd.Timestamp('2019-01-01'): continue
        scores={}
        for n in names:
            s=tf.score_twofactor(close,n,sig)
            if np.isfinite(s): scores[n]=s
        common=sorted(scores)
        if len(common)<7: continue
        chosen=sorted(common,key=lambda n:scores[n],reverse=True)[:p13.TOP_N]
        actual=p13.basket_return(close,chosen,entry,exit_); ew=p13.basket_return(close,common,entry,exit_); smh=p13.asset_return(close,'SMH',entry,exit_)
        if all(np.isfinite(v) for v in (actual,ew,smh)): rows.append((close.index[entry],actual-BP/10000,ew,smh))
    f=pd.DataFrame(rows,columns=['entry','candidate','ew','smh'])
    out={}
    for lab,g in [('full',f),('2022_forward',f[f.entry>=pd.Timestamp('2022-01-01')])]:
        out[lab]={'months':len(g),'candidate_cagr':cagr(g.candidate),'ew_cagr':cagr(g.ew),'smh_cagr':cagr(g.smh),'excess_vs_ew':cagr(g.candidate)-cagr(g.ew),'excess_vs_smh':cagr(g.candidate)-cagr(g.smh)}
    return out

def main():
    base=run(); tests={n:run(n) for n in p13.UNIVERSE}; recent=[v['2022_forward']['excess_vs_smh'] for v in tests.values()]; ew=[v['2022_forward']['excess_vs_ew'] for v in tests.values()]
    supported=min(recent)>0 and min(ew)>0
    out={'schema':'research.p13_twofactor_name_jackknife_r1','parent':'P13','scientific_contract':{'candidate':'prior-only 126-session SMH+QQQ residual top-3 monthly','cost_bps':BP,'jackknife':'remove each current-name semiconductor one at a time and recompute rankings','comparators':['same-jackknife equal weight','SMH'],'windows':['full','2022-forward'],'known_current-name_survivorship_risk_preserved':True,'no_parameter_search':True},'base':base,'leave_one_name_out':tests,'recent_min_excess_vs_smh':min(recent),'recent_min_excess_vs_ew':min(ew),'recent_worst_name_vs_smh':p13.UNIVERSE[int(np.argmin(recent))],'decision':'P13_TWOFACTOR_NOT_SINGLE_NAME_DEPENDENT' if supported else 'P13_TWOFACTOR_NAME_CONCENTRATION_RISK'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_twofactor_name_jackknife_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
