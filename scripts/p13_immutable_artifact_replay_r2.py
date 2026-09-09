from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import p13_semiconductor_stock_specific_residual as p13
import p13_twofactor_residual_r1 as tf

EXPECTED_PANEL='a5f7f8eb3ce1ad9b185df661701623681c7b918edb55d31d188f4dc886650253'
EXPECTED_FP='e6b63d26f01d7b21f752a9bb32cd6866f2551e7dfe9aeb59363d6a9a6a59f64f'
BP=50

def cagr(x):
    x=np.asarray(x,float); return float(np.prod(1+x)**(12/len(x))-1)

def main():
    raw=Path('input/p13_adjusted_close_frozen.csv').read_bytes(); panel_sha=hashlib.sha256(raw).hexdigest()
    if panel_sha!=EXPECTED_PANEL: raise RuntimeError(f'panel sha mismatch {panel_sha}')
    close=pd.read_csv('input/p13_adjusted_close_frozen.csv',index_col=0,parse_dates=True).sort_index().sort_index(axis=1)
    positions=p13.month_end_indices(close.index); rows=[]
    for j in range(len(positions)-1):
        sig,nxt=positions[j],positions[j+1]; entry,exit_=sig+1,nxt+1
        if sig<p13.LOOKBACK or exit_>=len(close) or close.index[entry]<pd.Timestamp('2019-01-01'): continue
        rawscore={}; one={}; two={}
        for n in p13.UNIVERSE:
            now,then=close.iloc[sig][n],close.iloc[sig-p13.LOOKBACK][n]
            if np.isfinite(now) and np.isfinite(then) and then>0: rawscore[n]=float(now/then-1)
            s1=p13.stock_specific_residual_score(close,n,sig); s2=tf.score_twofactor(close,n,sig)
            if np.isfinite(s1): one[n]=s1
            if np.isfinite(s2): two[n]=s2
        eligible=sorted(set(rawscore).intersection(one).intersection(two))
        if len(eligible)<8: continue
        chosen=sorted(eligible,key=lambda n:(-two[n],n))[:p13.TOP_N]
        ret=p13.basket_return(close,chosen,entry,exit_); ew=p13.basket_return(close,eligible,entry,exit_); smh=p13.asset_return(close,'SMH',entry,exit_); qqq=p13.asset_return(close,'QQQ',entry,exit_)
        if not all(np.isfinite(v) for v in (ret,ew,smh,qqq)): continue
        rows.append({'signal_date':str(close.index[sig].date()),'entry_date':str(close.index[entry].date()),'exit_date':str(close.index[exit_].date()),'eligible':eligible,'selected':chosen,'candidate_net_50bp':float(ret-.005),'equal_weight':float(ew),'smh':float(smh),'qqq':float(qqq)})
    fp=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if fp!=EXPECTED_FP: raise RuntimeError(f'fingerprint mismatch {fp}')
    recent=[r for r in rows if r['entry_date']>='2022-01-01']
    def stats(rr): return {'months':len(rr),'candidate_cagr':cagr([r['candidate_net_50bp'] for r in rr]),'equal_weight_cagr':cagr([r['equal_weight'] for r in rr]),'smh_cagr':cagr([r['smh'] for r in rr]),'qqq_cagr':cagr([r['qqq'] for r in rr])}
    out={'schema':'research.p13_immutable_artifact_replay_r2','parent':'P13','source_run_id':34325797529,'source_artifact_id':10093700209,'panel_sha256':panel_sha,'selection_return_fingerprint_sha256':fp,'full':stats(rows),'2022_forward':stats(recent),'decision':'P13_IMMUTABLE_REPLAY_EXACT_MATCH'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_immutable_artifact_replay_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
