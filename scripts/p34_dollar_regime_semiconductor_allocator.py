#!/usr/bin/env python3
import hashlib, json, math, time
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START="2006-01-01"
END="2026-09-08"
COSTS=(10,25,50)


def get(url, attempts=5):
    last=None
    for i in range(attempts):
        try:
            req=Request(url,headers={"User-Agent":"Mozilla/5.0 research-compute"})
            with urlopen(req,timeout=30) as r: raw=r.read()
            if len(raw)<200: raise RuntimeError(f"short response {len(raw)}")
            return raw,i+1
        except Exception as e:
            last=e; time.sleep(min(2**i,8))
    raise RuntimeError(f"source_fetch_failed:{last}")


def yahoo(sym):
    p1=int(pd.Timestamp(START,tz="UTC").timestamp()); p2=int(pd.Timestamp(END,tz="UTC").timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true"
    raw,attempt=get(url); obj=json.loads(raw); r=obj["chart"]["result"][0]
    ts=pd.to_datetime(r["timestamp"],unit="s",utc=True).tz_convert(None)
    adj=r.get("indicators",{}).get("adjclose",[{}])[0].get("adjclose")
    if not adj: adj=r["indicators"]["quote"][0]["close"]
    s=pd.Series(adj,index=ts,dtype=float).dropna().sort_index()
    if len(s)<500: raise RuntimeError(f"{sym}_insufficient_rows={len(s)}")
    return s,{"url":url,"sha256":hashlib.sha256(raw).hexdigest(),"rows":int(len(s)),"attempt":attempt,"source_class":"YAHOO_CHART_V8_EXTERNAL_RESEARCH_NOT_MM_CANONICAL"}


def cagr(r):
    r=pd.Series(r).dropna(); n=len(r)
    if n==0:return float("nan")
    total=float((1+r).prod())
    return total**(12.0/n)-1 if total>0 else -1.0


def maxdd(r):
    eq=(1+pd.Series(r).fillna(0)).cumprod(); return float((eq/eq.cummax()-1).min())


def annvol(r): return float(pd.Series(r).std(ddof=1)*math.sqrt(12))


def folds(df,s,c):
    out=[]
    for n,arr in enumerate(np.array_split(np.arange(len(df)),5),1):
        x=df.iloc[arr]; a=cagr(x[s]); b=cagr(x[c])
        out.append({"fold":n,"start":str(x.index.min().date()),"end":str(x.index.max().date()),"strategy_cagr":a,"control_cagr":b,"excess_cagr":a-b})
    return out


def main():
    prices={}; src={}
    for sym in ("SMH","QQQ","SPY","UUP"):
        prices[sym],src[sym]=yahoo(sym)
    m=pd.concat({k:v.resample("ME").last() for k,v in prices.items()},axis=1).dropna()
    rets=m.pct_change()
    # Frozen macro mechanism: a weakening dollar over the prior 3 month-ends favors export/global-cycle semiconductors next month; otherwise QQQ.
    signal=(m["UUP"].pct_change(3)<0).astype(int).shift(1)
    df=pd.DataFrame(index=m.index)
    df["smh_ret"]=rets["SMH"]; df["qqq_ret"]=rets["QQQ"]; df["spy_ret"]=rets["SPY"]; df["signal_smh"]=signal
    df=df.dropna().copy()
    df["gross"]=np.where(df["signal_smh"]==1,df["smh_ret"],df["qqq_ret"])
    df["static_50_50"]=0.5*df["smh_ret"]+0.5*df["qqq_ret"]
    switches=df["signal_smh"].diff().abs().fillna(1.0)
    result={"schema":"research.p34_dollar_regime_semiconductor_allocator.v1","hypothesis":"Prior 3-month decline in UUP selects SMH for next month; otherwise QQQ.","window":{"start":str(df.index.min().date()),"end":str(df.index.max().date()),"months":int(len(df))},"sources":src,"switches":int(switches.sum()),"controls":{},"cost_cases":{}}
    for name,col in (("SMH","smh_ret"),("QQQ","qqq_ret"),("SPY","spy_ret"),("STATIC_50_50_SMH_QQQ","static_50_50")):
        result["controls"][name]={"cagr":cagr(df[col]),"max_drawdown":maxdd(df[col]),"ann_vol":annvol(df[col])}
    for bps in COSTS:
        col=f"net_{bps}"; df[col]=df["gross"]-switches*(bps/10000.0); fs=folds(df,col,"static_50_50")
        result["cost_cases"][str(bps)]={"cagr":cagr(df[col]),"max_drawdown":maxdd(df[col]),"ann_vol":annvol(df[col]),"excess_vs_static_50_50":cagr(df[col])-cagr(df["static_50_50"]),"positive_folds_vs_static":sum(x["excess_cagr"]>0 for x in fs),"folds":fs}
    p=result["cost_cases"]["25"]; s=result["cost_cases"]["50"]
    result["decision"]="SUPPORTED_CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION" if p["excess_vs_static_50_50"]>0 and p["positive_folds_vs_static"]>=3 and s["excess_vs_static_50_50"]>0 else "NOT_SUPPORTED_ROTATE"
    result["protected_boundaries"]={"mm_canonical_claim":False,"strategy_spec_mutation":False,"runtime_authority_change":False,"broker_submission":False,"live_trading_change":False}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p34_dollar_regime_semiconductor_allocator.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("P34_RESULT="+json.dumps(result,sort_keys=True))

if __name__=="__main__": main()
