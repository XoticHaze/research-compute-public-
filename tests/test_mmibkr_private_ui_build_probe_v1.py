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



def test_vite_safe_failure_diagnostic_is_bounded_and_never_prints_private_source(tmp_path, capsys):
    import hashlib
    import sys
    private_sentinel = "SYNTHETIC_PRIVATE_VITE_SOURCE_DO_NOT_PUBLISH_20261026"
    path = "src/pages/SyntheticPrivate.jsx"
    raw = (
        "Transform failed with 1 error:\\n"
        f"/runner/private/ui-react/{path}:42:7: ERROR: {private_sentinel}\\n"
    )
    expected = {
        "class": "TRANSFORM_ERROR",
        "source_path_sha256_16": hashlib.sha256(path.encode()).hexdigest()[:16],
        "source_line": 42,
    }
    assert mod._safe_vite_failure_class(raw) == expected
    safe = json.dumps(expected)
    assert private_sentinel not in safe and path not in safe and "/runner/" not in safe
    assert mod._safe_vite_failure_class("Could not resolve secret-import") == {"class": "UNRESOLVED_IMPORT"}

    log = tmp_path / "vite-build.log"
    code = "import sys;sys.stdout.write(" + repr(raw) + ");sys.exit(1)"
    result = mod._run_captured(
        [sys.executable, "-c", code],
        cwd=tmp_path, log_path=log, timeout=15,
    )
    output = capsys.readouterr()
    assert result["status"] == "FAIL"
    assert result["exit_code"] == 1
    assert "MMIBKR_PRIVATE_UI_VITE_SAFE_FAILURE=" in output.out
    assert private_sentinel not in output.out + output.err
    assert path not in output.out and "/runner/private" not in output.out
    assert not log.exists()



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
    for exact in (
        "ui-react/src/lib/pilotMatrixPlan.test.mjs",
        "ui-react/src/lib/botConsoleExactAccountHoldings.test.mjs",
        "ui-react/src/lib/botConsolePositionTruth.test.mjs",
        "ui-react/src/lib/botConsoleOpenOrdersTruth.test.mjs",
        "ui-react/src/lib/builderLocalDraftRestore.test.mjs",
        "ui-react/src/lib/builderConditionId.test.mjs",
        "ui-react/src/pages/botConsoleModeTruth.test.mjs",
    ):
        assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/lib/pilotMatrixPlan.live-submit.test.mjs",
        "ui-react/src/lib/pilotMatrixPlan.test.js",
        "ui-react/src/lib/botConsoleExactAccountHoldings.live-submit.test.mjs",
        "ui-react/src/lib/botConsoleExactAccountHoldings.test.js",
        "ui-react/src/lib/botConsolePositionTruth.live-submit.test.mjs",
        "ui-react/src/lib/botConsolePositionTruth.test.js",
        "ui-react/src/lib/botConsoleOpenOrdersTruth.live-submit.test.mjs",
        "ui-react/src/lib/botConsoleOpenOrdersTruth.test.js",
        "ui-react/src/lib/../pages/botConsoleOpenOrdersTruth.test.mjs",
        "ui-react/src/lib/builderLocalDraftRestore.live-submit.test.mjs",
        "ui-react/src/lib/builderConditionId.live-submit.test.mjs",
        "ui-react/src/pages/botConsoleModeTruth.live-submit.test.mjs",
        "ui-react/src/pages/botConsoleModeTruth.test.js",
        "ui-react/src/pages/../lib/botConsoleModeTruth.test.mjs",
        "ui-react/src/lib/builderConditionId.test.js",
        "ui-react/src/lib/../pages/builderConditionId.test.mjs",
        "ui-react/src/lib/builderLocalDraftRestore.test.js",
        "ui-react/src/lib/../pages/builderLocalDraftRestore.test.mjs",
    ):
        with pytest.raises(ValueError):
            mod.validate_acceptance_file(denied)
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


