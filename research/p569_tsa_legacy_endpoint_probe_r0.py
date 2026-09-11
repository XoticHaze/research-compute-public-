from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

URLS = [
    "https://www.tsa.gov/coronavirus/passenger-throughput",
    "https://www.tsa.gov/coronavirus/passenger-throughput?page=0",
    "https://www.tsa.gov/coronavirus/passenger-throughput?page=1",
]
UA={"User-Agent":"XoticHaze Research xotichaze@users.noreply.github.com"}


def inspect(url:str)->dict:
    r=requests.get(url,headers=UA,timeout=(15,60),allow_redirects=True)
    item={"url":url,"status":r.status_code,"final_url":r.url,"history":[{"status":x.status_code,"url":x.url,"location":x.headers.get("location")} for x in r.history],"bytes":len(r.content),"content_type":r.headers.get("content-type"),"last_modified":r.headers.get("last-modified"),"sha256":hashlib.sha256(r.content).hexdigest()}
    soup=BeautifulSoup(r.content,"html.parser")
    tables=[]
    for ti,t in enumerate(soup.select("table")):
        rows=[]
        for tr in t.select("tr")[:12]:
            cells=[c.get_text(" ",strip=True) for c in tr.find_all(["th","td"])]
            if cells: rows.append(cells)
        tables.append({"index":ti,"sample_rows":rows})
    item["tables"]=tables
    item["title"]=soup.title.get_text(" ",strip=True) if soup.title else None
    return item


def main():
    out={"schema":"research.p569_tsa_legacy_endpoint_probe_r0","parent":"P07","child":"P569","decision":"LEGACY_ENDPOINT_DIAGNOSTIC_ONLY","requests":[],"boundaries":{"alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
    for u in URLS:
        try: out["requests"].append(inspect(u))
        except Exception as exc: out["requests"].append({"url":u,"exception":repr(exc)})
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p569_tsa_legacy_endpoint_probe_r0.json").write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps(out,sort_keys=True))
if __name__=="__main__":main()
