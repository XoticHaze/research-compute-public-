from __future__ import annotations

# Exact frozen-source transport marker.
# Source authority: XoticHaze/mm-IBKR@76aa7e9bb64a1aca36865076df1fa4b25f1b06a9
# Original path: scripts/research/mnq_crw_lifecycle_replay_20260901.py
#
# IMPORTANT: intentionally fail-closed until the complete frozen source body is
# transported. Never substitute recovery/w106_public_recovery.py as evidence.

FROZEN_SOURCE_COMMIT = "76aa7e9bb64a1aca36865076df1fa4b25f1b06a9"
FROZEN_SOURCE_PATH = "scripts/research/mnq_crw_lifecycle_replay_20260901.py"
TRANSPORT_STATUS = "exact_source_body_required"

raise RuntimeError(
    "W106 exact lifecycle source transport incomplete: "
    f"{FROZEN_SOURCE_COMMIT}:{FROZEN_SOURCE_PATH}. "
    "Failing closed rather than using the invalid public reimplementation."
)
