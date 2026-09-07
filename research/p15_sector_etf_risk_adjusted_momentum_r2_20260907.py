from __future__ import annotations
import json, math
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

START="2000-01-01"; END="2026-09-07"
SECTORS=["XLK","XLF","XLV","XLE","XLI","XLY","XLP","XLU","XLB"]
ALL=SECTORS+["SPY","QQQ"]
LOOKBACK=126; VOL=63; TOP=3; COSTS=[10.0,25.0,50.0]; PRIMARY=25.0
OUT="p15-sector-etf-risk-adjusted-momentum-receipt.json"

def epoch(x): return int(datetime.fromisoformat(x).replace(tzinfo=timezone.utc).timestamp())
def load(s):
 q=urlencode({"period1":epoch(START),"period2":epoch(END),"interval":"1d","events":"history","includeAdjustedClose":"true"})
 req=Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?{q}",headers={"User-Agent":"Mozilla/5.0 research-compute/1.0"})
 with urlopen(req,timeout=30) as r: p=json.loads(r.read().decode())
 x=(p.get("chart",{}).get("result") or [None])[0]
 if not x: raise RuntimeError(f"{s}: no chart result")
 ts=pd.to_datetime(x.get("timestamp") or [],unit="s",utc=True)
 ind=x.get("indicators",{}); adj=(ind.get("adjclose") or [{}])[0].get("adjclose"); close=adj or (ind.get("quote") or [{}])[0].get("close")
 z=pd.Series(pd.to_numeric(pd.Series(close),errors="coerce").to_numpy(),index=ts,name=s).dropna()
 if len(z)<1000: raise RuntimeError(f"{s}: insufficient rows {len(z)}")
 return z[~z.index.duplicated(keep="last")].sort_index()

def weights(sel): return {s:1.0/TOP for s in sel}
def turnover(a,b):
 names=set(a)|set(b); risky=sum(abs(b.get(s,0)-a.get(s,0)) for s in names)
 return 0.5*(risky+abs((1-sum(b.values()))-(1-sum(a.values()))))
def summary(rows):
 eq=[1.0]; yrs={}
 for d,r in rows:
  eq.append(eq[-1]*(1+r)); y=str(d.year); yrs[y]=yrs.get(y,1.0)*(1+r)
 span=max((rows[-1][0]-rows[0][0]).days/365.25,1/12); peak=eq[0]; mdd=0.0
 for v in eq: peak=max(peak,v); mdd=min(mdd,v/peak-1)
 return {"periods":len(rows),"total_return":eq[-1]-1,"cagr":eq[-1]**(1/span)-1,"max_drawdown":mdd,"year_returns":{y:v-1 for y,v in sorted(yrs.items())}}

