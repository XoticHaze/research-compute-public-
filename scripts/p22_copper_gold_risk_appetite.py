#!/usr/bin/env python3
import json, math, statistics, urllib.request
from datetime import datetime, timezone

SYMS=["CPER","GLD","SMH","QQQ","SPY"]
START=1325376000  # 2012-01-01 UTC
END=int(datetime.now(timezone.utc).timestamp())
LOOKBACK=63
COSTS=[0.0010,0.0025,0.0050]  # per switch, one-way allocation turnover approximation

def yahoo(sym):
    u=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true"
    req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=30) as r: raw=r.read()
    j=json.loads(raw); z=j["chart"]["result"][0]
    adj=(z.get("indicators",{}).get("adjclose") or [{}])[0].get("adjclose")
    if not adj: adj=z["indicators"]["quote"][0]["close"]
    out={}
    for t,p in zip(z["timestamp"],adj):
        if p is not None: out[datetime.fromtimestamp(t,timezone.utc).date().isoformat()]=float(p)
    return out

def cagr(vals,years): return vals[-1]**(1/years)-1 if years>0 else 0

def maxdd(vals):
    peak=vals[0]; dd=0
    for v in vals:
        peak=max(peak,v); dd=min(dd,v/peak-1)
    return dd

def run(cost):
    d={s:yahoo(s) for s in SYMS}
    dates=sorted(set.intersection(*(set(x) for x in d.values())))
    ratio=[d["CPER"][x]/d["GLD"][x] for x in dates]
    eq=bench=smh=qqq=spy=1.0; prev=None; curve=[1.0]; folds=[]; yearly={}
    daily=[]
    for i in range(LOOKBACK,len(dates)-1):
        state="SMH" if ratio[i]/ratio[i-LOOKBACK]-1>0 else "QQQ"
        nxt=dates[i+1]; cur=dates[i]
        r={s:d[s][nxt]/d[s][cur]-1 for s in ["SMH","QQQ","SPY"]}
        turnover=cost if prev is not None and state!=prev else 0.0
        rr=r[state]-turnover
        eq*=1+rr; smh*=1+r["SMH"]; qqq*=1+r["QQQ"]; spy*=1+r["SPY"]; bench*=1+0.5*(r["SMH"]+r["QQQ"])
        curve.append(eq); daily.append((nxt,rr,r["SMH"],r["QQQ"],0.5*(r["SMH"]+r["QQQ"])))
        prev=state
    years=(datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[LOOKBACK])).days/365.25
    n=len(daily); chunk=n//5
    foldwins=0
    for k in range(5):
        a=k*chunk; b=n if k==4 else (k+1)*chunk
        ps=pb=1.0
        for _,x,_,_,y in daily[a:b]: ps*=1+x; pb*=1+y
        foldwins += ps>pb
    yr={}
    for dt,x,_,_,y in daily:
        yk=dt[:4]; yr.setdefault(yk,[1.0,1.0]); yr[yk][0]*=1+x; yr[yk][1]*=1+y
    yearwins=sum(a>b for a,b in yr.values())
    return {"window_start":daily[0][0],"window_end":daily[-1][0],"sessions":n,"strategy_cagr":cagr([1,eq],years),"equal_smh_qqq_cagr":cagr([1,bench],years),"smh_cagr":cagr([1,smh],years),"qqq_cagr":cagr([1,qqq],years),"spy_cagr":cagr([1,spy],years),"strategy_max_dd":maxdd(curve),"excess_vs_equal_pp":100*(cagr([1,eq],years)-cagr([1,bench],years)),"positive_equal_excess_folds":foldwins,"positive_equal_excess_years":yearwins,"represented_years":len(yr)}

def main():
    results={str(int(c*10000)):run(c) for c in COSTS}
    p=results["25"]
    decision="P22_COPPER_GOLD_RISK_APPETITE_SUPPORTED" if p["excess_vs_equal_pp"]>0 and p["positive_equal_excess_folds"]>=3 and results["50"]["excess_vs_equal_pp"]>0 else "P22_COPPER_GOLD_RISK_APPETITE_NOT_SUPPORTED"
    out={"schema":"p22.copper_gold_risk_appetite.v1","frozen_contract":{"signal":"CPER/GLD 63-session momentum > 0","allocation":"SMH when positive else QQQ","controls":["SMH","QQQ","SPY","equal SMH/QQQ"],"cost_bps_per_allocation_switch":[10,25,50]},"results":results,"decision":decision}
    print(json.dumps(out,indent=2,sort_keys=True)); open("p22_result.json","w").write(json.dumps(out,indent=2,sort_keys=True)+"\n")
if __name__=="__main__": main()
