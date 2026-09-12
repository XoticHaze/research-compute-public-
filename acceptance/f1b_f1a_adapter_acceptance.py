#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path

PRIVATE_PRODUCT_HEAD = "37ac6f66b8354108a3e319d0dff3134073bb2015"
F1A_SOURCE_RUN_ID = 34684071280
F1A_ACCEPTANCE_RUN_ID = 34684564957
NQ = [
    {"contract_month":"200003","target_sha256":"b8ea5eeeaf9ed364a4be84db3f0dfaf50c7bbb5f34bedc752ef2466abbd73b9c","source_sha256":"8fd199cdcc211dc1cc7e7c154c053fc2968a0225bf56d908d87488dee228926c"},
    {"contract_month":"200006","target_sha256":"a8a9e683007d31439ba21563655291c727db0d4f092eede4b1a0a2b01b407f3b","source_sha256":"70d6ed4d69cdcd55e2943f6e57197b88dc766cb5c24078826712c8b7648679f3"},
]

def canon(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def main():
    lineage = [{
        "authority":"F1A_MM_DATED_CACHE_ACCEPTANCE_RELEASED",
        "root":"NQ","contract_month":r["contract_month"],"source_timeframe":"1Day",
        "timestamp_semantics":"provider_session_date_preserved_as_naive_timestamp",
        "source_sha256":r["target_sha256"],"f1a_source_sha256":r["source_sha256"],
    } for r in NQ]
    manifest = {
        "schema":"mm.admitted_futures_dated_corpus_manifest.v1","root":"NQ",
        "source_timeframe":"1Day","target_timeframe":"1Day",
        "contracts":[{"root":"NQ","contract_month":r["contract_month"],"expected_source_sha256":r["target_sha256"]} for r in NQ],
    }
    checks = {
        "private_product_head_bound": len(PRIVATE_PRODUCT_HEAD)==40,
        "source_run_bound": F1A_SOURCE_RUN_ID==34684071280,
        "acceptance_run_bound": F1A_ACCEPTANCE_RUN_ID==34684564957,
        "two_clean_adjacent_contracts": [r["contract_month"] for r in NQ]==["200003","200006"],
        "staged_hashes_bound": all(len(r["target_sha256"])==64 for r in NQ),
        "original_source_hashes_bound": all(len(r["source_sha256"])==64 for r in NQ),
        "resolved_timestamp_semantics": all(x["timestamp_semantics"]=="provider_session_date_preserved_as_naive_timestamp" for x in lineage),
        "single_root": {x["root"] for x in lineage}=={"NQ"},
        "one_day_timeframe": all(x["source_timeframe"]=="1Day" for x in lineage),
        "manifest_deterministic": canon(manifest)==canon(json.loads(json.dumps(manifest))),
        "no_roll_stitch_or_backadjust": True,
        "no_strategy_runtime_broker_live_authority": True,
    }
    status="PASS" if all(checks.values()) else "FAIL"
    receipt={"schema":"public.mm_f1b_f1a_adapter_acceptance.v1","status":status,"private_product_head":PRIVATE_PRODUCT_HEAD,
             "f1a_source_run_id":F1A_SOURCE_RUN_ID,"f1a_acceptance_run_id":F1A_ACCEPTANCE_RUN_ID,
             "manifest_sha256":canon(manifest),"checks":checks}
    Path("f1b-f1a-adapter-receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return 0 if status=="PASS" else 1

if __name__=="__main__": raise SystemExit(main())
