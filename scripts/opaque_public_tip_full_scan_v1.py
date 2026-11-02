"""Full CURRENT-TIP public exchange audit, values and filenames NEVER printed.

Audits all Git blobs at the *public* rendezvous-exchange branch tip via a single
streaming git cat-file. Git history, clones, CI logs/artifacts and escaped secrets
outside that ref are NOT covered. This tool only emits aggregate counters.
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from threading import Thread

REF = "refs/remotes/origin/rendezvous-exchange"
MAX_ITEMS = 20000
MAX_BYTES = 200_000_000
MAX_BLOB = 20_000_000
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 10000
FORBIDDEN = frozenset({
    "plaintext_sha256", "plaintext_digest", "source_sha256", "payload_sha256",
    "private_digest", "source_repo", "source_ref", "source_root",
    "source_path", "private_source", "private_repository",
    "authority", "harness", "business_identifier", "private_endpoint",
    "github_token", "api_key", "private_key", "access_token",
})

class AuditRejected(RuntimeError):
    pass

def _unique_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise AuditRejected("duplicate_keys")
        out[k] = v
    return out

def _nested_key_flags(node):
    stack = [(node,0)]
    checked = 0
    found = False
    while stack:
        val, depth = stack.pop()
        checked += 1
        if depth > MAX_JSON_DEPTH or checked > MAX_JSON_NODES:
            return None
        if isinstance(val, dict):
            if any(isinstance(k,str) and k.lower() in FORBIDDEN for k in val):
                found = True
            stack.extend((v,depth+1) for v in val.values() if isinstance(v,(list,dict)))
        elif isinstance(val,list):
            stack.extend((v,depth+1) for v in val if isinstance(v,(list,dict)))
    return found

def classify(path: str, blob: bytes) -> dict[str,int]:
    """Safe aggregate inspection. No content or paths returned."""
    out = Counter()
    if not path.lower().endswith(".json"):
        out["non_json_extension"] += 1
        return dict(out)
    out["json_extension"] += 1
    try:
        node = json.loads(blob.decode("utf-8"),object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError, AuditRejected):
        out["json_parse_or_duplicate_failure"] += 1
        return dict(out)
    if not isinstance(node, dict):
        out["json_non_object"] += 1
        return dict(out)
    out["json_object"] += 1
    if any(isinstance(k,str) and k.lower() in FORBIDDEN for k in node):
        out["forbidden_outer_keys"] += 1
    nested = _nested_key_flags(list(node.values()))
    if nested is None:
        out["nested_scan_incomplete"] += 1
    elif nested:
        out["forbidden_nested_keys"] += 1
    if set(node) == {"schema","run_id","direction","recipient_key_id",
                     "sender_public_b64","nonce_b64","ciphertext_b64",
                     "ciphertext_sha256"} and node.get("schema") in (
                         "opaque-capsule-v1","opaque-capsule-p256-aesgcm-v1"):
        out["canonical_outer_shape"] += 1
    else:
        out["noncanonical_json_outer_shape"] += 1
    return dict(out)

def _catalog(git_dir:Path):
    proc = subprocess.run(["git","-C",str(git_dir),"ls-tree","-r","-z",
                           "--long",REF], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,check=True,timeout=60)
    chunks = proc.stdout.split(b"\x00")
    entries = []
    total=0
    for raw in chunks:
        if not raw:
            continue
        try:
            meta,path = raw.split(b"\t",1)
            mode,kind,sha,size = meta.split(b" ")
            if kind != b"blob" or not re.fullmatch(rb"[0-9a-f]{40}",sha):
                raise AuditRejected("invalid_tree_object")
            n=int(size)
            if n<0 or n>MAX_BLOB:
                raise AuditRejected("blob_size_limit")
            total+=n
            entries.append((sha.decode("ascii"),n,path.decode("utf-8","replace")))
        except (ValueError,UnicodeError):
            raise AuditRejected("malformed_tree") from None
        if len(entries)>MAX_ITEMS or total>MAX_BYTES:
            raise AuditRejected("tip_inventory_bounds")
    return entries,total

def _read_exact(src, n:int) -> bytes:
    result=bytearray()
    while len(result)<n:
        piece=src.read(min(n-len(result),65536))
        if not piece:
            raise AuditRejected("truncated_batch")
        result.extend(piece)
    return bytes(result)

def live_scan(git_dir:Path) -> dict:
    entries,total=_catalog(git_dir)
    if not entries:
        raise AuditRejected("empty_tip")
    proc=subprocess.Popen(["git","-C",str(git_dir),"cat-file","--batch"],
                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    writing_errors=[]
    def writer():
        try:
            for sha,_,_ in entries:
                proc.stdin.write((sha+"\n").encode("ascii"))
            proc.stdin.close()
        except Exception:
            writing_errors.append(True)
    thread=Thread(target=writer,daemon=True)
    thread.start()
    counts=Counter()
    try:
        for sha, size, path in entries:
            header=proc.stdout.readline()
            if header!=f"{sha} blob {size}\n".encode("ascii"):
                raise AuditRejected("batch_identity_or_size_mismatch")
            blob=_read_exact(proc.stdout,size)
            if _read_exact(proc.stdout,1)!=b"\n":
                raise AuditRejected("batch_delimiter")
            counts.update(classify(path,blob))
        thread.join(timeout=30)
        if thread.is_alive() or writing_errors:
            raise AuditRejected("batch_writer_failed")
        if proc.wait(timeout=45)!=0:
            raise AuditRejected("git_batch_failed")
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        thread.join(timeout=1)
    return {
        "schema":"opaque-public-current-tip-full-redacted-inventory-v1",
        "status":"TIP_INVENTORY_ONLY_NOT_STORAGE_CONFIDENTIALITY_CERTIFIED",
        "public_branch_tip_only":True,
        "history_logs_artifacts_audited":False,
        "privacy_certified":False,
        "blob_files":len(entries),
        "git_blob_bytes":total,
        "aggregate_counts":dict(sorted(counts.items())),
    }

def main() -> int:
    try:
        report=live_scan(Path.cwd())
    except Exception:
        print(json.dumps({"schema":"opaque-public-current-tip-full-redacted-inventory-v1",
                          "status":"FAIL_CLOSED","privacy_certified":False},sort_keys=True))
        return 1
    print(json.dumps(report,sort_keys=True,separators=(",",":")))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
