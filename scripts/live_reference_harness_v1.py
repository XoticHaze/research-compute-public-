from __future__ import annotations

import base64
import hashlib
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

REQUEST_SCHEMA = "reference-private-request-v1"
RESULT_SCHEMA = "reference-private-result-v1"
BROKER_URL = "https://reference-release-broker-v1.slenderiq.workers.dev/v1/release"
AUDIENCE = "secure-compute-reference-v1"

def _github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("github_token_missing")
    return token

def _repo() -> str:
    value = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in value:
        raise RuntimeError("repository_context_rejected")
    return value

def _api(path: str, *, method: str = "GET", node: dict | None = None) -> dict | None:
    data = None if node is None else json.dumps(node, separators=(",", ":")).encode("utf-8")
    req = Request(
        "https://api.github.com" + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + _github_token(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "reference-harness-v1",
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

def _put_json(path: str, node: dict) -> None:
    payload = base64.b64encode(
        (json.dumps(node, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).decode("ascii")
    body = {
        "message": "ref: exchange",
        "content": payload,
        "branch": os.environ.get("GITHUB_REF_NAME", "main"),
    }
    current = _api(f"/repos/{_repo()}/contents/{path}?ref={os.environ.get('GITHUB_REF_NAME','main')}")
    if current and current.get("sha"):
        body["sha"] = current["sha"]
    if not _api(f"/repos/{_repo()}/contents/{path}", method="PUT", node=body):
        raise RuntimeError("publish_rejected")

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

def _oidc_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not bearer:
        raise RuntimeError("oidc_context_missing")
    sep = "&" if "?" in url else "?"
    req = Request(
        url + sep + "audience=" + AUDIENCE,
        headers={"Authorization": "Bearer " + bearer},
    )
    with urlopen(req, timeout=20) as response:
        node = json.load(response)
    token = str(node.get("value") or "")
    if token.count(".") != 2:
        raise RuntimeError("oidc_token_rejected")
    return token

def _broker_release(intent: dict, worker_key_id: str) -> dict:
    body = json.dumps(
        {"worker_key_id": worker_key_id, "intent": intent},
        separators=(",", ":"),
    ).encode("utf-8")
    req = Request(
        BROKER_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + _oidc_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "reference-harness-v1",
        },
    )
    with urlopen(req, timeout=30) as response:
        node = json.load(response)
    if node.get("ok") is not True or not isinstance(node.get("ticket"), dict):
        raise RuntimeError("broker_release_rejected")
    return node["ticket"]

def _main() -> int:
    run_id = str(os.environ.get("GITHUB_RUN_ID") or "")
    bootstrap = _get_json("proof/live/bootstrap-intent.json")
    if not bootstrap or set(bootstrap) != {"schema", "intent"}:
        raise RuntimeError("intent_bootstrap_rejected")
    if bootstrap.get("schema") != "reference-live-intent-v1" or not isinstance(bootstrap.get("intent"), dict):
        raise RuntimeError("intent_bootstrap_rejected")
    if not run_id.isdigit():
        raise RuntimeError("run_context_rejected")

    request_private, request_public, worker_key_id = generate_keypair()
    ticket = _broker_release(bootstrap["intent"], worker_key_id)

    base = f"proof/live/{run_id}"
    _put_json(
        f"{base}/offer.json",
        {
            "schema": "reference-live-offer-v1",
            "run_id": run_id,
            "worker_public_b64": request_public,
            "worker_key_id": worker_key_id,
            "ticket": ticket,
        },
    )

    request_node = None
    deadline = time.time() + 480
    while time.time() < deadline:
        request_node = _get_json(f"{base}/request.json")
        if request_node is not None:
            break
        time.sleep(2)
    if request_node is None:
        raise RuntimeError("request_timeout")

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

    return_public = private_request["return_public_b64"]
    try:
        if private_request["operation"] != "H1":
            raise RuntimeError("operation_rejected")
        payload = base64.b64decode(private_request["payload_b64"].encode("ascii"), validate=True)
        result_node = {
            "schema": RESULT_SCHEMA,
            "request_id": private_request["request_id"],
            "ok": True,
            "output_b64": base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii"),
            "cleanup_contract": "PROCESS_EXIT_NO_PLAINTEXT_ARTIFACT",
        }
        public_state = "PASS"
        exit_code = 0
    except Exception as exc:
        payload = b""
        result_node = {
            "schema": RESULT_SCHEMA,
            "request_id": private_request["request_id"],
            "ok": False,
            "error_type": type(exc).__name__,
            "error_code": str(exc)[:128],
            "cleanup_contract": "PROCESS_EXIT_NO_PLAINTEXT_ARTIFACT",
        }
        public_state = "FAIL"
        exit_code = 1

    result_payload = json.dumps(result_node, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result_envelope = seal(
        result_payload,
        recipient_public_b64=return_public,
        run_id=run_id,
        direction="result",
    )
    _put_json(f"{base}/result.json", result_envelope)

    payload = b""
    request_raw = b""
    result_payload = b""
    result_node = {}
    private_request = {}
    request_private = ""
    print("REFERENCE_LIVE_EXECUTION_" + public_state + "=1")
    return exit_code

def main() -> int:
    try:
        return _main()
    except BaseException:
        print("REFERENCE_LIVE_EXECUTION_FAIL=1")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