def test_ui_compute_trust_mode_required_at_both_existing_triggers():
    assert mod.validate_compute_requirements({"trust_mode": "public_encrypted"}) == "public_encrypted"
    for rejected in (None, "", {}, [], {"trust_mode": None},
                     {"trust_mode": "agent_local"}, {"trust_mode": "public"},
                     {"trust_mode": "public_encrypted", "executor": "caller-authored"}):
        with pytest.raises(ValueError):
            mod.validate_compute_requirements(rejected)
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
                / "mmibkr-private-ui-build-probe-r1.yml").read_text(encoding="utf-8")
    assert "DISPATCH_TRUST_MODE:" in workflow
    assert "resolve_ui_request(" in workflow
    assert 'dispatch_trust_mode=os.environ.get("DISPATCH_TRUST_MODE", "")' in workflow
    assert "MMIBKR_PRIVATE_UI_TRUST_MODE=" in workflow


def test_ui_request_resolver_executes_both_triggers_and_rejects_untrusted_modes():
    sha = "a" * 40
    acceptance = "ui-react/src/lib/pilotStrategySpecHandoff.acceptance.test.mjs"
    expected = {"source_ref": sha, "acceptance_file": acceptance,
                "trust_mode": "public_encrypted"}
    assert mod.resolve_ui_request(
        event_name="workflow_dispatch", dispatch_source_ref=sha,
        dispatch_acceptance_file=acceptance, dispatch_trust_mode="public_encrypted",
    ) == expected
    fire = {"schema": "mmibkr.private_ui_build_probe_fire.v1",
            "source_ref": sha, "acceptance_file": acceptance,
            "compute_requirements": {"trust_mode": "public_encrypted"}}
    assert mod.resolve_ui_request(event_name="push", fire=fire) == expected
    for mode in ("", "agent_local", "public", "public_encrypted\\nOTHER=1"):
        with pytest.raises(ValueError):
            mod.resolve_ui_request(
                event_name="workflow_dispatch", dispatch_source_ref=sha,
                dispatch_acceptance_file=acceptance, dispatch_trust_mode=mode,
            )
        with pytest.raises(ValueError):
            mod.resolve_ui_request(event_name="push", fire={
                **fire, "compute_requirements": {"trust_mode": mode},
            })
    for bad in (None, {}, {**fire, "schema": "other"},
                {**fire, "compute_requirements": None},
                {**fire, "source_ref": "not-a-sha"},
                {**fire, "acceptance_file": "../secret"}):
        with pytest.raises(ValueError):
            mod.resolve_ui_request(event_name="push", fire=bad)
    with pytest.raises(ValueError):
        mod.resolve_ui_request(event_name="unknown")


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
    assert 'if event == "push" else None' in source
    assert "request = resolve_ui_request(" in source


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
    guard = "request = resolve_ui_request("
    env_write = 'with Path(os.environ["GITHUB_ENV"]).open'
    assert guard in source
    assert source.index(guard) < source.index(env_write)
    assert "private UI build request rejected" in source
    # The helper dynamically exercises both triggers, not a stale inline parser.
    resolver = Path(mod.__file__).read_text(encoding="utf-8")
    assert "validate_acceptance_file(acceptance)" in resolver
    assert "validate_compute_requirements(requirements)" in resolver


def _synthetic_safe_public_receipt():
    step = {
        "status": "PASS", "exit_code": 0,
        "captured_output_sha256": "d" * 64,
        "captured_output_bytes": 10,
    }
    return {
        "schema": mod.SCHEMA, "status": "PASS",
        "source_identity": {
            "repository": "XoticHaze/mm-IBKR",
            "source_ref": "a" * 40, "source_sha": "a" * 40,
            "source_archive_sha256": "b" * 64,
            "source_archive_bytes": 123,
            "source_manifest_sha256": "c" * 64,
            "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
            "vault_attestation_verified": True,
        },
        "package_contract": {
            "build_script": "vite build", "lockfile_version": 3,
            "lifecycle_hooks_disabled": True,
        },
        "acceptance_file": "ui-react/src/pages/BotConsolePage.acceptance.test.mjs",
        "npm_ci": dict(step), "node_acceptance": dict(step), "vite_build": dict(step),
        "vite_failure_class": None,
        "dist_index_present": True, "dist_file_count": 2,
        "dist_digest_sha256": "e" * 64,
        "authority": {
            "research_only": True, "private_repository_token_used": False,
            "broker_credentials_used": False, "broker_request_made": False,
            "broker_action": False, "strategy_spec_write": False,
            "runtime_activation": False, "promotion_mutation": False,
            "live_trading_allowed": False,
        },
        "sanitization": {
            "private_plaintext_published": False,
            "captured_build_output_published": False,
            "output_retained_as_digest_only": True,
        },
    }


