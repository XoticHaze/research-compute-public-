from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

SYMS=("VTI","VEA","IEF","IAU","GSG"); REQ=(*SYMS,"SPY","QQQ"); START="2007-01-01"

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12
    c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min())
    return {"cagr":c,"annualized_mean":a,"annualized_vol":v,"sharpe_rf0":a/v if v else None,"max_drawdown_monthly":m,"calmar":c/abs(m) if m<0 else None}

def build():
    d=yf.download(list(REQ),start=START,auto_adjust=True,progress=False,threads=False)
    close=d["Close"] if isinstance(d.columns,pd.MultiIndex) else d[["Close"]]
    close=close.loc[:,list(REQ)].dropna(how="all").astype(float)
    last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last
    m=close.resample("ME").last(); m=m.loc[m.index<=last.normalize()]
    dr=close.pct_change(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample("ME").last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample("ME").last(); mom=m.pct_change(6)
    prev={s:0. for s in SYMS}; rows=[]
    for dt in m.index:
        b=pd.DataFrame({"mom6":mom.loc[dt,list(SYMS)],"trend200":trend.loc[dt,list(SYMS)],"drawdown6":dd.loc[dt,list(SYMS)]},index=list(SYMS))
        if b.isna().any().any() or pd.isna(mom.loc[dt,"SPY"]): continue
        loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
        nxt=m.index[loc+1]; r=m.loc[nxt,list(REQ)]/m.loc[dt,list(REQ)]-1
        if r.isna().any(): continue
        score=b.rank(axis=0,pct=True,method="average").mean(axis=1); chosen=score.sort_values(ascending=False).head(2).index
        w={s:(.5 if s in chosen else 0.) for s in SYMS}; turn=.5*sum(abs(w[s]-prev[s]) for s in SYMS)
        rows.append({"date":nxt,"gross":sum(w[s]*float(r[s]) for s in SYMS),"turn":turn,"ew":float(r.loc[list(SYMS)].mean()),"spy":float(r["SPY"]),"qqq":float(r["QQQ"]),"state":"risk_on" if float(mom.loc[dt,"SPY"])>0 else "risk_off"})
        prev=w
    return pd.DataFrame(rows).set_index("date")

def main():
    f=build(); costs=[0,10,25,50,75,100,150,200]; grid={}
    ew=metrics(f.ew); spy=metrics(f.spy); qqq=metrics(f.qqq)
    for bps in costs:
        net=f.gross-f.turn*bps/10000
        mm=metrics(net); grid[str(bps)]={"strategy":mm,"excess_cagr_vs_ew":mm["cagr"]-ew["cagr"],"excess_cagr_vs_spy":mm["cagr"]-spy["cagr"],"excess_cagr_vs_qqq":mm["cagr"]-qqq["cagr"]}
    vals=[]
    for bps in range(0,301):
        vals.append((bps,metrics(f.gross-f.turn*bps/10000)["cagr"]-ew["cagr"]))
    pos=[x for x in vals if x[1]>0]; breakeven=max(x[0] for x in pos) if pos else None
    state={}
    net25=f.gross-f.turn*25/10000
    for s,g in f.assign(net25=net25).groupby("state"):
        state[s]={"months":len(g),"strategy":metrics(g.net25),"matched_ew":metrics(g.ew),"annualized_mean_excess":float((g.net25-g.ew).mean()*12),"positive_month_fraction":float((g.net25>g.ew).mean())}
    excess=net25-f.ew; strongest=excess.nlargest(5); trimmed=excess.drop(strongest.index)
    out={"schema":"research.p92_p87_cost_state_risk_r1","parent_ids":["P46","P87","P91","P92"],"contract":{"mechanism":"frozen P87 momentum+trend+drawdown top2 on VTI/VEA/IEF/IAU/GSG","cost_grid_bps":costs,"state":"prior SPY 6m return sign","no_parameter_tuning":True},"window":{"start":str(f.index.min().date()),"end":str(f.index.max().date()),"months":len(f)},"matched_controls":{"equal_weight":ew,"SPY":spy,"QQQ":qqq},"cost_grid":grid,"estimated_break_even_bps_vs_equal_weight":breakeven,"state_attribution_25bps":state,"five_strongest_months_removed_annualized_mean_excess":float(trimmed.mean()*12),"five_strongest_months":{str(k.date()):float(v) for k,v in strongest.items()}}
    supported=(grid["50"]["excess_cagr_vs_ew"]>0 and breakeven is not None and breakeven>=50 and out["five_strongest_months_removed_annualized_mean_excess"]>0)
    out["decision"]="SUPPORTED_IMPLEMENTATION_HEADROOM_STATE_DEPENDENCE_MEASURED" if supported else "IMPLEMENTATION_HEADROOM_OR_CONCENTRATION_CAUTION"
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p92_p87_cost_state_risk_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"decision":out["decision"],"breakeven_bps":breakeven,"25":grid["25"],"50":grid["50"],"states":state,"trimmed_excess_ann_mean":out["five_strongest_months_removed_annualized_mean_excess"],"window":out["window"]},sort_keys=True))
if __name__=="__main__": main()
