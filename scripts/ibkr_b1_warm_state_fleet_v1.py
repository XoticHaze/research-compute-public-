from __future__ import annotations

"""Fleet transport for the already-encrypted canonical B1 warm-state envelope."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

AUDIENCE = "mmibkr-fleet-authority"
MANIFEST_SCHEMA = "mmibkr.b1_warm_state_manifest.v1"
MAX_ENVELOPE_BYTES = 64 * 1024 * 1024
CHUNK_CHARS = 90000


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _oidc_url(base: str) -> str:
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = AUDIENCE
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )


def _oidc_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not token:
        raise RuntimeError("github_oidc_environment_missing")
    req = Request(
        _oidc_url(url),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(req, timeout=20) as response:
        node = json.loads(response.read().decode("utf-8"))
    value = str(node.get("value") or "")
    if value.count(".") != 2:
        raise RuntimeError("github_oidc_token_invalid")
    return value


def _api(
    authority_base: str,
    path: str,
    *,
    method: str,
    run_id: str,
    token: str,
    payload: Mapping[str, Any] | None = None,
    raw: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, bytes, Mapping[str, str]]:
    if not str(authority_base).startswith("https://"):
        raise RuntimeError("authority_url_rejected")
    request_headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "mmibkr-b1-warm-state-fleet-v1",
        "X-MMIBKR-Caller-Run-Id": str(run_id),
        **dict(headers or {}),
    }
    data = raw
    if payload is not None:
        data = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    req = Request(
        str(authority_base).rstrip("/") + path,
        data=data,
        method=method,
        headers=request_headers,
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return int(response.status), response.read(MAX_ENVELOPE_BYTES * 2), dict(response.headers.items())
    except HTTPError as exc:
        return int(exc.code), exc.read(65536), dict(exc.headers.items()) if exc.headers else {}


def publish(
    *,
    authority_base: str,
    run_id: str,
    envelope_path: str | Path,
    token_factory: Callable[[], str] = _oidc_token,
    api: Callable[..., tuple[int, bytes, Mapping[str, str]]] = _api,
) -> dict[str, Any]:
    run_id = str(run_id or "").strip()
    if not run_id.isdigit():
        raise ValueError("warm_state_run_id_rejected")
    path = Path(envelope_path)
    if not path.is_file():
        raise RuntimeError("warm_state_envelope_missing")
    blob = path.read_bytes()
    if len(blob) <= 0 or len(blob) > MAX_ENVELOPE_BYTES:
        raise RuntimeError("warm_state_envelope_size_rejected")

    encoded = base64.b64encode(blob).decode("ascii")
    chunks = [
        encoded[index:index + CHUNK_CHARS]
        for index in range(0, len(encoded), CHUNK_CHARS)
    ]
    if not chunks or len(chunks) > 2048:
        raise RuntimeError("warm_state_chunk_count_rejected")
    descriptors = [
        {
            "index": index,
            "chars": len(text),
            "sha256": _sha256(text.encode("ascii")),
        }
        for index, text in enumerate(chunks)
    ]

    token = token_factory()
    token_started = time.monotonic()
    for index, text in enumerate(chunks):
        if time.monotonic() - token_started > 240:
            token = token_factory()
            token_started = time.monotonic()
        status, raw, _ = api(
            authority_base,
            f"/v1/b1-warm-state/publish/{run_id}/chunk/{index}",
            method="PUT",
            run_id=run_id,
            token=token,
            raw=text.encode("ascii"),
            headers={
                "Content-Type": "text/plain; charset=us-ascii",
                "X-MMIBKR-Chunk-SHA256": descriptors[index]["sha256"],
            },
        )
        if status != 200:
            raise RuntimeError(f"warm_state_chunk_publish_http_{status}:{index}")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "run_id": run_id,
        "generation": run_id,
        "envelope_sha256": _sha256(blob),
        "envelope_bytes": len(blob),
        "chunk_count": len(chunks),
        "chunks": descriptors,
    }
    status, raw, _ = api(
        authority_base,
        f"/v1/b1-warm-state/publish/{run_id}/manifest",
        method="POST",
        run_id=run_id,
        token=token,
        payload=manifest,
    )
    if status != 200:
        raise RuntimeError(f"warm_state_manifest_publish_http_{status}")
    node = json.loads(raw.decode("utf-8"))
    if node.get("ok") is not True or node.get("status") != "finalized":
        raise RuntimeError("warm_state_manifest_publish_not_finalized")
    return {
        "schema": "mmibkr.b1_warm_state_fleet_publish.v1",
        "ok": True,
        "run_id": run_id,
        "envelope_sha256": manifest["envelope_sha256"],
        "envelope_bytes": manifest["envelope_bytes"],
        "chunk_count": manifest["chunk_count"],
        "fleet_stores_encrypted_state_only": True,
    }


def fetch_latest(
    *,
    authority_base: str,
    run_id: str,
    output: str | Path,
    token_factory: Callable[[], str] = _oidc_token,
    api: Callable[..., tuple[int, bytes, Mapping[str, str]]] = _api,
) -> dict[str, Any]:
    run_id = str(run_id or "").strip()
    if not run_id.isdigit():
        raise ValueError("warm_state_run_id_rejected")
    token = token_factory()
    status, raw, _ = api(
        authority_base,
        "/v1/b1-warm-state/latest",
        method="GET",
        run_id=run_id,
        token=token,
    )
    if status == 404:
        return {
            "schema": "mmibkr.b1_warm_state_fleet_fetch.v1",
            "ok": True,
            "status": "not_found",
            "restored": False,
        }
    if status != 200:
        raise RuntimeError(f"warm_state_latest_http_{status}")
    wrapper = json.loads(raw.decode("utf-8"))
    manifest = wrapper.get("manifest") if isinstance(wrapper, Mapping) else None
    if wrapper.get("ok") is not True or not isinstance(manifest, Mapping):
        raise RuntimeError("warm_state_latest_manifest_missing")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise RuntimeError("warm_state_latest_manifest_schema_rejected")
    generation = str(manifest.get("generation") or "")
    if not generation.isdigit():
        raise RuntimeError("warm_state_generation_rejected")
    count = int(manifest.get("chunk_count") or 0)
    chunks = manifest.get("chunks")
    if count <= 0 or count > 2048 or not isinstance(chunks, list) or len(chunks) != count:
        raise RuntimeError("warm_state_chunk_manifest_rejected")

    encoded: list[str] = []
    for index, desc in enumerate(chunks):
        if not isinstance(desc, Mapping) or int(desc.get("index", -1)) != index:
            raise RuntimeError("warm_state_chunk_descriptor_rejected")
        status, chunk_raw, headers = api(
            authority_base,
            f"/v1/b1-warm-state/generation/{generation}/chunk/{index}",
            method="GET",
            run_id=run_id,
            token=token,
        )
        if status != 200:
            raise RuntimeError(f"warm_state_chunk_fetch_http_{status}:{index}")
        text = chunk_raw.decode("ascii")
        digest = _sha256(text.encode("ascii"))
        expected = str(desc.get("sha256") or "")
        if len(text) != int(desc.get("chars") or 0) or digest != expected:
            raise RuntimeError("warm_state_chunk_integrity_rejected")
        header_digest = next(
            (
                value
                for key, value in headers.items()
                if key.lower() == "x-mmibkr-chunk-sha256"
            ),
            "",
        )
        if header_digest and header_digest != expected:
            raise RuntimeError("warm_state_chunk_header_rejected")
        encoded.append(text)

    try:
        blob = base64.b64decode("".join(encoded).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("warm_state_envelope_base64_rejected") from exc
    if len(blob) != int(manifest.get("envelope_bytes") or 0):
        raise RuntimeError("warm_state_envelope_size_mismatch")
    if _sha256(blob) != str(manifest.get("envelope_sha256") or ""):
        raise RuntimeError("warm_state_envelope_digest_mismatch")

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    return {
        "schema": "mmibkr.b1_warm_state_fleet_fetch.v1",
        "ok": True,
        "status": "restored",
        "restored": True,
        "generation": generation,
        "envelope_sha256": _sha256(blob),
        "envelope_bytes": len(blob),
        "fleet_stores_encrypted_state_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-base", required=True)
    parser.add_argument("--run-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--envelope", required=True)
    fetch_parser = sub.add_parser("fetch-latest")
    fetch_parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "publish":
        result = publish(
            authority_base=args.authority_base,
            run_id=args.run_id,
            envelope_path=args.envelope,
        )
    else:
        result = fetch_latest(
            authority_base=args.authority_base,
            run_id=args.run_id,
            output=args.output,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
