from __future__ import annotations
import json
from pathlib import Path
import p47_deep_robustness_r2 as p47

BASE=tuple(p47.BASE)
FACTORS=("mom6","trend200")

def pack(fr): return {"25":p47.score(fr,25),"50":p47.score(fr,50)}

def main():
    tests={}
    hashes={}
    for omitted in BASE:
        syms=tuple(s for s in BASE if s!=omitted)
        fr,close=p47.run(syms,FACTORS,0)
        tests[f"leave_out_{omitted}"]=pack(fr)
        hashes[omitted]=p47.base.source_hash(close)
    pass25=sum(v["25"]["excess_cagr"]>0 and v["25"]["positive_folds"]>=3 for v in tests.values())
    pass50=sum(v["50"]["excess_cagr"]>0 for v in tests.values())
    out={
      "schema":"research.p52_leave_one_industry_out_r2",
      "parent":"P52",
      "hypothesis":"The fixed P52 momentum+trend mechanism is not dependent on any single original industry ETF.",
      "scientific_contract":{"base_universe":list(BASE),"factors":list(FACTORS),"top_k":3,"cadence":"monthly","costs_bps":[25,50],"matched_comparator":"same reduced-universe equal weight","tests":"leave each original industry out once","no_parameter_tuning":True},
      "source":{"provider":"Yahoo Finance via yfinance","panel_sha256_by_omission":hashes},
      "summary":{"variants":len(tests),"variants_positive_25_with_3of5_folds":pass25,"variants_positive_50":pass50},
      "tests":tests
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p52_leave_one_industry_out_r2.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"summary":out["summary"],"tests":{k:{"excess25":v["25"]["excess_cagr"],"folds25":v["25"]["positive_folds"],"excess50":v["50"]["excess_cagr"]} for k,v in tests.items()}},sort_keys=True))
if __name__=="__main__": main()
