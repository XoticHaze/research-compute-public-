from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import p13_semiconductor_stock_specific_residual as p13
import p13_twofactor_residual_r1 as tf

BP=50

def sha_bytes(b: bytes)->str: return hashlib.sha256(b).hexdigest()
def cagr(x):
    x=np.asarray(x,float); return float(np.prod(1+x)**(12/len(x))-1)

def main():
    close,volume=p13.download()
    close=close.sort_index().sort_index(axis=1)
    csv=close.to_csv(date_format='%Y-%m-%d',float_format='%.12g').encode()
    positions=p13.month_end_indices(close.index); rows=[]
    for j in range(len(positions)-1):
        sig,nxt=positions[j],positions[j+1]; entry,exit_=sig+1,nxt+1
        if sig<p13.LOOKBACK or exit_>=len(close) or close.index[entry]<pd.Timestamp('2019-01-01'): continue
        raw={}; one={}; two={}
        for n in p13.UNIVERSE:
            now,then=close.iloc[sig][n],close.iloc[sig-p13.LOOKBACK][n]
            if np.isfinite(now) and np.isfinite(then) and then>0: raw[n]=float(now/then-1)
            s1=p13.stock_specific_residual_score(close,n,sig); s2=tf.score_twofactor(close,n,sig)
            if np.isfinite(s1): one[n]=s1
            if np.isfinite(s2): two[n]=s2
        eligible=sorted(set(raw).intersection(one).intersection(two))
        if len(eligible)<8: continue
        chosen=sorted(eligible,key=lambda n:(-two[n],n))[:p13.TOP_N]
        ret=p13.basket_return(close,chosen,entry,exit_); ew=p13.basket_return(close,eligible,entry,exit_); smh=p13.asset_return(close,'SMH',entry,exit_); qqq=p13.asset_return(close,'QQQ',entry,exit_)
        if not all(np.isfinite(v) for v in (ret,ew,smh,qqq)): continue
        rows.append({'signal_date':str(close.index[sig].date()),'entry_date':str(close.index[entry].date()),'exit_date':str(close.index[exit_].date()),'eligible':eligible,'selected':chosen,'candidate_net_50bp':float(ret-.005),'equal_weight':float(ew),'smh':float(smh),'qqq':float(qqq)})
    sel_blob=json.dumps(rows,sort_keys=True,separators=(',',':')).encode(); recent=[r for r in rows if r['entry_date']>='2022-01-01']
    def stats(rr):
        return {'months':len(rr),'candidate_cagr':cagr([r['candidate_net_50bp'] for r in rr]),'equal_weight_cagr':cagr([r['equal_weight'] for r in rr]),'smh_cagr':cagr([r['smh'] for r in rr]),'qqq_cagr':cagr([r['qqq'] for r in rr])}
    out={'schema':'research.p13_frozen_contract_replay_r1','parent':'P13','scientific_contract':{'source_request':{'start':p13.START,'end':p13.END,'tickers':p13.UNIVERSE+p13.BENCHMARKS,'auto_adjust':True},'eligibility':'intersection(raw_126d, onefactor_SMH_residual_126d, twofactor_SMH_QQQ_residual_126d)','selection':'top3 twofactor residual with symbol tie-break','cost_bps':BP,'no_parameter_search':True},'panel_sha256':sha_bytes(csv),'panel_shape':[int(close.shape[0]),int(close.shape[1])],'selection_return_fingerprint_sha256':sha_bytes(sel_blob),'full':stats(rows),'2022_forward':stats(recent),'monthly_records':rows,'decision':'P13_FROZEN_CONTRACT_BASELINE_MATERIALIZED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_adjusted_close_frozen.csv').write_bytes(csv); Path('artifacts/p13_frozen_contract_replay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:v for k,v in out.items() if k!='monthly_records'},sort_keys=True))
if __name__=='__main__': main()
