from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import p104_p111_crossasset_model_family_tournament_r1 as base
import p137_p105_dual_horizon_incremental_mechanism_r1 as p137

def folds(a,b,n=3): return sum(base.metrics(a.iloc[i])["cagr"]>base.metrics(b.iloc[i])["cagr"] for i in np.array_split(np.arange(len(a)),n) if len(i))
def build(assets):
    syms=tuple(dict.fromkeys((*assets,"SPY","QQQ"))); raw=yf.download(list(syms),start="2007-01-01",auto_adjust=True,progress=False,threads=False); close=raw["Close"] if isinstance(raw.columns,pd.MultiIndex) else raw[["Close"]]; close=close.loc[:,list(syms)].dropna(how="all").astype(float); close.index=pd.DatetimeIndex(close.index).tz_localize(None); m=close.resample("ME").last(); ret=m.pct_change(); prev=pd.Series(0.0,index=assets); rows=[]
    for i in range(1,len(m.index)-1):
        dt=m.index[i]; nxt=m.index[i+1]; month=nxt.month; hist=ret.loc[(ret.index<nxt)&(ret.index.month==month),list(assets)].dropna(how="any"); nr=ret.loc[nxt,list(syms)]
        if len(hist)<3 or nr.isna().any(): continue
        score=hist.mean(); keep=score.sort_values(ascending=False).head(2).index; w=pd.Series(0.0,index=assets); w.loc[keep]=0.5; rows.append({"date":nxt,"gross":float((w*nr.loc[list(assets)]).sum()),"turn":0.5*float((w-prev).abs().sum()),"ew":float(nr.loc[list(assets)].mean()),"spy":float(nr.SPY),"qqq":float(nr.QQQ)}); prev=w
    return pd.DataFrame(rows).set_index("date")
def ev(f,start,bps):
    g=f if start=="full" else f.loc[f.index>=pd.Timestamp(start)]; s=g.gross-g.turn*bps/10000; ew=g.ew; inc=s-ew; keep=inc.sort_values(ascending=False).index[min(5,len(inc)):]; sm,em=base.metrics(s),base.metrics(ew)
    return {"strategy":sm,"equal_weight":em,"excess_vs_equal_weight":sm["cagr"]-em["cagr"],"excess_vs_spy":sm["cagr"]-base.metrics(g.spy)["cagr"],"excess_vs_qqq":sm["cagr"]-base.metrics(g.qqq)["cagr"],"positive_folds_vs_equal_weight":folds(s,ew),"five_best_relative_months_removed":base.metrics(s.loc[keep])["cagr"]-base.metrics(ew.loc[keep])["cagr"],"annual_turnover":float(g.turn.mean()*12)}
def main():
    out={"schema":"research.p141_expanding_calendar_seasonality_r1","contract":{"mechanism":"expanding prior-only same-calendar-month historical mean return, top2","minimum_prior_same_month_observations":3,"representations":{k:list(v) for k,v in p137.REPRESENTATIONS.items()},"windows":["full","2018-01-31","2022-01-31"],"costs_bps":[25,50],"matched_control":"same-universe equal weight","opportunity_cost":["SPY","QQQ"],"chronological_folds":3,"concentration_test":"remove five strongest seasonality-minus-equal-weight months","no_future_rows_or_parameter_topk_threshold_tuning":True},"results":{}}
    for rep,a in p137.REPRESENTATIONS.items():
        f=build(a); out["results"][rep]={s:{str(b):ev(f,s,b) for b in (25,50)} for s in ("full","2018-01-31","2022-01-31")}
    late=[(r,s) for r in p137.REPRESENTATIONS for s in ("2018-01-31","2022-01-31")]; cells=[out["results"][r][s][str(b)]["excess_vs_equal_weight"]>0 for r,s in late for b in (25,50)]; fo=[out["results"][r][s]["25"]["positive_folds_vs_equal_weight"]>=2 for r,s in late]; tr=[out["results"][r][s]["25"]["five_best_relative_months_removed"]>0 for r,s in late]
    out["decision"]="CALENDAR_SEASONALITY_BROAD_DURABLE_ALPHA_SUPPORTED" if all(cells) and all(fo) and all(tr) else ("CALENDAR_SEASONALITY_ALPHA_MIXED_OR_CONCENTRATED" if sum(cells)>=8 and sum(fo)>=4 else "CALENDAR_SEASONALITY_NOT_BROADLY_SUPPORTED")
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p141_expanding_calendar_seasonality_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); c={r:{s:{"25_ew":out["results"][r][s]["25"]["excess_vs_equal_weight"],"50_ew":out["results"][r][s]["50"]["excess_vs_equal_weight"],"25_spy":out["results"][r][s]["25"]["excess_vs_spy"],"25_qqq":out["results"][r][s]["25"]["excess_vs_qqq"],"25_folds":out["results"][r][s]["25"]["positive_folds_vs_equal_weight"],"25_trim":out["results"][r][s]["25"]["five_best_relative_months_removed"],"turn":out["results"][r][s]["25"]["annual_turnover"]} for s in ("full","2018-01-31","2022-01-31")} for r in p137.REPRESENTATIONS}; print(json.dumps({"decision":out["decision"],"results":c},sort_keys=True))
if __name__=="__main__": main()
