#!/usr/bin/env python3
import hashlib, json, math, time
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
START="2003-01-01"; END="2026-09-08"; COSTS=(10,25,50)

def get(url,attempts=5):
    last=None
    for i in range(attempts):
        try:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 research-compute"}),timeout=30) as r: raw=r.read()
            if len(raw)<200: raise RuntimeError(f"short_response={len(raw)}")
            return raw,i+1
        except Exception as e:
            last=e; time.sleep(min(2**i,8))
    raise RuntimeError(f"source_fetch_failed:{last}")

def yahoo(sym):
    p1=int(pd.Timestamp(START,tz="UTC").timestamp()); p2=int(pd.Timestamp(END,tz="UTC").timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true"
    raw,attempt=get(url); r=json.loads(raw)["chart"]["result"][0]
    idx=pd.to_datetime(r["timestamp"],unit="s",utc=True).tz_convert(None)
    vals=r.get("indicators",{}).get("adjclose",[{}])[0].get("adjclose") or r["indicators"]["quote"][0]["close"]
    s=pd.Series(vals,index=idx,dtype=float).dropna().sort_index()
    if len(s)<500: raise RuntimeError(f"{sym}_insufficient_rows={len(s)}")
    return s,{"url":url,"sha256":hashlib.sha256(raw).hexdigest(),"rows":int(len(s)),"attempt":attempt,"last_observation":str(s.index.max().date()),"source_class":"YAHOO_CHART_V8_EXTERNAL_RESEARCH_NOT_MM_CANONICAL"}

def cagr(r):
    r=pd.Series(r).dropna(); total=float((1+r).prod()); return total**(12/len(r))-1 if len(r) and total>0 else -1.0

def maxdd(r):
    eq=(1+pd.Series(r).fillna(0)).cumprod(); return float((eq/eq.cummax()-1).min())

def vol(r): return float(pd.Series(r).std(ddof=1)*math.sqrt(12))
def folds(df,s,c):
    out=[]
    for n,a in enumerate(np.array_split(np.arange(len(df)),5),1):
        x=df.iloc[a]; sa=cagr(x[s]); ca=cagr(x[c]); out.append({"fold":n,"start":str(x.index.min().date()),"end":str(x.index.max().date()),"strategy_cagr":sa,"control_cagr":ca,"excess_cagr":sa-ca})
    return out

def main():
    px={}; src={}
    for sym in ("SMH","QQQ","SPY","RSP"):
        px[sym],src[sym]=yahoo(sym)
    common_last=min(v.index.max() for v in px.values()); month_end=common_last.normalize()+pd.offsets.MonthEnd(0)
    m=pd.concat({k:v.resample("ME").last() for k,v in px.items()},axis=1).dropna()
    if common_last.normalize()<month_end.normalize(): m=m.loc[m.index<month_end]
    r=m.pct_change(); breadth_rel=(m["RSP"].pct_change(3)-m["SPY"].pct_change(3)).shift(1)
    df=pd.DataFrame(index=m.index); df["smh"]=r["SMH"]; df["qqq"]=r["QQQ"]; df["spy"]=r["SPY"]; df["signal"]=(breadth_rel>0).astype(float); df=df.dropna()
    df["gross"]=np.where(df["signal"]>0,df["smh"],df["qqq"]); df["static"]=0.5*df["smh"]+0.5*df["qqq"]
    switches=df["signal"].diff().abs().fillna(1)
    out={"schema":"research.p35_equal_weight_breadth_semiconductor_allocator.v1","hypothesis":"Prior 3-month RSP-minus-SPY relative return above zero selects SMH next month; otherwise QQQ.","window":{"start":str(df.index.min().date()),"end":str(df.index.max().date()),"months":int(len(df))},"sources":src,"switches":int(switches.sum()),"controls":{},"cost_cases":{},"evaluation_integrity":{"common_last_daily_observation":str(common_last.date()),"incomplete_terminal_month_excluded":True}}
    for name,col in (("SMH","smh"),("QQQ","qqq"),("SPY","spy"),("STATIC_50_50_SMH_QQQ","static")): out["controls"][name]={"cagr":cagr(df[col]),"max_drawdown":maxdd(df[col]),"ann_vol":vol(df[col])}
    for bps in COSTS:
        col=f"net_{bps}"; df[col]=df["gross"]-switches*(bps/10000); fs=folds(df,col,"static")
        out["cost_cases"][str(bps)]={"cagr":cagr(df[col]),"max_drawdown":maxdd(df[col]),"ann_vol":vol(df[col]),"excess_vs_static_50_50":cagr(df[col])-cagr(df["static"]),"positive_folds_vs_static":sum(x["excess_cagr"]>0 for x in fs),"folds":fs}
    p=out["cost_cases"]["25"]; s=out["cost_cases"]["50"]; out["decision"]="SUPPORTED_CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION" if p["excess_vs_static_50_50"]>0 and p["positive_folds_vs_static"]>=3 and s["excess_vs_static_50_50"]>0 else "NOT_SUPPORTED_ROTATE"
    out["protected_boundaries"]={"mm_canonical_claim":False,"strategy_spec_mutation":False,"runtime_authority_change":False,"broker_submission":False,"live_trading_change":False}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p35_equal_weight_breadth_semiconductor_allocator.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print("P35_RESULT="+json.dumps(out,sort_keys=True))
if __name__=="__main__": main()