def test_public_receipt_rejects_nested_private_sentinel_without_echo(monkeypatch, capsys):
    import copy
    import sys
    valid = _synthetic_safe_public_receipt()
    assert mod._public_receipt(valid) == valid
    sentinel = "SYNTHETIC_PRIVATE_NESTED_SENTINEL_20261024"
    for mutation in ("extra_nested", "digest_field"):
        bad = copy.deepcopy(valid)
        if mutation == "extra_nested":
            bad["source_identity"]["untrusted_nested"] = {"secret": sentinel}
        else:
            bad["source_identity"]["source_manifest_sha256"] = sentinel
        with pytest.raises(ValueError):
            mod._public_receipt(bad)
        monkeypatch.setattr(sys, "argv", [
            "mmibkr_private_ui_build_probe_v1.py",
            "--source-root", "/synthetic",
            "--source-materialization", "/synthetic/source.json",
            "--source-ref", "a" * 40,
            "--acceptance-file", "ui-react/src/pages/BotConsolePage.acceptance.test.mjs",
        ])
        monkeypatch.setattr(mod, "run_probe", lambda **_kwargs: bad)
        assert mod.main() == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        assert sentinel not in captured.out + captured.err
        assert json.loads(captured.out.splitlines()[0].split("=", 1)[1]) == {
            "schema": mod.SCHEMA, "status": "REJECTED",
        }


def test_builder_model_digest_and_crw_cross_timeframe_exact_allowlist():
    exact = (
        "ui-react/src/lib/builderPersistedReviewTruth.test.mjs",
        "ui-react/src/lib/tradingProductReadiness.digest-identity.test.mjs",
        "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.cross-timeframe-capability.test.mjs",
        "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.local-draft-storage.test.mjs",
    )
    for path in exact:
        assert mod.validate_acceptance_file(path) == path
    for denied in (
        "ui-react/src/lib/builderPersistedReviewTruth.mjs",
        "ui-react/src/lib/builderPersistedReviewTruth.test.mjs.bak",
        "ui-react/src/lib/tradingProductReadiness.mjs",
        "ui-react/src/lib/tradingProductReadiness.digest-identity.test.mjs.bak",
        "ui-react/src/lib/other/tradingProductReadiness.digest-identity.test.mjs",
        "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.cross-timeframe-capability.test.mjs.extra",
        "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.local-draft-storage.test.mjs.bak",
        "ui-react/src/components/other/CRWStrategyBuilderBacktestWorkbenchBase.local-draft-storage.test.mjs",
        "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.jsx",
    ):
        with pytest.raises(ValueError, match="not_allowlisted"):
            mod.validate_acceptance_file(denied)



def test_public_failure_never_echoes_private_cli_or_exception_sentinel(monkeypatch, capsys):
    secret = "NESTED_PRIVATE_UI_SENTINEL_NEVER_PUBLIC_20261024"

    def fail_with_private_exception(**_kwargs):
        raise RuntimeError("private-path/" + secret)

    monkeypatch.setattr(mod, "run_probe", fail_with_private_exception)
    monkeypatch.setattr("sys.argv", [
        "probe", "--source-root", "/private/" + secret,
        "--source-materialization", "/private/" + secret,
        "--source-ref", "a" * 40,
        "--acceptance-file",
        "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.local-draft-storage.test.mjs",
    ])
    assert mod.main() == 1
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert captured.err == ""
    assert json.loads(captured.out.splitlines()[0].split("=", 1)[1]) == {
        "schema": mod.SCHEMA, "status": "REJECTED",
    }




