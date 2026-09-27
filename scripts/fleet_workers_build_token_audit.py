from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"

def main() -> int:
    account=os.environ.get("CLOUDFLARE_ACCOUNT_ID","").strip()
    token=os.environ.get("CLOUDFLARE_API_TOKEN","").strip()
    if not account or not token:
        raise SystemExit("existing Cloudflare deployment binding missing")

    url=f"{API}/accounts/{account}/builds/tokens"
    req=Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/json",
        "User-Agent":"fleet-workers-build-token-audit-r1",
    })
    try:
        with urlopen(req,timeout=30) as response:
            raw=response.read()
            status=int(response.status)
    except HTTPError as exc:
        raw=exc.read()
        status=int(exc.code)

    try:
        node=json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        node={}

    rows=[]
    if status == 200 and node.get("success") is True and isinstance(node.get("result"),list):
        for item in node["result"]:
            if not isinstance(item,dict):
                continue
            rows.append({
                "build_token_name":str(item.get("build_token_name") or ""),
                "build_token_uuid":str(item.get("build_token_uuid") or ""),
                "cloudflare_token_id":str(item.get("cloudflare_token_id") or ""),
                "owner_type":str(item.get("owner_type") or ""),
            })

    receipt={
        "schema":"fleet.workers_build_token_audit.r1",
        "http_status":status,
        "success":status == 200 and node.get("success") is True,
        "tokens":rows,
        "read_only":True,
        "mutation_performed":False,
        "secrets_included":False,
    }
    out=Path("rendezvous/receipts/fleet-workers-build-token-audit-r1.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(receipt,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
