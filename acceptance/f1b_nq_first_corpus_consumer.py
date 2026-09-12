#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MM_PRODUCT_HEAD = "b03162cfcdfb6e82d0297a435e318f2ca5ff7647"
F1A_SOURCE_RUN_ID = 34684071280
F1A_ACCEPTANCE_RUN_ID = 34684564957
STAGING_ARTIFACT_ID = 10294324888
RECEIPT_ARTIFACT_ID = 10294544510
ROOT = "NQ"
MONTHS = ["200003", "200006"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def load_receipt(root: Path) -> tuple[Path, dict[str, Any]]:
    for path in sorted(root.rglob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("staged_files"), list):
            return path, obj
    raise RuntimeError("released F1a acceptance receipt with staged_files not found")


def resolve_staged(root: Path, rel: str) -> Path:
    direct = root / rel
    if direct.is_file():
        return direct
    rel_norm = rel.replace("\\", "/").lstrip("./")
    matches = [p for p in root.rglob("*") if p.is_file() and p.as_posix().endswith(rel_norm)]
    if len(matches) != 1:
        raise RuntimeError(f"cannot resolve staged path {rel!r}; matches={len(matches)}")
    return matches[0]


def main() -> int:
    receipt_path, receipt = load_receipt(Path("input/receipt"))
    if receipt.get("acceptance") != "MM_LOCAL_DATED_CACHE_COMPATIBLE_STAGING_WITH_SOURCE_QUARANTINE":
        raise RuntimeError("unexpected F1a acceptance state")
    if str(receipt.get("source_run_id")) != str(F1A_SOURCE_RUN_ID):
        raise RuntimeError("source run identity mismatch")
    if receipt.get("continuous_series_constructed") is not False or receipt.get("roll_cutoff_selected") is not False:
        raise RuntimeError("released staging exceeded dated-cache authority")

    selected = []
    for item in receipt["staged_files"]:
        if not isinstance(item, dict) or str(item.get("root", "")).upper() != ROOT:
            continue
        if str(item.get("contract_month", "")) in MONTHS:
            selected.append(item)
    selected.sort(key=lambda x: str(x.get("contract_month")))
    if [str(x.get("contract_month")) for x in selected] != MONTHS:
        raise RuntimeError("exact first-two NQ months not found in released staging")

    contracts = []
    for item in selected:
        rel = str(item.get("target_path") or "")
        staged = resolve_staged(Path("input/staging"), rel)
        actual = sha256(staged)
        expected = str(item.get("target_sha256") or "").lower()
        if actual != expected:
            raise RuntimeError(f"staged hash mismatch for {item.get('contract_month')}: {actual} != {expected}")
        contracts.append({
            "root": ROOT,
            "contract_month": str(item["contract_month"]),
            "expected_source_sha256": actual,
            "f1a_source_sha256": str(item.get("source_sha256") or ""),
        })

    manifest_projection = {
        "schema": "mm.admitted_futures_dated_corpus_manifest.v1",
        "root": ROOT,
        "source_timeframe": "1Day",
        "target_timeframe": "1Day",
        "contracts": [{
            "root": x["root"],
            "contract_month": x["contract_month"],
            "expected_source_sha256": x["expected_source_sha256"],
        } for x in contracts],
    }
    receipt_out = {
        "schema": "public.mm_f1b_nq_first_corpus_consumer_receipt.v1",
        "status": "PASS",
        "authority": "RELEASE_FIRST_CONSUMER_ONLY",
        "mm_product_head": MM_PRODUCT_HEAD,
        "f1a_source_run_id": F1A_SOURCE_RUN_ID,
        "f1a_acceptance_run_id": F1A_ACCEPTANCE_RUN_ID,
        "staging_artifact_id": STAGING_ARTIFACT_ID,
        "acceptance_receipt_artifact_id": RECEIPT_ARTIFACT_ID,
        "acceptance_receipt_sha256": sha256(receipt_path),
        "root": ROOT,
        "contract_count": len(contracts),
        "contracts": contracts,
        "manifest_projection_sha256": canon(manifest_projection),
        "actual_released_bytes_verified": True,
        "continuous_series_constructed": False,
        "roll_cutoff_selected": False,
        "back_adjustment": False,
        "strategy_spec_mutation": False,
        "runtime_authority_change": False,
        "broker_submission": False,
        "live_trading_change": False,
    }
    Path("f1b-nq-first-corpus-consumer-receipt.json").write_text(
        json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt_out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
