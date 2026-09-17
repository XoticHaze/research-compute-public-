# Market Research execution trigger 2026-09-17; scientific contract unchanged.
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from research.p279_p249_p266_forward_shadow_observer_r1 import (
    ALL as CORE_SYMBOLS,
    P266_COST_BP,
    _month_costs,
    _portfolio_weights,
    _turnover,
)

START_DOWNLOAD = "2018-01-01"
START_EVAL = "2021-01-01"
END = "2026-09-01"
CANDIDATE_WEIGHT = 0.25
CORE_WEIGHT = 0.75
MIX_REBALANCE_COST = 0.001
ENDPOINT_COST = 0.0025
CASH = "BIL"
SIMPLE_CANDIDATES = ["JAAA", "SRLN", "KMLM"]
CANDIDATES = ["P266", *SIMPLE_CANDIDATES]
OUT = Path("research/artifacts/p249_orthogonal_sleeve_tournament_r1.json")


def stats(s: pd.Series) -> dict[str, float | int | None]:
    x = s.dropna().astype(float)
    if len(x) < 12:
        return {"months": int(len(x)), "cagr": None, "vol": None, "sharpe": None, "max_drawdown": None}
    y = x.to_numpy().copy(); y[0] -= ENDPOINT_COST; y[-1] -= ENDPOINT_COST
    wealth = np.cumprod(1 + y); years = len(y) / 12.0
    cagr = float(wealth[-1] ** (1 / years) - 1); vol = float(np.std(y, ddof=1) * math.sqrt(12))
    sharpe = float(np.mean(y) * 12 / vol) if vol > 0 else None
    maxdd = float(np.min(wealth / np.maximum.accumulate(wealth) - 1))
    return {"months": int(len(y)), "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": maxdd}


def mix_net(core: pd.Series, sleeve: pd.Series) -> pd.Series:
    q = pd.concat([core.rename("core"), sleeve.rename("sleeve")], axis=1).dropna(); out=[]
    for core_ret, sleeve_ret in q.to_numpy():
        gross=CORE_WEIGHT*core_ret+CANDIDATE_WEIGHT*sleeve_ret; denom=1+gross
        if denom<=0: out.append(np.nan); continue
        ca=CORE_WEIGHT*(1+core_ret)/denom; sa=CANDIDATE_WEIGHT*(1+sleeve_ret)/denom
        out.append(gross-MIX_REBALANCE_COST*(abs(ca-CORE_WEIGHT)+abs(sa-CANDIDATE_WEIGHT)))
    return pd.Series(out,index=q.index,dtype=float)


def build_core_and_p266_monthly(close: pd.DataFrame):
    core_close=close[list(CORE_SYMBOLS)].dropna(how="all").astype(float); daily_ret=core_close.pct_change(fill_method=None)
    eval_days=daily_ret.index[daily_ret.index>=pd.Timestamp(START_EVAL)]; core_rows=[]; p266_rows=[]; prev_state=None; state_cache={}; seen=set(); cost_detail={}
    for dt in eval_days:
        period=dt.to_period("M"); key=str(period)
        if key not in state_cache: state_cache[key]=_portfolio_weights(core_close.loc[:dt],period)
        state=state_cache[key]; core_cost=0.0; p266_cost=0.0
        if key not in seen:
            core_cost,_,detail=_month_costs(prev_state,state); p266_turn=_turnover(None if prev_state is None else prev_state["p266"],state["p266"])
            p266_cost=P266_COST_BP*p266_turn/10000.0; cost_detail[key]={**detail,"p266_standalone_cost_bp":P266_COST_BP*p266_turn}; prev_state=state; seen.add(key)
        day=daily_ret.loc[dt]; cg=sum(state["p249_core"].get(sym,0.0)*float(day.get(sym,np.nan)) for sym in state["p249_core"]); pg=sum(state["p266"].get(sym,0.0)*float(day.get(sym,np.nan)) for sym in state["p266"])
        if not np.isnan(cg): core_rows.append((dt,cg-core_cost))
        if not np.isnan(pg): p266_rows.append((dt,pg-p266_cost))
    core_daily=pd.Series(dict(core_rows),dtype=float).sort_index(); p266_daily=pd.Series(dict(p266_rows),dtype=float).sort_index()
    cm=core_daily.resample("ME").apply(lambda x:float((1+x).prod()-1) if len(x) else np.nan).dropna(); pm=p266_daily.resample("ME").apply(lambda x:float((1+x).prod()-1) if len(x) else np.nan).dropna()
    return cm,pm,{"core_months":int(len(cm)),"p266_months":int(len(pm)),"first_core_month":str(cm.index.min().date()) if len(cm) else None,"last_core_month":str(cm.index.max().date()) if len(cm) else None,"monthly_cost_detail":cost_detail}


def frame(core,sleeve,cash,start,end=None):
    q=pd.concat([core.rename("core"),sleeve.rename("sleeve"),cash.rename("cash")],axis=1).loc[start:end].dropna(); cs=mix_net(q["core"],q["sleeve"]); ms=mix_net(q["core"],q["cash"]); c=stats(q["core"]); a=stats(cs); m=stats(ms); ex=q["sleeve"]-q["cash"]; down=q[q["core"]<0]
    return {"months":int(len(q)),"core":c,"challenger":a,"capital_parking_control":m,"matched_capital_excess_cagr_pp":None if a["cagr"] is None or m["cagr"] is None else 100*(a["cagr"]-m["cagr"]),"core_cagr_delta_pp":None if a["cagr"] is None or c["cagr"] is None else 100*(a["cagr"]-c["cagr"]),"sharpe_delta_vs_core":None if a["sharpe"] is None or c["sharpe"] is None else a["sharpe"]-c["sharpe"],"maxdd_improvement_vs_core_pp":None if a["max_drawdown"] is None or c["max_drawdown"] is None else 100*(a["max_drawdown"]-c["max_drawdown"]),"sleeve_excess_to_core_corr":float(ex.corr(q["core"])) if len(q)>=12 else None,"downside_excess_to_core_corr":float((down["sleeve"]-down["cash"]).corr(down["core"])) if len(down)>=6 else None,"downside_months":int(len(down)),"sleeve_positive_when_core_negative_fraction":float((down["sleeve"]>0).mean()) if len(down) else None}


