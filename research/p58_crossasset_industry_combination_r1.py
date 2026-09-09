from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

CROSS=tuple(base.UNIVERSES["crossasset"])
IND=tuple(base.UNIVERSES["industry"])
ALL=tuple(dict.fromkeys((*CROSS,*IND)))

def maps(close):
    m=close.resample("ME").last(); dr=close.pct_change()
    return m,{"mom6":m.pct_change(6),"trend200":(close/close.rolling(200,min_periods=160).mean()-1).resample("ME").last(),"low_vol6":-(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample("ME").last(),"drawdown6":(close/close.rolling(126,min_periods=100).max()-1).resample("ME").last()}

def sleeve_score(fm,dt,syms,factors):
    b=pd.DataFrame({f:fm[f].loc[dt,list(syms)] for f in factors},index=list(syms))
    if b.isna().any().any(): return None
    return b.rank(axis=0,pct=True,method="average").mean(axis=1)

def run():
    close=base.load(ALL); m,fm=maps(close)
    prev_c={s:0.0 for s in CROSS}; prev_i={s:0.0 for s in IND}; rec=[]
    for dt in m.index:
        cs=sleeve_score(fm,dt,CROSS,("mom6","trend200","low_vol6","drawdown6"))
        ins=sleeve_score(fm,dt,IND,("mom6","trend200"))
        if cs is None or ins is None: continue
        loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
        nxt=m.index[loc+1]
        rc=m.loc[nxt,list(CROSS)]/m.loc[dt,list(CROSS)]-1
        ri=m.loc[nxt,list(IND)]/m.loc[dt,list(IND)]-1
        if rc.isna().any() or ri.isna().any(): continue
        cc=cs.sort_values(ascending=False).head(2).index.tolist(); ic=ins.sort_values(ascending=False).head(3).index.tolist()
        wc={s:(0.5 if s in cc else 0.0) for s in CROSS}; wi={s:(1/3 if s in ic else 0.0) for s in IND}
        tc=0.5*sum(abs(wc[s]-prev_c[s]) for s in CROSS); ti=0.5*sum(abs(wi[s]-prev_i[s]) for s in IND)
        cg=sum(wc[s]*float(rc[s]) for s in CROSS); ig=sum(wi[s]*float(ri[s]) for s in IND)
        rec.append({"date":nxt,"cross_gross":cg,"industry_gross":ig,"cross_turn":tc,"industry_turn":ti,"matched":0.5*float(rc.mean())+0.5*float(ri.mean()),"spy":float(m.at[nxt,"SPY"]/m.at[dt,"SPY"]-1),"qqq":float(m.at[nxt,"QQQ"]/m.at[dt,"QQQ"]-1)})
        prev_c,prev_i=wc,wi
    return pd.DataFrame(rec).set_index("date"),close

def evaluate(fr,bps):
    cross=fr.cross_gross-fr.cross_turn*bps/10000
    ind=fr.industry_gross-fr.industry_turn*bps/10000
    combo=0.5*cross+0.5*ind
    cm,bm=base.metrics(combo),base.metrics(fr.matched); pos,folds=base.fold_count(combo,fr.matched)
    return {"combo":cm,"matched_static_blend":bm,"cross_sleeve":base.metrics(cross),"industry_sleeve":base.metrics(ind),"spy":base.metrics(fr.spy),"qqq":base.metrics(fr.qqq),"excess_cagr_vs_matched":cm["cagr"]-bm["cagr"],"excess_cagr_vs_cross":cm["cagr"]-base.metrics(cross)["cagr"],"excess_cagr_vs_industry":cm["cagr"]-base.metrics(ind)["cagr"],"positive_folds":pos,"folds":folds,"sleeve_return_correlation":float(cross.corr(ind)),"mean_annual_turnover_combined":float((0.5*fr.cross_turn+0.5*fr.industry_turn).mean()*12)}
def pack(fr): return {"25":evaluate(fr,25),"50":evaluate(fr,50)}

def main():
    full,close=run(); tests={"full":pack(full)}
    for start in ("2015-01-01","2020-01-01"):
        tests[f"{start[:4]}_forward"]=pack(full.loc[pd.Timestamp(start):])
    out={"schema":"research.p58_crossasset_industry_combination_r1","parents":["P46","P52"],"hypothesis":"A fixed 50/50 blend of the supported P46 four-factor cross-asset sleeve and P52 two-factor industry sleeve creates after-cost diversification value beyond the exact static blended universe and either sleeve alone.","scientific_contract":{"crossasset":{"universe":list(CROSS),"factors":["mom6","trend200","low_vol6","drawdown6"],"top_k":2},"industry":{"universe":list(IND),"factors":["mom6","trend200"],"top_k":3},"sleeve_weights":[0.5,0.5],"cadence":"monthly","costs_bps":[25,50],"matched_comparator":"50% crossasset equal-weight + 50% industry equal-weight","opportunity_controls":["each dynamic sleeve","SPY","QQQ"],"temporal_holdouts":["2015-forward","2020-forward"],"no_weight_or_parameter_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","normalized_price_panel_sha256":base.source_hash(close)},"tests":tests}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p58_crossasset_industry_combination_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({k:{"excess25":v["25"]["excess_cagr_vs_matched"],"folds25":v["25"]["positive_folds"],"excess50":v["50"]["excess_cagr_vs_matched"],"corr25":v["25"]["sleeve_return_correlation"]} for k,v in tests.items()},sort_keys=True))
if __name__=="__main__": main()
