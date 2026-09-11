from __future__ import annotations
import json,re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
BASE="https://www.tsa.gov/foia/readingroom"
UA={"User-Agent":"XoticHaze Research xotichaze@users.noreply.github.com"}

def main():
 s=requests.Session(); links={}; pages=[]
 for p in range(0,80):
  u=BASE+("" if p==0 else f"?page={p}"); r=s.get(u,headers=UA,timeout=(15,60)); item={"page":p,"status":r.status_code,"bytes":len(r.content)}
  if r.status_code!=200: pages.append(item); break
  soup=BeautifulSoup(r.content,"html.parser"); found=0
  for a in soup.find_all("a",href=True):
   text=a.get_text(" ",strip=True); href=a["href"]
   if "throughput data" in text.lower() and href.lower().endswith(".pdf"):
    full=urljoin("https://www.tsa.gov",href); links[full]=text; found+=1
  item["throughput_links"]=found; pages.append(item)
  if p>0 and found==0: break
 out={"schema":"research.p569_tsa_foia_catalog_r2","parent":"P07","child":"P569_TSA_PHYSICAL_DEMAND","pages_scanned":len(pages),"pdf_count":len(links),"pages":pages,"pdfs":[{"url":u,"text":t} for u,t in sorted(links.items())],"decision":"ARCHIVE_CATALOG_ONLY","boundaries":{"alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
 Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p569_tsa_foia_catalog_r2.json").write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({"pages_scanned":len(pages),"pdf_count":len(links),"first":out["pdfs"][:2],"last":out["pdfs"][-2:]},sort_keys=True))
if __name__=="__main__":main()
