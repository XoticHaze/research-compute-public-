from __future__ import annotations
import json
from datetime import date,timedelta
from pathlib import Path
import requests
UA={"User-Agent":"XoticHaze Research xotichaze@users.noreply.github.com"}; ROOT="https://www.tsa.gov/sites/default/files/foia-readingroom/"
def fmt(d): return f"{d.strftime('%B').lower()}-{d.day}-{d.year}"
def candidates(a,b):
 x=f"{fmt(a)}-to-{fmt(b)}.pdf"
 return [f"tsa-throughput-data-to-{x}",f"tsa-throughput-data-{x}",f"tsa-total-throughput-data-{x}",f"tsa-total-throughput-data-to-{x}"]
def main():
 s=requests.Session(); found=[]; misses=0
 d=date(2024,1,7)
 while d<=date(2025,12,28):
  e=d+timedelta(days=6); hit=None
  for slug in candidates(d,e):
   u=ROOT+slug
   try:
    r=s.head(u,headers=UA,timeout=(8,20),allow_redirects=True)
    if r.status_code==200 and "pdf" in (r.headers.get("content-type") or "").lower(): hit={"start":str(d),"end":str(e),"url":u,"bytes":r.headers.get("content-length"),"last_modified":r.headers.get("last-modified")}; break
   except Exception: pass
  if hit: found.append(hit)
  else: misses+=1
  d+=timedelta(days=7)
 out={"schema":"research.p569_tsa_historical_slug_probe_r3","parent":"P07","child":"P569_TSA_PHYSICAL_DEMAND","weeks_found":len(found),"weeks_missed":misses,"first":found[:5],"last":found[-5:],"found":found,"decision":"HISTORICAL_URL_DISCOVERY_ONLY","boundaries":{"alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
 Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p569_tsa_historical_slug_probe_r3.json").write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({k:out[k] for k in ("weeks_found","weeks_missed","first","last")},sort_keys=True))
if __name__=="__main__":main()
