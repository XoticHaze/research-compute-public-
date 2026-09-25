from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

SCHEMA = "reference-release-grant-v1"
ISSUER = "private-authority-v1"
AUDIENCE = "independent-release-broker-v1"
SIGNATURE_FORMAT = "ecdsa-p256-sha256-p1363"
FIELDS = {
    "schema", "issuer", "audience", "grant_id", "run_id", "run_attempt",
    "harness_sha", "worker_key_id", "broker_key_id", "not_before",
    "admission_not_after",
}
WRAPPER_FIELDS = {"payload_b64", "signature_b64", "signer_key_id", "signature_format"}


class GrantRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ExpectedGrant:
    grant_id: str
    run_id: str
    run_attempt: str
    harness_sha: str
    worker_key_id: str
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


def generate_authority_signer() -> tuple[str, str, str]:
    private = ec.generate_private_key(ec.SECP256R1())
    private_der = private.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_raw = _public_raw(private.public_key())
    return _b64e(private_der), _b64e(public_raw), _key_id(public_raw)


def _validate_payload(node: dict) -> None:
    if not isinstance(node, dict) or set(node) != FIELDS:
        raise GrantRejected("grant_fields_rejected")
    if node.get("schema") != SCHEMA or node.get("issuer") != ISSUER or node.get("audience") != AUDIENCE:
        raise GrantRejected("grant_schema_rejected")
    if not str(node.get("grant_id") or ""):
        raise GrantRejected("grant_id_rejected")
    if not str(node.get("run_id") or "").isdigit():
        raise GrantRejected("grant_run_rejected")
    if not str(node.get("run_attempt") or "").isdigit():
        raise GrantRejected("grant_attempt_rejected")
    harness_sha = str(node.get("harness_sha") or "")
    if len(harness_sha) != 40 or any(ch not in "0123456789abcdef" for ch in harness_sha):
        raise GrantRejected("grant_harness_rejected")
    for key in ("worker_key_id", "broker_key_id"):
        value = str(node.get(key) or "")
        if not value.startswith("sha256:") or len(value) != 71:
            raise GrantRejected(f"{key}_rejected")
    not_before = int(node.get("not_before"))
    expires = int(node.get("admission_not_after"))
    if expires <= not_before:
        raise GrantRejected("grant_time_rejected")


def sign_grant(private_b64: str, grant: dict) -> dict:
    _validate_payload(grant)
    private = serialization.load_der_private_key(_b64d(private_b64), password=None)
    if not isinstance(private, ec.EllipticCurvePrivateKey) or not isinstance(private.curve, ec.SECP256R1):
        raise GrantRejected("authority_private_key_rejected")
    public_raw = _public_raw(private.public_key())
    payload = _canonical(grant)
    der = private.sign(payload, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return {
        "payload_b64": _b64e(payload),
        "signature_b64": _b64e(raw),
        "signer_key_id": _key_id(public_raw),
        "signature_format": SIGNATURE_FORMAT,
    }


def verify_grant(
    wrapper: dict,
    *,
    authority_public_b64: str,
    expected: ExpectedGrant,
    now: int | None = None,
    max_admission_seconds: int = 900,
) -> dict:
    if not isinstance(wrapper, dict) or set(wrapper) != WRAPPER_FIELDS:
        raise GrantRejected("wrapper_fields_rejected")
    if wrapper.get("signature_format") != SIGNATURE_FORMAT:
        raise GrantRejected("signature_format_rejected")
    public_raw = _b64d(authority_public_b64)
    try:
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_raw)
    except ValueError as exc:
        raise GrantRejected("authority_public_key_rejected") from exc
    if wrapper.get("signer_key_id") != _key_id(public_raw):
        raise GrantRejected("authority_key_id_rejected")

    payload = _b64d(str(wrapper.get("payload_b64") or ""))
    signature = _b64d(str(wrapper.get("signature_b64") or ""))
    if len(signature) != 64:
        raise GrantRejected("signature_rejected")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    try:
        public.verify(encode_dss_signature(r, s), payload, ec.ECDSA(hashes.SHA256()))
    except Exception as exc:
        raise GrantRejected("signature_rejected") from exc

    try:
        node = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise GrantRejected("payload_rejected") from exc
    _validate_payload(node)

    for field in (
        "grant_id", "run_id", "run_attempt", "harness_sha",
        "worker_key_id", "broker_key_id",
    ):
        if str(node[field]) != str(getattr(expected, field)):
            raise GrantRejected(f"{field}_mismatch")

    now_i = int(time.time() if now is None else now)
    not_before = int(node["not_before"])
    expires = int(node["admission_not_after"])
    if now_i < not_before:
        raise GrantRejected("grant_not_yet_valid")
    if expires <= now_i:
        raise GrantRejected("grant_expired")
    if expires - not_before > int(max_admission_seconds):
        raise GrantRejected("grant_ttl_too_long")
    return node
