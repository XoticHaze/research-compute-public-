from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import (
    generate_keypair,
    open_capsule,
    seal,
)

API = "https://api.github.com"
REQUEST_SCHEMA = "reference-private-request-v1"
RESULT_SCHEMA = "reference-private-result-v1"

def _repo() -> str:
    value = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in value:
        raise RuntimeError("repository_context_rejected")
    return value

def _token() -> str:
    value = os.environ.get("GITHUB_TOKEN", "")
    if not value:
        raise RuntimeError("token_missing")
    return value

def _api(path: str, *, method: str = "GET", node: dict | None = None) -> dict | None:
    data = None if node is None else json.dumps(node, separators=(",", ":")).encode("utf-8")
    req = Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + _token(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "reference-worker-v1",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return json.loads(raw.decode("utf-8")) if raw else {}

def _put(path: str, obj: dict, *, message: str) -> None:
    content = base64.b64encode(
        (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).decode("ascii")
    node = {
        "message": message,
        "content": content,
        "branch": os.environ.get("GITHUB_REF_NAME", "main"),
    }
    current = _api(f"/repos/{_repo()}/contents/{path}?ref={os.environ.get('GITHUB_REF_NAME','main')}")
    if current and current.get("sha"):
        node["sha"] = current["sha"]
    response = _api(f"/repos/{_repo()}/contents/{path}", method="PUT", node=node)
    if not response:
        raise RuntimeError("publish_failed")

def _get_json(path: str) -> dict | None:
    node = _api(f"/repos/{_repo()}/contents/{path}?ref={os.environ.get('GITHUB_REF_NAME','main')}")
    if not node:
        return None
    encoded = "".join(str(node["content"]).split())
    raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("json_object_required")
    return value

def _main() -> int:
    run_id = str(os.environ.get("GITHUB_RUN_ID") or "")
    if not run_id.isdigit():
        raise RuntimeError("run_context_rejected")

    request_private, request_public, request_key_id = generate_keypair()
    base = f"proof/rendezvous/{run_id}"
    offer = {
        "schema": "reference-worker-offer-v1",
        "run_id": run_id,
        "recipient_public_b64": request_public,
        "recipient_key_id": request_key_id,
    }
    _put(f"{base}/offer.json", offer, message="ref: publish offer")

    request_node = None
    deadline = time.time() + 180
    while time.time() < deadline:
        request_node = _get_json(f"{base}/request.json")
        if request_node is not None:
            break
        time.sleep(2)
    if request_node is None:
        raise SystemExit("REFERENCE_EXECUTION_FAIL=1")

    try:
        request_raw = open_capsule(
            request_node,
            recipient_private_b64=request_private,
            expected_run_id=run_id,
            expected_direction="request",
        )
        private_request = json.loads(request_raw.decode("utf-8"))
        if set(private_request) != {
            "schema", "request_id", "operation", "payload_b64", "return_public_b64"
        }:
            raise RuntimeError("private_request_fields_rejected")
        if private_request["schema"] != REQUEST_SCHEMA:
            raise RuntimeError("private_request_schema_rejected")
        if private_request["operation"] != "H1":
            raise RuntimeError("operation_rejected")
        payload = base64.b64decode(
            private_request["payload_b64"].encode("ascii"), validate=True
        )

        import hashlib
        result_payload = json.dumps(
            {
                "schema": RESULT_SCHEMA,
                "request_id": private_request["request_id"],
                "ok": True,
                "output_b64": base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii"),
                "cleanup_contract": "PROCESS_EXIT_NO_PLAINTEXT_ARTIFACT",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        result_envelope = seal(
            result_payload,
            recipient_public_b64=private_request["return_public_b64"],
            run_id=run_id,
            direction="result",
        )
        _put(f"{base}/result.json", result_envelope, message="ref: publish result")

        payload = b""
        request_raw = b""
        result_payload = b""
        private_request = {}
        request_private = ""
        print("REFERENCE_EXECUTION_PASS=1")
        return 0
    except Exception:
        print("REFERENCE_EXECUTION_FAIL=1")
        return 1

def main() -> int:
    try:
        return _main()
    except BaseException:
        print("REFERENCE_EXECUTION_FAIL=1")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
