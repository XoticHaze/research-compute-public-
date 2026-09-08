from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import fixed_multifactor_cross_sectional_r1 as base
import fixed_multifactor_cross_sectional_r1_complete_month as guard

SYMBOLS = base.UNIVERSES["crossasset"]
VARIANTS = {
    "full": ("mom6", "trend200", "low_vol6", "drawdown6"),
    "momentum_only": ("mom6",),
    "mom_trend": ("mom6", "trend200"),
    "mom_lowvol": ("mom6", "low_vol6"),
    "mom_drawdown": ("mom6", "drawdown6"),
    "without_momentum": ("trend200", "low_vol6", "drawdown6"),
}


def materialize(close: pd.DataFrame):
    monthly = close.resample("ME").last()
    daily_r = close.pct_change()
    f = {
        "mom6": monthly.pct_change(6),
        "trend200": (close / close.rolling(200, min_periods=160).mean() - 1).resample("ME").last(),
        "low_vol6": -(daily_r.rolling(126, min_periods=100).std(ddof=0) * np.sqrt(252)).resample("ME").last(),
        "drawdown6": (close / close.rolling(126, min_periods=100).max() - 1).resample("ME").last(),
    }
    last = pd.Timestamp(close.index.max())
    if last.tzinfo is not None:
        last = last.tz_localize(None)
    monthly = monthly.loc[monthly.index <= last.normalize()].copy()
    f = {k: v.loc[v.index.isin(monthly.index)] for k, v in f.items()}
    return monthly, f


def returns_for(monthly, f, fields):
    prev = {s: 0.0 for s in SYMBOLS}
    rows=[]
    for month in monthly.index:
        block=pd.DataFrame(index=list(SYMBOLS))
        for field in fields:
            block[field]=f[field].loc[month,list(SYMBOLS)]
        if block.isna().any().any():
            continue
        score=block.rank(axis=0,pct=True,method="average").mean(axis=1)
        chosen=score.sort_values(ascending=False).head(2).index.tolist()
        loc=monthly.index.get_loc(month)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly):
            continue
        nxt=monthly.index[loc+1]
        realized=monthly.loc[nxt,list(SYMBOLS)]/monthly.loc[month,list(SYMBOLS)]-1
        if realized.isna().any(): continue
        w={s:(0.5 if s in chosen else 0.0) for s in SYMBOLS}
        turnover=0.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS)
        rows.append({"month":str(nxt.date()),"gross":sum(w[s]*float(realized[s]) for s in SYMBOLS),"ew":float(realized.mean()),"turnover":turnover})
        prev=w
    return pd.DataFrame(rows)


def main():
    close=base.load(SYMBOLS)
    monthly,f=materialize(close)
    out={"schema":"research.crossasset_composite_attribution_r1","source_sha256":base.source_hash(close),"variants":{}}
    for name,fields in VARIANTS.items():
        frame=returns_for(monthly,f,fields)
        c=frame.gross-frame.turnover*0.0025
        b=frame.ew
        cm,bm=base.metrics(c),base.metrics(b)
        pos,folds=base.fold_count(c,b)
        c50=frame.gross-frame.turnover*0.005
        m50=base.metrics(c50)
        out["variants"][name]={"fields":list(fields),"window":{"start":frame.iloc[0].month,"end":frame.iloc[-1].month,"months":len(frame)},"candidate_25":cm,"matched_ew_25":bm,"excess_cagr_25":cm["cagr"]-bm["cagr"],"positive_folds":int(pos),"folds":folds,"excess_cagr_50":m50["cagr"]-bm["cagr"],"annual_turnover":float(frame.turnover.mean()*12)}
    full=out["variants"]["full"]
    rivals={k:v for k,v in out["variants"].items() if k!="full"}
    best=max(rivals.items(),key=lambda kv:kv[1]["candidate_25"]["calmar"])
    out["decision"]={"full_supported":bool(full["excess_cagr_25"]>0.01 and full["positive_folds"]>=3 and full["excess_cagr_50"]>0),"best_simpler_by_calmar":best[0],"best_simpler_excess_cagr_25":best[1]["excess_cagr_25"],"full_minus_best_simpler_cagr":full["candidate_25"]["cagr"]-best[1]["candidate_25"]["cagr"]}
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/crossasset_composite_attribution.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out["decision"],sort_keys=True))

if __name__=="__main__": main()