def test_public_parser_and_allowlist_never_echo_unknown_private_text(monkeypatch, capsys):
    secret = "UNKNOWN_PRIVATE_UI_ARGUMENT_SENTINEL_20261024"
    with pytest.raises(ValueError) as exc:
        mod.validate_acceptance_file("ui-react/src/" + secret + ".mjs")
    assert str(exc.value) == "ui_acceptance_file_not_allowlisted"
    assert secret not in str(exc.value)
    monkeypatch.setattr("sys.argv", ["probe", "--unknown", secret])
    assert mod.main() == 1
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert captured.err == ""
    assert json.loads(captured.out.splitlines()[0].split("=", 1)[1]) == {
        "schema": mod.SCHEMA, "status": "REJECTED",
    }



def test_exact_selected_bot_console_empty_holdings_acceptance_is_allowlisted_only():
    # Private Node acceptance remains exact-file and Source Vault-bound.
    exact = "ui-react/src/lib/botConsoleSelectedHoldingsEmpty.product.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        exact + ".bak",
        exact.replace(".test.mjs", ".mjs"),
        exact.replace(".test.mjs", ".test.mjs.js"),
        "ui-react/src/lib/../lib/botConsoleSelectedHoldingsEmpty.product.test.mjs",
    ):
        with pytest.raises(ValueError, match="not_allowlisted"):
            mod.validate_acceptance_file(denied)





def test_exact_counted_warmup_readiness_acceptance_allowlist_only():
    # Product #1037 R2 is now carried by selected #888 and #975; admit only
    # its one exact brokerless Node presentation test through existing probe.
    exact = "ui-react/src/lib/historicalRangeReadinessLabel.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/lib/historicalRangeReadinessLabel.mjs",
        exact + ".bak",
        exact.replace(".test.mjs", ".test.mjs.js"),
        "ui-react/src/lib/../lib/historicalRangeReadinessLabel.test.mjs",
        "ui-react/src/components/historicalRangeReadinessLabel.test.mjs",
    ):
        with pytest.raises(ValueError, match="not_allowlisted"):
            mod.validate_acceptance_file(denied)



def test_exact_builder_literal_finite_helper_node_acceptance_is_allowlisted_only():
    # Selected #888/#975 consumed Product #1041's pure Node literal parser.
    exact = "ui-react/src/lib/builderLiteralValue.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/lib/builderLiteralValue.mjs",
        exact + ".bak",
        exact + ".js",
        "ui-react/src/components/builderLiteralValue.test.mjs",
    ):
        with pytest.raises(ValueError):
            mod.validate_acceptance_file(denied)





def test_exact_selected_contract_pnl_multiplier_acceptance_allowlist_only():
    # Pure UI presentation safety. No account/broker/order/FX authority.
    exact = "ui-react/src/lib/contractPnlCurrency.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/lib/contractPnlCurrency.mjs",
        exact + ".bak",
        exact + ".js",
        "ui-react/src/components/contractPnlCurrency.test.mjs",
        "ui-react/src/lib/../lib/contractPnlCurrency.test.mjs",
    ):
        with pytest.raises(ValueError, match="not_allowlisted"):
            mod.validate_acceptance_file(denied)



def test_exact_selected_runtime_badge_truth_acceptance_allowlist_only():
    # Read-only badge/trace presentation. Never grants broker mutation.
    exact = "ui-react/src/lib/selectedRuntimeBadgeTruth.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/lib/selectedRuntimeBadgeTruth.mjs",
        exact + ".bak",
        exact + ".js",
        "ui-react/src/components/selectedRuntimeBadgeTruth.test.mjs",
        "ui-react/src/lib/../lib/selectedRuntimeBadgeTruth.test.mjs",
    ):
        with pytest.raises(ValueError, match="not_allowlisted"):
            mod.validate_acceptance_file(denied)



