from __future__ import annotations

import argparse
import json
from pathlib import Path

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--ciphertext", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--harness", required=True)
    p.add_argument("--response-root", required=True)
    p.add_argument("--authority", default="research_only")
    args = p.parse_args()

    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=Path(args.ciphertext).read_bytes(),
        private_key_path=Path(args.private_key),
        expected_schema=args.schema,
        expected_run_id=args.run_id,
        expected_harness=args.harness,
        response_root=args.response_root,
        expected_authority=args.authority,
    )
    Path(args.output).write_bytes(plaintext)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
