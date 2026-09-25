from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

SCHEMA = "reference-release-intent-v1"
ISSUER = "private-authority-v1"
AUDIENCE = "independent-release-broker-v1"
SIGNATURE_FORMAT = "ecdsa-p256-sha256-p1363"
FIELDS = {
    "schema", "issuer", "audience", "grant_id",
    "caller_policy_sha256", "harness_sha", "broker_key_id",
    "not_before", "intent_not_after",
}
WRAPPER_FIELDS = {"payload_b64", "signature_b64", "signer_key_id", "signature_format"}


class IntentRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ExpectedIntent:
    grant_id: str
    caller_policy_sha256: str
    harness_sha: str
    broker_key_id: str


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def _canonical(node: dict) -> bytes:
    return json.dumps(node, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _public_raw(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )


def _key_id(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def generate_signer() -> tuple[str, str, str]:
    private = ec.generate_private_key(ec.SECP256R1())
    private_der = private.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_raw = _public_raw(private.public_key())
    return _b64e(private_der), _b64e(public_raw), _key_id(public_raw)


def _validate(node: dict) -> None:
    if not isinstance(node, dict) or set(node) != FIELDS:
        raise IntentRejected("intent_fields_rejected")
    if node.get("schema") != SCHEMA or node.get("issuer") != ISSUER or node.get("audience") != AUDIENCE:
        raise IntentRejected("intent_schema_rejected")
    if not str(node.get("grant_id") or ""):
        raise IntentRejected("intent_grant_rejected")
    for key in ("caller_policy_sha256", "broker_key_id"):
        value = str(node.get(key) or "")
        if key == "caller_policy_sha256":
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise IntentRejected("intent_caller_policy_rejected")
        else:
            if not value.startswith("sha256:") or len(value) != 71:
                raise IntentRejected("intent_broker_key_rejected")
    harness = str(node.get("harness_sha") or "")
    if len(harness) != 40 or any(ch not in "0123456789abcdef" for ch in harness):
        raise IntentRejected("intent_harness_rejected")
    if int(node.get("intent_not_after")) <= int(node.get("not_before")):
        raise IntentRejected("intent_time_rejected")


def sign_intent(private_b64: str, node: dict) -> dict:
    _validate(node)
    private = serialization.load_der_private_key(_b64d(private_b64), password=None)
    if not isinstance(private, ec.EllipticCurvePrivateKey) or not isinstance(private.curve, ec.SECP256R1):
        raise IntentRejected("authority_private_key_rejected")
    public_raw = _public_raw(private.public_key())
    payload = _canonical(node)
    der = private.sign(payload, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return {
        "payload_b64": _b64e(payload),
        "signature_b64": _b64e(sig),
        "signer_key_id": _key_id(public_raw),
        "signature_format": SIGNATURE_FORMAT,
    }


def verify_intent(
    wrapper: dict,
    *,
    authority_public_b64: str,
    expected: ExpectedIntent,
    now: int | None = None,
    max_intent_seconds: int = 24 * 60 * 60,
) -> dict:
    if not isinstance(wrapper, dict) or set(wrapper) != WRAPPER_FIELDS:
        raise IntentRejected("intent_wrapper_rejected")
    if wrapper.get("signature_format") != SIGNATURE_FORMAT:
        raise IntentRejected("intent_signature_format_rejected")
    public_raw = _b64d(authority_public_b64)
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_raw)
    if wrapper.get("signer_key_id") != _key_id(public_raw):
        raise IntentRejected("intent_signer_rejected")
    payload = _b64d(str(wrapper.get("payload_b64") or ""))
    signature = _b64d(str(wrapper.get("signature_b64") or ""))
    if len(signature) != 64:
        raise IntentRejected("intent_signature_rejected")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    try:
        public.verify(encode_dss_signature(r, s), payload, ec.ECDSA(hashes.SHA256()))
    except Exception as exc:
        raise IntentRejected("intent_signature_rejected") from exc
    node = json.loads(payload.decode("utf-8"))
    _validate(node)
    for field in ("grant_id","caller_policy_sha256","harness_sha","broker_key_id"):
        if str(node[field]) != str(getattr(expected, field)):
            raise IntentRejected(f"{field}_mismatch")
    now_i = int(time.time() if now is None else now)
    if now_i < int(node["not_before"]):
        raise IntentRejected("intent_not_yet_valid")
    if now_i >= int(node["intent_not_after"]):
        raise IntentRejected("intent_expired")
    if int(node["intent_not_after"]) - int(node["not_before"]) > int(max_intent_seconds):
        raise IntentRejected("intent_window_too_long")
    return node
