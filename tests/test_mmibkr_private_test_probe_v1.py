from pathlib import Path

import pytest

from mmibkr_private_test_probe_v1 import (\n    module_file_path,\n    pytest_container_command,\n    validated_modules,\n    validate_source_identity,\n)


SOURCE = "0123456789abcdef0123456789abcdef01234567"


def test_allowlist_accepts_research_autotuner_registry_and_data_materializer():
    assert validated_modules(
        "tests.test_autotuner_strategy_family_catalog_vnext,"
        "tests.test_autotuner_behavioral_consumption_vnext "
        "tests.test_strategy_backtest_registry_dispatch "
        "tests.test_canonical_data_materialize_v1"
    ) == [
        "tests.test_autotuner_strategy_family_catalog_vnext",
        "tests.test_autotuner_behavioral_consumption_vnext",
        "tests.test_strategy_backtest_registry_dispatch",
        "tests.test_canonical_data_materialize_v1",
    ]


@pytest.mark.parametrize(
    "module",
    [
        "tests.test_selected_runtime_submit_authority",
        "tests.test_ibkr_remote_submit",
        "tests.test_live_bot_runtime_scope",
        "tests.test_not_allowlisted",
        "../escape",
    ],
)
def test_allowlist_rejects_authority_or_unknown_modules(module):
    with pytest.raises(ValueError):
        validated_modules(module)


def test_allowlist_accepts_only_exact_selected_runtime_strategyspec_integrity_module():
    assert validated_modules(
        "tests.test_selected_runtime_strategy_spec_integrity_v1"
    ) == ["tests.test_selected_runtime_strategy_spec_integrity_v1"]

    with pytest.raises(ValueError, match="test_module_authority_rejected"):
        validated_modules("tests.test_selected_runtime_strategy_inventory_v1")



def test_allowlist_accepts_exact_model_lab_scientific_chain_only():
    assert validated_modules(
        "tests.test_model_lab_canonical_data_authority_cc44 "
        "tests.test_model_lab_training_matrix_authority_cc44 "
        "tests.test_model_lab_canonical_trainer "
        "tests.test_model_lab_xgboost"
    ) == [
        "tests.test_model_lab_canonical_data_authority_cc44",
        "tests.test_model_lab_training_matrix_authority_cc44",
        "tests.test_model_lab_canonical_trainer",
        "tests.test_model_lab_xgboost",
    ]

    with pytest.raises(ValueError, match="test_module_not_allowlisted"):
        validated_modules("tests.test_model_lab_status_endpoints")



def test_module_file_path_and_pytest_command_are_exact_and_shell_free():
    assert module_file_path("tests.test_model_lab_xgboost") == "tests/test_model_lab_xgboost.py"
    command = pytest_container_command("probe:test", "tests.test_model_lab_xgboost")
    assert command == [
        "docker",
        "run",
        "--rm",
        "-e",
        "ENABLE_LIVE_TRADING=0",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "probe:test",
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_model_lab_xgboost.py",
    ]
    with pytest.raises(ValueError, match="test_module_rejected"):
        module_file_path("../escape")


def test_pytest_runner_executes_unittest_modules_too_by_contract():
    command = pytest_container_command(
        "probe:test", "tests.test_autotuner_campaign_runner"
    )
    assert command[-3:] == [
        "pytest",
        "-q",
        "tests/test_autotuner_campaign_runner.py",
    ]

def _materialization(source: Path, **overrides):
    node = {
        "schema": "mmibkr.attested_source_materialization.v2",
        "ok": True,
        "source_ref": SOURCE,
        "source_sha": SOURCE,
        "source_root": str(source.resolve()),
        "source_archive_sha256": "a" * 64,
        "source_archive_bytes": 123,
        "source_manifest_sha256": "b" * 64,
        "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
        "vault_attestation_verified": True,
        "private_repository_token_used": False,
        "broker_credentials_used": False,
        "plaintext_emitted": False,
        "live_execution_allowed": False,
    }
    node.update(overrides)
    return node


def test_source_identity_requires_sanitized_encrypted_vault_materialization(tmp_path: Path):
    source = tmp_path / "mm-ibkr"
    source.mkdir()
    (source / "Dockerfile.bot").write_text("FROM scratch\n", encoding="utf-8")
    materialization = tmp_path / "source.json"
    materialization.write_text(
        __import__("json").dumps(_materialization(source)),
        encoding="utf-8",
    )
    node = validate_source_identity(source, materialization, SOURCE)
    assert node["source_sha"] == SOURCE
    assert node["vault_attestation_verified"] is True
    assert node["source_transport"] == "fleet_authority_exact_sha_encrypted_snapshot_vault"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("schema", "mmibkr.cloud_source_materialization.v1", "source_materialization_schema_rejected"),
        ("vault_attestation_verified", False, "vault_attestation_contract_rejected"),
        ("source_transport", "mmibkr_cloud_source_exchange_v1", "source_transport_contract_rejected"),
        ("private_repository_token_used", True, "private_repository_token_contract_rejected"),
        ("broker_credentials_used", True, "broker_credential_contract_rejected"),
        ("plaintext_emitted", True, "plaintext_emission_contract_rejected"),
        ("live_execution_allowed", True, "live_execution_contract_rejected"),
    ],
)
def test_source_identity_rejects_legacy_or_authority_drift(
    tmp_path: Path, field: str, value, error: str
):
    source = tmp_path / "mm-ibkr"
    source.mkdir()
    (source / "Dockerfile.bot").write_text("FROM scratch\n", encoding="utf-8")
    materialization = tmp_path / "source.json"
    materialization.write_text(
        __import__("json").dumps(_materialization(source, **{field: value})),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match=error):
        validate_source_identity(source, materialization, SOURCE)
