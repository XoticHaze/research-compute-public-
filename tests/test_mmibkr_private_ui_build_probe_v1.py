from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import mmibkr_private_ui_build_probe_v1 as mod


def _materialization(tmp_path: Path, source_root: Path, sha: str) -> Path:
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            {
                "schema": "mmibkr.attested_source_materialization.v2",
                "ok": True,
                "source_ref": sha,
                "source_sha": sha,
                "source_root": str(source_root),
                "source_archive_sha256": "b" * 64,
                "source_archive_bytes": 123,
                "source_manifest_sha256": "c" * 64,
                "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
                "vault_attestation_verified": True,
                "private_repository_token_used": False,
                "broker_credentials_used": False,
                "plaintext_emitted": False,
                "live_execution_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    return path


def _ui_tree(tmp_path: Path) -> Path:
    source_root = tmp_path / "mm-ibkr"
    ui = source_root / "ui-react"
    ui.mkdir(parents=True)
    (ui / "package.json").write_text(
        json.dumps({"scripts": {"build": "vite build"}}),
        encoding="utf-8",
    )
    (ui / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3}),
        encoding="utf-8",
    )
    return source_root


def test_acceptance_file_is_exact_allowlist():
    assert (
        mod.validate_acceptance_file(
            "ui-react/src/canonical-market-chart-provenance.acceptance.test.mjs"
        )
        == "ui-react/src/canonical-market-chart-provenance.acceptance.test.mjs"
    )
    assert (
        mod.validate_acceptance_file(
            "ui-react/src/lib/pilotStrategySpecHandoff.acceptance.test.mjs"
        )
        == "ui-react/src/lib/pilotStrategySpecHandoff.acceptance.test.mjs"
    )
    with pytest.raises(ValueError, match="not_allowlisted"):
        mod.validate_acceptance_file("ui-react/src/other.test.mjs")
    with pytest.raises(ValueError):
        mod.validate_acceptance_file("../private.mjs")


def test_source_identity_requires_exact_attested_sha(tmp_path):
    root = _ui_tree(tmp_path)
    sha = "a" * 40
    materialization = _materialization(tmp_path, root, sha)
    node = mod.validate_source_identity(root, materialization, sha)
    assert node["source_sha"] == sha

    with pytest.raises(RuntimeError, match="source_ref_mismatch"):
        mod.validate_source_identity(root, materialization, "d" * 40)


def test_package_contract_rejects_lifecycle_hooks(tmp_path):
    root = _ui_tree(tmp_path)
    ui = root / "ui-react"
    assert mod.validate_package_contract(ui)["lockfile_version"] == 3

    (ui / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "prebuild": "echo no",
                    "build": "vite build",
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="lifecycle_hook"):
        mod.validate_package_contract(ui)



def test_workflow_exposes_private_ui_rendezvous_fire_and_dispatch():
    source=(
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "mmibkr-private-ui-build-probe-r1.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "source_ref:" in source
    assert "acceptance_file:" in source
    assert "push:" in source
    assert "- 'rendezvous/fire/mmibkr-private-ui-build-probe-r1'" in source
    assert "elif event == \"push\":" in source
