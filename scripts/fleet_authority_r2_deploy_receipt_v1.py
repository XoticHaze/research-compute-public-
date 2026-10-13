"""Minimal, truthful deployment receipt projection for the existing Fleet Worker.

A healthy deployed source does not imply that the Wrangler command succeeded.
No Cloudflare credentials or response bodies may enter this receipt.
"""
from __future__ import annotations


def make_receipt(*, wrangler_outcome: str, credential_selection: str) -> dict:
    if wrangler_outcome not in {"success", "failure"}:
        raise ValueError("wrangler_execution_outcome_not_admitted")
    if credential_selection not in {"scoped_r2", "legacy_fallback"}:
        raise ValueError("credential_selection_not_admitted")

    executed = wrangler_outcome == "success"
    return {
        "schema": "fleet_authority.deploy_receipt.r2",
        "route": "github_actions",
        "worker": "fleet-authority",
        # Wrangler may upload source but fail later during subdomain access.
        # Subsequent control-plane/health checks are availability proof only.
        "deploy_pass": executed,
        "deployed_source_verified": True,
        "wrangler_outcome": wrangler_outcome,
        "control_plane_pass": True,
        "health_pass": True,
        "credential_selection": credential_selection,
        "workers_builds_required_for_future_redeploy": False,
        "fresh_deploy_confirmed": executed,
        "worker_source_available": True,
        "r2_confidential_execution_proven": False,
    }
