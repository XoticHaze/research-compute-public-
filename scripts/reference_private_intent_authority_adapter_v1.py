"""Independent private authority: one-use signed release INTENT issuance.

This is the LIVE broker reference-release-intent-v1 contract, not the
legacy reference-release-grant-v1 compatibility helper. It reuses the
reviewed P-256 signer and verifier. No key generation, new Worker, Cloudflare
token, public endpoint, GitHub workflow or private Actions compute.

A separately admitted private owner must supply existing protected key
custody, independently verified caller-policy/harness/broker pins, and an
atomic private issuance journal. This source library cannot grant itself
those permissions or authenticate a caller-supplied policy.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .reference_release_intent_v1 import (
    SCHEMA, ISSUER, AUDIENCE, ExpectedIntent, _key_id, _public_raw,
    sign_intent, verify_intent,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
KEY_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
GRANT_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
FIELDS = frozenset({
    "grant_id", "caller_policy_sha256", "harness_sha", "broker_key_id",
    "not_before", "intent_not_after",
})


class NotAuthorized(RuntimeError):
    """Public/log-safe constant denial, independent of private intent facts."""


class PrivateIntentJournal(Protocol):
    def consume_once(self, *, grant_id: str, payload_sha256: str) -> bool:
        """Use an independently admitted atomic, non-retryable private journal."""


@dataclass(frozen=True)
class PrivateIntentPolicy:
    """Protected private-owner policy; never derived from the public request."""

    authority_public_b64: str
    authority_key_id: str
    broker_key_id: str
    harness_sha: str
    caller_policy_sha256: str
    max_seconds: int = 300


def _reject() -> None:
    raise NotAuthorized("PRIVATE_INTENT_ISSUE_REJECTED")


def _key_attests(private_b64: str, policy: PrivateIntentPolicy) -> bool:
    try:
        private = serialization.load_der_private_key(
            base64.b64decode(private_b64.encode("ascii"), validate=True),
            password=None,
        )
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
    policy: PrivateIntentPolicy,
    protected_private_key_b64: str,
    journal: PrivateIntentJournal,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Produce actual broker signed intent, only after consuming private nonce.

    The key/policy/journal must come from a trusted private authority, never
    from GitHub runner PLACED, a caller-provided JSON key, or the neutral
    broker itself. There is deliberately no CLI/network/public output here.
    """
    if (type(request) is not dict or set(request) != FIELDS
        or type(policy) is not PrivateIntentPolicy
        or not isinstance(protected_private_key_b64, str)
        or not hasattr(journal, "consume_once")
        or not callable(journal.consume_once)):
        _reject()
    if (not HEX40.fullmatch(policy.harness_sha)
        or not HEX64.fullmatch(policy.caller_policy_sha256)
        or not KEY_ID.fullmatch(policy.authority_key_id)
        or not KEY_ID.fullmatch(policy.broker_key_id)
        or type(policy.max_seconds) is not int
        or not 1 <= policy.max_seconds <= 259200):
        _reject()
    if (type(request["grant_id"]) is not str
        or not GRANT_ID.fullmatch(request["grant_id"])
        or type(request["caller_policy_sha256"]) is not str
        or not HEX64.fullmatch(request["caller_policy_sha256"])
        or type(request["harness_sha"]) is not str
        or not HEX40.fullmatch(request["harness_sha"])
        or type(request["broker_key_id"]) is not str
        or not KEY_ID.fullmatch(request["broker_key_id"])):
        _reject()
    if (request["caller_policy_sha256"] != policy.caller_policy_sha256
        or request["harness_sha"] != policy.harness_sha
        or request["broker_key_id"] != policy.broker_key_id):
        _reject()
    try:
        now = int(clock())
    except Exception:
        _reject()
    if (type(request["not_before"]) is not int
        or type(request["intent_not_after"]) is not int
        or not now - 30 <= request["not_before"] <= now + 30
        or request["intent_not_after"] <= now
        or request["intent_not_after"] > request["not_before"] + policy.max_seconds):
        _reject()
    if not _key_attests(protected_private_key_b64, policy):
        _reject()

    intent = dict(request, schema=SCHEMA, issuer=ISSUER, audience=AUDIENCE)
    try:
        wrapper = sign_intent(protected_private_key_b64, intent)
        checked = verify_intent(
            wrapper,
            authority_public_b64=policy.authority_public_b64,
            expected=ExpectedIntent(
                grant_id=request["grant_id"],
                caller_policy_sha256=request["caller_policy_sha256"],
                harness_sha=request["harness_sha"],
                broker_key_id=request["broker_key_id"],
            ),
            now=now,
            max_intent_seconds=policy.max_seconds,
        )
        if checked != intent:
            _reject()
        digest = hashlib.sha256(
            json.dumps(intent, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            .encode("ascii")
        ).hexdigest()
        # A failed or ambiguous durable consume MUST NOT return signed bytes.
        # The private owner binds the journal to an independently authenticated
        # grant identity and never retries an uncertain prior issuance.
        if journal.consume_once(grant_id=request["grant_id"], payload_sha256=digest) is not True:
            _reject()
    except Exception:
        _reject()
    return wrapper
