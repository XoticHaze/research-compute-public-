from pathlib import Path

import pytest

from mmibkr_private_test_probe_v1 import (
    SAFE_EXACT,
    module_file_path,
    validate_native_fire_boolean,
    pytest_container_command,
    validated_modules,
    validate_source_identity,
    validate_compute_requirements,
)


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
        "tests.test_ibkr_remote_submit",
        "tests.test_live_bot_runtime_scope",
        "tests.test_not_allowlisted",
        "../escape",
    ],
)
def test_allowlist_rejects_authority_or_unknown_modules(module):
    with pytest.raises(ValueError):
        validated_modules(module)


@pytest.mark.parametrize(
    "module",
    [
        "tests.test_ibkr_account_context",
        "tests.test_ibkr_production_live_account_context_v1",
        "tests.test_ibkr_remote_account_hygiene_slot_v1",
        "tests.test_selected_runtime_submit_authority",
        "tests.test_paper_flatten_canonical_route_authority_667",
        "tests.test_selected_runtime_account_sizing_submit_hook_14th31lg",
    ],
)
def test_exact_sensitive_named_modules_are_network_isolated(module):
    # Exact allowlist admission cannot override network isolation for a
    # broker/account/submit/flatten test. These are source-only regressions.
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)


def test_exact_live_seal_source_only_p0_modules_run_without_network_or_live_authority():
    exact = [
        "tests.test_legacy_submit_fail_closed_r10",
        "tests.test_legacy_strategy_live_guard_r11",
        "tests.test_selected_runtime_mutation_boundary_inspect_v1",
        "tests.test_live_seal_compose_runner_v1",
    ]
    assert validated_modules(" ".join(exact)) == exact
    for module in exact:
        cmd = pytest_container_command("sealed-test-image", module)
        assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in cmd
        assert cmd[-1] == module_file_path(module)
    for rejected in ("tests.test_legacy_live_broker_submit", "tests.test_live_order_submit"):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_exact_live_successor_ledger_reconciler_stays_networkless_and_disabled():
    module = "tests.test_ibkr_live_successor_ledger_reconcile_v1"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    with pytest.raises(ValueError):
        validated_modules("tests.test_ibkr_live_successor_broker_submit_v1")


def test_exact_live_owner_journal_writer_and_broker_provenance_are_source_only():
    modules = (
        "tests.test_selected_runtime_live_order_intent_journal_v1",
        "tests.test_selected_runtime_live_execution_ledger_v1",
        "tests.test_selected_runtime_live_broker_provenance_v1",
        "tests.test_selected_runtime_live_p0_integrated_checkpoint_v1",
    )
    for module in modules:
        assert validated_modules(module) == [module]
        cmd = pytest_container_command("sealed-test-image", module)
        assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in cmd
        assert cmd[-1] == module_file_path(module)
    with pytest.raises(ValueError):
        validated_modules("tests.test_selected_runtime_live_broker_submit_v1")


def test_signed_owner_candidate_is_allowlisted_only_as_networkless_disabled_source():
    module = "tests.test_selected_runtime_live_owner_candidate_certificate_v1"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    with pytest.raises(ValueError):
        validated_modules("tests.test_selected_runtime_live_owner_broker_order_v1")