def rank_candidates(results):
    eligible={n:r for n,r in results.items() if r["persistence_passed"]}
    if not eligible:return []
    rows=[]
    for n,r in eligible.items():
        f=r["windows"]["2021+"]; rows.append({"candidate":n,"matched_capital_excess_cagr_pp":f["matched_capital_excess_cagr_pp"],"core_cagr_delta_pp":f["core_cagr_delta_pp"],"sharpe_delta_vs_core":f["sharpe_delta_vs_core"],"maxdd_improvement_vs_core_pp":f["maxdd_improvement_vs_core_pp"],"abs_downside_excess_to_core_corr":None if f["downside_excess_to_core_corr"] is None else abs(f["downside_excess_to_core_corr"])})
    t=pd.DataFrame(rows).set_index("candidate"); higher=["matched_capital_excess_cagr_pp","core_cagr_delta_pp","sharpe_delta_vs_core","maxdd_improvement_vs_core_pp"]; parts=[t[c].rank(method="average",ascending=True,pct=True) for c in higher]; d=t["abs_downside_excess_to_core_corr"].copy(); worst=float(d.dropna().max())+1 if d.notna().any() else 2; parts.append((-d.fillna(worst)).rank(method="average",ascending=True,pct=True)); t["equal_rank_utility_score"]=pd.concat(parts,axis=1).mean(axis=1); t["rank"]=t["equal_rank_utility_score"].rank(method="min",ascending=False).astype(int); t=t.sort_values(["rank","matched_capital_excess_cagr_pp","core_cagr_delta_pp"],ascending=[True,False,False]); return [{"candidate":i,**{k:(None if pd.isna(v) else float(v)) for k,v in row.items()}} for i,row in t.iterrows()]


def main():
    tickers=list(dict.fromkeys(list(CORE_SYMBOLS)+SIMPLE_CANDIDATES+[CASH])); raw=yf.download(tickers,start=START_DOWNLOAD,end=END,auto_adjust=True,progress=False,threads=False)
    if raw.empty: raise SystemExit("SOURCE_FAILURE_EMPTY")
    close=raw["Close"] if isinstance(raw.columns,pd.MultiIndex) else raw; close=close.reindex(columns=tickers).dropna(how="all").astype(float)
    if close.empty: raise SystemExit("SOURCE_FAILURE_NO_CLOSE")
    core,p266,diag=build_core_and_p266_monthly(close); simple=close[SIMPLE_CANDIDATES+[CASH]].resample("ME").last().pct_change(fill_method=None); cash=simple[CASH]; sleeves={"P266":p266,"JAAA":simple["JAAA"],"SRLN":simple["SRLN"],"KMLM":simple["KMLM"]}; ws={"2021+":("2021-01-01",None),"2022+":("2022-01-01",None),"2023+":("2023-01-01",None)}; bs={"2021_2022":("2021-01-01","2022-12-31"),"2023_2024":("2023-01-01","2024-12-31"),"2025_plus":("2025-01-01",None)}; results={}
    for n,s in sleeves.items():
        w={k:frame(core,s,cash,*b) for k,b in ws.items()}; b={k:frame(core,s,cash,*v) for k,v in bs.items()}; ready=all(v["months"]>=18 for v in b.values()); pw=sum(v["months"]>=18 and (v["matched_capital_excess_cagr_pp"] or -999)>0 for v in w.values()); pb=sum(v["months"]>=18 and (v["matched_capital_excess_cagr_pp"] or -999)>0 for v in b.values()); full=w["2021+"]["matched_capital_excess_cagr_pp"]; results[n]={"windows":w,"blocks":b,"coverage_ready":ready,"positive_windows":int(pw),"positive_blocks":int(pb),"persistence_passed":bool(ready and pw>=2 and pb>=2 and full is not None and full>0)}
    ranking=rank_candidates(results); top=[r for r in ranking if r["rank"]==1]; decision="P249_ORTHOGONAL_SLEEVE_TOURNAMENT__NO_PERSISTENT_CANDIDATE" if not ranking else (f"P249_ORTHOGONAL_SLEEVE_TOURNAMENT__{top[0]['candidate']}__TOP_NORMALIZED_UTILITY" if len(top)==1 else "P249_ORTHOGONAL_SLEEVE_TOURNAMENT__TOP_UTILITY_TIE"); result={"schema":"research.p249_orthogonal_sleeve_tournament_r1.v1","workload_id":"P249_ORTHOGONAL_SLEEVE_TOURNAMENT_R1","contract":{"candidate_weight":CANDIDATE_WEIGHT,"core_weight":CORE_WEIGHT,"capital_parking_control":"25% BIL + 75% unchanged P249 core","completed_month_cutoff":"2026-08-31","parameter_search":False},"dynamic_materialization":diag,"candidates":results,"ranking":ranking,"decision":decision}; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__": main()
