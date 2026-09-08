#!/usr/bin/env python3
# Frozen P22 contract; trigger revision 1.
import json, urllib.request
from datetime import datetime, timezone
SYMS=["CPER","GLD","SMH","QQQ","SPY"]; START=1325376000; END=int(datetime.now(timezone.utc).timestamp()); LOOKBACK=63; COSTS=[0.0010,0.0025,0.0050]
def yahoo(sym):
 u=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true"; req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
 with urllib.request.urlopen(req,timeout=30) as r: j=json.loads(r.read())
 z=j["chart"]["result"][0]; adj=(z.get("indicators",{}).get("adjclose") or [{}])[0].get("adjclose") or z["indicators"]["quote"][0]["close"]; return {datetime.fromtimestamp(t,timezone.utc).date().isoformat():float(p) for t,p in zip(z["timestamp"],adj) if p is not None}
def cagr(v,y): return v**(1/y)-1
def maxdd(vals):
 peak=vals[0]; dd=0
 for v in vals: peak=max(peak,v); dd=min(dd,v/peak-1)
 return dd
def run(cost):
 d={s:yahoo(s) for s in SYMS}; dates=sorted(set.intersection(*(set(x) for x in d.values()))); ratio=[d["CPER"][x]/d["GLD"][x] for x in dates]; eq=bench=smh=qqq=spy=1.; prev=None; curve=[1.]; daily=[]
 for i in range(LOOKBACK,len(dates)-1):
  state="SMH" if ratio[i]/ratio[i-LOOKBACK]-1>0 else "QQQ"; cur,nxt=dates[i],dates[i+1]; r={s:d[s][nxt]/d[s][cur]-1 for s in ["SMH","QQQ","SPY"]}; rr=r[state]-(cost if prev is not None and state!=prev else 0); eq*=1+rr; smh*=1+r["SMH"]; qqq*=1+r["QQQ"]; spy*=1+r["SPY"]; br=.5*(r["SMH"]+r["QQQ"]); bench*=1+br; curve.append(eq); daily.append((nxt,rr,br)); prev=state
 years=(datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[LOOKBACK])).days/365.25; n=len(daily); chunk=n//5; fw=0
 for k in range(5):
  ps=pb=1.; a=k*chunk; b=n if k==4 else (k+1)*chunk
  for _,x,y in daily[a:b]: ps*=1+x; pb*=1+y
  fw+=ps>pb
 yr={}
 for dt,x,y in daily: q=yr.setdefault(dt[:4],[1.,1.]); q[0]*=1+x; q[1]*=1+y
 sc,bc=cagr(eq,years),cagr(bench,years)
 return {"window_start":daily[0][0],"window_end":daily[-1][0],"sessions":n,"strategy_cagr":sc,"equal_smh_qqq_cagr":bc,"smh_cagr":cagr(smh,years),"qqq_cagr":cagr(qqq,years),"spy_cagr":cagr(spy,years),"strategy_max_dd":maxdd(curve),"excess_vs_equal_pp":100*(sc-bc),"positive_equal_excess_folds":fw,"positive_equal_excess_years":sum(a>b for a,b in yr.values()),"represented_years":len(yr)}
def main():
 results={str(int(c*10000)):run(c) for c in COSTS}; p=results["25"]; decision="P22_COPPER_GOLD_RISK_APPETITE_SUPPORTED" if p["excess_vs_equal_pp"]>0 and p["positive_equal_excess_folds"]>=3 and results["50"]["excess_vs_equal_pp"]>0 else "P22_COPPER_GOLD_RISK_APPETITE_NOT_SUPPORTED"; out={"schema":"p22.copper_gold_risk_appetite.v1","frozen_contract":{"signal":"CPER/GLD 63-session momentum > 0","allocation":"SMH when positive else QQQ","controls":["SMH","QQQ","SPY","equal SMH/QQQ"],"cost_bps_per_allocation_switch":[10,25,50]},"results":results,"decision":decision}; print(json.dumps(out,indent=2,sort_keys=True)); open("p22_result.json","w").write(json.dumps(out,indent=2,sort_keys=True)+"\n")
if __name__=="__main__": main()
