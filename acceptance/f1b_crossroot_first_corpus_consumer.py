#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MM_PRODUCT_HEAD = "c1ea7dc3b94924305bf39631eca7fee0babf74d7"
F1A_SOURCE_RUN_ID = 34684071280
F1A_ACCEPTANCE_RUN_ID = 34684564957
STAGING_ARTIFACT_ID = 10294324888
RECEIPT_ARTIFACT_ID = 10294544510
ROOTS = ["ES", "NG", "ZS", "6E"]
CONTRACTS_PER_ROOT = 2


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


def select_contracts(receipt: dict[str, Any], root: str) -> list[dict[str, Any]]:
    rows = [
        item for item in receipt["staged_files"]
        if isinstance(item, dict) and str(item.get("root", "")).upper() == root
    ]
    rows.sort(key=lambda x: str(x.get("contract_month", "")))
    if len(rows) < CONTRACTS_PER_ROOT:
        raise RuntimeError(f"{root}: expected >= {CONTRACTS_PER_ROOT} clean staged contracts, got {len(rows)}")
    chosen = rows[:CONTRACTS_PER_ROOT]
    months = [str(x.get("contract_month", "")) for x in chosen]
    if len(months) != len(set(months)) or any(len(m) != 6 or not m.isdigit() for m in months):
        raise RuntimeError(f"{root}: invalid/duplicate contract months {months}")
    return chosen


def main() -> int:
    receipt_path, receipt = load_receipt(Path("input/receipt"))
    if receipt.get("acceptance") != "MM_LOCAL_DATED_CACHE_COMPATIBLE_STAGING_WITH_SOURCE_QUARANTINE":
        raise RuntimeError("unexpected F1a acceptance state")
    if str(receipt.get("source_run_id")) != str(F1A_SOURCE_RUN_ID):
        raise RuntimeError("source run identity mismatch")
    if receipt.get("continuous_series_constructed") is not False or receipt.get("roll_cutoff_selected") is not False:
        raise RuntimeError("released staging exceeded dated-cache authority")

    roots_out: list[dict[str, Any]] = []
    all_manifest_contracts: list[dict[str, str]] = []
    for root in ROOTS:
        contracts_out: list[dict[str, str]] = []
        for item in select_contracts(receipt, root):
            rel = str(item.get("target_path") or "")
            staged = resolve_staged(Path("input/staging"), rel)
            actual = sha256(staged)
            expected = str(item.get("target_sha256") or "").lower()
            if not expected or actual != expected:
                raise RuntimeError(f"{root} {item.get('contract_month')}: staged hash mismatch")
            contract = {
                "root": root,
                "contract_month": str(item["contract_month"]),
                "expected_source_sha256": actual,
                "f1a_source_sha256": str(item.get("source_sha256") or ""),
            }
            contracts_out.append(contract)
            all_manifest_contracts.append({k: contract[k] for k in ("root", "contract_month", "expected_source_sha256")})
        roots_out.append({"root": root, "contract_count": len(contracts_out), "contracts": contracts_out})

    manifest_projection = {
        "schema": "mm.admitted_futures_dated_corpus_manifest.v1",
        "source_timeframe": "1Day",
        "target_timeframe": "1Day",
        "roots": ROOTS,
        "contracts": all_manifest_contracts,
    }
    receipt_out = {
        "schema": "public.mm_f1b_crossroot_first_corpus_consumer_receipt.v1",
        "status": "PASS",
        "authority": "RELEASE_CROSSROOT_FIRST_CONSUMER_ONLY",
        "mm_product_head": MM_PRODUCT_HEAD,
        "f1a_source_run_id": F1A_SOURCE_RUN_ID,
        "f1a_acceptance_run_id": F1A_ACCEPTANCE_RUN_ID,
        "staging_artifact_id": STAGING_ARTIFACT_ID,
        "acceptance_receipt_artifact_id": RECEIPT_ARTIFACT_ID,
        "acceptance_receipt_sha256": sha256(receipt_path),
        "roots": roots_out,
        "root_count": len(roots_out),
        "contract_count": len(all_manifest_contracts),
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
    Path("f1b-crossroot-first-corpus-consumer-receipt.json").write_text(
        json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt_out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
