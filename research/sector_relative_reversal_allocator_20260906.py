from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
START="2014-01-01"; END="2026-09-07"
SECTORS=["XLK","XLF","XLV","XLE","XLI","XLY","XLP","XLU","XLB"]
ALL=SECTORS+["SPY","QQQ"]; LOOKBACK=21; HOLD=21; TOP_K=3; PRIMARY=10.0; STRESS=25.0
def epoch(x): return int(datetime.fromisoformat(x).replace(tzinfo=timezone.utc).timestamp())
def load(s):
 q=urlencode({"period1":epoch(START),"period2":epoch(END),"interval":"1d","events":"history","includeAdjustedClose":"true"})
 req=Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?{q}",headers={"User-Agent":"Mozilla/5.0 research-compute/1.0"})
 with urlopen(req,timeout=30) as r: p=json.loads(r.read().decode())
 x=(p.get("chart",{}).get("result") or [None])[0]
 if not x: raise RuntimeError(f"{s}: no chart result")
 ts=pd.to_datetime(x.get("timestamp") or [],unit="s",utc=True); ind=x.get("indicators",{}); adj=(ind.get("adjclose") or [{}])[0].get("adjclose"); close=adj or (ind.get("quote") or [{}])[0].get("close")
 z=pd.Series(pd.to_numeric(pd.Series(close),errors="coerce").to_numpy(),index=ts,name=s).dropna(); return z[~z.index.duplicated(keep="last")].sort_index()
def folds(v):
 a=np.asarray(v,float); return [float(np.mean(a[i])) for i in np.array_split(np.arange(len(a)),5) if len(i)]
def main():
 px={s:load(s) for s in ALL}; common=pd.DatetimeIndex(sorted(set.intersection(*[set(x.index) for x in px.values()]))); f=pd.DataFrame({k:v.reindex(common) for k,v in px.items()}).dropna()
 if len(f)<2000: raise RuntimeError(f"insufficient common history {len(f)}")
 rows=[]
 for i in range(LOOKBACK,len(f)-HOLD,HOLD):
  trailing={s:float(f[s].iloc[i]/f[s].iloc[i-LOOKBACK]-1) for s in SECTORS}; eq_trail=float(np.mean(list(trailing.values()))); score={s:trailing[s]-eq_trail for s in SECTORS}; selected=sorted(SECTORS,key=lambda s:(score[s],s))[:TOP_K]
  gross=float(np.mean([f[s].iloc[i+HOLD]/f[s].iloc[i]-1 for s in selected]))*10000; eq=float(np.mean([f[s].iloc[i+HOLD]/f[s].iloc[i]-1 for s in SECTORS]))*10000; spy=float(f.SPY.iloc[i+HOLD]/f.SPY.iloc[i]-1)*10000; qqq=float(f.QQQ.iloc[i+HOLD]/f.QQQ.iloc[i]-1)*10000
  rows.append({"decision_date":f.index[i].isoformat(),"exit_date":f.index[i+HOLD].isoformat(),"selected":selected,"prior21_relative_bps":{s:score[s]*10000 for s in SECTORS},"candidate_net10_bps":gross-PRIMARY,"candidate_net25_bps":gross-STRESS,"equal_sector_net10_bps":eq-PRIMARY,"equal_sector_net25_bps":eq-STRESS,"spy_gross_bps":spy,"qqq_gross_bps":qqq,"excess_vs_equal_sector_10_bps":gross-eq,"excess_vs_equal_sector_25_bps":gross-eq,"excess_vs_spy_10_bps":gross-PRIMARY-spy,"excess_vs_qqq_10_bps":gross-PRIMARY-qqq})
 def avg(k): return float(np.mean([r[k] for r in rows]))
 ef=folds([r["excess_vs_equal_sector_10_bps"] for r in rows]); sf=folds([r["excess_vs_spy_10_bps"] for r in rows]); qf=folds([r["excess_vs_qqq_10_bps"] for r in rows])
 agg={"events":len(rows),"candidate_net10_mean_bps":avg("candidate_net10_bps"),"candidate_net25_mean_bps":avg("candidate_net25_bps"),"equal_sector_net10_mean_bps":avg("equal_sector_net10_bps"),"equal_sector_net25_mean_bps":avg("equal_sector_net25_bps"),"excess_vs_equal_sector_10_mean_bps":avg("excess_vs_equal_sector_10_bps"),"excess_vs_equal_sector_25_mean_bps":avg("excess_vs_equal_sector_25_bps"),"excess_vs_spy_10_mean_bps":avg("excess_vs_spy_10_bps"),"excess_vs_qqq_10_mean_bps":avg("excess_vs_qqq_10_bps"),"positive_equal_sector_folds":sum(x>0 for x in ef),"positive_spy_folds":sum(x>0 for x in sf),"positive_qqq_folds":sum(x>0 for x in qf),"equal_sector_fold_excess_bps":ef,"spy_fold_excess_bps":sf,"qqq_fold_excess_bps":qf}
 ok=agg["excess_vs_equal_sector_10_mean_bps"]>0 and agg["excess_vs_equal_sector_25_mean_bps"]>0 and agg["excess_vs_spy_10_mean_bps"]>0 and agg["positive_equal_sector_folds"]>=3 and agg["positive_spy_folds"]>=3
 out={"schema":"public_research.sector_relative_reversal_allocator.v1","research_only":True,"mechanism":"monthly bottom-3 prior-21-session sector return relative to equal-sector basket","universe":SECTORS,"costs_bps":{"primary":PRIMARY,"stress":STRESS},"aggregate":agg,"decision":"SECTOR_RELATIVE_REVERSAL_SUPPORTED" if ok else "SECTOR_RELATIVE_REVERSAL_REJECTED","rows":rows,"allocation_authority":False,"promotion_authority":False,"runtime_authority":False,"broker_authority":False,"live_trading_change":False}
 open("sector-relative-reversal-allocator-receipt.json","w").write(json.dumps(out,sort_keys=True,indent=2)+"\n"); print("SECTOR_RELATIVE_REVERSAL="+json.dumps(out,sort_keys=True))
if __name__=="__main__": main()
