"""Typed independent-private-authority grant bridge for shared compute R1.

Uses the existing P-256 release-grant module; does NOT create a new key,
Worker, credential, issuance API, public GitHub action, or private Actions
runner. It is a library to be installed by an independently authorized
private authority that already holds a protected P-256 key and an atomic
grant/replay journal. It cannot authenticate that authority itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .reference_release_grant_v1 import (
    SCHEMA, ISSUER, AUDIENCE, ExpectedGrant, _key_id, _public_raw,
    sign_grant, verify_grant,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
KEY_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
GRANT_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
REQ_FIELDS = frozenset({
    "grant_id", "run_id", "run_attempt", "harness_sha",
    "identity_sha256", "worker_key_id", "broker_key_id",
    "not_before", "admission_not_after",
})


class NotAuthorized(RuntimeError):
    """Constant error with no private claims, key or job semantics."""


class IndependentGrantJournal(Protocol):
    def consume_once(self, *, grant_id: str, payload_sha256: str) -> bool:
        """Atomic, persistent, independently approved non-replay claim."""


@dataclass(frozen=True)
class PrivateGrantPolicy:
    """Protected owner-admitted, NOT decoded from public PLACED/request JSON."""

    authority_public_b64: str
    authority_key_id: str
    broker_key_id: str
    harness_sha: str
    identity_sha256: str
    max_seconds: int = 300


def _reject() -> None:
    raise NotAuthorized("PRIVATE_GRANT_ISSUE_REJECTED")


def _key_attests(private_b64: str, policy: PrivateGrantPolicy) -> bool:
    try:
        encoded = base64.b64decode(private_b64.encode("ascii"), validate=True)
        private = serialization.load_der_private_key(encoded, password=None)
        if (not isinstance(private, ec.EllipticCurvePrivateKey)
            or not isinstance(private.curve, ec.SECP256R1)):
            return False
        public = _public_raw(private.public_key())
        return (_key_id(public) == policy.authority_key_id
                and base64.b64encode(public).decode("ascii") == policy.authority_public_b64)
    except Exception:
        return False


def issue_once(
    request: dict[str, Any],
    *,
    policy: PrivateGrantPolicy,
    protected_private_key_b64: str,
    journal: IndependentGrantJournal,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Sign ONE exact grant, then claim atomic issuance before returning bytes.

    The trusted private authority must obtain policy/key/journal from
    independently authenticated local owner state, not a public job or
    Cloudflare broker. No key generation, disk writes or remote dispatch.
    """
    if (type(request) is not dict or set(request) != REQ_FIELDS
        or type(policy) is not PrivateGrantPolicy
        or not isinstance(protected_private_key_b64, str)
        or not hasattr(journal, "consume_once")
        or not callable(journal.consume_once)):
        _reject()
    if (not HEX40.fullmatch(policy.harness_sha)
        or not HEX64.fullmatch(policy.identity_sha256)
        or not KEY_ID.fullmatch(policy.authority_key_id)
        or not KEY_ID.fullmatch(policy.broker_key_id)
        or type(policy.max_seconds) is not int
        or not 1 <= policy.max_seconds <= 900):
        _reject()
    if (not GRANT_ID.fullmatch(str(request.get("grant_id") or ""))
        or not RUN_ID.fullmatch(str(request.get("run_id") or ""))
        or not RUN_ID.fullmatch(str(request.get("run_attempt") or ""))
        or not HEX40.fullmatch(str(request.get("harness_sha") or ""))
        or not HEX64.fullmatch(str(request.get("identity_sha256") or ""))
        or not KEY_ID.fullmatch(str(request.get("worker_key_id") or ""))
        or not KEY_ID.fullmatch(str(request.get("broker_key_id") or ""))):
        _reject()
    if (request["harness_sha"] != policy.harness_sha
        or request["identity_sha256"] != policy.identity_sha256
        or request["broker_key_id"] != policy.broker_key_id):
        _reject()
    try:
        now = int(clock())
    except Exception:
        _reject()
    if (type(request["not_before"]) is not int
        or type(request["admission_not_after"]) is not int
        or not now - 30 <= request["not_before"] <= now + 30
        or request["admission_not_after"] <= now
        or request["admission_not_after"] > request["not_before"] + policy.max_seconds):
        _reject()
    if not _key_attests(protected_private_key_b64, policy):
        _reject()
    grant = dict(request, schema=SCHEMA, issuer=ISSUER, audience=AUDIENCE)
    try:
        wrapper = sign_grant(protected_private_key_b64, grant)
        verified = verify_grant(
            wrapper,
            authority_public_b64=policy.authority_public_b64,
            expected=ExpectedGrant(
                grant_id=request["grant_id"],
                run_id=request["run_id"],
                run_attempt=request["run_attempt"],
                harness_sha=request["harness_sha"],
                identity_sha256=request["identity_sha256"],
                worker_key_id=request["worker_key_id"],
                broker_key_id=request["broker_key_id"],
            ),
            now=now,
            max_admission_seconds=policy.max_seconds,
        )
        if verified != grant:
            _reject()
        payload_sha = hashlib.sha256(
            json.dumps(grant, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        ).hexdigest()
        # Non-ambiguous journal response required. If a previous attempt was
        # consumed, this call never returns a signed grant to its caller.
        claimed = journal.consume_once(
            grant_id=request["grant_id"], payload_sha256=payload_sha
        )
        if claimed is not True:
            _reject()
    except Exception:
        _reject()
    return wrapper
