#!/usr/bin/env python3
import hashlib, io, json, math, time
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START="2000-01-01"
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
    raise RuntimeError(f"source_fetch_failed: {last}")


def yahoo(sym):
    p1=int(pd.Timestamp(START,tz="UTC").timestamp()); p2=int(pd.Timestamp(END,tz="UTC").timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true"
    raw,attempt=get(url); obj=json.loads(raw); r=obj["chart"]["result"][0]
    ts=pd.to_datetime(r["timestamp"],unit="s",utc=True).tz_convert(None)
    adj=r.get("indicators",{}).get("adjclose",[{}])[0].get("adjclose")
    if not adj: adj=r["indicators"]["quote"][0]["close"]
    s=pd.Series(adj,index=ts,dtype=float).dropna().sort_index()
    if len(s)<500: raise RuntimeError(f"{sym}_insufficient_rows={len(s)}")
    return s,{"url":url,"sha256":hashlib.sha256(raw).hexdigest(),"rows":int(len(s)),"attempt":attempt}


def fred(series):
    url=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    raw,attempt=get(url)
    df=pd.read_csv(io.BytesIO(raw)); df.columns=["date","value"]
    df["date"]=pd.to_datetime(df["date"]); df["value"]=pd.to_numeric(df["value"],errors="coerce")
    s=df.dropna().set_index("date")["value"].sort_index()
    if len(s)<100: raise RuntimeError(f"{series}_insufficient_rows={len(s)}")
    return s,{"url":url,"sha256":hashlib.sha256(raw).hexdigest(),"rows":int(len(s)),"attempt":attempt}


def cagr(r):
    r=pd.Series(r).dropna(); n=len(r)
    if n==0:return float("nan")
    total=float((1+r).prod())
    return total**(12.0/n)-1 if total>0 else -1.0


def maxdd(r):
    eq=(1+pd.Series(r).fillna(0)).cumprod(); peak=eq.cummax(); return float((eq/peak-1).min())


def annvol(r): return float(pd.Series(r).std(ddof=1)*math.sqrt(12))


def fold_stats(df, strat_col, control_col):
    idx=np.array_split(np.arange(len(df)),5); out=[]
    for n,arr in enumerate(idx,1):
        x=df.iloc[arr]
        a=cagr(x[strat_col]); b=cagr(x[control_col])
        out.append({"fold":n,"start":str(x.index.min().date()),"end":str(x.index.max().date()),"strategy_cagr":a,"control_cagr":b,"excess_cagr":a-b})
    return out


def main():
    prices={}; src={}
    for sym in ("ITB","QQQ","SPY"):
        prices[sym],src[sym]=yahoo(sym)
    mort,src["MORTGAGE30US"]=fred("MORTGAGE30US")
    m=pd.concat({k:v.resample("ME").last() for k,v in prices.items()},axis=1).dropna()
    mortgage=mort.resample("ME").last().reindex(m.index,method="ffill")
    # Frozen causal state: falling financing cost over prior 3 month-ends -> ITB next month, else QQQ.
    signal=(mortgage.diff(3)<0).astype(int)
    rets=m.pct_change()
    df=pd.DataFrame(index=m.index)
    df["itb_ret"]=rets["ITB"]; df["qqq_ret"]=rets["QQQ"]; df["spy_ret"]=rets["SPY"]
    df["signal_itb"]=signal.shift(1)
    df=df.dropna().copy()
    df["gross"]=np.where(df["signal_itb"]==1,df["itb_ret"],df["qqq_ret"])
    df["static_50_50"]=0.5*df["itb_ret"]+0.5*df["qqq_ret"]
    switches=df["signal_itb"].diff().abs().fillna(1.0)
    result={
      "schema":"research.p32_mortgage_rate_homebuilder_allocator.v1",
      "hypothesis":"Prior 3-month decline in US 30Y mortgage rate selects ITB for next month; otherwise QQQ.",
      "window":{"start":str(df.index.min().date()),"end":str(df.index.max().date()),"months":int(len(df))},
      "sources":src,"switches":int(switches.sum()),"controls":{},"cost_cases":{},
    }
    for name,col in (("ITB","itb_ret"),("QQQ","qqq_ret"),("SPY","spy_ret"),("STATIC_50_50_ITB_QQQ","static_50_50")):
        result["controls"][name]={"cagr":cagr(df[col]),"max_drawdown":maxdd(df[col]),"ann_vol":annvol(df[col])}
    for bps in COSTS:
        col=f"net_{bps}"; df[col]=df["gross"]-switches*(bps/10000.0)
        folds=fold_stats(df,col,"static_50_50")
        result["cost_cases"][str(bps)]={"cagr":cagr(df[col]),"max_drawdown":maxdd(df[col]),"ann_vol":annvol(df[col]),"excess_vs_static_50_50":cagr(df[col])-cagr(df["static_50_50"]),"positive_folds_vs_static":sum(x["excess_cagr"]>0 for x in folds),"folds":folds}
    primary=result["cost_cases"]["25"]; stress=result["cost_cases"]["50"]
    result["decision"]="SUPPORTED_CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION" if primary["excess_vs_static_50_50"]>0 and primary["positive_folds_vs_static"]>=3 and stress["excess_vs_static_50_50"]>0 else "NOT_SUPPORTED_ROTATE"
    result["protected_boundaries"]={"mm_canonical_claim":False,"strategy_spec_mutation":False,"runtime_authority_change":False,"broker_submission":False,"live_trading_change":False}
    Path("artifacts").mkdir(exist_ok=True); out=Path("artifacts/p32_mortgage_rate_homebuilder_allocator.json"); out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("P32_RESULT="+json.dumps(result,sort_keys=True))

if __name__=="__main__": main()
