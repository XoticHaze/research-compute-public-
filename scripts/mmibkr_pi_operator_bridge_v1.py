#!/usr/bin/env python3
"""Bounded owner-gated GitHub OIDC publisher for one private Pi bot-origin observation.

Never emits private payload, token, source path, Git SHA, or broker/account details
to public logs/artifacts. This source alone is NOT publisher or compute admission.
"""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, build_opener, HTTPRedirectHandler
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("publisher redirect rejected")

NO_REDIRECT = build_opener(RejectRedirect)

RECORD_SCHEMA = "commandcenter.pi.bot_live_observation_outbox.v1"
ENVELOPE_SCHEMA = "mmibkr.pi_bot_live_observation_envelope.v2"
RECORD_KEYS = frozenset({
    "schema", "node_id", "observation_id", "observed_at", "snapshot_sha256",
    "snapshot", "producer", "read_only", "broker_mutation_attempted",
    "gateway_mutation_attempted"
})
SNAPSHOT_KEYS = frozenset({
    "schema", "node_id", "status", "live_switches_enabled", "bot_running",
    "gateway_running", "gateway_network_namespace_matched",
    "single_canonical_main", "global_live_flags", "selected_live_policies",
    "stock_canary_enabled", "private_network_attested_by_launcher",
    "legacy_backtest_disabled", "restart_persistent",
    "gateway_readonly_api_configuration", "broker_submission_verified",
    "broker_mutation_attempted", "gateway_mutation_attempted", "read_only"
})

def require(ok, message="publisher admission rejected"):
    if not ok:
        raise ValueError(message)

def github(path, token):
    req = Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "mmibkr-pi-operator-bridge-r1",
    })
    with NO_REDIRECT.open(req, timeout=20) as response:
        return json.load(response)

def oidc():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["audience"] = "mmibkr-operator-console"
    token_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                            urlencode(params), parts.fragment))
    req = Request(token_url, headers={
        "Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"],
        "Accept": "application/json",
    })
    with NO_REDIRECT.open(req, timeout=20) as response:
        token = str(json.load(response).get("value") or "")
    require(token.count(".") == 2)
    return token

