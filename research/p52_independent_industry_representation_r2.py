from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p47_deep_robustness_r2 as p47

SYMS=("SOXX","XBI","XHB","KRE","ITA","IGV","IYT","XRT","XOP","IHI")
FACTORS=("mom6","trend200")

def pack(fr): return {"25":p47.score(fr,25),"50":p47.score(fr,50)}

def main():
    full,close=p47.run(SYMS,FACTORS,0)
    lag,_=p47.run(SYMS,FACTORS,1)
    tests={"full":pack(full),"one_month_execution_lag":pack(lag)}
    for start in ("2015-01-01","2020-01-01"):
        tests[f"{start[:4]}_forward"]=pack(full.loc[pd.Timestamp(start):])
    out={
      "schema":"research.p52_independent_industry_representation_r2",
      "parent":"P52",
      "hypothesis":"The fixed momentum+trend top-3 industry mechanism preserves after-cost matched alpha in a materially different industry ETF representation.",
      "scientific_contract":{"universe":list(SYMS),"factors":list(FACTORS),"top_k":3,"cadence":"monthly","costs_bps":[25,50],"matched_comparator":"same-universe equal weight","broad_controls":["SPY","QQQ"],"temporal_holdouts":["2015-forward","2020-forward"],"execution_lag_test":"one month","no_parameter_tuning":True},
      "source":{"provider":"Yahoo Finance via yfinance","normalized_price_panel_sha256":p47.base.source_hash(close)},
      "tests":tests
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p52_independent_industry_representation_r2.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({k:{"excess25":v["25"]["excess_cagr"],"folds25":v["25"]["positive_folds"],"excess50":v["50"]["excess_cagr"]} for k,v in tests.items()},sort_keys=True))
if __name__=="__main__": main()
