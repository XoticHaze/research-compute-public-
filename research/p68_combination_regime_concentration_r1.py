from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p57_crossasset_parsimonious_r1 as p57
import p47_deep_robustness_r2 as p47

IND=("SOXX","XBI","XHB","KRE","ITA","IGV","IYT","XRT","XOP","IHI")
FACTORS=("mom6","trend200")

def frame(bps):
    cross,close=p57.run(0); ind,_=p47.run(IND,FACTORS,0); idx=cross.index.intersection(ind.index)
    cand=.5*(cross.loc[idx].gross-cross.loc[idx].turnover*bps/10000)+.5*(ind.loc[idx].gross-ind.loc[idx].turnover*bps/10000)
    matched=.5*cross.loc[idx].ew+.5*ind.loc[idx].ew
    m=close.resample("ME").last(); state=(close["SPY"]>close["SPY"].rolling(200,min_periods=160).mean()).resample("ME").last().shift(1).reindex(idx)
    qqq=m["QQQ"].pct_change().reindex(idx)
    return pd.DataFrame({"candidate":cand,"matched":matched,"qqq":qqq,"risk_on":state}).dropna(),close

def score(c,b):
    cm,bm=base.metrics(c),base.metrics(b)
    return {"months":len(c),"candidate":cm,"benchmark":bm,"excess_cagr":cm["cagr"]-bm["cagr"],"annualized_mean_excess":float((c-b).mean()*12)}

def main():
    tests={}; src=None
    for bp in (25,50):
        fr,close=frame(bp); src=close; rows={}
        for label,val in (("risk_on",True),("risk_off",False)):
            s=fr[fr.risk_on==val]; rows[f"{label}_vs_matched"]=score(s.candidate,s.matched); rows[f"{label}_vs_qqq"]=score(s.candidate,s.qqq)
        ex=fr.candidate-fr.matched; strong=ex.nlargest(5).index; keep=~fr.index.isin(strong)
        rows["remove_five_strongest_vs_matched"]={**score(fr.candidate[keep],fr.matched[keep]),"removed":[str(x.date()) for x in strong]}
        tests[str(bp)]=rows
    out={"schema":"research.p68_combination_regime_concentration_r1","parents":["P58","P64"],"hypothesis":"The fixed P64 combination reduces P57 risk-off and extreme-month concentration while preserving matched after-cost alpha.","scientific_contract":{"sleeve_weights":[.5,.5],"costs_bps":[25,50],"regime":"prior feature-month SPY above causal 200d SMA","concentration_test":"remove five strongest candidate-minus-matched months","benchmarks":["matched static blend","QQQ"],"no_parameter_or_weight_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","cross_panel_sha256":base.source_hash(src)},"tests":tests}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p68_combination_regime_concentration_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({bp:{k:{"months":v["months"],"excess":v["excess_cagr"]} for k,v in rows.items()} for bp,rows in tests.items()},sort_keys=True))
if __name__=="__main__": main()
