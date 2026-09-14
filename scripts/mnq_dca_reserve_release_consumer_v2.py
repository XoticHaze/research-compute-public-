from __future__ import annotations

import argparse
import json
from pathlib import Path

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext
from mnq_dca_reserve_release_consumer_v1 import EXPECTED_HARNESS, EXPECTED_SCHEMA, _sha, evaluate


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True, type=Path)
    p.add_argument("--ciphertext", required=True, type=Path)
    p.add_argument("--private-key", required=True, type=Path)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=args.ciphertext.read_bytes(),
        private_key_path=args.private_key,
        expected_schema=EXPECTED_SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=EXPECTED_HARNESS,
        response_root=args.response_root,
    )
    payload = json.loads(plaintext.decode("utf-8"))
    result = evaluate(payload)
    result["private_payload_sha256"] = _sha(plaintext)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("MNQ_DCA_RESERVE_RELEASE_RECEIPT=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
