from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

START = "2005-01-01"
BREADTH = ("SOXX", "XBI", "XHB", "KRE", "ITA", "IGV", "IYT", "XRT", "XOP", "IHI")
TRADED = ("QQQ", "SHY")
COSTS_BPS = (10, 25, 50)


def metric(r: pd.Series) -> dict[str, float]:
    r = pd.Series(r, dtype=float).dropna()
    eq = (1 + r).cumprod(); years = len(r) / 12
    cagr = float(eq.iloc[-1] ** (1 / years) - 1)
    ann = float(r.mean() * 12); vol = float(r.std(ddof=0) * math.sqrt(12)); sharpe = ann / vol if vol else float("nan")
    dd = eq / eq.cummax() - 1; mdd = float(dd.min())
    return {"cagr": cagr, "annualized_vol": vol, "sharpe_rf0": sharpe, "max_drawdown_monthly": mdd, "calmar": cagr / abs(mdd) if mdd < 0 else float("nan")}


def fold_count(c: pd.Series, b: pd.Series):
    folds=[]
    for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
        cm,bm=metric(c.iloc[idx]),metric(b.iloc[idx]); folds.append({"fold":n,"candidate_cagr":cm["cagr"],"baseline_cagr":bm["cagr"],"excess_cagr":cm["cagr"]-bm["cagr"]})
    return sum(x["excess_cagr"]>0 for x in folds),folds


def main():
    symbols=tuple(dict.fromkeys((*BREADTH,*TRADED,"SPY")))
    data=yf.download(list(symbols),start=START,auto_adjust=True,progress=False,threads=False)
    close=data["Close"] if isinstance(data.columns,pd.MultiIndex) else data[["Close"]]
    close=close.loc[:,list(symbols)].astype(float)
    sha=hashlib.sha256(close.reset_index().to_csv(index=False,float_format="%.10g").encode()).hexdigest()
    sma200=close.loc[:,list(BREADTH)].rolling(200,min_periods=160).mean()
    breadth=((close.loc[:,list(BREADTH)]>sma200).sum(axis=1)/len(BREADTH)).resample("ME").last()
    monthly=close.resample("ME").last()
    recs=[]; prev=0.0
    for i,dt in enumerate(monthly.index[:-1]):
        nxt=monthly.index[i+1]
        if pd.isna(breadth.get(dt)) or monthly.loc[[dt,nxt],list(TRADED)+["SPY"]].isna().any().any(): continue
        exposure=1.0 if float(breadth.loc[dt])>=0.5 else 0.0
        q=float(monthly.at[nxt,"QQQ"]/monthly.at[dt,"QQQ"]-1); shy=float(monthly.at[nxt,"SHY"]/monthly.at[dt,"SHY"]-1); spy=float(monthly.at[nxt,"SPY"]/monthly.at[dt,"SPY"]-1)
        turnover=abs(exposure-prev)
        recs.append({"feature_month":str(dt.date()),"return_month":str(nxt.date()),"gross":exposure*q+(1-exposure)*shy,"qqq":q,"shy":shy,"spy":spy,"qqq_exposure":exposure,"turnover":turnover,"breadth":float(breadth.loc[dt])})
        prev=exposure
    fr=pd.DataFrame(recs)
    if len(fr)<120: raise RuntimeError(f"insufficient_months:{len(fr)}")
    avg=float(fr.qqq_exposure.mean()); matched=avg*fr.qqq+(1-avg)*fr.shy
    out={"schema":"research.p72_industry_breadth_qqq_r1","hypothesis":"A causal majority-above-SMA200 industry breadth state can improve QQQ/SHY allocation beyond both raw QQQ and a static QQQ/SHY blend matched to the strategy's average equity exposure.","scientific_contract":{"breadth_universe":list(BREADTH),"signal":"prior month-end fraction above daily SMA200 >= 0.5","risk_on":"QQQ","risk_off":"SHY","costs_bps":list(COSTS_BPS),"matched_control":"static QQQ/SHY using candidate mean QQQ exposure","broad_control":"SPY","no_threshold_lookback_or_allocation_tuning":True},"source":{"provider":"Yahoo Finance via yfinance","normalized_panel_sha256":sha},"window":{"start":fr.iloc[0].return_month,"end":fr.iloc[-1].return_month,"months":int(len(fr))},"mean_qqq_exposure":avg,"mean_annual_turnover":float(fr.turnover.mean()*12),"costs":{}}
    for bp in COSTS_BPS:
        c=fr.gross-fr.turnover*bp/10000; cm,mm,qm,sm=metric(c),metric(matched),metric(fr.qqq),metric(fr.spy)
        pos,folds=fold_count(c,matched)
        out["costs"][str(bp)]={"candidate":cm,"matched_static_exposure":mm,"qqq":qm,"spy":sm,"excess_cagr_vs_matched":cm["cagr"]-mm["cagr"],"excess_cagr_vs_qqq":cm["cagr"]-qm["cagr"],"excess_cagr_vs_spy":cm["cagr"]-sm["cagr"],"positive_folds_vs_matched":int(pos),"folds_vs_matched":folds}
    p,s=out["costs"]["25"],out["costs"]["50"]
    out["decision"]="SUPPORTED_BREADTH_QQQ_CANDIDATE" if p["excess_cagr_vs_matched"]>0.01 and p["positive_folds_vs_matched"]>=3 and p["excess_cagr_vs_qqq"]>0 and s["excess_cagr_vs_matched"]>0 else "NOT_SUPPORTED_BREADTH_QQQ_ROTATE"
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p72_industry_breadth_qqq_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"decision":out["decision"],"window":out["window"],"mean_qqq_exposure":avg,"turnover":out["mean_annual_turnover"],"25":{k:p[k] for k in ("excess_cagr_vs_matched","excess_cagr_vs_qqq","excess_cagr_vs_spy","positive_folds_vs_matched")},"50":{k:s[k] for k in ("excess_cagr_vs_matched","excess_cagr_vs_qqq","excess_cagr_vs_spy")}},sort_keys=True))

if __name__=="__main__": main()
