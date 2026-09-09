from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p47_deep_robustness_r2 as p47

SYMS=tuple(p47.BASE); FACTORS=("mom6","trend200")

def main():
    fr,close=p47.run(SYMS,FACTORS,0)
    spy=close["SPY"]
    risk_on=(spy>spy.rolling(200,min_periods=160).mean()).resample("ME").last()
    risk_on=risk_on.reindex(fr.index).astype("boolean")
    tests={}
    for bps in (25,50):
        cand=fr.gross-fr.turnover*bps/10000
        ex=cand-fr.ew
        rows={}
        for label,mask in (("risk_on",risk_on==True),("risk_off",risk_on==False)):
            e=ex[mask.fillna(False)]
            c=cand[mask.fillna(False)]; b=fr.ew[mask.fillna(False)]
            rows[label]={"months":int(len(e)),"annualized_mean_excess":float(e.mean()*12),"candidate":p47.base.metrics(c),"matched_ew":p47.base.metrics(b),"excess_cagr":p47.base.metrics(c)["cagr"]-p47.base.metrics(b)["cagr"]}
        strongest=ex.nlargest(5).index
        keep=~fr.index.isin(strongest)
        c2=cand[keep]; b2=fr.ew[keep]
        rows["remove_five_strongest_relative_months"]={"months":int(keep.sum()),"removed":[str(pd.Timestamp(x).date()) for x in strongest],"candidate":p47.base.metrics(c2),"matched_ew":p47.base.metrics(b2),"excess_cagr":p47.base.metrics(c2)["cagr"]-p47.base.metrics(b2)["cagr"]}
        tests[str(bps)]=rows
    out={"schema":"research.p59_p52_regime_concentration_r1","parent":"P52","hypothesis":"P52 matched alpha is not solely a risk-on or extreme-month artifact.","scientific_contract":{"universe":list(SYMS),"factors":list(FACTORS),"top_k":3,"cadence":"monthly","costs_bps":[25,50],"regime":"prior/current month-end SPY above its causal 200d SMA","concentration_test":"remove five strongest candidate-minus-matched months","no_parameter_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","normalized_price_panel_sha256":p47.base.source_hash(close)},"tests":tests}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p59_p52_regime_concentration_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({bp:{k:{"months":v["months"],"excess":v.get("annualized_mean_excess",v.get("excess_cagr"))} for k,v in rows.items()} for bp,rows in tests.items()},sort_keys=True))
if __name__=="__main__": main()
