from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import p104_p111_crossasset_model_family_tournament_r1 as base
import p137_p105_dual_horizon_incremental_mechanism_r1 as p137

def top2(score,assets):
    w=pd.Series(0.0,index=assets); k=score.dropna().sort_values(ascending=False).head(2).index
    if len(k): w.loc[k]=1/len(k)
    return w

def folds(a,b,n=3): return sum(base.metrics(a.iloc[i])["cagr"]>base.metrics(b.iloc[i])["cagr"] for i in np.array_split(np.arange(len(a)),n) if len(i))
def build(assets):
    syms=tuple(dict.fromkeys((*assets,"BIL","SPY","QQQ"))); raw=yf.download(list(syms),start="2007-01-01",auto_adjust=True,progress=False,threads=False); close=raw["Close"] if isinstance(raw.columns,pd.MultiIndex) else raw[["Close"]]; close=close.loc[:,list(syms)].dropna(how="all").astype(float); close.index=pd.DatetimeIndex(close.index).tz_localize(None); monthly=close.resample("ME").last(); m6=monthly.pct_change(6); sma200=close.rolling(200,min_periods=160).mean().resample("ME").last(); trend=monthly/sma200-1; dd=(close/close.rolling(126,min_periods=100).max()-1).resample("ME").last(); prev={"p87":pd.Series(0.0,index=assets),"m6":pd.Series(0.0,index=assets)}; rows=[]
    for i,dt in enumerate(monthly.index[:-1]):
        nxt=monthly.index[i+1]; req=pd.DataFrame({"m6":m6.loc[dt,list(assets)],"trend":trend.loc[dt,list(assets)],"dd":dd.loc[dt,list(assets)]}); nr=monthly.loc[nxt,list(syms)]/monthly.loc[dt,list(syms)]-1
        if req.isna().any().any() or nr.isna().any(): continue
        scores={"p87":req.rank(pct=True).mean(axis=1),"m6":req.m6.rank(pct=True)}; row={"date":nxt,"ew":float(nr.loc[list(assets)].mean()),"spy":float(nr.SPY),"qqq":float(nr.QQQ)}
        for name,s in scores.items():
            w=top2(s,assets); row[name+"_gross"]=float((w*nr.loc[list(assets)]).sum()); row[name+"_turn"]=0.5*float((w-prev[name]).abs().sum()); prev[name]=w
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")
def ev(f,start,bps):
    g=f if start=="full" else f.loc[f.index>=pd.Timestamp(start)]; p=g.p87_gross-g.p87_turn*bps/10000; m=g.m6_gross-g.m6_turn*bps/10000; ew=g.ew; inc=p-m; keep=inc.sort_values(ascending=False).index[min(5,len(inc)):]; pm,mm,em=base.metrics(p),base.metrics(m),base.metrics(ew)
    return {"p87":pm,"m6":mm,"ew":em,"incremental_vs_m6":pm["cagr"]-mm["cagr"],"excess_vs_ew":pm["cagr"]-em["cagr"],"excess_vs_spy":pm["cagr"]-base.metrics(g.spy)["cagr"],"excess_vs_qqq":pm["cagr"]-base.metrics(g.qqq)["cagr"],"positive_folds_vs_m6":folds(p,m),"five_best_incremental_months_removed":base.metrics(p.loc[keep])["cagr"]-base.metrics(m.loc[keep])["cagr"],"annual_turnover":float(g.p87_turn.mean()*12)}
def main():
    out={"schema":"research.p139_three_factor_vs_six_month_incremental_r1","contract":{"candidate":"fixed P87 rank-average 6m momentum + 200d trend + 126d drawdown top2","reference":"fixed six-month momentum top2","representations":{k:list(v) for k,v in p137.REPRESENTATIONS.items()},"windows":["full","2018-01-31","2022-01-31"],"costs_bps":[25,50],"no_factor_weight_horizon_topk_or_threshold_tuning":True},"results":{}}
    for rep,a in p137.REPRESENTATIONS.items():
        f=build(a); out["results"][rep]={s:{str(b):ev(f,s,b) for b in (25,50)} for s in ("full","2018-01-31","2022-01-31")}
    late=[(r,s) for r in p137.REPRESENTATIONS for s in ("2018-01-31","2022-01-31")]; pos=[out["results"][r][s][str(b)]["incremental_vs_m6"]>0 for r,s in late for b in (25,50)]; fo=[out["results"][r][s]["25"]["positive_folds_vs_m6"]>=2 for r,s in late]; tr=[out["results"][r][s]["25"]["five_best_incremental_months_removed"]>0 for r,s in late]; out["decision"]="THREE_FACTOR_COMPOSITE_INCREMENT_BROADLY_SUPPORTED" if all(pos) and all(fo) and all(tr) else ("THREE_FACTOR_COMPOSITE_INCREMENT_MIXED" if sum(pos)>=8 and sum(fo)>=4 else "THREE_FACTOR_COMPOSITE_NOT_BETTER_THAN_SIX_MONTH"); Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p139_three_factor_vs_six_month_incremental_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); c={r:{s:{"25_inc":out["results"][r][s]["25"]["incremental_vs_m6"],"50_inc":out["results"][r][s]["50"]["incremental_vs_m6"],"25_ew":out["results"][r][s]["25"]["excess_vs_ew"],"25_folds":out["results"][r][s]["25"]["positive_folds_vs_m6"],"25_trim":out["results"][r][s]["25"]["five_best_incremental_months_removed"]} for s in ("full","2018-01-31","2022-01-31")} for r in p137.REPRESENTATIONS}; print(json.dumps({"decision":out["decision"],"results":c},sort_keys=True))
if __name__=="__main__": main()
