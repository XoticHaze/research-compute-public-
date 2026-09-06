from __future__ import annotations

"""Source-only point-in-time SEC fundamental coverage preflight."""
import json, os, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
OUT=Path("semiconductor_sec_fundamental_preflight_20260906.json")
SYMBOLS=("AMAT","APH","KLAC","LRCX","TXN","NXPI","ADI")
CIKS={"AMAT":"0000006951","APH":"0000820313","KLAC":"0000319201","LRCX":"0000707549","TXN":"0000097476","NXPI":"0001413447","ADI":"0000006281"}
START_FILED,CUTOFF_FILED="2014-01-01","2026-09-03"; FORMS={"10-Q","10-K","20-F","40-F"}; MIN_DISTINCT_FILINGS,MIN_FILED_YEARS=16,8
USER_AGENT="XoticHaze research-compute-public- 152584286+XoticHaze@users.noreply.github.com"
BASE=os.environ.get("SEC_COMPANYFACTS_BASE","https://data.sec.gov/api/xbrl/companyfacts").rstrip("/")
CANDIDATES={"revenue":(("us-gaap","RevenueFromContractWithCustomerExcludingAssessedTax"),("us-gaap","SalesRevenueNet"),("us-gaap","Revenues"),("ifrs-full","Revenue")),"gross_profit":(("us-gaap","GrossProfit"),("ifrs-full","GrossProfit")),"operating_income":(("us-gaap","OperatingIncomeLoss"),("ifrs-full","ProfitLossFromOperatingActivities")),"assets":(("us-gaap","Assets"),("ifrs-full","Assets")),"inventory":(("us-gaap","InventoryNet"),("us-gaap","InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"),("ifrs-full","Inventories")),"cash":(("us-gaap","CashAndCashEquivalentsAtCarryingValue"),("us-gaap","CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),("ifrs-full","CashAndCashEquivalents"))}
def get_json(url):
 last=None
 for attempt in range(3):
  try:
   with urlopen(Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"}),timeout=30) as r:return json.loads(r.read().decode())
  except Exception as exc:
   last=exc
   if attempt<2:time.sleep(1+attempt)
 raise RuntimeError(f"GET failed after 3 attempts: {url}: {last}")
def rows(facts,ns,concept):
 fact=facts.get("facts",{}).get(ns,{}).get(concept)
 if not fact:return []
 return [r for r in fact.get("units",{}).get("USD",[]) if START_FILED<=str(r.get("filed") or "")<=CUTOFF_FILED and str(r.get("form") or "") in FORMS and isinstance(r.get("val"),(int,float))]
def summary(rs):
 filings={(str(r.get("filed")),str(r.get("accn") or "")) for r in rs if r.get("filed")}; dates=sorted({d for d,_ in filings}); years={d[:4] for d in dates}
 return {"rows":len(rs),"distinct_filings":len(filings),"filed_years":len(years),"first_filed":dates[0] if dates else None,"last_filed":dates[-1] if dates else None}
def pick(facts,candidates):
 scored=[{"namespace":ns,"concept":c,**summary(rows(facts,ns,c))} for ns,c in candidates]; scored.sort(key=lambda x:(x["distinct_filings"],x["filed_years"],x["rows"]),reverse=True); best=dict(scored[0]); best["eligible"]=best["distinct_filings"]>=MIN_DISTINCT_FILINGS and best["filed_years"]>=MIN_FILED_YEARS; return best,scored
def main():
 coverage={}; ok=True
 for s in SYMBOLS:
  facts=get_json(f"{BASE}/CIK{CIKS[s]}.json"); cats={}
  for cat,cands in CANDIDATES.items():
   best,scored=pick(facts,cands); cats[cat]={"selected":best,"candidates":scored}; ok &= bool(best["eligible"])
  coverage[s]={"cik":CIKS[s],"entity_name":facts.get("entityName"),"categories":cats}; time.sleep(.15)
 status="PASS" if ok else "FAIL"; out={"schema":"public_compute.semiconductor_sec_fundamental_preflight.v1","generated_at":datetime.now(timezone.utc).isoformat(),"development_universe":list(SYMBOLS),"pinned_ciks":CIKS,"source":"SEC Company Facts","companyfacts_base":BASE,"filing_time_authority":"SEC filed date; later-filed restatements are unavailable to earlier signal dates","allowed_forms":sorted(FORMS),"filed_window":{"start":START_FILED,"cutoff":CUTOFF_FILED},"semantic_categories_frozen_before_model_outcomes":list(CANDIDATES),"coverage":coverage,"status":status,"targets_computed":False,"model_executed":False,"external_semiconductor_holdouts_loaded":False,"research_only":True,"promotion_authority":False,"runtime_mutation":False,"broker_action":False,"live_trading_change":False}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print("SEMICONDUCTOR_SEC_FUNDAMENTAL_PREFLIGHT="+json.dumps(out,sort_keys=True));
 if status!="PASS":raise SystemExit(2)
if __name__=="__main__":
 try:main()
 except SystemExit:raise
 except Exception as exc:
  failure={"schema":"public_compute.semiconductor_sec_fundamental_preflight.v1","generated_at":datetime.now(timezone.utc).isoformat(),"development_universe":list(SYMBOLS),"pinned_ciks":CIKS,"companyfacts_base":BASE,"status":"TRANSPORT_FAILURE","error":str(exc),"targets_computed":False,"model_executed":False,"external_semiconductor_holdouts_loaded":False,"research_only":True,"promotion_authority":False,"runtime_mutation":False,"broker_action":False,"live_trading_change":False}; OUT.write_text(json.dumps(failure,indent=2,sort_keys=True)+"\n"); print("SEMICONDUCTOR_SEC_FUNDAMENTAL_PREFLIGHT="+json.dumps(failure,sort_keys=True)); raise
