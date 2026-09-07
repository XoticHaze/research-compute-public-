from __future__ import annotations

import hashlib
import json

import opportunity_semiconductor_fundamental_cycle_allocator_20260907 as batch

_original_sha256_file = batch.sha256_file


def producer_identity(path):
    if path == batch.CYCLE_CACHE:
        payload = json.loads(path.read_text(encoding="utf-8"))
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
    return _original_sha256_file(path)


batch.sha256_file = producer_identity

if __name__ == "__main__":
    batch.main()
