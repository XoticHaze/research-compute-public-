"""Frozen W106 lifecycle replay transport marker.

Canonical source authority: XoticHaze/mm-IBKR@76aa7e9bb64a1aca36865076df1fa4b25f1b06a9

This file intentionally fails closed until the complete canonical lifecycle body is transported.
It prevents the public execution plane from silently substituting the invalid standalone W106
reimplementation while the exact dependency slice is being materialized.
"""

FROZEN_MM_COMMIT = "76aa7e9bb64a1aca36865076df1fa4b25f1b06a9"
STRATEGY_SPEC_DIGEST = "3680e21e"


def run_lifecycle_replay(*args, **kwargs):
    raise RuntimeError(
        "canonical W106 lifecycle body not yet transported; "
        "do not substitute recovery/w106_public_recovery.py"
    )
