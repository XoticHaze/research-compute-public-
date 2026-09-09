from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import p57_crossasset_parsimonious_r1 as p57


def window_stats(fr,months,bps=25):
    cand=fr.gross-fr.turnover*bps/10000; base=fr.ew; vals=[]
    for i in range(0,len(fr)-months+1):
        c=cand.iloc[i:i+months]; b=base.iloc[i:i+months]
        cg=float((1+c).prod()**(12/months)-1); bg=float((1+b).prod()**(12/months)-1)
        vals.append(cg-bg)
    a=np.asarray(vals,float)
    return {"window_months":months,"n":int(len(a)),"positive_fraction":float((a>0).mean()),"median_excess_cagr":float(np.median(a)),"p10_excess_cagr":float(np.quantile(a,.1)),"worst_excess_cagr":float(a.min()),"best_excess_cagr":float(a.max())}

def moving_block_bootstrap(fr,bps=25,block=12,n=5000,seed=65):
    x=(fr.gross-fr.turnover*bps/10000-fr.ew).to_numpy(float); N=len(x); rng=np.random.default_rng(seed); vals=[]
    starts=np.arange(0,N-block+1)
    for _ in range(n):
        chunks=[]
        while sum(len(z) for z in chunks)<N:
            s=int(rng.choice(starts)); chunks.append(x[s:s+block])
        y=np.concatenate(chunks)[:N]; vals.append(float(y.mean()*12))
    a=np.asarray(vals,float); q=np.quantile(a,[.025,.975])
    return {"block_months":block,"n":n,"annualized_mean_excess":float(x.mean()*12),"bootstrap_95pct":[float(q[0]),float(q[1])],"p_excess_le_zero":float((a<=0).mean())}

def main():
    fr,close=p57.run(0)
    out={"schema":"research.p65_crossasset_serial_persistence_r1","parents":["P46","P57"],"hypothesis":"The fixed P57 matched excess is persistent across multi-year contiguous windows and survives a serial-dependence-aware moving-block bootstrap.","scientific_contract":{"factors":["mom6","trend200"],"top_k":2,"cadence":"monthly","cost_bps":25,"matched_comparator":"same-universe equal weight","rolling_windows_months":[36,60],"moving_block_bootstrap_months":12,"bootstrap_draws":5000,"no_parameter_tuning":True},"source":{"normalized_price_panel_sha256":p57.base.source_hash(close)},"tests":{"rolling_36m":window_stats(fr,36),"rolling_60m":window_stats(fr,60),"moving_block_bootstrap_25":moving_block_bootstrap(fr)}}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p65_crossasset_serial_persistence_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out["tests"],sort_keys=True))
if __name__=="__main__": main()
