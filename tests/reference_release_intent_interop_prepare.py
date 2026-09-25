import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reference_release_intent_v1 import generate_signer, sign_intent

now = 100000
private_b64, public_b64, _ = generate_signer()
intent = {
    "schema": "reference-release-intent-v1",
    "issuer": "private-authority-v1",
    "audience": "independent-release-broker-v1",
    "grant_id": "grant_0123456789abcdef",
    "caller_policy_sha256": "5" * 64,
    "harness_sha": "477b76085c06f77fee72b57771225a66545aa43f",
    "broker_key_id": "sha256:" + "3" * 64,
    "not_before": now,
    "intent_not_after": now + 8 * 60 * 60,
}
wrapper = sign_intent(private_b64, intent)
Path("reference-authority-intent.json").write_text(json.dumps(wrapper) + "\n")
Path("reference-authority-intent-public.txt").write_text(public_b64 + "\n")
Path("reference-authority-intent-expected.json").write_text(
    json.dumps({**intent, "now": now + 1}) + "\n"
)
print("REFERENCE_AUTHORITY_INTENT_PREPARED=1")