def main():
 px={s:load(s) for s in ALL}; common=pd.DatetimeIndex(sorted(set.intersection(*[set(x.index) for x in px.values()])))
 f=pd.DataFrame({k:v.reindex(common) for k,v in px.items()}).dropna()
 if len(f)<2500: raise RuntimeError(f"insufficient common history {len(f)}")
 monthends=[i for i in range(LOOKBACK,len(f)-1) if f.index[i].month!=f.index[i+1].month]
 if len(monthends)<120: raise RuntimeError(f"insufficient decisions {len(monthends)}")
 decisions=[]
 for n,i in enumerate(monthends[:-1]):
  j=monthends[n+1]; raw={}; risk={}
  for s in SECTORS:
   r=float(f[s].iloc[i]/f[s].iloc[i-LOOKBACK]-1); lr=np.log(f[s].iloc[i-VOL:i+1].to_numpy()[1:]/f[s].iloc[i-VOL:i+1].to_numpy()[:-1]); v=float(np.std(lr,ddof=1)*math.sqrt(252)); raw[s]=r; risk[s]=r/v if r>0 and v>0 else -np.inf
  cand=[s for s in sorted(SECTORS,key=lambda s:(-risk[s],s)) if np.isfinite(risk[s])][:TOP]
  ctrl=[s for s in sorted(SECTORS,key=lambda s:(-raw[s],s)) if raw[s]>0][:TOP]
  decisions.append((i,j,cand,ctrl))
 policies={"risk_adjusted":{c:[] for c in COSTS},"raw_momentum":{c:[] for c in COSTS}}; prev={"risk_adjusted":{},"raw_momentum":{}}
 base={"equal_sector":[],"SPY":[],"QQQ":[]}; turns={"risk_adjusted":[],"raw_momentum":[]}
 for i,j,cand,ctrl in decisions:
  for label,sel in (("risk_adjusted",cand),("raw_momentum",ctrl)):
   w=weights(sel); gross=sum(wt*float(f[s].iloc[j]/f[s].iloc[i]-1) for s,wt in w.items()); t=turnover(prev[label],w); turns[label].append(t)
   for c in COSTS: policies[label][c].append((f.index[j],gross-t*c/10000.0))
   prev[label]=w
  base["equal_sector"].append((f.index[j],float(np.mean([f[s].iloc[j]/f[s].iloc[i]-1 for s in SECTORS])))); base["SPY"].append((f.index[j],float(f.SPY.iloc[j]/f.SPY.iloc[i]-1))); base["QQQ"].append((f.index[j],float(f.QQQ.iloc[j]/f.QQQ.iloc[i]-1)))
 sums={"risk_adjusted":{str(int(c)):summary(policies["risk_adjusted"][c]) for c in COSTS},"raw_momentum":{str(int(c)):summary(policies["raw_momentum"][c]) for c in COSTS},**{k:summary(v) for k,v in base.items()}}
 k="25"; ca=sums["risk_adjusted"][k]; ra=sums["raw_momentum"][k]; ew=sums["equal_sector"]; spy=sums["SPY"]; qqq=sums["QQQ"]
 years=sorted(set(ca["year_returns"])&set(ra["year_returns"])&set(ew["year_returns"])&set(spy["year_returns"])&set(qqq["year_returns"]))
 years=[y for y in years if y not in {str(f.index[decisions[0][0]].year),str(f.index[decisions[-1][1]].year)}]
 ye={y:{"vs_raw":ca["year_returns"][y]-ra["year_returns"][y],"vs_equal_sector":ca["year_returns"][y]-ew["year_returns"][y],"vs_SPY":ca["year_returns"][y]-spy["year_returns"][y],"vs_QQQ":ca["year_returns"][y]-qqq["year_returns"][y]} for y in years}
 pr=sum(v["vs_raw"]>0 for v in ye.values()); pe=sum(v["vs_equal_sector"]>0 for v in ye.values()); ps=sum(v["vs_SPY"]>0 for v in ye.values())
 robust=len(years)>=10 and pr/len(years)>=.60 and pe/len(years)>=.60 and ca["cagr"]>ra["cagr"] and ca["cagr"]>ew["cagr"]
 out={"schema":"public_research.p15_sector_etf_risk_adjusted_momentum.v1","research_only":True,"frozen_hypothesis":"126-session sector momentum divided by prior 63-session realized volatility improves monthly top-3 scarce-capital selection versus raw momentum.","source":{"provider":"Yahoo chart adjusted close","query_host":"query1.finance.yahoo.com"},"matched_window":{"signal_start":f.index[decisions[0][0]].isoformat(),"return_end":f.index[decisions[-1][1]].isoformat(),"common_rows":len(f),"monthly_decisions":len(decisions)},"universe":SECTORS,"parameters":{"lookback":LOOKBACK,"vol_window":VOL,"top_n":TOP,"costs_bps":COSTS,"primary_cost_bps":PRIMARY},"summaries":sums,"primary_25bps_excess":{"cagr_vs_raw":ca["cagr"]-ra["cagr"],"cagr_vs_equal_sector":ca["cagr"]-ew["cagr"],"cagr_vs_SPY":ca["cagr"]-spy["cagr"],"cagr_vs_QQQ":ca["cagr"]-qqq["cagr"],"full_years":len(years),"positive_years_vs_raw":pr,"positive_years_vs_equal_sector":pe,"positive_years_vs_SPY":ps,"year_excess":ye},"turnover":{k:{"mean_one_way":float(np.mean(v)),"median_one_way":float(np.median(v))} for k,v in turns.items()},"decision":"P15_RISK_ADJUSTED_SECTOR_MOMENTUM_CONTINUE" if robust else "P15_RISK_ADJUSTED_SECTOR_MOMENTUM_NOT_SUPPORTED","allocation_authority":False,"promotion_authority":False,"runtime_authority":False,"broker_authority":False,"live_trading_change":False}
 open(OUT,"w").write(json.dumps(out,sort_keys=True,indent=2)+"\n"); print("P15_RESULT="+json.dumps(out,sort_keys=True))
if __name__=="__main__": main()
