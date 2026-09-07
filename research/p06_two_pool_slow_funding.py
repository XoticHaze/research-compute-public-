#!/usr/bin/env python3
# Frozen P06 contract. Trigger commit changes execution state only, not scientific semantics.
import json, math, time, urllib.request
from datetime import datetime, timezone
SYMS=["SMH","ITB","SPY","QQQ"]; LOOKBACK=126; COSTS_BPS=[10,25,50]; PRIMARY_BPS=25
def yahoo(sym):
 url=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2={int(time.time())}&interval=1d&events=history&includeAdjustedClose=true"; req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
 with urllib.request.urlopen(req,timeout=30) as r: obj=json.load(r)
 x=obj["chart"]["result"][0]; return {datetime.fromtimestamp(t,timezone.utc).date():float(v) for t,v in zip(x["timestamp"],x["indicators"]["adjclose"][0]["adjclose"]) if v is not None}
def month_ends(ds):
 out=[]
 for d in sorted(ds):
  if not out or (d.year,d.month)!=(out[-1].year,out[-1].month): out.append(d)
  else: out[-1]=d
 return out
def cagr(v,y): return v[-1]**(1/y)-1
def mdd(v):
 p=v[0]; w=0
 for x in v: p=max(p,x); w=min(w,x/p-1)
 return w
def run(cb):
 p={s:yahoo(s) for s in SYMS}; dates=sorted(set.intersection(*(set(v) for v in p.values()))); idx={d:i for i,d in enumerate(dates)}; mes=month_ends(dates); rows=[]
 for j in range(len(mes)-1):
  d,n=mes[j],mes[j+1]; i=idx[d]
  if i<LOOKBACK: continue
  old=dates[i-LOOKBACK]; mom={s:p[s][d]/p[s][old]-1 for s in ["SMH","ITB"]}; pick=max(mom,key=mom.get); ret={s:p[s][n]/p[s][d]-1 for s in SYMS}; rows.append((d,n,pick,ret))
 curves={q:[1.] for q in ["switch","equal","SMH","ITB","SPY","QQQ"]}; yearly={}; folds=[[] for _ in range(5)]; prev=None
 for k,(d,n,pick,ret) in enumerate(rows):
  cost=(1. if prev is None or pick!=prev else 0.)*cb/10000.; rr={"switch":ret[pick]-cost,"equal":.5*ret["SMH"]+.5*ret["ITB"],"SMH":ret["SMH"],"ITB":ret["ITB"],"SPY":ret["SPY"],"QQQ":ret["QQQ"]}
  for q,v in rr.items(): curves[q].append(curves[q][-1]*(1+v))
  yearly.setdefault(n.year,{q:1. for q in rr})
  for q,v in rr.items(): yearly[n.year][q]*=1+v
  folds[min(4,k*5//len(rows))].append(rr); prev=pick
 years=(rows[-1][1]-rows[0][0]).days/365.25; stats={q:{"cagr":cagr(v,years),"max_drawdown":mdd(v),"terminal":v[-1]} for q,v in curves.items()}; full=[y for y in yearly if sum(r[1].year==y for r in rows)>=11]; bases=["equal","SMH","ITB","SPY","QQQ"]
 fw={b:0 for b in bases}
 for f in folds:
  sw=math.prod(1+r["switch"] for r in f)-1
  for b in bases: fw[b]+=sw>math.prod(1+r[b] for r in f)-1
 return {"window":{"start":str(rows[0][0]),"end":str(rows[-1][1]),"monthly_decisions":len(rows)},"cost_bps_per_switch":cb,"stats":stats,"excess_cagr_pp":{b:100*(stats["switch"]["cagr"]-stats[b]["cagr"]) for b in bases},"full_years":len(full),"year_wins":{b:sum(yearly[y]["switch"]>yearly[y][b] for y in full) for b in bases},"fold_wins_of_5":fw,"selection_counts":{"SMH":sum(r[2]=="SMH" for r in rows),"ITB":sum(r[2]=="ITB" for r in rows)}}
def main():
 results={str(c):run(c) for c in COSTS_BPS}; p=results[str(PRIMARY_BPS)]; ok=p["excess_cagr_pp"]["equal"]>0 and p["fold_wins_of_5"]["equal"]>=3 and p["year_wins"]["equal"]>=math.ceil(p["full_years"]*.5) and results["50"]["excess_cagr_pp"]["equal"]>0; out={"schema":"p06-two-pool-slow-funding-v1","frozen_contract":{"supported_pool_proxies":{"semiconductor":"SMH","homebuilder":"ITB"},"decision_frequency":"month-end","state":"126-session adjusted-close relative momentum","allocation":"100% to higher-momentum supported pool for next month","controls":["equal 50/50 SMH-ITB","SMH","ITB","SPY","QQQ"],"costs_bps_per_switch":COSTS_BPS,"primary_bps":PRIMARY_BPS},"results":results,"decision":"CONTINUE" if ok else "NOT_SUPPORTED","promotion_gate":"positive excess vs equal at 25 and 50 bps, >=3/5 fold wins vs equal, >=50% full-year wins vs equal"}; open("p06_two_pool_slow_funding_result.json","w").write(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,indent=2,sort_keys=True))
if __name__=="__main__": main()
