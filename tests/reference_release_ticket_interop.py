import json
from pathlib import Path

from scripts.reference_release_ticket_v1 import ExpectedRelease, verify_ticket

wrapper = json.loads(Path("reference-release-ticket.json").read_text())
public = Path("reference-release-signer-public.txt").read_text().strip()
expected_node = json.loads(Path("reference-release-expected.json").read_text())
now = int(expected_node.pop("now"))
expected = ExpectedRelease(**expected_node)
node = verify_ticket(
    wrapper,
    signer_public_b64=public,
    expected=expected,
    now=now,
)
if node["harness_sha"] != expected.harness_sha:
    raise SystemExit(41)
print("REFERENCE_RELEASE_TICKET_INTEROP_PASS=1")
