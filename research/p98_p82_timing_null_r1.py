from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p82_smh_representation_r1 as p82
N=2000; BLOCK=6; SEED=982026

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)

def block_perm(x,rng):
    x=np.asarray(x,float); blocks=[x[i:i+BLOCK] for i in range(0,len(x),BLOCK)]; order=rng.permutation(len(blocks)); return np.concatenate([blocks[i] for i in order])[:len(x)]

def main():
    f,_=p82.blend(); q=f.loc[f.index>=p82.START].dropna().copy(); actual=cagr(q.candidate); matched=cagr(q.matched); qqq=cagr(q.qqq); actual_m=actual-matched; actual_q=actual-qqq
    rng=np.random.default_rng(SEED); nm=[]; nq=[]
    p64=q.p64.to_numpy(float); p36=q.p36.to_numpy(float)
    for _ in range(N):
        sh=block_perm(p36,rng); cand=.5*p64+.5*sh; cc=cagr(cand); nm.append(cc-matched); nq.append(cc-qqq)
    nm=np.asarray(nm); nq=np.asarray(nq)
    out={'schema':'research.p98_p82_timing_null_r1','parent':'P82','hypothesis':'If the delayed SMH P82 blend depends on contemporaneous complementarity rather than generic component return distributions, preserving P64 exactly while six-month-block permuting only the P36-SMH realized component should rarely reproduce actual matched and QQQ excess.','scientific_contract':{'representation':'P82 SMH representation unchanged','start':'2015-01-01','component_cost_bps':50,'execution_delay_trading_days':5,'sleeve_weights':[0.5,0.5],'null':'permute P36-SMH realized monthly component in six-month blocks while holding P64 and controls fixed','replications':N,'seed':SEED,'no_parameter_tuning':True},'actual':{'months':len(q),'cagr':actual,'matched_cagr':matched,'qqq_cagr':qqq,'excess_vs_matched':actual_m,'excess_vs_qqq':actual_q},'null':{'matched_mean':float(nm.mean()),'matched_p95':float(np.quantile(nm,.95)),'matched_p_ge_actual':float(np.mean(nm>=actual_m)),'qqq_mean':float(nq.mean()),'qqq_p95':float(np.quantile(nq,.95)),'qqq_p_ge_actual':float(np.mean(nq>=actual_q))}}
    out['decision']='P82_TIMING_COMPLEMENTARITY_SUPPORTED' if out['null']['matched_p_ge_actual']<=.10 and out['null']['qqq_p_ge_actual']<=.10 else 'P82_TIMING_COMPLEMENTARITY_NOT_ESTABLISHED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p98_p82_timing_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
