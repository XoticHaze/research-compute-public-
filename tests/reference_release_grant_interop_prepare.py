import json
from pathlib import Path

from scripts.reference_release_grant_v1 import generate_authority_signer, sign_grant

now = 100000
private_b64, public_b64, _ = generate_authority_signer()
grant = {
    "schema": "reference-release-grant-v1",
    "issuer": "private-authority-v1",
    "audience": "independent-release-broker-v1",
    "grant_id": "grant_0123456789abcdef",
    "run_id": "36177988341",
    "run_attempt": "1",
    "harness_sha": "155e3120494ddb0f81b88cb901c3dffc96e687f7",
    "worker_key_id": "sha256:" + "2" * 64,
    "broker_key_id": "sha256:" + "3" * 64,
    "not_before": now,
    "admission_not_after": now + 300,
}
wrapper = sign_grant(private_b64, grant)
Path("reference-authority-grant.json").write_text(json.dumps(wrapper) + "\n")
Path("reference-authority-public.txt").write_text(public_b64 + "\n")
Path("reference-authority-grant-expected.json").write_text(json.dumps({**grant, "now": now + 1}) + "\n")
print("REFERENCE_AUTHORITY_GRANT_PREPARED=1")
