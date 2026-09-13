#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from urllib.request import Request, urlopen

TARGETS = {"LEN": 920760, "DFH": 1825088}
OUT = Path("research/results/homebuilder_pit_share_concept_audit_r1.json")
UA = "research-compute share-concept-audit/1.0 contact@example.com"

def get(cik):
    req = Request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers={"User-Agent": UA})
    with urlopen(req, timeout=45) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))

def main():
    result = {"schema":"public.homebuilder_pit_share_concept_audit_r1.v1","experiment_id":"HOMEBUILDER-PIT-SHARE-CONCEPT-AUDIT-R1","economic_outcomes_examined":False,"symbols":{}}
    for symbol,cik in TARGETS.items():
        p=get(cik); rows=[]
        for taxonomy, facts in sorted(p.get("facts",{}).items()):
            for concept,node in sorted(facts.items()):
                low=concept.lower()
                if "share" not in low and "stock" not in low and "float" not in low:
                    continue
                units=node.get("units",{})
                for unit,vals in sorted(units.items()):
                    usable=[]
                    for f in vals:
                        if f.get("val") is None or not f.get("filed") or not f.get("end"):
                            continue
                        usable.append(f)
                    if not usable:
                        continue
                    latest=max(usable,key=lambda f:(f.get("filed",""),f.get("end","")))
                    rows.append({"taxonomy":taxonomy,"concept":concept,"label":node.get("label"),"unit":unit,"count":len(usable),"latest_end":latest.get("end"),"latest_filed":latest.get("filed"),"latest_form":latest.get("form"),"latest_value":latest.get("val")})
        result["symbols"][symbol]=rows
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
if __name__=="__main__": main()
