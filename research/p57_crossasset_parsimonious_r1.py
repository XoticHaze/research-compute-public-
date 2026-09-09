from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES["crossasset"])

def run(lag=0):
    close=base.load(SYMS)
    m=close.resample("ME").last()
    mom=m.pct_change(6)
    trend=(close/close.rolling(200,min_periods=160).mean()-1).resample("ME").last()
    prev={s:0.0 for s in SYMS}; rec=[]
    for dt in m.index:
        b=pd.DataFrame({"mom6":mom.loc[dt,list(SYMS)],"trend200":trend.loc[dt,list(SYMS)]},index=list(SYMS))
        if b.isna().any().any(): continue
        score=b.rank(axis=0,pct=True,method="average").mean(axis=1)
        loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1+lag>=len(m): continue
        start=m.index[loc+lag]; nxt=m.index[loc+1+lag]
        r=m.loc[nxt,list(SYMS)]/m.loc[start,list(SYMS)]-1
        if r.isna().any(): continue
        chosen=score.sort_values(ascending=False).head(2).index.tolist()
        w={s:(0.5 if s in chosen else 0.0) for s in SYMS}
        to=0.5*sum(abs(w[s]-prev[s]) for s in SYMS)
        rec.append({"date":nxt,"gross":sum(w[s]*float(r[s]) for s in SYMS),"ew":float(r.mean()),"turnover":to})
        prev=w
    return pd.DataFrame(rec).set_index("date"),close

def score(fr,bps):
    c=fr.gross-fr.turnover*bps/10000; b=fr.ew
    cm,bm=base.metrics(c),base.metrics(b); pos,folds=base.fold_count(c,b)
    return {"months":len(fr),"start":str(fr.index.min().date()),"end":str(fr.index.max().date()),"candidate":cm,"matched_ew":bm,"excess_cagr":cm["cagr"]-bm["cagr"],"positive_folds":pos,"folds":folds}
def pack(fr): return {"25":score(fr,25),"50":score(fr,50)}

def main():
    full,close=run(0); lag,_=run(1)
    tests={"full":pack(full),"one_month_execution_lag":pack(lag)}
    for start in ("2015-01-01","2020-01-01"):
        tests[f"{start[:4]}_forward"]=pack(full.loc[pd.Timestamp(start):])
    out={"schema":"research.p57_crossasset_parsimonious_r1","parent":"P46","hypothesis":"Removing low-volatility and drawdown terms preserves or improves the supported cross-asset mechanism, yielding a simpler momentum+trend top-2 allocator.","scientific_contract":{"universe":list(SYMS),"factors":["mom6","trend200"],"top_k":2,"cadence":"monthly","costs_bps":[25,50],"matched_comparator":"same-universe equal weight","temporal_holdouts":["2015-forward","2020-forward"],"execution_lag_test":"one month","no_parameter_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","normalized_price_panel_sha256":base.source_hash(close)},"tests":tests}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p57_crossasset_parsimonious_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({k:{"excess25":v["25"]["excess_cagr"],"folds25":v["25"]["positive_folds"],"excess50":v["50"]["excess_cagr"]} for k,v in tests.items()},sort_keys=True))
if __name__=="__main__": main()
