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
    assert (
        mod.validate_acceptance_file(
            "ui-react/src/lib/pilotPromotionAdmissionExport.acceptance.test.mjs"
        )
        == "ui-react/src/lib/pilotPromotionAdmissionExport.acceptance.test.mjs"
    )
    assert (
        mod.validate_acceptance_file(
            "ui-react/src/pages/BotConsolePage.acceptance.test.mjs"
        )
        == "ui-react/src/pages/BotConsolePage.acceptance.test.mjs"
    )
    assert (
        mod.validate_acceptance_file("ui-react/src/lib/accountMarginSafety.test.mjs")
        == "ui-react/src/lib/accountMarginSafety.test.mjs"
    )
    assert (
        mod.validate_acceptance_file("ui-react/src/components/operatorOrderSnapshot.cancel-guard.test.mjs")
        == "ui-react/src/components/operatorOrderSnapshot.cancel-guard.test.mjs"
    )
    # No sibling wildcard, mutation, or arbitrary private script execution.
    for denied in (
        "ui-react/src/components/operatorOrderSnapshot.cancel-guard.live-submit.test.mjs",
        "ui-react/src/components/operatorOrderSnapshot.cancel-guard.test.js",
        "ui-react/src/components/../pages/operatorOrderSnapshot.cancel-guard.test.mjs",
        "ui-react/src/lib/accountMarginSafety.live-submit.test.mjs",
        "ui-react/src/lib/accountMarginSafety.test.js",
        "ui-react/src/lib/../pages/accountMarginSafety.test.mjs",
    ):
        with pytest.raises(ValueError):
            mod.validate_acceptance_file(denied)
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


def test_public_cli_unknown_argument_never_echoes_nested_private_text(monkeypatch, capsys):
    import sys
    sentinel = "SYNTHETIC_PRIVATE_NESTED_SENTINEL_20261024"
    monkeypatch.setattr(sys, "argv", [
        "mmibkr_private_ui_build_probe_v1.py",
        "--source-root", "/synthetic",
        "--source-materialization", "/synthetic/source.json",
        "--source-ref", "a" * 40,
        "--acceptance-file", "ui-react/src/pages/BotConsolePage.acceptance.test.mjs",
        "--unexpected", sentinel,
    ])
    assert mod.main() == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert sentinel not in captured.out + captured.err
    receipt = json.loads(captured.out.splitlines()[0].split("=", 1)[1])
    assert receipt == {"schema": mod.SCHEMA, "status": "REJECTED"}


def test_public_cli_private_exception_never_echoes_path_or_nested_sentinel(monkeypatch, capsys):
    import sys
    sentinel = "SYNTHETIC_PRIVATE_NESTED_SENTINEL_20261024"
    monkeypatch.setattr(sys, "argv", [
        "mmibkr_private_ui_build_probe_v1.py",
        "--source-root", "/synthetic",
        "--source-materialization", "/synthetic/source.json",
        "--source-ref", "a" * 40,
        "--acceptance-file", "ui-react/src/pages/BotConsolePage.acceptance.test.mjs",
    ])
    def raise_private(**_kwargs):
        raise RuntimeError(f"private_source_path/{sentinel}/nested/secret")
    monkeypatch.setattr(mod, "run_probe", raise_private)
    assert mod.main() == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert sentinel not in captured.out + captured.err
    assert "private_source_path" not in captured.out + captured.err
    receipt = json.loads(captured.out.splitlines()[0].split("=", 1)[1])
    assert receipt == {"schema": mod.SCHEMA, "status": "REJECTED"}


def test_workflow_validates_allowlist_before_env_write_or_private_source():
    source = (
        Path(__file__).resolve().parents[1]
        / ".github" / "workflows" / "mmibkr-private-ui-build-probe-r1.yml"
    ).read_text(encoding="utf-8")
    guard = "acceptance = validate_acceptance_file(acceptance)"
    env_write = 'with Path(os.environ["GITHUB_ENV"]).open'
    assert guard in source
    assert source.index(guard) < source.index(env_write)
    assert "private UI build acceptance file rejected" in source
