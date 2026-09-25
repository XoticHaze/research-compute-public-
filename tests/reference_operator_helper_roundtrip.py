from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reference_release_intent_v1 import ExpectedIntent, verify_intent


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/operator/reference_release_keygen.mjs"),
                str(out),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        broker_key_id = (out / "broker-key-id.txt").read_text(encoding="utf-8").strip()
        authority_public = (out / "authority-public.b64").read_text(encoding="utf-8").strip()

        bootstrap_path = out / "bootstrap-intent.json"
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/operator/reference_release_prepare_intent.mjs"),
                str(out / "authority-private.pkcs8.b64"),
                broker_key_id,
                str(bootstrap_path),
                "28800",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
        if set(bootstrap) != {"schema", "intent"}:
            raise RuntimeError("bootstrap_fields_rejected")
        if bootstrap["schema"] != "reference-live-intent-v1":
            raise RuntimeError("bootstrap_schema_rejected")

        payload = json.loads(
            __import__("base64").b64decode(
                bootstrap["intent"]["payload_b64"].encode("ascii"), validate=True
            ).decode("utf-8")
        )
        expected = ExpectedIntent(
            grant_id=payload["grant_id"],
            caller_policy_sha256=payload["caller_policy_sha256"],
            harness_sha=payload["harness_sha"],
            broker_key_id=payload["broker_key_id"],
        )
        verified = verify_intent(
            bootstrap["intent"],
            authority_public_b64=authority_public,
            expected=expected,
            now=int(payload["not_before"]) + 60,
            max_intent_seconds=259200,
        )
        if verified != payload:
            raise RuntimeError("operator_intent_roundtrip_mismatch")

        if not (out / "broker-private.jwk").exists():
            raise RuntimeError("broker_private_missing")
        if not (out / "authority-private.pkcs8.b64").exists():
            raise RuntimeError("authority_private_missing")

    print("REFERENCE_OPERATOR_HELPER_ROUNDTRIP_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
