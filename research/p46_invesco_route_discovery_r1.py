from __future__ import annotations
import json, re, urllib.parse, urllib.request
from pathlib import Path

PAGES={
  "QQQ":"https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=investors&productId=QQQ&ticker=QQQ",
  "DBC":"https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=investors&productId=DBC&ticker=DBC",
}
PATTERNS=("xls","xlsx","csv","download","histor","nav","performance","product-data","api/")

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 CC-Market-Research/1.0"})
    with urllib.request.urlopen(req,timeout=45) as r:
        body=r.read().decode("utf-8","ignore")
        return r.status,r.geturl(),body

def candidates(base,html):
    vals=set(re.findall(r'''(?:href|src)=["']([^"']+)["']''',html,re.I))
    vals.update(re.findall(r'''https?://[^"'<>\\\s]+''',html,re.I))
    out=[]
    for x in vals:
        u=urllib.parse.urljoin(base,x.replace("&amp;","&"))
        low=u.lower()
        if any(p in low for p in PATTERNS): out.append(u)
    return sorted(set(out))

def main():
    out={"schema":"research.p46_invesco_route_discovery_r1","parent":"P46","purpose":"discover issuer-owned machine-readable historical data routes for unresolved QQQ and DBC without using third-party price history","pages":{}}
    for ticker,url in PAGES.items():
        try:
            status,final,html=fetch(url)
            hits=candidates(final,html)
            out["pages"][ticker]={"status":status,"final_url":final,"html_bytes":len(html.encode()),"candidate_count":len(hits),"candidates":hits[:200]}
        except Exception as e:
            out["pages"][ticker]={"error":repr(e)}
    out["decision"]="CANDIDATE_ROUTES_DISCOVERED" if any(v.get("candidate_count",0)>0 for v in out["pages"].values()) else "STATIC_HTML_ROUTE_DISCOVERY_EMPTY"
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p46_invesco_route_discovery_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps(out,sort_keys=True))

if __name__=="__main__": main()
