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

def frame():
    cross,close=p57.run(0); ind,_=p47.run(IND,FACTORS,0); idx=cross.index.intersection(ind.index)
    m=close.resample("ME").last(); qqq=m["QQQ"].pct_change().reindex(idx); spy=m["SPY"].pct_change().reindex(idx)
    gross=.5*cross.loc[idx].gross+.5*ind.loc[idx].gross
    turnover=.5*cross.loc[idx].turnover+.5*ind.loc[idx].turnover
    matched=.5*cross.loc[idx].ew+.5*ind.loc[idx].ew
    return pd.DataFrame({"gross":gross,"turnover":turnover,"matched":matched,"qqq":qqq,"spy":spy}).dropna(),close

def metric(r):
    m=base.metrics(r); return {"cagr":m["cagr"],"ann_vol":m["annualized_vol"],"sharpe":m["sharpe_rf0"],"max_drawdown":m["max_drawdown_monthly"],"calmar":m["calmar"]}

def main():
    fr,close=frame(); tests={}
    for bp in (25,50,100):
        c=fr.gross-fr.turnover*bp/10000; cm=metric(c); mm=metric(fr.matched); qm=metric(fr.qqq); sm=metric(fr.spy)
        tests[str(bp)]={"candidate":cm,"matched":mm,"qqq":qm,"spy":sm,"excess_cagr_vs_matched":cm["cagr"]-mm["cagr"],"excess_cagr_vs_qqq":cm["cagr"]-qm["cagr"],"excess_cagr_vs_spy":cm["cagr"]-sm["cagr"],"mean_annual_turnover":float(fr.turnover.mean()*12)}
    base_cagr=base.metrics(fr.matched)["cagr"]; xs=[]
    for bp in range(0,251): xs.append(base.metrics(fr.gross-fr.turnover*bp/10000)["cagr"]-base_cagr)
    non=[i for i,x in enumerate(xs) if x<=0]
    out={"schema":"research.p69_combination_capital_risk_r1","parents":["P58","P64"],"hypothesis":"The fixed P64 combination has sufficient cost headroom and risk efficiency to justify continued research despite QQQ opportunity cost.","scientific_contract":{"sleeve_weights":[.5,.5],"costs_bps":[25,50,100],"matched_comparator":"fixed static blend","broad_controls":["SPY","QQQ"],"risk_metrics":["volatility","Sharpe","max drawdown","Calmar"],"no_parameter_or_weight_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","cross_panel_sha256":base.source_hash(close)},"tests":tests,"matched_cost_breakeven":{"first_nonpositive_bps":non[0] if non else None,"excess_at_25":xs[25],"excess_at_50":xs[50],"excess_at_100":xs[100]}}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p69_combination_capital_risk_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"tests":{k:{"ex_matched":v["excess_cagr_vs_matched"],"ex_qqq":v["excess_cagr_vs_qqq"],"ex_spy":v["excess_cagr_vs_spy"],"mdd":v["candidate"]["max_drawdown"],"sharpe":v["candidate"]["sharpe"]} for k,v in tests.items()},"breakeven":out["matched_cost_breakeven"]},sort_keys=True))
if __name__=="__main__": main()
