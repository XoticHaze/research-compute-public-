#!/usr/bin/env python3
from __future__ import annotations
import json, math, time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import pandas as pd

SYMBOLS=("DHI","LEN","PHM","NVR","TOL","MTH","KBH","LGIH","DFH"); DEV=SYMBOLS[:-1]; EXTERNAL="DFH"
START="2019-01-01"; END_EXCLUSIVE="2026-09-14"; MAX_STALE_DAYS=200
OUT=Path("research/results/homebuilder_pit_valuation_source_probe_r2.json")
UA="research-compute valuation-source-probe-r2/1.0 contact@example.com"
INSTANT_SHARES=(("dei","EntityCommonStockSharesOutstanding"),("us-gaap","CommonStockSharesOutstanding"))
WEIGHTED_SHARES=("us-gaap","WeightedAverageNumberOfSharesOutstandingBasic")
EQUITY=(("us-gaap","StockholdersEquity"),("us-gaap","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))

def get(url,ua=UA):
 req=Request(url,headers={"User-Agent":ua});
 with urlopen(req,timeout=45) as r:return json.loads(r.read().decode())
def epoch(s):return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
def prices(sym):
 q=urlencode({"period1":epoch(START),"period2":epoch(END_EXCLUSIVE),"interval":"1d","events":"history","includeAdjustedClose":"true"})
 p=get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}","Mozilla/5.0 research-compute/1.0"); r=(p.get("chart",{}).get("result") or [None])[0]
 if not r: raise RuntimeError(f"{sym}: no chart")
 tz=r.get("meta",{}).get("exchangeTimezoneName") or "America/New_York"; idx=pd.to_datetime(r.get("timestamp") or [],unit="s",utc=True).tz_convert(tz).normalize().tz_localize(None)
 vals=((r.get("indicators",{}).get("quote") or [{}])[0].get("close") or []); s=pd.Series(pd.to_numeric(pd.Series(vals),errors="coerce").to_numpy(),index=idx).dropna(); return s[~s.index.duplicated(keep="last")].sort_index()
def ciks():
 p=get("https://www.sec.gov/files/company_tickers.json"); return {v["ticker"].upper():int(v["cik_str"]) for v in p.values()}
def units(p,tax,concept):
 u=p.get("facts",{}).get(tax,{}).get(concept,{}).get("units",{}); return u.get("shares") or u.get("USD") or (u[sorted(u)[0]] if u else [])
def instant(p,concepts,asof):
 ad=asof.date()
 for tax,c in concepts:
  q=[]
  for f in units(p,tax,c):
   try:e=date.fromisoformat(f["end"]); fd=date.fromisoformat(f["filed"]); v=float(f["val"])
   except Exception:continue
   if v>0 and fd<=ad and e<=ad and (ad-e).days<=MAX_STALE_DAYS:q.append((e,fd,v,c))
  if q:
   e,fd,v,c=max(q,key=lambda x:(x[0],x[1])); return {"value":v,"concept":c,"method":"instant","end":e.isoformat(),"filed":fd.isoformat(),"staleness_days":(ad-e).days}
 return None
def share_fact(p,asof):
 x=instant(p,INSTANT_SHARES,asof)
 if x:return x
 ad=asof.date(); tax,c=WEIGHTED_SHARES; q=[]
 for f in units(p,tax,c):
  try:s=date.fromisoformat(f["start"]); e=date.fromisoformat(f["end"]); fd=date.fromisoformat(f["filed"]); v=float(f["val"])
  except Exception:continue
  dur=(e-s).days
  if v>0 and 60<=dur<=110 and fd<=ad and e<=ad and (ad-e).days<=MAX_STALE_DAYS:q.append((e,fd,-abs(dur-91),v,c,dur))
 if not q:return None
 e,fd,_near,v,c,dur=max(q,key=lambda x:(x[0],x[1],x[2])); return {"value":v,"concept":c,"method":"quarterly_weighted_average_basic","duration_days":dur,"end":e.isoformat(),"filed":fd.isoformat(),"staleness_days":(ad-e).days}
def month_ends():return list(pd.date_range("2019-01-31","2026-08-31",freq="ME"))+[pd.Timestamp("2026-09-12")]
def px_at(s,a):
 x=s.loc[s.index<=a]
 if x.empty:return None
 d=x.index[-1]; return None if (a-d).days>7 else (d,float(x.iloc[-1]))
def main():
 cm=ciks(); diag={}; rows={}
 for sym in SYMBOLS:
  ps=prices(sym); cf=get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cm[sym]:010d}.json"); time.sleep(.12); rr=[]; methods=set()
  for a in month_ends():
   px=px_at(ps,a); sh=share_fact(cf,a); eq=instant(cf,EQUITY,a)
   if not px or not sh or not eq:continue
   d,p=px; m=sh["value"]*p; b=eq["value"]/m if m>0 else float('nan')
   if not(math.isfinite(m) and math.isfinite(b) and 1e8<=m<=2e11 and .01<=b<=10):continue
   methods.add(sh["method"]); rr.append({"asof":a.date().isoformat(),"price_date":d.date().isoformat(),"raw_close":p,"shares":sh,"equity":eq,"market_cap":m,"book_to_market":b})
  rows[sym]=rr; vals=[r["book_to_market"] for r in rr]; diag[sym]={"eligible_months":len(rr),"first":rr[0]["asof"] if rr else None,"last":rr[-1]["asof"] if rr else None,"share_methods":sorted(methods),"btm_median":float(pd.Series(vals).median()) if vals else None,"btm_min":min(vals,default=None),"btm_max":max(vals,default=None)}
 gates={"all_dev_min_72_months":all(diag[s]["eligible_months"]>=72 for s in DEV),"dfh_min_48_months":diag[EXTERNAL]["eligible_months"]>=48,"all_symbols_covered":all(diag[s]["eligible_months"]>0 for s in SYMBOLS)}
 out={"schema":"public.homebuilder_pit_valuation_source_probe_r2.v1","experiment_id":"HOMEBUILDER-PIT-VALUATION-SOURCE-PROBE-R2","inherits_source_probe":"HOMEBUILDER-PIT-VALUATION-SOURCE-PROBE-R1","uncertainty_resolved":"whether a filed-at quarterly weighted-average basic-share fallback repairs source coverage for LEN and DFH without observing economic returns","economic_outcomes_examined":False,"contract":{"instant_shares_preferred":True,"fallback":"WeightedAverageNumberOfSharesOutstandingBasic, filed <= signal, 60-110 day period, latest end, max 200d stale","market_price":"raw contemporaneous close","equity":"deterministic StockholdersEquity fallback","source_sanity_only":"market cap $0.1b-$200b and B/M 0.01-10"},"diagnostics":diag,"gates":gates,"decision":"HOMEBUILDER_PIT_VALUATION_SOURCE_ADMITTED_R2" if all(gates.values()) else "HOMEBUILDER_PIT_VALUATION_SOURCE_REJECTED_R2","rows_by_symbol":rows,"authority":"SOURCE_CONTRACT_ONLY","live_trading_change":False}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print(json.dumps({"decision":out["decision"],"diagnostics":diag,"gates":gates},indent=2,sort_keys=True))
if __name__=="__main__":main()
