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

def evaluate(cross,ind,close,bps):
    idx=cross.index.intersection(ind.index)
    c=cross.loc[idx].gross-cross.loc[idx].turnover*bps/10000
    i=ind.loc[idx].gross-ind.loc[idx].turnover*bps/10000
    combo=.5*c+.5*i
    matched=.5*cross.loc[idx].ew+.5*ind.loc[idx].ew
    mm=close.resample("ME").last().pct_change().reindex(idx)
    cm,bm=base.metrics(combo),base.metrics(matched); pos,folds=base.fold_count(combo,matched)
    return {"months":len(idx),"start":str(idx.min().date()),"end":str(idx.max().date()),"combo":cm,"matched_static_blend":bm,"cross_sleeve":base.metrics(c),"industry_sleeve":base.metrics(i),"spy":base.metrics(mm.SPY),"qqq":base.metrics(mm.QQQ),"excess_cagr_vs_matched":cm["cagr"]-bm["cagr"],"excess_cagr_vs_spy":cm["cagr"]-base.metrics(mm.SPY)["cagr"],"excess_cagr_vs_qqq":cm["cagr"]-base.metrics(mm.QQQ)["cagr"],"positive_folds":pos,"folds":folds,"sleeve_return_correlation":float(c.corr(i))}

def main():
    cross,cclose=p57.run(0); ind,iclose=p47.run(IND,FACTORS,0)
    close=pd.concat([cclose[["SPY","QQQ"]],iclose],axis=1)
    full_idx=cross.index.intersection(ind.index); tests={}
    for label,start in (("full",None),("2015_forward","2015-01-01"),("2020_forward","2020-01-01")):
        cc=cross if start is None else cross.loc[pd.Timestamp(start):]
        ii=ind if start is None else ind.loc[pd.Timestamp(start):]
        tests[label]={str(bp):evaluate(cc,ii,close,bp) for bp in (25,50)}
    out={"schema":"research.p64_independent_combination_r1","parents":["P57","P52","P58"],"hypothesis":"A fixed 50/50 blend of the parsimonious cross-asset sleeve and the independently represented industry sleeve preserves after-cost excess and diversification without relying on the original P52 representation.","scientific_contract":{"crossasset":{"factors":["mom6","trend200"],"top_k":2},"industry":{"universe":list(IND),"factors":list(FACTORS),"top_k":3},"sleeve_weights":[.5,.5],"cadence":"monthly","costs_bps":[25,50],"matched_comparator":"50% crossasset EW + 50% independent-industry EW","broad_controls":["SPY","QQQ"],"temporal_holdouts":["2015-forward","2020-forward"],"no_parameter_or_weight_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","cross_panel_sha256":base.source_hash(cclose),"industry_panel_sha256":base.source_hash(iclose)},"tests":tests}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p64_independent_combination_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({k:{"excess25":v["25"]["excess_cagr_vs_matched"],"excess50":v["50"]["excess_cagr_vs_matched"],"exqqq25":v["25"]["excess_cagr_vs_qqq"],"folds25":v["25"]["positive_folds"],"corr25":v["25"]["sleeve_return_correlation"]} for k,v in tests.items()},sort_keys=True))
if __name__=="__main__": main()
