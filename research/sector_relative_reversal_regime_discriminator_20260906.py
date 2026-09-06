from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
START="2014-01-01"; END="2026-09-07"
SECTORS=["XLK","XLF","XLV","XLE","XLI","XLY","XLP","XLU","XLB"]
ALL=SECTORS+["SPY","QQQ"]; LOOKBACK=21; HOLD=21; TOP_K=3; COST=10.0; SPY_REGIME_LOOKBACK=63

def epoch(x): return int(datetime.fromisoformat(x).replace(tzinfo=timezone.utc).timestamp())
def load(s):
 q=urlencode({"period1":epoch(START),"period2":epoch(END),"interval":"1d","events":"history","includeAdjustedClose":"true"})
 req=Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?{q}",headers={"User-Agent":"Mozilla/5.0 research-compute/1.0"})
 with urlopen(req,timeout=30) as r: p=json.loads(r.read().decode())
 x=(p.get("chart",{}).get("result") or [None])[0]
 if not x: raise RuntimeError(f"{s}: no chart result")
 ts=pd.to_datetime(x.get("timestamp") or [],unit="s",utc=True); ind=x.get("indicators",{}); adj=(ind.get("adjclose") or [{}])[0].get("adjclose"); close=adj or (ind.get("quote") or [{}])[0].get("close")
 return pd.Series(pd.to_numeric(pd.Series(close),errors="coerce").to_numpy(),index=ts,name=s).dropna().sort_index()
def mean(rows,k): return float(np.mean([r[k] for r in rows])) if rows else None
def summarize(rows):
 if not rows: return {"events":0}
 return {"events":len(rows),"candidate_net10_mean_bps":mean(rows,"candidate_net10_bps"),"equal_sector_net10_mean_bps":mean(rows,"equal_sector_net10_bps"),"spy_gross_mean_bps":mean(rows,"spy_gross_bps"),"qqq_gross_mean_bps":mean(rows,"qqq_gross_bps"),"excess_vs_equal_sector_mean_bps":mean(rows,"excess_vs_equal_sector_bps"),"excess_vs_spy_mean_bps":mean(rows,"excess_vs_spy_bps"),"excess_vs_qqq_mean_bps":mean(rows,"excess_vs_qqq_bps")}
def main():
 px={s:load(s) for s in ALL}; common=pd.DatetimeIndex(sorted(set.intersection(*[set(x.index) for x in px.values()]))); f=pd.DataFrame({k:v.reindex(common) for k,v in px.items()}).dropna()
 rows=[]
 for i in range(max(LOOKBACK,SPY_REGIME_LOOKBACK),len(f)-HOLD,HOLD):
  trailing={s:float(f[s].iloc[i]/f[s].iloc[i-LOOKBACK]-1) for s in SECTORS}; eq_trail=float(np.mean(list(trailing.values()))); selected=sorted(SECTORS,key=lambda s:(trailing[s]-eq_trail,s))[:TOP_K]
  gross=float(np.mean([f[s].iloc[i+HOLD]/f[s].iloc[i]-1 for s in selected]))*10000; eq=float(np.mean([f[s].iloc[i+HOLD]/f[s].iloc[i]-1 for s in SECTORS]))*10000; spy=float(f.SPY.iloc[i+HOLD]/f.SPY.iloc[i]-1)*10000; qqq=float(f.QQQ.iloc[i+HOLD]/f.QQQ.iloc[i]-1)*10000
  spy_prior63=float(f.SPY.iloc[i]/f.SPY.iloc[i-SPY_REGIME_LOOKBACK]-1)*10000; regime="SPY_PRIOR63_NONPOSITIVE" if spy_prior63<=0 else "SPY_PRIOR63_POSITIVE"
  rows.append({"decision_date":f.index[i].isoformat(),"regime":regime,"spy_prior63_bps":spy_prior63,"selected":selected,"candidate_net10_bps":gross-COST,"equal_sector_net10_bps":eq-COST,"spy_gross_bps":spy,"qqq_gross_bps":qqq,"excess_vs_equal_sector_bps":gross-eq,"excess_vs_spy_bps":gross-COST-spy,"excess_vs_qqq_bps":gross-COST-qqq})
 by={r: summarize([x for x in rows if x["regime"]==r]) for r in ("SPY_PRIOR63_NONPOSITIVE","SPY_PRIOR63_POSITIVE")}
 neg=by["SPY_PRIOR63_NONPOSITIVE"]
 supported=neg.get("events",0)>=20 and neg.get("excess_vs_equal_sector_mean_bps",-1)>0 and neg.get("excess_vs_spy_mean_bps",-1)>0
 out={"schema":"public_research.sector_relative_reversal_regime_discriminator.v1","research_only":True,"parent_mechanism":"bottom-3 prior-21-session sector relative reversal","regime_definition":"SPY prior 63-session total return <= 0 at decision time","cost_bps":COST,"by_regime":by,"decision":"REGIME_CONDITIONAL_SIGNAL_SUPPORTED" if supported else "REGIME_CONDITIONAL_SIGNAL_NOT_SUPPORTED","note":"Diagnostic only. No parameter search, promotion, allocation, runtime, broker, or live authority.","allocation_authority":False,"promotion_authority":False,"live_trading_change":False}
 open("sector-relative-reversal-regime-receipt.json","w").write(json.dumps(out,sort_keys=True,indent=2)+"\n"); print("SECTOR_REVERSAL_REGIME="+json.dumps(out,sort_keys=True))
if __name__=="__main__": main()