def test_exact_selected_reviewed_backtest_fetch_guard_allowlist_only():
    # Read-only acceptance; no Builder apply/config/broker authority.
    exact = "ui-react/src/components/strategy-builder-reviewed-fetch-guard.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/components/strategy-builder-reviewed-fetch-guard.js",
        exact + ".bak",
        exact + ".js",
        "ui-react/src/lib/strategy-builder-reviewed-fetch-guard.test.mjs",
        "ui-react/src/components/../components/strategy-builder-reviewed-fetch-guard.test.mjs",
    ):
        with pytest.raises(ValueError, match="not_allowlisted"):
            mod.validate_acceptance_file(denied)


def test_selected_builder_decimal_threshold_exact_allowlist_and_lookalike_denials():
    exact = "ui-react/src/lib/builderLiteralValue.decimalAdmission.product.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/lib/builderLiteralValue.decimalAdmission.product.test.js",
        "ui-react/src/lib/builderLiteralValue.decimalAdmission.product.live-submit.test.mjs",
        "ui-react/src/lib/../pages/builderLiteralValue.decimalAdmission.product.test.mjs",
        "ui-react/src/lib/builderLiteralValue.decimalAdmission.product.test.mjs.py",
    ):
        with pytest.raises(ValueError):
            mod.validate_acceptance_file(denied)



def test_safe_vite_receipt_class_and_main_diagnostic_both_survive_merge():
    raw = "Could not resolve private-module\\n/runner/private/ui-react/src/pages/BotConsolePage.jsx:42:7"
    assert mod._safe_vite_receipt_class(raw) == "IMPORT_RESOLUTION"
    diagnostic = mod._safe_vite_failure_class(raw)
    assert diagnostic["class"] == "UNRESOLVED_IMPORT"
    assert diagnostic["source_line"] == 42
    assert "/runner/private" not in json.dumps(diagnostic)
    assert "private-module" not in json.dumps(diagnostic)
    assert mod._safe_vite_receipt_class("out of memory") == "RESOURCE_EXHAUSTION"


def test_public_vite_receipt_fixed_enum_requires_failed_build():
    import copy
    valid = _synthetic_safe_public_receipt()
    valid["vite_build"]["status"] = "FAIL"
    valid["vite_build"]["exit_code"] = 1
    valid["vite_failure_class"] = "IMPORT_RESOLUTION"
    assert mod._public_receipt(valid) == valid
    bad = copy.deepcopy(valid)
    bad["vite_failure_class"] = "private/source/path"
    with pytest.raises(ValueError, match="public_receipt_vite_failure_class_rejected"):
        mod._public_receipt(bad)
    success = copy.deepcopy(valid)
    success["vite_build"]["status"] = "PASS"
    with pytest.raises(ValueError, match="public_receipt_vite_failure_class_rejected"):
        mod._public_receipt(success)



def test_safe_vite_marker_and_fixed_receipt_class_in_diagnose_mode(tmp_path, capsys):
    import sys
    raw = "Could not resolve synthetic-private-module\\n"
    log = tmp_path / "vite-build.log"
    code = "import sys;sys.stdout.write(" + repr(raw) + ");sys.exit(1)"
    result = mod._run_captured(
        [sys.executable, "-c", code],
        cwd=tmp_path, log_path=log, timeout=15, diagnose_vite=True,
    )
    output = capsys.readouterr()
    assert result["status"] == "FAIL"
    assert result["_safe_vite_failure_class"] == "IMPORT_RESOLUTION"
    assert "MMIBKR_PRIVATE_UI_VITE_SAFE_FAILURE=" in output.out
    assert "synthetic-private-module" not in output.out + output.err
    assert not log.exists()


def test_selected_builder_coverage_review_exact_node_acceptance_only():
    # Collision-safe adoption from selected #2017; no private UI execution.
    exact = "ui-react/src/lib/builderBacktestCoverageReview.test.mjs"
    assert mod.validate_acceptance_file(exact) == exact
    for denied in (
        "ui-react/src/lib/builderBacktestCoverageReview.mjs",
        exact + ".bak",
        exact + ".js",
        "ui-react/src/pages/builderBacktestCoverageReview.test.mjs",
        "ui-react/src/lib/../lib/builderBacktestCoverageReview.test.mjs",
    ):
        with pytest.raises(ValueError):
            mod.validate_acceptance_file(denied)
