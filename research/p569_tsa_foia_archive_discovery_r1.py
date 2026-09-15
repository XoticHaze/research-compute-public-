from __future__ import annotations
import hashlib,json,re
from pathlib import Path
import requests
from bs4 import BeautifulSoup
UA={"User-Agent":"XoticHaze Research xotichaze@users.noreply.github.com"}
QUERIES=[
 "https://www.tsa.gov/sites/default/files/foia-readingroom/tsa-total-throughput-data-december-29-2024-to-january-4-2025.pdf",
 "https://www.tsa.gov/sites/default/files/foia-readingroom/tsa-throughput-data-to-june-29-2025-to-july-5-2025.pdf",
]
SEARCH="https://www.tsa.gov/foia/readingroom"

def main():
 s=requests.Session(); out={"schema":"research.p569_tsa_foia_archive_discovery_r1","parent":"P07","child":"P569_TSA_PHYSICAL_DEMAND","direct":{},"reading_room":{},"decision":"SOURCE_DISCOVERY_ONLY","boundaries":{"alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
 for u in QUERIES:
  r=s.get(u,headers=UA,timeout=(15,90)); out["direct"][u]={"status":r.status_code,"bytes":len(r.content),"content_type":r.headers.get("content-type"),"last_modified":r.headers.get("last-modified"),"sha256":hashlib.sha256(r.content).hexdigest() if r.status_code==200 else None,"pdf_magic":r.content[:4]==b"%PDF"}
 r=s.get(SEARCH,headers=UA,timeout=(15,90)); item={"status":r.status_code,"bytes":len(r.content),"content_type":r.headers.get("content-type")}
 if r.status_code==200:
  soup=BeautifulSoup(r.content,"html.parser"); links=[]
  for a in soup.find_all("a",href=True):
   href=a["href"]; text=a.get_text(" ",strip=True)
   if "throughput" in (href+" "+text).lower(): links.append({"text":text[:160],"href":href})
  item["throughput_links"]=links[:100]; item["throughput_link_count"]=len(links)
 out["reading_room"]=item
 Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p569_tsa_foia_archive_discovery_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=="__main__":main()
