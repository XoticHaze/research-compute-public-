#!/usr/bin/env python3
"""Materialize an exact private MM-IBKR source archive through Fleet Authority OIDC.

Research-only helper. It never accepts symbolic refs, repository tokens, broker
credentials, or paper/live authority. The caller supplies an exact 40-hex source
SHA and receives a bounded extracted tree plus a deterministic materialization
record compatible with public research consumers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

AUDIENCE = "mmibkr-fleet-authority"
SCHEMA = "mmibkr.cloud_source_materialization.v1"


def _oidc() -> str:
    parsed = urlparse(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = AUDIENCE
    url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))
    req = Request(url, headers={
        "Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"],
        "Accept": "application/json",
    })
    with urlopen(req, timeout=20) as response:
        token = str(json.load(response).get("value") or "")
    if token.count(".") != 2:
        raise RuntimeError("OIDC token invalid")
    return token


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authority-base", required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--destination", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--timeout-sec", type=int, default=900)
    args = ap.parse_args()

    source_sha = args.source_sha.strip().lower()
    if len(source_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_sha):
        raise SystemExit("exact 40-hex source sha required")

    base = args.authority_base.rstrip("/")
    destination = Path(args.destination).resolve()
    output = Path(args.output).resolve()
    archive = destination.parent / (destination.name + ".tar.gz")
    destination.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(1, args.timeout_sec)
    response_headers = None
    last = None
    url = f"{base}/v1/source-vault/private-archive/{source_sha}"

    while time.monotonic() < deadline:
        try:
            req = Request(url, headers={
                "Authorization": "Bearer " + _oidc(),
                "Accept": "application/gzip",
                "User-Agent": "p01-crw-dca-fleet-private-archive",
                "X-MMIBKR-Caller-Run-Id": args.run_id,
            })
            with urlopen(req, timeout=60) as response:
                response_headers = dict(response.headers.items())
                with archive.open("wb") as out:
                    shutil.copyfileobj(response, out, length=1024 * 1024)
            last = None
            break
        except HTTPError as exc:
            body = exc.read(1024).decode("utf-8", "replace")
            last = f"HTTP {exc.code}: {body[:240]}"
            if exc.code not in {401, 403, 502, 503}:
                raise
            time.sleep(5)
    else:
        raise SystemExit("exact private source admission did not converge: " + str(last))

    headers = {str(k).lower(): str(v) for k, v in (response_headers or {}).items()}
    if headers.get("x-mmibkr-source-sha") != source_sha:
        raise SystemExit("source sha response mismatch")
    if headers.get("x-mmibkr-private-source-token-exposed") != "false":
        raise SystemExit("source token exposure contract violated")
    stream_id = headers.get("x-mmibkr-source-stream-id", "")
    if not stream_id:
        raise SystemExit("source stream id missing")

    archive_sha, archive_bytes = _sha256(archive)
    if archive_bytes <= 0:
        raise SystemExit("private archive empty")

    attestation = {
        "schema": "mmibkr-fleet-private-source-attest-v1",
        "source_sha": source_sha,
        "stream_id": stream_id,
        "archive_sha256": archive_sha,
        "archive_bytes": archive_bytes,
    }
    req = Request(
        base + "/v1/source-vault/private-archive/attest",
        data=json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode(),
        method="POST",
        headers={
            "Authorization": "Bearer " + _oidc(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "p01-crw-dca-fleet-private-archive",
            "X-MMIBKR-Caller-Run-Id": args.run_id,
        },
    )
    with urlopen(req, timeout=30) as response:
        attested = json.load(response)
    if not (
        attested.get("ok") is True
        and attested.get("source_sha") == source_sha
        and attested.get("archive_sha256") == archive_sha
        and int(attested.get("archive_bytes") or 0) == archive_bytes
        and attested.get("private_source_token_exposed") is False
    ):
        raise SystemExit("source attestation failed")

    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        tops = {Path(m.name).parts[0] for m in members if Path(m.name).parts}
        if len(tops) != 1:
            raise SystemExit("private archive root invalid")
        root = (destination / next(iter(tops))).resolve()
        files = total = 0
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or member.isdev():
                raise SystemExit("unsafe private archive member")
            target = (destination / path).resolve()
            if target != root and root not in target.parents:
                raise SystemExit("private archive escape")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise SystemExit("private archive member type rejected")
            files += 1
            total += int(member.size or 0)
            if files > 30000 or total > 500 * 1024 * 1024:
                raise SystemExit("private archive expansion rejected")
            handle = tf.extractfile(member)
            if handle is None:
                raise SystemExit("private archive member unreadable")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as out:
                shutil.copyfileobj(handle, out, length=1024 * 1024)

    node = {
        "schema": SCHEMA,
        "ok": True,
        "source_ref": source_sha,
        "source_sha": source_sha,
        "source_root": str(root),
        "source_archive_sha256": archive_sha,
        "source_archive_bytes": archive_bytes,
        "source_stream_id": stream_id,
        "private_repository_token_used": False,
        "broker_credentials_used": False,
        "paper_or_live_authority": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(node, sort_keys=True) + "\n", encoding="utf-8")
    archive.unlink(missing_ok=True)
    print("MMIBKR_FLEET_PRIVATE_SOURCE_SHA=" + source_sha)
    print("MMIBKR_FLEET_PRIVATE_SOURCE_ARCHIVE_SHA256=" + archive_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
