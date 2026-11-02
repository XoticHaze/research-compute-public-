"""Synthetic old/new public-compute disclosure comparison, never private data.

The historical compressed session is deliberately not executed; we model
its reversible serialization and compare it to actual M1/A1 AEAD.
No source names, plaintext, keys, or envelopes are published.
"""
from __future__ import annotations

import base64
import copy
import json
import zlib

from scripts import opaque_bidirectional_capsule_v1 as m1
from scripts import opaque_bidirectional_capsule_p256_aesgcm_v1 as a1

RUN_ID = "99001234567890"
MARKER = "SYNTHETIC_ONLY_NOT_PRIVATE_8F31E6"
TEST_BODY = {
    "schema": "synthetic-private-job-fixture.v1",
    "synthetic_project": "EXAMPLE-ONLY-DO-NOT-TREAT-AS-PRIVATE-SOURCE",
    "synthetic_marker": MARKER,
    "synthetic_result": "DETERMINISTIC-TEST-OUTPUT",
}

def _rejected(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False

def compare() -> dict:
    raw = json.dumps(TEST_BODY, sort_keys=True, separators=(",", ":")).encode()
    legacy = base64.b64encode(zlib.compress(raw)).decode("ascii")
    legacy_recoverable = zlib.decompress(base64.b64decode(legacy, validate=True)) == raw
    results = {}
    for label, module in (("M1", m1), ("A1", a1)):
        worker_priv, worker_pub, _ = module.generate_keypair()
        return_priv, return_pub, _ = module.generate_keypair()
        wrong_priv, _, _ = module.generate_keypair()
        request = module.seal(raw, recipient_public_b64=worker_pub, run_id=RUN_ID, direction="request")
        serialized = json.dumps(request, sort_keys=True, separators=(",", ":"))
        recovered = module.open_capsule(request, recipient_private_b64=worker_priv,
                                        expected_run_id=RUN_ID, expected_direction="request")
        result = module.seal(b"synthetic-ok", recipient_public_b64=return_pub,
                             run_id=RUN_ID, direction="result")
        return_ok = module.open_capsule(result, recipient_private_b64=return_priv,
                                       expected_run_id=RUN_ID, expected_direction="result") == b"synthetic-ok"
        tampered = copy.deepcopy(request)
        tampered["ciphertext_sha256"] = "0" * 64
        results[label] = {
            "request_roundtrip": recovered == raw,
            "encrypted_result_roundtrip": return_ok,
            "synthetic_marker_absent_from_public_envelope": MARKER not in serialized,
            "private_semantic_keys_absent_from_public_envelope": not (set(TEST_BODY) - {"schema"}).intersection(request),
            "fixed_size_ciphertext_bucket": len(base64.b64decode(request["ciphertext_b64"])) - 16 in module.BUCKETS,
            "wrong_run_rejected": _rejected(lambda: module.open_capsule(request,
                 recipient_private_b64=worker_priv, expected_run_id=RUN_ID + "1", expected_direction="request")),
            "wrong_recipient_rejected": _rejected(lambda: module.open_capsule(request,
                 recipient_private_b64=wrong_priv, expected_run_id=RUN_ID, expected_direction="request")),
            "direction_swap_rejected": _rejected(lambda: module.open_capsule(request,
                 recipient_private_b64=worker_priv, expected_run_id=RUN_ID, expected_direction="result")),
            "tampering_rejected": _rejected(lambda: module.open_capsule(tampered,
                 recipient_private_b64=worker_priv, expected_run_id=RUN_ID, expected_direction="request")),
        }
    out = {
        "schema": "opaque-capsule-synthetic-exposure-comparison-v1",
        "scope": "SYNTHETIC_ONLY_NO_PRIVATE_DATA_NO_PRODUCTION_ADMISSION",
        "legacy_compressed_session_recoverable_without_key": legacy_recoverable,
        "upgraded_profiles": results,
        "production_route_admitted": False,
        "confidential_compute_attested": False,
    }
    if not legacy_recoverable or not all(all(v.values()) for v in results.values()):
        raise RuntimeError("synthetic_exposure_comparison_failed")
    return out

def main() -> int:
    print(json.dumps(compare(), sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
