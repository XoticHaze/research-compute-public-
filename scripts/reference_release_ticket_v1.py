from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

SCHEMA = "reference-release-ticket-v1"
ISSUER = "independent-release-broker-v1"
SIGNATURE_FORMAT = "ecdsa-p256-sha256-p1363"
FIELDS = {
    "schema", "issuer", "grant_id", "run_id", "run_attempt",
    "harness_sha", "worker_key_id", "issued_at", "admission_not_after",
}
WRAPPER_FIELDS = {"payload_b64", "signature_b64", "signer_key_id", "signature_format"}


class TicketRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ExpectedRelease:
    grant_id: str
    run_id: str
    run_attempt: str
    harness_sha: str
    worker_key_id: str


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def _canonical(node: dict) -> bytes:
    return json.dumps(node, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _public_raw(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint,
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


def _validate_payload(node: dict) -> None:
    if not isinstance(node, dict) or set(node) != FIELDS:
        raise TicketRejected("ticket_fields_rejected")
    if node.get("schema") != SCHEMA or node.get("issuer") != ISSUER:
        raise TicketRejected("ticket_schema_rejected")
    if not str(node.get("grant_id") or ""):
        raise TicketRejected("ticket_grant_rejected")
    run_id = str(node.get("run_id") or "")
    if not run_id.isdigit():
        raise TicketRejected("ticket_run_rejected")
    attempt = str(node.get("run_attempt") or "")
    if not attempt.isdigit():
        raise TicketRejected("ticket_attempt_rejected")
    harness_sha = str(node.get("harness_sha") or "")
    if len(harness_sha) != 40 or any(ch not in "0123456789abcdef" for ch in harness_sha):
        raise TicketRejected("ticket_harness_rejected")
    worker = str(node.get("worker_key_id") or "")
    if not worker.startswith("sha256:") or len(worker) != 71:
        raise TicketRejected("ticket_worker_key_rejected")
    issued = int(node.get("issued_at"))
    expires = int(node.get("admission_not_after"))
    if expires <= issued:
        raise TicketRejected("ticket_time_rejected")


def sign_ticket(private_b64: str, claims: dict) -> dict:
    _validate_payload(claims)
    private = serialization.load_der_private_key(_b64d(private_b64), password=None)
    if not isinstance(private, ec.EllipticCurvePrivateKey) or not isinstance(private.curve, ec.SECP256R1):
        raise TicketRejected("signer_private_key_rejected")
    public_raw = _public_raw(private.public_key())
    der = private.sign(_canonical(claims), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return {
        "payload_b64": _b64e(_canonical(claims)),
        "signature_b64": _b64e(raw),
        "signer_key_id": _key_id(public_raw),
        "signature_format": SIGNATURE_FORMAT,
    }


def verify_ticket(
    wrapper: dict,
    *,
    signer_public_b64: str,
    expected: ExpectedRelease,
    now: int | None = None,
    max_ticket_seconds: int = 900,
) -> dict:
    if not isinstance(wrapper, dict) or set(wrapper) != WRAPPER_FIELDS:
        raise TicketRejected("wrapper_fields_rejected")
    if wrapper.get("signature_format") != SIGNATURE_FORMAT:
        raise TicketRejected("signature_format_rejected")

    public_raw = _b64d(signer_public_b64)
    try:
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_raw)
    except ValueError as exc:
        raise TicketRejected("signer_public_key_rejected") from exc
    if wrapper.get("signer_key_id") != _key_id(public_raw):
        raise TicketRejected("signer_key_id_rejected")

    payload = _b64d(str(wrapper.get("payload_b64") or ""))
    signature = _b64d(str(wrapper.get("signature_b64") or ""))
    if len(signature) != 64:
        raise TicketRejected("signature_rejected")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    try:
        public.verify(encode_dss_signature(r, s), payload, ec.ECDSA(hashes.SHA256()))
    except Exception as exc:
        raise TicketRejected("signature_rejected") from exc

    try:
        node = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise TicketRejected("payload_rejected") from exc
    _validate_payload(node)

    if node["grant_id"] != expected.grant_id:
        raise TicketRejected("grant_mismatch")
    if str(node["run_id"]) != str(expected.run_id):
        raise TicketRejected("run_mismatch")
    if str(node["run_attempt"]) != str(expected.run_attempt):
        raise TicketRejected("attempt_mismatch")
    if node["harness_sha"] != expected.harness_sha:
        raise TicketRejected("harness_mismatch")
    if node["worker_key_id"] != expected.worker_key_id:
        raise TicketRejected("worker_key_mismatch")

    now_i = int(time.time() if now is None else now)
    issued = int(node["issued_at"])
    expires = int(node["admission_not_after"])
    if issued > now_i + 30:
        raise TicketRejected("issued_in_future")
    if expires <= now_i:
        raise TicketRejected("ticket_expired")
    if expires - issued > int(max_ticket_seconds):
        raise TicketRejected("ticket_ttl_too_long")
    return node