def select_record():
    token = os.environ["PI_OUTBOX_GITHUB_READ_TOKEN"]
    repo = os.environ["PI_OUTBOX_REPO"]
    branch = os.environ["PI_OUTBOX_REF"]
    prefix = os.environ["PI_OUTBOX_PREFIX"].strip("/")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo))
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", branch))
    require(prefix and ".." not in prefix.split("/") and
            all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in prefix.split("/")))
    root = "/repos/" + quote(repo, safe="/")
    ref = github(root + "/git/ref/heads/" + quote(branch, safe=""), token)
    commit_sha = (ref.get("object") or {}).get("sha")
    require(isinstance(commit_sha, str) and re.fullmatch(r"[0-9a-f]{40}", commit_sha))
    commit = github(root + "/git/commits/" + commit_sha, token)
    tree_sha = (commit.get("tree") or {}).get("sha")
    require(isinstance(tree_sha, str) and re.fullmatch(r"[0-9a-f]{40}", tree_sha))
    tree = github(root + "/git/trees/" + tree_sha + "?recursive=1", token)
    require(tree.get("truncated") is False)
    files = [entry for entry in tree.get("tree", [])
             if entry.get("type") == "blob" and
             re.fullmatch(re.escape(prefix) + r"/pibotobs-[0-9]{14}-[0-9a-f]{16}\.json",
                          str(entry.get("path") or ""))]
    require(files)
    entry = max(files, key=lambda x: x["path"])
    path = entry["path"]
    blob_sha = entry.get("sha")
    require(isinstance(blob_sha, str) and re.fullmatch(r"[0-9a-f]{40}", blob_sha))
    blob = github(root + "/git/blobs/" + blob_sha, token)
    require(blob.get("encoding") == "base64")
    raw = base64.b64decode(blob["content"], validate=False)
    require(len(raw) <= 8192 and
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == blob_sha)
    record = json.loads(raw)
    require(isinstance(record, dict) and set(record) == RECORD_KEYS)
    snapshot = record["snapshot"]
    require(isinstance(snapshot, dict) and set(snapshot) == SNAPSHOT_KEYS)
    require(record["schema"] == RECORD_SCHEMA and record["node_id"] == "cc-pi4")
    require(record["producer"] == "root_approved_fixed_pi_bot_inspection")
    require(record["read_only"] is True and record["broker_mutation_attempted"] is False
            and record["gateway_mutation_attempted"] is False)
    require(snapshot["read_only"] is True and snapshot["broker_submission_verified"] is False
            and snapshot["broker_mutation_attempted"] is False
            and snapshot["gateway_mutation_attempted"] is False)
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    require(record["snapshot_sha256"] == digest)
    observed = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
    require(observed.utcoffset() is not None)
    observed = observed.astimezone(timezone.utc)
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    require(-60 <= age <= 420)
    expected = "pibotobs-" + observed.strftime("%Y%m%d%H%M%S") + "-" + digest[:16]
    require(record["observation_id"] == expected and path == prefix + "/" + expected + ".json")
    # Authenticate the ROOT issuer independently of Git object hashes and OIDC.
    # The exact same immutable Git tree must contain the detached attestation.
    att_path = prefix + "/" + expected + ".attestation.json"
    att_entries = [item for item in tree.get("tree", []) if item.get("type") == "blob"
                   and item.get("path") == att_path]
    require(len(att_entries) == 1)
    att_blob_sha = att_entries[0].get("sha")
    require(isinstance(att_blob_sha, str) and re.fullmatch(r"[0-9a-f]{40}", att_blob_sha))
    att_blob = github(root + "/git/blobs/" + att_blob_sha, token)
    require(att_blob.get("encoding") == "base64")
    att_raw = base64.b64decode(att_blob["content"], validate=False)
    require(len(att_raw) <= 2048 and hashlib.sha1(
        b"blob " + str(len(att_raw)).encode() + bytes([0]) + att_raw).hexdigest() == att_blob_sha)
    att = json.loads(att_raw)
    keys = {"schema", "node_id", "observation_id", "observed_at", "record_sha256",
            "root_source_sha256", "key_id", "signature_b64"}
    require(isinstance(att, dict) and set(att) == keys)
    require(att["schema"] == "commandcenter.pi.bot_root_observation_attestation.v1"
            and att["node_id"] == "cc-pi4" and att["observation_id"] == expected
            and att["observed_at"] == record["observed_at"])
    allowed_key_id = os.environ["PI_BOT_ROOT_VERIFY_KEY_ID"]
    allowed_root_sha = os.environ["PI_BOT_ROOT_SIGNER_SOURCE_SHA256"]
    require(re.fullmatch(r"[A-Za-z0-9_-]{8,100}", allowed_key_id)
            and re.fullmatch(r"[0-9a-f]{64}", allowed_root_sha))
    require(att["key_id"] == allowed_key_id
            and att["root_source_sha256"] == allowed_root_sha
            and re.fullmatch(r"[0-9a-f]{64}", str(att["record_sha256"])))
    record_digest = hashlib.sha256(json.dumps(record, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    require(att["record_sha256"] == record_digest)
    unsigned = {k: att[k] for k in keys if k != "signature_b64"}
    pubkey = base64.b64decode(os.environ["PI_BOT_ROOT_VERIFY_PUBKEY_B64"], validate=True)
    signature = base64.b64decode(att["signature_b64"], validate=True)
    require(len(pubkey) == 32 and len(signature) == 64)
    msg = b"commandcenter.pi.bot_root_observation_attestation.v1" + bytes([0]) + json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    try:
        Ed25519PublicKey.from_public_bytes(pubkey).verify(signature, msg)
    except (InvalidSignature, ValueError):
        require(False)
    # Project no private repo/ref/path into the public ingress envelope.
    opaque_binding = os.environ["PI_OUTBOX_OPAQUE_BINDING_ID"]
    require(re.fullmatch(r"[A-Za-z0-9_-]{24,128}", opaque_binding))
    # HMAC keeps private commit/blob replay identity out of public storage.
    secret_hex = os.environ["PI_BOT_PRIVATE_RECEIPT_HMAC_KEY_HEX"]
    require(re.fullmatch(r"[0-9a-f]{64}", secret_hex))
    proof = hmac.new(bytes.fromhex(secret_hex),
        b"mmibkr.pi.bot.source-receipt.v1" + bytes([0])
        + bytes.fromhex(commit_sha) + bytes.fromhex(blob_sha)
        + bytes.fromhex(record_digest), hashlib.sha256).hexdigest()
    return {
        "schema": ENVELOPE_SCHEMA, "node_id": "cc-pi4",
        "source_binding_id": opaque_binding, "source_receipt_id": proof,
        "record": record,
    }, record["observed_at"]

def main():
    require(os.environ.get("MMIBKR_PI_BRIDGE_OWNER_ENABLED") == "true")
    envelope, observed = select_record()
    run_id = os.environ["GITHUB_RUN_ID"]
    require(re.fullmatch(r"[0-9]{4,24}", run_id))
    url = os.environ["OPERATOR_CONSOLE_URL"].rstrip("/") + "/v1/pi-bot-live-status"
    require(url.startswith("https://") and urlsplit(url).hostname ==
            "mmibkr-operator-console.slenderiq.workers.dev")
    payload = json.dumps({"envelope": envelope}, separators=(",", ":")).encode()
    require(len(payload) <= 8192)
    req = Request(url, data=payload, method="POST", headers={
        "Authorization": "Bearer " + oidc(),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-MMIBKR-Caller-Run-Id": run_id,
    })
    with NO_REDIRECT.open(req, timeout=20) as response:
        require(response.status == 201)
        result = json.load(response)
    require(result.get("schema") == "mmibkr.pi_bot_live_publish_receipt.v1"
            and result.get("ok") is True
            and result.get("durable_readback_verified") is True
            and result.get("observed_at") == observed
            and result.get("broker_mutation_authority") is False)
    print("PI_BOT_OIDC_INGEST_DURABLE_READBACK=PASS")
    print("PI_BOT_BROKER_MUTATION=NONE")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("PI_BOT_PUBLISHER_FAIL_CLOSED") from None
