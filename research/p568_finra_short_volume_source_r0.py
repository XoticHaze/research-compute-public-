from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests

UA={"User-Agent":"XoticHaze Research xotichaze@users.noreply.github.com"}
API="https://api.finra.org/data/group/otcMarket/name/regShoDaily?limit=10"
DATES=["20260910","20240102","20200102","20150102"]
SYMBOLS={"AMAT","APH","CAT","JPM","XOM","NVDA","SPY"}


def inspect_text(content:bytes)->dict:
    text=content.decode("utf-8",errors="replace")
    lines=[x for x in text.splitlines() if x.strip()]
    header=lines[0] if lines else None
    selected=[]
    for line in lines[1:-1] if len(lines)>2 else []:
        parts=line.split("|")
        if len(parts)>=5 and parts[1] in SYMBOLS:
            selected.append(line[:300])
    return {"line_count":len(lines),"header":header,"trailer":lines[-1] if lines else None,"selected_rows":selected[:30]}


def main():
    s=requests.Session()
    out={
        "schema":"research.p568_finra_short_volume_source_r0",
        "parent":"P05",
        "child":"P568",
        "decision":"SOURCE_SHAPE_ONLY",
        "api":{},
        "daily_files":{},
        "boundaries":{"alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False},
    }
    try:
        r=s.get(API,headers=UA,timeout=(15,60))
        out["api"]={"url":API,"status":r.status_code,"content_type":r.headers.get("content-type"),"bytes":len(r.content),"sha256":hashlib.sha256(r.content).hexdigest(),"body_prefix":r.text[:1200]}
    except Exception as exc:
        out["api"]={"url":API,"exception":repr(exc)}
    for d in DATES:
        url=f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
        item={"url":url}
        try:
            r=s.get(url,headers=UA,timeout=(15,60))
            item.update({"status":r.status_code,"content_type":r.headers.get("content-type"),"last_modified":r.headers.get("last-modified"),"bytes":len(r.content),"sha256":hashlib.sha256(r.content).hexdigest()})
            if r.status_code==200:
                item["shape"]=inspect_text(r.content)
        except Exception as exc:
            item["exception"]=repr(exc)
        out["daily_files"][d]=item
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p568_finra_short_volume_source_r0.json").write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps(out,sort_keys=True))

if __name__=="__main__":main()
