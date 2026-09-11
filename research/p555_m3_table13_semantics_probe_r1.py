from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

UA={"User-Agent":"XoticHaze Research xotichaze@users.noreply.github.com"}
BASE="https://www.census.gov/manufacturing/m3/historical_data/pressreleases/prel/{year}/{mon}{yy}prel.pdf"
SAMPLES=[(2012,"jan"),(2016,"jan"),(2020,"jan"),(2021,"dec"),(2024,"jul"),(2026,"jan")]


def extract(data:bytes)->str:
    exe=shutil.which("pdftotext")
    if not exe: raise RuntimeError("pdftotext missing")
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.pdf"; p.write_bytes(data)
        cp=subprocess.run([exe,"-layout",str(p),"-"],capture_output=True,text=True,timeout=90)
        if cp.returncode: raise RuntimeError(cp.stderr[-500:])
        return cp.stdout


def clean(s:str)->str:
    return re.sub(r"\s+"," ",s).strip()


def table_page(text:str, table_no:int, phrase:str)->dict:
    pages=text.split("\f")
    c=[]
    for idx,page in enumerate(pages,start=1):
        low=page.lower()
        if f"table {table_no}" in low and phrase in low:
            lines=page.splitlines()
            inds=[i for i,l in enumerate(lines) if "industrial machinery" in l.lower()]
            c.append({
                "page":idx,
                "header_excerpt":[clean(x) for x in lines[:40] if clean(x)],
                "industrial_rows":[clean(" ".join(lines[max(0,i-1):min(len(lines),i+2)])) for i in inds],
            })
    return {"candidate_count":len(c),"candidate_pages":c}


def release_date(text:str)->str|None:
    first=text.split("\f")[0]
    pats=[r"FOR RELEASE[^\n]*?([A-Z][A-Z]+\s+\d{1,2},\s+\d{4})",r"FOR RELEASE[^\n]*?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",r"([A-Z][A-Z]+\s+\d{1,2},\s+\d{4})",r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})"]
    for p in pats:
        m=re.search(p,first)
        if m:return m.group(1)
    return None


def main():
    rows=[]
    for year,mon in SAMPLES:
        url=BASE.format(year=year,mon=mon,yy=str(year)[2:])
        item={"year":year,"month":mon,"url":url}
        try:
            r=requests.get(url,headers=UA,timeout=(20,90)); item.update({"status":r.status_code,"bytes":len(r.content),"sha256":hashlib.sha256(r.content).hexdigest()}); r.raise_for_status()
            t=extract(r.content)
            item["release_date_text"]=release_date(t)
            item["table1"]=table_page(t,1,"shipments")
            item["table3"]=table_page(t,3,"unfilled orders")
            def one(tab): return tab["candidate_count"]==1 and len(tab["candidate_pages"][0]["industrial_rows"])>=1
            item["usable"]=one(item["table1"]) and one(item["table3"])
        except Exception as e:
            item["exception"]=repr(e); item["usable"]=False
        rows.append(item)
    usable=sum(bool(x.get("usable")) for x in rows)
    out={"schema":"research.p555_m3_table13_semantics_probe_r1","parent":"P555","decision":"TABLE13_SEMANTICS_STABLE" if usable==len(rows) else "TABLE13_SEMANTICS_NEEDS_REPAIR","usable":usable,"sample_count":len(rows),"samples":rows,"boundaries":{"scientific_alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p555_m3_table13_semantics_probe_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps(out,sort_keys=True))

if __name__=="__main__": main()
