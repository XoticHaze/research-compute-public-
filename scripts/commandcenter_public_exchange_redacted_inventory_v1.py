"""Read-only, value-redacting public exchange inventory for CommandCenter #901.

No GitHub mutation, no private-key access, no file paths/contents or digest
values in output. Snapshot accounts for the CURRENT GIT TIP ONLY and does not
certify full storage privacy, prior Git history, clones, artifacts or R2.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import urllib.error
import urllib.request

REPO = "XoticHaze/research-compute-public-"
REF = "rendezvous-exchange"
CATEGORY = {
    "rendezvous/returns/": "returns",
    "rendezvous/responses/": "responses",
    "rendezvous/recipients/": "recipients",
    "rendezvous/receipts/": "receipts",
    "rendezvous/producer-requests/": "producer_requests",
    "rendezvous/proof-chunks/": "proof_chunks",
    "rendezvous/diagnostics/": "diagnostics",
}
FORBIDDEN_OUTER = frozenset({
    "plaintext_sha256", "plaintext_digest", "source_sha256",
    "payload_sha256", "authority", "harness", "private_digest",
})
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MAX_TREE_BYTES = 12_000_000
MAX_SAMPLE_BYTES = 150_000
MAX_TOTAL_SAMPLES = 24
MAX_NESTED_NODES = 4096
MAX_NESTED_DEPTH = 16


class AuditRejected(RuntimeError):
    pass


def _request(url: str, token: str, *, max_bytes: int) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cc-public-privacy-inventory",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=35) as response:
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AuditRejected("observation_size_exceeded")
    return content


def _live_tree(token: str) -> dict:
    raw = _request(
        f"https://api.github.com/repos/{REPO}/git/trees/{REF}?recursive=1",
        token, max_bytes=MAX_TREE_BYTES,
    )
    return json.loads(raw)


def _live_blob(token: str, sha: str) -> bytes:
    if not SHA40.fullmatch(sha):
        raise AuditRejected("blob_identity_rejected")
    node = json.loads(_request(
        f"https://api.github.com/repos/{REPO}/git/blobs/{sha}",
        token, max_bytes=MAX_SAMPLE_BYTES * 2,
    ))
    if not isinstance(node, dict) or node.get("encoding") != "base64":
        raise AuditRejected("blob_encoding_rejected")
    try:
        raw = base64.b64decode(node["content"], validate=False)
    except (KeyError, TypeError, binascii.Error):
        raise AuditRejected("blob_decode_rejected") from None
    if len(raw) > MAX_SAMPLE_BYTES:
        raise AuditRejected("blob_size_rejected")
    return raw


def _kind(path: str) -> str:
    for prefix, kind in CATEGORY.items():
        if path.startswith(prefix):
            return kind
    return "other"


def _nested_forbidden(value: dict | list) -> bool | None:
    """Detect nested prohibited field names without retaining or emitting values.

    None means the bounded traversal was incomplete, never "clean".
    """
    pending = [(value, 0)]
    visited = 0
    while pending:
        node, depth = pending.pop()
        visited += 1
        if visited > MAX_NESTED_NODES or depth > MAX_NESTED_DEPTH:
            return None
        if isinstance(node, dict):
            if depth and any(isinstance(key, str) and key.casefold() in FORBIDDEN_OUTER
                             for key in node):
                return True
            pending.extend((child, depth + 1) for child in node.values()
                           if isinstance(child, (dict, list)))
        elif isinstance(node, list):
            pending.extend((child, depth + 1) for child in node
                           if isinstance(child, (dict, list)))
    return False


def _sample(entry: dict, raw: bytes) -> tuple[str, bool, bool | None]:
    if not isinstance(raw, bytes):
        raise AuditRejected("blob_sample_type")
    if str(entry["path"]).lower().endswith(".json"):
        try:
            value = json.loads(raw)
        except (UnicodeError, ValueError):
            return "json_parse_failed", False, False
        if isinstance(value, list):
            # Root JSON arrays can contain forbidden nested object keys too.
            return "json_non_object", False, _nested_forbidden(value)
        if not isinstance(value, dict):
            return "json_non_object", False, False
        outer = any(isinstance(key, str) and key.casefold() in FORBIDDEN_OUTER
                    for key in value)
        return "json_object", outer, _nested_forbidden(value)
    return "other_extension_unclassified", False, False


def audit_tree(tree: dict, fetch_blob=None) -> dict:
    if not isinstance(tree, dict) or tree.get("truncated") is not False:
        raise AuditRejected("tree_missing_or_truncated")
    tree_sha = tree.get("sha")
    if not isinstance(tree_sha, str) or not SHA40.fullmatch(tree_sha):
        raise AuditRejected("tree_identity_unverified")
    entries = tree.get("tree")
    if not isinstance(entries, list):
        raise AuditRejected("tree_shape_rejected")
    buckets = {name: {"files": 0, "bytes": 0, "json_files": 0, "other_files": 0}
               for name in (*CATEGORY.values(), "other")}
    candidates = {name: [] for name in CATEGORY.values()}
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("path"), str):
            raise AuditRejected("tree_entry_rejected")
        if e.get("type") != "blob":
            continue
        if not SHA40.fullmatch(str(e.get("sha") or "")):
            raise AuditRejected("blob_identity_rejected")
        size = e.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise AuditRejected("blob_size_rejected")
        kind = _kind(e["path"])
        group = buckets[kind]
        group["files"] += 1
        group["bytes"] += size
        is_json = e["path"].lower().endswith(".json")
        group["json_files" if is_json else "other_files"] += 1
        if kind in candidates and is_json and 0 < size <= MAX_SAMPLE_BYTES:
            candidates[kind].append(e)

    samples = {"inspected": 0, "json_object": 0, "json_parse_failed": 0,
               "json_non_object": 0, "other_extension_unclassified": 0,
               "forbidden_outer_metadata": 0, "forbidden_nested_metadata": 0,
               "nested_scan_incomplete": 0, "coverage": "bounded_not_exhaustive"}
    if fetch_blob:
        selected = []
        for kind in sorted(candidates):
            ordered = sorted(candidates[kind], key=lambda e: e["path"])
            if ordered:
                selected.extend([ordered[0], ordered[len(ordered)//2], ordered[-1]])
        already = set()
        for entry in selected[:MAX_TOTAL_SAMPLES]:
            if entry["sha"] in already:
                continue
            already.add(entry["sha"])
            type_label, outer_forbidden, nested_forbidden = _sample(entry, fetch_blob(entry["sha"]))
            samples["inspected"] += 1
            samples[type_label] += 1
            samples["forbidden_outer_metadata"] += int(outer_forbidden)
            samples["forbidden_nested_metadata"] += int(nested_forbidden is True)
            samples["nested_scan_incomplete"] += int(nested_forbidden is None)
    return {
        "schema": "cc-public-exchange-redacted-inventory-v1",
        "status": "OBSERVATION_PASS_NOT_STORAGE_CERTIFICATION",
        "trust_mode": "public_encrypted",
        "snapshot_git_tree_sha": tree_sha,
        "current_tip_only": True,
        "history_erased": False,
        "private_consumer_ack_proven": False,
        "r2_confidential_execution_proven": False,
        "storage_privacy_certified": False,
        "total_files": sum(x["files"] for x in buckets.values()),
        "buckets": buckets,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    args = parser.parse_args()
    try:
        token = os.environ.get("GH_TOKEN", "")
        result = audit_tree(_live_tree(token), fetch_blob=lambda sha: _live_blob(token, sha))
    except Exception:
        # Explicitly suppress all GitHub API error bodies, filenames, blob bytes,
        # private data and credential content on every failure path.
        print('PUBLIC_EXCHANGE_AUDIT={"status":"FAIL_CLOSED","storage_privacy_certified":false}')
        return 1
    print("PUBLIC_EXCHANGE_AUDIT=" + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
