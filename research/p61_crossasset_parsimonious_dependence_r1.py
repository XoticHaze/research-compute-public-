from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

BASE=tuple(base.UNIVERSES["crossasset"])

def run(symbols):
    close=base.load(tuple(symbols)); m=close.resample("ME").last(); mom=m.pct_change(6); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample("ME").last(); prev={s:0.0 for s in symbols}; rec=[]
    for dt in m.index:
        b=pd.DataFrame({"mom6":mom.loc[dt,list(symbols)],"trend200":trend.loc[dt,list(symbols)]},index=list(symbols))
        if b.isna().any().any(): continue
        sc=b.rank(axis=0,pct=True,method="average").mean(axis=1); loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
        nxt=m.index[loc+1]; r=m.loc[nxt,list(symbols)]/m.loc[dt,list(symbols)]-1
        if r.isna().any(): continue
        chosen=sc.sort_values(ascending=False).head(2).index.tolist(); w={s:(0.5 if s in chosen else 0.0) for s in symbols}; to=0.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rec.append({"date":nxt,"gross":sum(w[s]*float(r[s]) for s in symbols),"ew":float(r.mean()),"turnover":to}); prev=w
    return pd.DataFrame(rec).set_index("date"),close

def score(fr,bps):
    c=fr.gross-fr.turnover*bps/10000; b=fr.ew; cm,bm=base.metrics(c),base.metrics(b); pos,folds=base.fold_count(c,b)
    return {"candidate":cm,"matched_ew":bm,"excess_cagr":cm["cagr"]-bm["cagr"],"positive_folds":pos,"folds":folds}
def pack(fr): return {"25":score(fr,25),"50":score(fr,50)}

def main():
    tests={}; hashes={}
    full,close=run(BASE); hashes["full"]=base.source_hash(close)
    for omitted in BASE:
        syms=tuple(s for s in BASE if s!=omitted); fr,c=run(syms); tests[f"leave_out_{omitted}"]=pack(fr); hashes[omitted]=base.source_hash(c)
    c25=full.gross-full.turnover*0.0025; ex=c25-full.ew; strongest=ex.nlargest(5).index; keep=~full.index.isin(strongest); cm,bm=base.metrics(c25[keep]),base.metrics(full.ew[keep]); tests["remove_five_strongest_relative_months_25"]={"removed":[str(pd.Timestamp(x).date()) for x in strongest],"excess_cagr":cm["cagr"]-bm["cagr"],"candidate":cm,"matched_ew":bm}
    x=ex.to_numpy(); rng=np.random.default_rng(61); vals=np.array([rng.choice(x,size=len(x),replace=True).mean()*12 for _ in range(3000)]); q=np.quantile(vals,[.025,.975]); tests["paired_bootstrap_25"]={"annualized_mean_excess":float(x.mean()*12),"bootstrap_95pct":[float(q[0]),float(q[1])],"p_excess_le_zero":float((vals<=0).mean()),"n":3000}
    out={"schema":"research.p61_crossasset_parsimonious_dependence_r1","parents":["P46","P57"],"hypothesis":"P57 is not dependent on one original asset or a handful of extreme relative months.","scientific_contract":{"base_universe":list(BASE),"factors":["mom6","trend200"],"top_k":2,"cadence":"monthly","costs_bps":[25,50],"matched_comparator":"same reduced-universe equal weight","tests":["five leave-one-asset-out variants","remove five strongest relative months at 25bps","paired monthly bootstrap"],"no_parameter_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","panel_sha256":hashes},"tests":tests}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p61_crossasset_parsimonious_dependence_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"leave_out":{k:{"excess25":v["25"]["excess_cagr"],"folds25":v["25"]["positive_folds"],"excess50":v["50"]["excess_cagr"]} for k,v in tests.items() if k.startswith("leave_out_")},"extreme_removed_excess25":tests["remove_five_strongest_relative_months_25"]["excess_cagr"],"bootstrap":tests["paired_bootstrap_25"]},sort_keys=True))
if __name__=="__main__": main()
