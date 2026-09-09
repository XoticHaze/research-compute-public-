from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p57_crossasset_parsimonious_r1 as p57
import p47_deep_robustness_r2 as p47

IND=("SOXX","XBI","XHB","KRE","ITA","IGV","IYT","XRT","XOP","IHI")
FACTORS=("mom6","trend200")

def frame(bps=25):
    cross,cclose=p57.run(0); ind,_=p47.run(IND,FACTORS,0); idx=cross.index.intersection(ind.index)
    cand=.5*(cross.loc[idx].gross-cross.loc[idx].turnover*bps/10000)+.5*(ind.loc[idx].gross-ind.loc[idx].turnover*bps/10000)
    matched=.5*cross.loc[idx].ew+.5*ind.loc[idx].ew
    qqq=cclose.resample("ME").last().pct_change()["QQQ"].reindex(idx)
    return pd.DataFrame({"candidate":cand,"matched":matched,"qqq":qqq}).dropna(),cclose

def roll(fr,months,benchmark):
    vals=[]
    for i in range(len(fr)-months+1):
        c=fr.candidate.iloc[i:i+months]; b=fr[benchmark].iloc[i:i+months]
        vals.append(float((1+c).prod()**(12/months)-(1+b).prod()**(12/months)))
    a=np.asarray(vals,float)
    return {"window_months":months,"benchmark":benchmark,"n":int(len(a)),"positive_fraction":float((a>0).mean()),"median_excess_cagr":float(np.median(a)),"p10_excess_cagr":float(np.quantile(a,.1)),"worst_excess_cagr":float(a.min()),"best_excess_cagr":float(a.max())}

def block_bootstrap(fr,benchmark,block=12,n=5000,seed=66):
    x=(fr.candidate-fr[benchmark]).to_numpy(float); N=len(x); starts=np.arange(N-block+1); rng=np.random.default_rng(seed); vals=[]
    for _ in range(n):
        parts=[]
        while sum(len(z) for z in parts)<N:
            s=int(rng.choice(starts)); parts.append(x[s:s+block])
        vals.append(float(np.concatenate(parts)[:N].mean()*12))
    a=np.asarray(vals); q=np.quantile(a,[.025,.975])
    return {"benchmark":benchmark,"block_months":block,"n":n,"annualized_mean_excess":float(x.mean()*12),"bootstrap_95pct":[float(q[0]),float(q[1])],"p_excess_le_zero":float((a<=0).mean())}

def main():
    fr,close=frame(25); tests={}
    for months in (36,60):
        tests[f"rolling_{months}m_vs_matched"]=roll(fr,months,"matched")
        tests[f"rolling_{months}m_vs_qqq"]=roll(fr,months,"qqq")
    tests["block_bootstrap_vs_matched"]=block_bootstrap(fr,"matched")
    tests["block_bootstrap_vs_qqq"]=block_bootstrap(fr,"qqq",seed=166)
    out={"schema":"research.p66_combination_serial_persistence_r1","parents":["P58","P64"],"hypothesis":"The fixed P64 50/50 parsimonious cross-asset plus independent-industry blend improves contiguous matched persistence and clarifies QQQ opportunity cost.","scientific_contract":{"cost_bps":25,"sleeve_weights":[.5,.5],"rolling_windows_months":[36,60],"moving_block_months":12,"bootstrap_draws":5000,"benchmarks":["matched static blend","QQQ"],"no_parameter_or_weight_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","cross_panel_sha256":base.source_hash(close)},"tests":tests}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p66_combination_serial_persistence_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(tests,sort_keys=True))
if __name__=="__main__": main()
