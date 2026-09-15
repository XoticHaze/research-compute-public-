from __future__ import annotations

"""Gzip transport adapter for the fixed AutoTuner score-core consumer."""

import base64
import gzip
import json

import autotuner_score_core_consumer_core_v1 as core


def _load_gzip_payload(raw: bytes):
    node = json.loads(raw.decode("utf-8"))
    if not isinstance(node, dict) or "data_gzip_b64" not in node or "data_b64" in node:
        raise RuntimeError("AutoTuner gzip payload field mismatch")
    compressed = base64.b64decode(str(node.pop("data_gzip_b64")).encode("ascii"), validate=True)
    data = gzip.decompress(compressed)
    node["data_b64"] = base64.b64encode(data).decode("ascii")
    return _ORIGINAL_LOAD(json.dumps(node, sort_keys=True, separators=(",", ":")).encode("utf-8"))


_ORIGINAL_LOAD = core._load_payload
core._load_payload = _load_gzip_payload


if __name__ == "__main__":
    core.main()