def test_exact_pi_docker_endpoint_preflight_is_networkless():
    module = "tests.test_ibkr_persistent_host_preflight_v1"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (
        "tests.test_ibkr_persistent_host_preflight_v1_live_submit",
        "tests.test_ibkr_persistent_host_preflight_v1_extra",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_exact_readonly_market_data_consumer_is_networkless_only():
    module = "tests.test_ibkr_remote_readonly_market_data_consumer_v1"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for denied in (
        "tests.test_ibkr_remote_readonly_market_data_consumer_v1_live_submit",
        "tests.test_ibkr_remote_readonly_market_data_consumer_v1_broker_probe",
        "tests.test_ibkr_remote_readonly_market_data_consumer_v1_extra",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


@pytest.mark.parametrize(
    "module",
    [
        "tests.test_autotuner_parameter_consumption",
        "tests.test_capital_timestamp_binding_product_20261026",
        "tests.test_cloud_operator_snapshot_forward_root_binding_product_20261026",
        "tests.test_cloud_operator_snapshot_health_adapter_v1",
        "tests.test_cloud_operator_snapshot_inventory_readonly_product_20261027",
        "tests.test_crw_backtest_rth_asset_contract_product_20261027",
        "tests.test_survivor_paper_trade_evidence_materializer_v1",
    "tests.test_futures_range_tail_coverage_product_20261027",
    "tests.test_market_feed_range_orchestration_14th31ix",
    ],
)
def test_exact_selected_product_regressions_are_networkless_only(module):
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    # The legacy autotuner prefix is separately allowed; all other Product
    # names must be exact, not arbitrary suffixed executable modules.
    if not module.startswith("tests.test_autotuner_"):
        with pytest.raises(ValueError):
            validated_modules(module + "_extra")


def test_exact_selected_backfill_native_conid_guard_is_networkless():
    module = "tests.test_selected_runtime_initial_backfill_selected_conid_product_20261025"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for denied in (
        "tests.test_selected_runtime_initial_backfill_selected_conid_product_20261025_live_submit",
        "tests.test_selected_runtime_initial_backfill_selected_conid_product_20261025_extra",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_paper_postexecute_quarantine_is_networkless_and_nonmutating():
    exact = (
        "tests.test_selected_runtime_cloud_cycle_v1",
        "tests.test_selected_runtime_terminal_ledger_corruption_product_20261024",
        "tests.test_selected_runtime_strategy_inventory_unverified_receipt_product_20261024",
    )
    assert validated_modules(" ".join(exact)) == list(exact)
    for module in exact:
        cmd = pytest_container_command("sealed-test-image", module)
        assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in cmd
        assert cmd[-1] == module_file_path(module)
    for rejected in (
        "tests.test_selected_runtime_cloud_cycle_live_submit_v1",
        "tests.test_selected_runtime_terminal_ledger_broker_submit",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_allowlist_accepts_exact_pr798_read_only_position_projection_modules():
    assert validated_modules(
        "tests.test_selected_runtime_strategy_spec_integrity_v1 "
        "tests.test_selected_runtime_strategy_inventory_v1 "
        "tests.test_cloud_operator_snapshot_v1"
    ) == [
        "tests.test_selected_runtime_strategy_spec_integrity_v1",
        "tests.test_selected_runtime_strategy_inventory_v1",
        "tests.test_cloud_operator_snapshot_v1",
    ]



def test_allowlist_accepts_exact_model_lab_scientific_chain_only():
    assert validated_modules(
        "tests.test_model_lab_canonical_data_authority_cc44 "
        "tests.test_model_lab_training_matrix_authority_cc44 "
        "tests.test_model_lab_canonical_trainer "
        "tests.test_model_lab_xgboost "
        "tests.test_model_lab_comparison_matrix_authority_cc44 "
        "tests.test_model_lab_validation_authority_cc44"
    ) == [
        "tests.test_model_lab_canonical_data_authority_cc44",
        "tests.test_model_lab_training_matrix_authority_cc44",
        "tests.test_model_lab_canonical_trainer",
        "tests.test_model_lab_xgboost",
        "tests.test_model_lab_comparison_matrix_authority_cc44",
        "tests.test_model_lab_validation_authority_cc44",
    ]

    with pytest.raises(ValueError, match="test_module_not_allowlisted"):
        validated_modules("tests.test_model_lab_status_endpoints")



def test_allowlist_accepts_exact_g05_g07_recovery_chain_only():
    assert validated_modules(
        "tests.test_data_manager_indicator_context_contract_14th31jq "
        "tests.test_data_manager_registry_authority_14th31lm "
        "tests.test_publish_canonical_feature_sidecar "
        "tests.test_builder_feature_rhs_comparison_14th31ky "
        "tests.test_strategy_backtest_registry_dispatch "
        "tests.test_crw_tradingview_dual_execution_replay_14th31js "
        "tests.test_crw_backtest_futures_timestamp_14th31kf"
    ) == [
        "tests.test_data_manager_indicator_context_contract_14th31jq",
        "tests.test_data_manager_registry_authority_14th31lm",
        "tests.test_publish_canonical_feature_sidecar",
        "tests.test_builder_feature_rhs_comparison_14th31ky",
        "tests.test_strategy_backtest_registry_dispatch",
        "tests.test_crw_tradingview_dual_execution_replay_14th31js",
        "tests.test_crw_backtest_futures_timestamp_14th31kf",
    ]

    with pytest.raises(ValueError, match="test_module_not_allowlisted"):
        validated_modules("tests.test_strategy_health_preview_binding")


def test_allowlist_accepts_strategy_spec_mtf_research_regressions():
    exact = [
        "tests.test_strategy_spec_mtf_registry_backtest_vnext",
        "tests.test_parameterized_indicator_instances_14th31kp",
        "tests.test_per_indicator_timeframe_execution_core_14th31kq",
        "tests.test_builder_cross_timeframe_aligned_evaluation_14th31ks",
        "tests.test_strategy_spec_source_feature_materialization_14th31kr",
    ]
    assert validated_modules(" ".join(exact)) == exact
    with pytest.raises(ValueError):
        validated_modules("tests.test_strategy_spec_mtf_live_submit")


def test_allowlist_accepts_s4_layered_mtf_economics_regression():
    exact = ["tests.test_s4_layered_mtf_matched_control_economics_20261004"]
    assert validated_modules(" ".join(exact)) == exact
    import pytest
    with pytest.raises(ValueError):
        validated_modules("tests.test_s4_layered_mtf_live_submit")


def test_allowlist_accepts_exact_g05b_futures_materialization_only():
    assert validated_modules(
        "tests.test_materialize_admitted_futures_source_canonical "
        "tests.test_materialize_admitted_futures_dated_contract "
        "tests.test_publish_canonical_feature_sidecar"
    ) == [
        "tests.test_materialize_admitted_futures_source_canonical",
        "tests.test_materialize_admitted_futures_dated_contract",
        "tests.test_publish_canonical_feature_sidecar",
    ]

    with pytest.raises(ValueError, match="test_module_not_allowlisted"):
        validated_modules("tests.test_futures_unapproved_materializer")


def test_allowlist_accepts_exact_options_research_regressions_only():
    assert validated_modules(
        "tests.test_options_snapshot_analysis "
        "tests.test_options_snapshot_features"
    ) == [
        "tests.test_options_snapshot_analysis",
        "tests.test_options_snapshot_features",
    ]

    with pytest.raises(ValueError, match="test_module_authority_rejected"):
        validated_modules("tests.test_options_runtime_submit")


def test_allowlist_accepts_exact_news_research_regressions_only():
    assert validated_modules(
        "tests.test_news_publication_time_integrity_20260902 "
        "tests.test_news_publication_time_integration_patch_20260902 "
        "tests.test_news_scorecard_cycle_break_14th31fd_r18"
    ) == [
        "tests.test_news_publication_time_integrity_20260902",
        "tests.test_news_publication_time_integration_patch_20260902",
        "tests.test_news_scorecard_cycle_break_14th31fd_r18",
    ]

    with pytest.raises(ValueError, match="test_module_authority_rejected"):
        validated_modules("tests.test_news_live_provider_submit")



def test_allowlist_accepts_exact_capital_survivor_and_corpus_regressions_only():
    exact = [
        "tests.test_backtest_capital_replay_v1",
        "tests.test_selected_runtime_account_sizing_14th31lg",
        "tests.test_selected_runtime_account_sizing_submit_hook_14th31lg",
        "tests.test_selected_runtime_margin_guard_14th31lg",
        "tests.test_selected_runtime_margin_whatif_hook_14th31lg",
        "tests.test_research_survivor_funnel",
        "tests.test_acquire_hfdl_bounded_equity_panel",
    ]
    assert validated_modules(" ".join(exact)) == exact

    # Exact admission must not open adjacent runtime/broker-authority modules.
    for rejected in (
        "tests.test_selected_runtime_margin_submit_live",
        "tests.test_backtest_capital_replay_submit",
        "tests.test_research_survivor_funnel_live",
        "tests.test_acquire_hfdl_bounded_equity_panel_submit",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_allowlist_accepts_exact_production_live_migration_regressions_only():
    exact = [
        "tests.test_ibkr_account_context",
        "tests.test_ibkr_production_live_account_context_v1",
        "tests.test_selected_runtime_submit_authority",
        "tests.test_paper_flatten_canonical_route_authority_667",
    ]
    assert validated_modules(" ".join(exact)) == exact

    for rejected in (
        "tests.test_ibkr_remote_submit",
        "tests.test_live_bot_runtime_scope",
        "tests.test_selected_runtime_live_submit",
        "tests.test_paper_flatten_live_broker_mutation",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_allowlist_accepts_exact_promotion_review_read_only_regressions():
    exact = [
        "tests.test_promotion_review_store",
        "tests.test_autotuner_promotion_review_backend_product",
        "tests.test_operator_snapshot_api",
        "tests.test_promotion_review_stale_status",
        "tests.test_research_ui_backend_restore",
        "tests.test_admit_exact_pilot_to_promotion_review_13z",
        "tests.test_ibkr_remote_forward_exact_ticks_slot_v1",
        "tests.test_ibkr_remote_account_hygiene_slot_v1",
    ]
    assert validated_modules(" ".join(exact)) == exact

    for rejected in (
        "tests.test_promotion_review_live_submit",
        "tests.test_promotion_review_broker_mutation",
        "tests.test_operator_snapshot_ibkr_submit",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_allowlist_accepts_only_exact_forward_historical_tick_evidence_modules():
    exact = [
        "tests.test_selected_runtime_forward_historical_tick_producer_v1",
        "tests.test_selected_runtime_forward_exact_extrema_v1",
    ]
    assert validated_modules(" ".join(exact)) == exact

    # Keep neighboring selected-runtime broker/runtime authority outside this
    # research-only exact validation aperture.
    for rejected in (
        "tests.test_selected_runtime_forward_execution_submit_v1",
        "tests.test_selected_runtime_forward_historical_tick_submit_v1",
        "tests.test_selected_runtime_forward_exact_extrema_live_v1",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)


@pytest.mark.parametrize("module", sorted(SAFE_EXACT))
def test_every_exact_allowlisted_module_is_networkless_even_without_sensitive_name(module):
    # Exact allowlist admission is not a network permission. Source-only
    # validation must not reach external data, brokers or arbitrary hosts.
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-test-image", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)


def test_module_file_path_and_pytest_command_are_exact_and_shell_free():
    assert module_file_path("tests.test_model_lab_xgboost") == "tests/test_model_lab_xgboost.py"
    command = pytest_container_command("probe:test", "tests.test_model_lab_xgboost")
    assert command == [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
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


def test_selected_model_lab_backend_modules_are_exact_networkless():
    """Only the five source-only #888 backend regressions are newly admitted."""
    exact = [
        "tests.test_model_lab_cancel_process_identity_product",
        "tests.test_model_lab_cancel_terminal_race_product",
        "tests.test_model_lab_orchestrator_identity_authority_product",
        "tests.test_model_lab_startup_status_race_product",
        "tests.test_model_lab_worker_early_cancel_product",
    ]
    assert validated_modules(" ".join(exact)) == exact
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
    for denied in (
        "tests.test_model_lab_runtime_submit",
        "tests.test_model_lab_cancel_live_order",
        "tests.test_model_lab_unreviewed_worker",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_selected_pnl_lifecycle_module_is_exact_and_networkless():
    """Only five exact source-only PnL modules can run, always networkless."""
    exact = [
        "tests.test_lifecycle_single_flat_roundtrip_product_20261023",
        "tests.test_lifecycle_decimal_flatness_product_20261024",
        "tests.test_lifecycle_matched_fill_count_truth_product_20261024",
        "tests.test_capital_adjusted_price_explicit_failclose_product_20261024",
        "tests.test_capital_fill_ledger_integrity_product_20261024",
    ]
    assert validated_modules(",".join(exact)) == exact
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
    for denied in (
        "tests.test_lifecycle_live_order_pnl",
        "tests.test_lifecycle_single_flat_roundtrip_product_20261023_extra",
        "tests.test_lifecycle_decimal_flatness_product_20261024_live_submit",
        "tests.test_lifecycle_matched_fill_count_truth_product_20261024_broker_mutation",
        "tests.test_capital_fill_ledger_integrity_product_20261024_live_submit",
        "tests.test_capital_fill_ledger_integrity_product_20261024_extra",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_p0_residue_and_foundry_issuer_modules_are_networkless():
    """Two newly changed private test modules reuse the sealed offline probe."""
    exact = [
        "tests.test_live_broker_position_residue_product_20261024",
        "tests.test_cloud_operator_exact_contract_position_product_20261024",
        "tests.test_foundry_model_promotion_admission_v1",
        "tests.test_foundry_model_limited_forward_sanity_product_20261024",
        "tests.test_promotion_review_get_http_current_product_20261024",
    "tests.test_foundry_model_order_intent_adapter_v1",
    "tests.test_foundry_model_arena_executor_conformance_v1",
    "tests.test_foundry_model_canonical_preview_conformance_v1",
    "tests.test_foundry_model_runtime_binding_v1",
    ]
    assert validated_modules(",".join(exact)) == exact
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
    for denied in (
        "tests.test_live_broker_position_residue_product_20261024_extra",
        "tests.test_foundry_model_promotion_admission_v1_live_submit",
        "tests.test_foundry_model_limited_forward_sanity_product_20261024_live_submit",
        "tests.test_promotion_review_get_http_current_product_20261024_live_submit",
        "tests.test_foundry_model_order_intent_adapter_v1_live_submit",
        "tests.test_foundry_model_runtime_binding_v1_extra",
        "tests.test_live_broker_position_residue_unreviewed",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_public_cli_unknown_private_sentinel_is_not_echoed(monkeypatch, capsys):
    import sys
    from mmibkr_private_test_probe_v1 import main, SCHEMA
    sentinel = "SYNTHETIC_PRIVATE_NESTED_SENTINEL_20261024"
    monkeypatch.setattr(sys, "argv", [
        "mmibkr_private_test_probe_v1.py",
        "--source-root", "/synthetic",
        "--source-materialization", "/synthetic/source.json",
        "--source-ref", "a" * 40,
        "--test-modules", "tests.test_lifecycle_single_flat_roundtrip_product_20261023",
        "--unexpected", sentinel,
    ])
    assert main() == 1
    out = capsys.readouterr()
    assert out.err == ""
    assert sentinel not in out.out + out.err
    import json
    assert json.loads(out.out.splitlines()[0].split("=", 1)[1]) == {
        "schema": SCHEMA, "status": "REJECTED",
    }


def test_public_cli_private_module_exception_is_fixed_field(monkeypatch, capsys):
    import sys
    from mmibkr_private_test_probe_v1 import main, SCHEMA
    sentinel = "SYNTHETIC_PRIVATE_NESTED_SENTINEL_20261024"
    monkeypatch.setattr(sys, "argv", [
        "mmibkr_private_test_probe_v1.py",
        "--source-root", "/synthetic",
        "--source-materialization", "/synthetic/source.json",
        "--source-ref", "a" * 40,
        "--test-modules", "tests.test_lifecycle_single_flat_roundtrip_product_20261023",
    ])
    import mmibkr_private_test_probe_v1 as probe
    monkeypatch.setattr(probe, "run_probe", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("private/" + sentinel)))
    assert main() == 1
    out = capsys.readouterr()
    assert out.err == ""
    assert sentinel not in out.out + out.err
    import json
    assert json.loads(out.out.splitlines()[0].split("=", 1)[1]) == {
        "schema": SCHEMA, "status": "REJECTED",
    }


def test_private_test_trust_mode_required_before_source_for_both_triggers():
    assert validate_compute_requirements({"trust_mode": "public_encrypted"}) == "public_encrypted"
    for denied in (None, "", [], {}, {"trust_mode": None}, {"trust_mode": "local"},
                   {"trust_mode": "public_encrypted", "executor": "untrusted"}):
        with pytest.raises(ValueError):
            validate_compute_requirements(denied)
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
                / "mmibkr-private-test-probe-r1.yml").read_text(encoding="utf-8")
    assert "DISPATCH_TRUST_MODE: ${{ inputs.trust_mode }}" in workflow
    assert 'requirements = node.get("compute_requirements")' in workflow
    assert "trust_mode = validate_compute_requirements(requirements)" in workflow
    assert workflow.index("trust_mode = validate_compute_requirements(requirements)") < workflow.index(
        'with Path(os.environ["GITHUB_ENV"]).open')
    assert workflow.index("trust_mode = validate_compute_requirements(requirements)") < workflow.index(
        "- name: Materialize exact private MM source from encrypted Source Vault")


def test_public_probe_workflow_validates_all_env_inputs_before_write():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github" / "workflows" / "mmibkr-private-test-probe-r1.yml"
    ).read_text(encoding="utf-8")
    assert "modules = \",\".join(validated_modules(modules))" in workflow
    assert "ui_acceptance = validate_acceptance_file(ui_acceptance)" in workflow
    assert "private probe parity key encoding rejected" in workflow
    assert workflow.index('modules = ",".join(validated_modules(modules))') < workflow.index('with Path(os.environ["GITHUB_ENV"]).open')


def test_exact_readonly_open_order_observation_is_networkless_and_nonauthoritative():
    module = "tests.test_cloud_operator_open_orders_truth_product_20261024"
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-test-image", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)
    for forbidden in (
        "tests.test_cloud_operator_open_orders_truth_product_20261024_live_submit",
        "tests.test_cloud_operator_open_orders_live_submit",
    ):
        with pytest.raises(ValueError):
            validated_modules(forbidden)


def test_exact_account_scope_operator_snapshot_is_networkless():
    module = "tests.test_cloud_operator_snapshot_v1"
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-test-image", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)
    for forbidden in ("tests.test_cloud_operator_snapshot_v1_live_submit", "tests.test_cloud_operator_snapshot_v1_broker_mutation"):
        with pytest.raises(ValueError):
            validated_modules(forbidden)


def test_exact_prebuilt_builder_scale_guard_networkless_and_fail_closed():
    module="tests.test_builder_prebuilt_group_logic_guard_product_20261023"
    assert validated_modules(module)==[module]
    command=pytest_container_command("sealed-test-image",module)
    assert command[:5]==["docker","run","--rm","--network","none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1]==module_file_path(module)
    for denied in (module+"_live_submit",module+"_broker_mutation",module+"_extra"):
        with pytest.raises(ValueError):
            validated_modules(denied)

def test_exact_unhashed_builder_feature_authority_is_networkless_and_fail_closed():
    # Only the already-reviewed Product #1039 synthetic feature-identity test.
    module = "tests.test_builder_prebuilt_feature_authority_product_20261025"
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-test-image", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)
    for denied in (
        module + "_live_submit", module + "_broker_mutation", module + "_extra",
        module + ".py", "tests.test_builder_prebuilt_feature_authority_unreviewed",
        "../tests.test_builder_prebuilt_feature_authority_product_20261025",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_b1_initial_backfill_ingest_is_networkless_and_nonmutating():
    # The private B1 module validates read-only handoff rows before cache writes.
    # It must never acquire a broker connection or enable live execution.
    module = "tests.test_selected_runtime_initial_backfill_ingest_v1"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (
        "tests.test_selected_runtime_initial_backfill_ingest_v1_live_submit",
        "tests.test_selected_runtime_initial_backfill_ingest_v1_extra",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_selected_b1_ohlcv_domain_product_regression_is_exact_and_networkless():
    # Reuse the canonical selected-source private test route. No broker client.
    module = "tests.test_selected_runtime_initial_backfill_ohlcv_domain_product_20261024"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (module + "_live_submit", module + "_broker_mutation",
                     module + "_extra", "tests.test_selected_runtime_initial_backfill_ohlcv_domain_product_20261024.py"):
        with pytest.raises(ValueError):
            validated_modules(rejected)


def test_selected_account_margin_guard_and_hook_are_exact_networkless():
    exact = (
        "tests.test_selected_runtime_margin_guard_14th31lg",
        "tests.test_selected_runtime_margin_whatif_hook_14th31lg",
    )
    assert validated_modules(" ".join(exact)) == list(exact)
    for module in exact:
        cmd = pytest_container_command("sealed-test-image", module)
        assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in cmd
        assert cmd[-1] == module_file_path(module)
    for denied in ("tests.test_selected_runtime_margin_guard_14th31lg_live_submit",
                   "tests.test_selected_runtime_margin_whatif_hook_14th31lg_extra"):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_one_shot_generator_funded_pnl_module_is_networkless():
    module = "tests.test_capital_generator_ledger_integrity_product_20261024"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (
        module + "_live_submit",
        "tests.test_capital_generator_ledger_integrity_product_20261024_extra",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)

def test_exact_cross_filter_execid_conflict_falsifier_is_networkless_and_nonmutating():
    module = "tests.test_execid_cross_filter_conflict_product"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (
        module + "_live_submit",
        module + "_extra",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)

def test_exact_missing_broker_execid_is_networkless_and_fail_closed():
    # Selected P0 Product #1022: no broker socket or mutation from source-only test.
    module = "tests.test_missing_execid_identity_product_20261024"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (
        module + "_live_submit",
        module + "_extra",
        "tests.test_missing_execid_identity_product_20261024.py",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)

def test_exact_open_position_mtm_unavailable_is_networkless_and_nonmutating():
    # Selected financial #911: missing chart marks cannot become false zero exposure.
    module = "tests.test_capital_curve_fill_time_identity_product_20261024"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert any(cmd[i:i+2] == ["--network", "none"] for i in range(len(cmd)-1))
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (
        module + "_live_submit",
        module + "_extra",
        "tests.test_capital_curve_fill_time_identity_product_20261024.py",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)

def test_exact_pnl_malformed_chart_rows_are_networkless_and_nonmutating():
    # Selected funded PnL #911 chart-source integrity, no broker/account writes.
    module = "tests.test_capital_malformed_chart_rows_product_20261024"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (module + "_live_submit", module + "_extra",
                     "tests.test_capital_malformed_chart_rows_product_20261024.py"):
        with pytest.raises(ValueError):
            validated_modules(rejected)

def test_exact_stock_intraday_coverage_is_brokerless_and_networkless():
    # Native stock/derived range integrity uses mocked DataManager source only.
    module = "tests.test_stock_range_intraday_coverage_product_20261024"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (module + "_live_submit", module + "_extra",
                     "tests.test_stock_range_intraday_coverage_product_20261024.py"):
        with pytest.raises(ValueError):
            validated_modules(rejected)

@pytest.mark.parametrize("field", (
    "crw_consumer_reprobe", "s3_composition_economics", "s4_layered_mtf_economics",
))
def test_push_fire_optional_flags_require_native_json_booleans(field):
    assert validate_native_fire_boolean({}, field) is False
    assert validate_native_fire_boolean({field: True}, field) is True
    assert validate_native_fire_boolean({field: False}, field) is False
    for invalid in ("false", "true", 0, 1, None, [], {}):
        with pytest.raises(ValueError, match="private_probe_fire_boolean_type_invalid"):
            validate_native_fire_boolean({field: invalid}, field)
    with pytest.raises(ValueError, match="private_probe_fire_boolean_field_unsupported"):
        validate_native_fire_boolean({field: False}, "arbitrary_flag")


def test_push_fire_workflow_uses_native_boolean_gate_before_env_publication():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
                / "mmibkr-private-test-probe-r1.yml").read_text(encoding="utf-8")
    for field in ("crw_consumer_reprobe", "s3_composition_economics", "s4_layered_mtf_economics"):
        assert f'validate_native_fire_boolean(node, "{field}")' in workflow
        assert f'bool(node.get("{field}"))' not in workflow
    assert workflow.index('validate_native_fire_boolean(node, "crw_consumer_reprobe")') < workflow.index(
        'with Path(os.environ["GITHUB_ENV"]).open')

def test_exact_futures_multiplier_invalid_funded_pnl_is_networkless():
    # Exact selected PnL #911: malformed explicit MNQ multiplier never becomes economics.
    module = "tests.test_capital_explicit_futures_multiplier_failclose_product_20261024"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    for rejected in (
        module + "_live_submit",
        module + "_extra",
        "tests.test_capital_explicit_futures_multiplier_failclose_product_20261024.py",
    ):
        with pytest.raises(ValueError):
            validated_modules(rejected)

def test_exact_selected_p0_execution_inventory_and_funded_cost_modules_are_networkless():
    # Exact already-selected private source tests, no broker or live mutation.
    for module in (
        "tests.test_completed_execution_fields_product_20261024",
        "tests.test_strategy_inventory_same_execid_conflict_product_20261024",
        "tests.test_capital_invalid_cost_schedule_product_20261024",
    ):
        assert validated_modules(module) == [module]
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for rejected in (module + "_live_submit", module + "_extra", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(rejected)



def test_exact_stock_warmup_readiness_modules_networkless():
    # Selected #888/#975 source-only warmup count and status projection tests.
    exact = (
        "tests.test_stock_warmup_count_product_20261025",
        "tests.test_stock_warmup_status_projection_product_20261025",
    )
    assert validated_modules(" ".join(exact)) == list(exact)
    for module in exact:
        cmd = pytest_container_command("sealed-test-image", module)
        assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in cmd
        assert cmd[-1] == module_file_path(module)
    for denied in (
        "tests.test_stock_warmup_count_product_20261025_live_submit",
        "tests.test_stock_warmup_status_projection_product_20261025_extra",
        "tests.test_stock_warmup_count_product_20261025.py",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_builder_pending_and_futures_conid_warmup_modules_networkless():
    # Existing selected #888 and #924 changed-source tests only, no broker.
    exact = (
        "tests.test_crw_builder_backtest_dca_dual_ledger_14th31jt",
        "tests.test_signal_history_warmup_exact_conid_product_20261024",
    )
    assert validated_modules(" ".join(exact)) == list(exact)
    for module in exact:
        cmd = pytest_container_command("sealed-test-image", module)
        assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in cmd
        assert cmd[-1] == module_file_path(module)
    for denied in (
        "tests.test_crw_builder_backtest_dca_dual_ledger_14th31jt_broker_submit",
        "tests.test_signal_history_warmup_exact_conid_product_20261024_live",
        "tests.test_signal_history_warmup_exact_conid_product_20261024.py",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_new_market_builder_and_funded_pnl_modules_networkless():
    # Release-selected #975/#911: pure private-source tests, never a broker client.
    exact = (
        "tests.test_market_data_invalid_explicit_now_product_20261024",
        "tests.test_builder_literal_rhs_finite_product_20261025",
        "tests.test_capital_oversized_numeric_failclosed_product_20261025",
    )
    assert validated_modules(",".join(exact)) == list(exact)
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
    for denied in (
        "tests.test_market_data_invalid_explicit_now_product_20261024_extra",
        "tests.test_builder_literal_rhs_finite_product_20261025_live_submit",
        "tests.test_capital_oversized_numeric_failclosed_product_20261025_broker",
        "tests.test_capital_oversized_numeric_failclosed_product_20261025.py",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_reviewed_builder_apply_packet_guard_networkless_only():
    # Product #1042 current 20/20 brokerless source accepted; selected #888/#975.
    exact = "tests.test_reviewed_apply_packet_safety_product_20261025"
    assert validated_modules(exact) == [exact]
    command = pytest_container_command("sealed-test-image", exact)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(exact)
    for denied in (
        exact + "_live_submit", exact + "_extra", exact + ".py",
        "tests.test_reviewed_apply_packet_broker_writer_20261025",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_selected_ui_admitted_futures_and_funded_utc_modules_networkless_only():
    # Selected MM #888 source-only Product #1049/#1050, never broker/runtime.
    exact = (
        "tests.test_admitted_futures_source_strict_identity_product_20261025",
        "tests.test_capital_timestamp_binding_product_20261025",
    )
    assert validated_modules(",".join(exact)) == list(exact)
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for denied in (module + "_extra", module + "_live_submit", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(denied)


def test_selected_financial_strict_decimal_economic_input_networkless_only():
    # Exact selected #911/#1052 pure funded parser, not a broker test.
    module = "tests.test_capital_strict_decimal_economic_input_product_20261025"
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-test-image", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)
    for denied in (
        module + "_extra", module + "_live_submit", module + "_broker", module + ".py",
    ):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_selected_builder_futures_financial_source_modules_networkless_only():
    # Exact selected #888@f9ac, #924@3ba, #911@83c source-only regressions.
    # Public allowlist acceptance is NOT selected private execution or PLACED.
    exact = (
        "tests.test_registry_builder_condition_execution_14th31kn",
        "tests.test_futures_signal_only_execution_authority_product_20261025",
        "tests.test_lifecycle_strict_broker_numeric_product_20261025",
    )
    assert validated_modules(",".join(exact)) == list(exact)
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for denied in (module + "_live_submit", module + "_extra", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(denied)


def test_selected_p0_strict_numeric_caps_and_margin_networkless_only():
    # Selected #1053 risk/account money pure-source tests, no broker writer.
    exact = (
        "tests.test_selected_runtime_sizing_strict_numeric_caps_product_20261025",
        "tests.test_selected_runtime_margin_strict_money_product_20261025",
    )
    assert validated_modules(",".join(exact)) == list(exact)
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for denied in (module + "_extra", module + "_live_submit", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(denied)


def test_selected_new_builder_shape_and_native_decimal_modules_networkless_only():
    # Exact selected #888@492a and #911@d453 source-only modules.
    # This checks public admission contract, not execution of private tests.
    exact = (
        "tests.test_builder_parameter_shape_product_20261025",
        "tests.test_capital_native_decimal_underflow_product_20261025",
    )
    assert validated_modules(",".join(exact)) == list(exact)
    for module in exact:
        command = pytest_container_command("sealed-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for denied in (module + "_live_submit", module + "_extra", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(denied)


def test_exact_builder_reviewed_http_apply_routes_are_networkless_and_fail_closed():
    module = "tests.test_builder_review_http_route_binding_product_20261025"
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-test-image", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)
    for denied in (module + "_live_submit", module + "_broker_mutation", module + "_extra",
                   module + ".py", "../" + module):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_legacy_autotuner_prefix_cannot_get_network():
    # The historical prefix admits more than the exact selected module set.
    # A private-source test must never gain network egress just by selecting
    # another syntactically permitted autotuner module name.
    for module in (
        "tests.test_autotuner_strategy_family_catalog_vnext",
        "tests.test_autotuner_future_synthetic",
    ):
        assert validated_modules(module) == [module]
        command = pytest_container_command("sealed-private-test-image", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
    with pytest.raises(ValueError):
        validated_modules("tests.test_autotuner_live_submit")


def test_selected_975_new_source_only_modules_exact_networkless_and_no_aliases():
    # Exact Product/Research postimages consumed by selected broad #975.
    # This only validates public probe admission, not private test execution.
    modules = (
        "tests.test_selected_runtime_forward_execution_lifecycle_v1",
        "tests.test_selected_runtime_forward_lifecycle_ledger_failclosed_product_20261027",
        "tests.test_cc44_source_cache_first_12m_r1",
        "tests.test_cc44_source_cache_session_gap_guard_r1",
        "tests.test_builder_cross_lane_condition_ids_product_20261027",
        "tests.test_strategy_builder_review_apply",
        "tests.test_strategy_builder_review_guard",
        "tests.test_mnq_dca_event_export",
        "tests.test_mnq_dca_path_outcomes",
    )
    assert validated_modules(",".join(modules)) == list(modules)
    for module in modules:
        command = pytest_container_command("sealed-selected-source-only", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for rejected in (module + "_extra", module + "_live_submit", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(rejected)


def test_selected_builder_prebuilt_timeframe_exact_networkless_only():
    # Exact #975 Builder cadence guard: public admission only, never broker execution.
    module = "tests.test_builder_prebuilt_timeframe_identity_product_20261027"
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-selected-builder", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)
    for denied in (module + "_extra", module + "_live_submit", module + ".py", "../" + module):
        with pytest.raises(ValueError):
            validated_modules(denied)


def test_exact_builder_preview_semantic_writer_guard_is_networkless_and_allowlisted():
    module = "tests.test_strategy_builder_review_preview_semantic_20261027"
    assert validated_modules(module) == [module]
    cmd = pytest_container_command("sealed-test-image", module)
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in cmd
    assert cmd[-1] == module_file_path(module)
    with pytest.raises(ValueError):
        validated_modules("tests.test_strategy_builder_review_preview_semantic_untrusted")


def test_selected_p0_forward_new_exact_modules_networkless_only():
    # Exact selected source guards; this tests public admission, not private execution.
    modules = (
        "tests.test_selected_runtime_live_incumbent_preflight_v1",
        "tests.test_selected_runtime_forward_completed_trade_admission_v1",
        "tests.test_selected_runtime_cloud_daemon_v1",
        "tests.test_selected_runtime_futures_roll_maintenance_v1",
    )
    assert validated_modules(",".join(modules)) == list(modules)
    for module in modules:
        command = pytest_container_command("sealed-selected-source-only", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for denied in (module + "_extra", module + "_live_submit", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(denied)


def test_selected_p0_privacy_risk_followons_exact_networkless_only():
    # Admission is source-only; no private job placement or broker authority.
    modules = (
        "tests.test_operator_lifecycle_snapshot_privacy_product_20261027",
        "tests.test_selected_runtime_live_preflight_risk_roll_product_20261027",
        "tests.test_live_canary_exact_contract_identity_product_20261027",
        "tests.test_active_runtime_identity_failclosed_product_20261027",
        "tests.test_selected_runtime_forward_execution_lifecycle_v1",
        "tests.test_selected_runtime_forward_partial_capture_product_20261027",
        "tests.test_forward_exact_tick_contract_integrity_product_20261027",
    )
    assert validated_modules(",".join(modules)) == list(modules)
    for module in modules:
        command = pytest_container_command("sealed-selected-p0-privacy-risk", module)
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert "ENABLE_LIVE_TRADING=0" in command
        assert command[-1] == module_file_path(module)
        for rejected in (module + "_extra", module + "_live_submit", module + "_broker", module + ".py"):
            with pytest.raises(ValueError):
                validated_modules(rejected)

def test_exact_product_1302_pilot_funded_capital_receipt_is_networkless_only():
    # Existing Promotion Review/Pilot receipt consumer, never a promotion issuer.
    module = "tests.test_pilot_capital_context_failclosed_product_20261027"
    assert validated_modules(module) == [module]
    command = pytest_container_command("sealed-selected-pilot-capital", module)
    assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "ENABLE_LIVE_TRADING=0" in command
    assert command[-1] == module_file_path(module)
    for denied in (module + "_extra", module + "_live_submit", module + "_promote", module + ".py"):
        with pytest.raises(ValueError):
            validated_modules(denied)
