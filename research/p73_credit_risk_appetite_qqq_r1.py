from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

START="2007-01-01"
SYMBOLS=("HYG","LQD","QQQ","SHY","SPY")
COSTS=(10,25,50)

def metric(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); years=len(r)/12
    cagr=float(eq.iloc[-1]**(1/years)-1); ann=float(r.mean()*12); vol=float(r.std(ddof=0)*math.sqrt(12)); dd=eq/eq.cummax()-1; mdd=float(dd.min())
    return {"cagr":cagr,"annualized_vol":vol,"sharpe_rf0":ann/vol if vol else float("nan"),"max_drawdown_monthly":mdd,"calmar":cagr/abs(mdd) if mdd<0 else float("nan")}

def folds(c,b):
    out=[]
    for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
        cm,bm=metric(c.iloc[idx]),metric(b.iloc[idx]); out.append({"fold":n,"candidate_cagr":cm["cagr"],"baseline_cagr":bm["cagr"],"excess_cagr":cm["cagr"]-bm["cagr"]})
    return sum(x["excess_cagr"]>0 for x in out),out

def main():
    data=yf.download(list(SYMBOLS),start=START,auto_adjust=True,progress=False,threads=False)
    close=data["Close"] if isinstance(data.columns,pd.MultiIndex) else data[["Close"]]; close=close.loc[:,list(SYMBOLS)].astype(float)
    sha=hashlib.sha256(close.reset_index().to_csv(index=False,float_format="%.10g").encode()).hexdigest()
    m=close.resample("ME").last(); rel3=m["HYG"].pct_change(3)-m["LQD"].pct_change(3)
    recs=[]; prev=0.0
    for i,dt in enumerate(m.index[:-1]):
        nxt=m.index[i+1]
        if pd.isna(rel3.loc[dt]) or m.loc[[dt,nxt],["QQQ","SHY","SPY"]].isna().any().any(): continue
        exp=1.0 if float(rel3.loc[dt])>0 else 0.0
        q=float(m.at[nxt,"QQQ"]/m.at[dt,"QQQ"]-1); shy=float(m.at[nxt,"SHY"]/m.at[dt,"SHY"]-1); spy=float(m.at[nxt,"SPY"]/m.at[dt,"SPY"]-1)
        recs.append({"feature_month":str(dt.date()),"return_month":str(nxt.date()),"gross":exp*q+(1-exp)*shy,"qqq":q,"shy":shy,"spy":spy,"qqq_exposure":exp,"turnover":abs(exp-prev),"hyg_minus_lqd_3m":float(rel3.loc[dt])}); prev=exp
    fr=pd.DataFrame(recs); avg=float(fr.qqq_exposure.mean()); matched=avg*fr.qqq+(1-avg)*fr.shy
    out={"schema":"research.p73_credit_risk_appetite_qqq_r1","hypothesis":"Positive trailing 3-month HYG-minus-LQD relative return identifies a causal credit-risk-on state that can improve QQQ/SHY allocation beyond QQQ and a static exposure-matched blend.","scientific_contract":{"signal":"prior month-end HYG 3m return minus LQD 3m return > 0","risk_on":"QQQ","risk_off":"SHY","costs_bps":list(COSTS),"matched_control":"static QQQ/SHY at candidate mean QQQ exposure","no_lookback_threshold_or_allocation_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","normalized_panel_sha256":sha},"window":{"start":fr.iloc[0].return_month,"end":fr.iloc[-1].return_month,"months":int(len(fr))},"mean_qqq_exposure":avg,"mean_annual_turnover":float(fr.turnover.mean()*12),"costs":{}}
    for bp in COSTS:
        c=fr.gross-fr.turnover*bp/10000; cm,mm,qm,sm=metric(c),metric(matched),metric(fr.qqq),metric(fr.spy); pos,fs=folds(c,matched)
        out["costs"][str(bp)]={"candidate":cm,"matched_static_exposure":mm,"qqq":qm,"spy":sm,"excess_cagr_vs_matched":cm["cagr"]-mm["cagr"],"excess_cagr_vs_qqq":cm["cagr"]-qm["cagr"],"excess_cagr_vs_spy":cm["cagr"]-sm["cagr"],"positive_folds_vs_matched":int(pos),"folds_vs_matched":fs}
    p,s=out["costs"]["25"],out["costs"]["50"]
    out["decision"]="SUPPORTED_CREDIT_QQQ_CANDIDATE" if p["excess_cagr_vs_matched"]>0.01 and p["positive_folds_vs_matched"]>=3 and p["excess_cagr_vs_qqq"]>0 and s["excess_cagr_vs_matched"]>0 else "NOT_SUPPORTED_CREDIT_QQQ_ROTATE"
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p73_credit_risk_appetite_qqq_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"decision":out["decision"],"window":out["window"],"mean_qqq_exposure":avg,"turnover":out["mean_annual_turnover"],"25":{k:p[k] for k in ("excess_cagr_vs_matched","excess_cagr_vs_qqq","excess_cagr_vs_spy","positive_folds_vs_matched")},"50":{k:s[k] for k in ("excess_cagr_vs_matched","excess_cagr_vs_qqq","excess_cagr_vs_spy")}},sort_keys=True))

if __name__=="__main__": main()
