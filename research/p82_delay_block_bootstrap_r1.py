from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p82_execution_delay_adjudicator_r1 as p82

DELAY=5; BP=50; N=5000; BLOCKS=(6,12); WINDOWS={'2015_forward':'2015-01-01','2022_forward':'2022-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def moving_block_indices(n,block,rng):
    starts=rng.integers(0,n,size=int(np.ceil(n/block)))
    out=[]
    for s in starts: out.extend((np.arange(s,s+block)%n).tolist())
    return np.asarray(out[:n],dtype=int)

def test(q,block,seed):
    cand=q.candidate.to_numpy(); matched=q.matched.to_numpy(); qqq=q.qqq.to_numpy(); n=len(q)
    actual_m=cagr(cand)-cagr(matched); actual_q=cagr(cand)-cagr(qqq)
    rng=np.random.default_rng(seed); em=np.empty(N); eq=np.empty(N)
    for i in range(N):
        ids=moving_block_indices(n,block,rng); em[i]=cagr(cand[ids])-cagr(matched[ids]); eq[i]=cagr(cand[ids])-cagr(qqq[ids])
    return {'months':n,'actual_excess_vs_matched':actual_m,'actual_excess_vs_qqq':actual_q,'block_months':block,'replications':N,'matched_excess_5_50_95_pct':[float(np.quantile(em,x)) for x in (.05,.5,.95)],'qqq_excess_5_50_95_pct':[float(np.quantile(eq,x)) for x in (.05,.5,.95)],'p_bootstrap_excess_le_zero_vs_matched':float(np.mean(em<=0)),'p_bootstrap_excess_le_zero_vs_qqq':float(np.mean(eq<=0)),'positive_probability_vs_matched':float(np.mean(em>0)),'positive_probability_vs_qqq':float(np.mean(eq>0))}

def main():
    f,close=p82.blend(DELAY)
    out={'schema':'research.p82_delay_block_bootstrap_r1','parent':'P82','hypothesis':'The fixed P82 blend retains serially robust positive after-cost excess under its already-tested five-trading-day implementation delay rather than depending on a small set of temporally clustered months.','scientific_contract':{'delay_trading_days':DELAY,'component_cost_bps':BP,'bootstrap_replications':N,'moving_block_lengths_months':list(BLOCKS),'controls':['fixed matched blend','QQQ'],'windows':WINDOWS,'no_signal_weight_window_or_threshold_tuning':True},'tests':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':p82.base.source_hash(close)}}
    for wi,(name,start) in enumerate(WINDOWS.items(),1):
        q=f.loc[f.index>=pd.Timestamp(start)].dropna(); out['tests'][name]={str(b):test(q,b,8200+wi*100+b) for b in BLOCKS}
    t=out['tests']['2022_forward']['12']; out['decision']='P82_DELAY_EDGE_BOOTSTRAP_SUPPORTED' if t['actual_excess_vs_matched']>0 and t['actual_excess_vs_qqq']>0 and t['p_bootstrap_excess_le_zero_vs_matched']<=.10 and t['p_bootstrap_excess_le_zero_vs_qqq']<=.10 else 'P82_DELAY_EDGE_STATISTICALLY_FRAGILE'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p82_delay_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
