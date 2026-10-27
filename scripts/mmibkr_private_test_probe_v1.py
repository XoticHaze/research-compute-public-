from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any


class _PublicSafeArgumentParser(argparse.ArgumentParser):
    """Reject public CLI errors without echoing private caller input."""

    def __init__(self) -> None:
        super().__init__(add_help=False)

    def error(self, _message: str) -> None:
        raise ValueError("invalid_public_test_probe_arguments")


SCHEMA = "mmibkr.private_test_probe_receipt.v1"
PYTEST_VERSION = "8.4.2"
MODULE_RE = re.compile(r"^tests\.test_[A-Za-z0-9_]+$")
FIRE_BOOLEAN_FIELDS = frozenset({
    "crw_consumer_reprobe", "s3_composition_economics", "s4_layered_mtf_economics",
})


def validate_native_fire_boolean(node: dict[str, Any], field: str) -> bool:
    """Fail closed optional push-fire flags before private-source admission."""
    if field not in FIRE_BOOLEAN_FIELDS:
        raise ValueError("private_probe_fire_boolean_field_unsupported")
    value = node.get(field, False)
    if type(value) is not bool:
        raise ValueError("private_probe_fire_boolean_type_invalid")
    return value


SAFE_PREFIXES = (
    "tests.test_autotuner_",
)
# Exact brokerless source/ledger regressions. No gateway credentials or broker calls.
# These modules are run network-isolated even inside the existing public probe.
SOURCE_ONLY_P0_MODULES = frozenset({
    "tests.test_legacy_submit_fail_closed_r10",
    "tests.test_legacy_strategy_live_guard_r11",
    "tests.test_selected_runtime_mutation_boundary_inspect_v1",
    "tests.test_live_seal_compose_runner_v1",
    # Brokerless exact successor ledger tests; never permit test network I/O.
    "tests.test_ibkr_live_successor_ledger_reconcile_v1",
    # Exact canonical read-only same-contract execId conflict falsifier; no broker I/O.
    "tests.test_execid_cross_filter_conflict_product",
    # Reject missing/non-native immutable broker execId before any order filter.
    "tests.test_missing_execid_identity_product_20261024",
    # Exact selected P0 #883 brokerless invalid native execution fields (#1030).
    "tests.test_completed_execution_fields_product_20261024",
    # Selected P0 #883 Product #1033: same execId cannot change persisted economics.
    "tests.test_strategy_inventory_same_execid_conflict_product_20261024",
    # Exact source-only P0 journal / fill validator / same-owner broker readback.
    "tests.test_selected_runtime_live_order_intent_journal_v1",
    "tests.test_selected_runtime_live_execution_ledger_v1",
    "tests.test_selected_runtime_live_broker_provenance_v1",
    "tests.test_selected_runtime_live_p0_integrated_checkpoint_v1",
    "tests.test_selected_runtime_live_owner_candidate_certificate_v1",
    # Brokerless selected-account what-if guard/hook tests must not access a network.
    "tests.test_selected_runtime_margin_guard_14th31lg",
    "tests.test_selected_runtime_margin_whatif_hook_14th31lg",
    # Exact synthetic Pi Docker endpoint-locality preflight; no daemon/broker access.
    "tests.test_ibkr_persistent_host_preflight_v1",
    # New exact paper post-execution quarantine regression, no broker access.
    "tests.test_selected_runtime_cloud_cycle_v1",
    # Exact canonical read-only B1 initial-backfill contract integrity, brokerless.
    "tests.test_selected_runtime_initial_backfill_ingest_v1",
    # Exact native-int selected execution conId denial before B1 cache or artifact access.
    "tests.test_selected_runtime_initial_backfill_selected_conid_product_20261025",
    # Exact selected P0 #1053 sizing and margin money guards; no broker/network.
    "tests.test_selected_runtime_sizing_strict_numeric_caps_product_20261025",
    "tests.test_selected_runtime_margin_strict_money_product_20261025",
    # Selected P0 B1 OHLCV and negative-volume fail-close, exact synthetic test.
    "tests.test_selected_runtime_initial_backfill_ohlcv_domain_product_20261024",
    "tests.test_selected_runtime_terminal_ledger_corruption_product_20261024",
    "tests.test_selected_runtime_strategy_inventory_unverified_receipt_product_20261024",
    # Native stock intraday/derived coverage test is brokerless AND networkless.
    "tests.test_stock_range_intraday_coverage_product_20261024",
    # Explicit invalid as-of must not silently select current wall time.
    "tests.test_market_data_invalid_explicit_now_product_20261024",
    # Counted pre-start warmup and status readiness remain source-only and brokerless.
    "tests.test_stock_warmup_count_product_20261025",
    "tests.test_stock_warmup_status_projection_product_20261025",
    # Exact selected Builder simulated next-open ledger and futures conId warmup.
    "tests.test_crw_builder_backtest_dca_dual_ledger_14th31jt",
    "tests.test_signal_history_warmup_exact_conid_product_20261024",
    # Exact selected-account position snapshot safety regression, networkless.
    "tests.test_cloud_operator_snapshot_v1",
    # Read-only account open-order completeness projection, never a broker consumer.
    "tests.test_cloud_operator_open_orders_truth_product_20261024",
    # Exact new flat-seed broker residue regression, synthetic and brokerless.
    "tests.test_live_broker_position_residue_product_20261024",
    # Exact operator snapshot contract identity, brokerless synthetic tests.
    "tests.test_cloud_operator_exact_contract_position_product_20261024",
})

SAFE_EXACT = {
    "tests.test_strategy_backtest_registry_dispatch",
    "tests.test_canonical_data_materialize_v1",
    "tests.test_selected_runtime_strategy_spec_integrity_v1",
    "tests.test_model_lab_canonical_data_authority_cc44",
    "tests.test_model_lab_training_matrix_authority_cc44",
    "tests.test_model_lab_canonical_trainer",
    "tests.test_model_lab_xgboost",
    "tests.test_model_lab_comparison_matrix_authority_cc44",
    "tests.test_model_lab_validation_authority_cc44",
    "tests.test_data_manager_indicator_context_contract_14th31jq",
    "tests.test_data_manager_registry_authority_14th31lm",
    "tests.test_historical_source_stitch",
    "tests.test_external_history_admitted_ingest_contract",
    "tests.test_materialize_admitted_stock_source_canonical",
    "tests.test_market_features_provenance_contract",
    "tests.test_backtest_range_contract_14th31im",
    "tests.test_publish_canonical_feature_sidecar",
    "tests.test_materialize_admitted_futures_source_canonical",
    "tests.test_materialize_admitted_futures_dated_contract",
    "tests.test_crw_tradingview_dual_execution_replay_14th31js",
    "tests.test_builder_feature_rhs_comparison_14th31ky",
    "tests.test_strategy_spec_mtf_registry_backtest_vnext",
    "tests.test_parameterized_indicator_instances_14th31kp",
    "tests.test_per_indicator_timeframe_execution_core_14th31kq",
    "tests.test_builder_cross_timeframe_aligned_evaluation_14th31ks",
    "tests.test_strategy_spec_source_feature_materialization_14th31kr",
    "tests.test_s4_layered_mtf_matched_control_economics_20261004",
    "tests.test_crw_backtest_futures_timestamp_14th31kf",
    "tests.test_news_publication_time_integrity_20260902",
    "tests.test_news_publication_time_integration_patch_20260902",
    "tests.test_news_scorecard_cycle_break_14th31fd_r18",
    "tests.test_options_snapshot_analysis",
    "tests.test_options_snapshot_features",
    # Exact research/accounting regressions. These modules are side-effect-free
    # validation consumers; selected_runtime names are admitted only by exact ID.
    "tests.test_backtest_capital_replay_v1",
    "tests.test_selected_runtime_account_sizing_14th31lg",
    "tests.test_selected_runtime_account_sizing_submit_hook_14th31lg",
    "tests.test_selected_runtime_margin_guard_14th31lg",
    "tests.test_selected_runtime_margin_whatif_hook_14th31lg",
    "tests.test_selected_runtime_forward_historical_tick_producer_v1",
    "tests.test_selected_runtime_forward_exact_extrema_v1",
    "tests.test_research_survivor_funnel",
    "tests.test_crw_consumer_observation_capture_20261003",
    "tests.test_s3_composition_matched_control_economics_20261003",
    "tests.test_acquire_hfdl_bounded_equity_panel",
    # Exact read-only Promotion Review / Pilot audit-boundary regressions.
    # These exercise durable decision records and HTTP presentation only; they
    # do not mutate selected runtime, broker state, StrategySpec, or live authority.
    "tests.test_promotion_review_store",
    "tests.test_autotuner_promotion_review_backend_product",
    "tests.test_operator_snapshot_api",
    "tests.test_cloud_operator_snapshot_v1",
    "tests.test_selected_runtime_strategy_inventory_v1",
    "tests.test_promotion_review_stale_status",
    "tests.test_research_ui_backend_restore",
    "tests.test_admit_exact_pilot_to_promotion_review_13z",
    "tests.test_ibkr_remote_forward_exact_ticks_slot_v1",
    "tests.test_ibkr_remote_account_hygiene_slot_v1",
    # Exact production-live migration regressions. These tests execute only
    # pure/account-context logic and source/AST assertions with
    # ENABLE_LIVE_TRADING=0; they do not connect to IBKR or mutate broker state.
    "tests.test_ibkr_account_context",
    "tests.test_ibkr_production_live_account_context_v1",
    "tests.test_selected_runtime_submit_authority",
    "tests.test_paper_flatten_canonical_route_authority_667",
    # Pure scheduler/dry-plan builders with no broker client or live enable.
    "tests.test_selected_runtime_cloud_bar_clock_v1",
    "tests.test_selected_runtime_cloud_runner_dry_plan_v1",
    # Exact new selected #975 source-only regression modules, all networkless.
    # Admission of test names is not a trusted placement or private execution.
    "tests.test_selected_runtime_forward_execution_lifecycle_v1",
    "tests.test_selected_runtime_forward_lifecycle_ledger_failclosed_product_20261027",
    "tests.test_cc44_source_cache_first_12m_r1",
    "tests.test_cc44_source_cache_session_gap_guard_r1",
    "tests.test_builder_cross_lane_condition_ids_product_20261027",
    "tests.test_strategy_builder_review_apply",
    "tests.test_strategy_builder_review_guard",
    # Exact canonical Builder Preview semantic write-gate regression, brokerless.
    "tests.test_strategy_builder_review_preview_semantic_20261027",
    "tests.test_mnq_dca_event_export",
    "tests.test_mnq_dca_path_outcomes",
}

# Exact selected Model Lab cancellation/identity regressions from MM-IBKR
# UI composite #888. Tests are brokerless; run with no network to prevent
# accidental external worker/model traffic. No generic module-name wildcard.
SOURCE_ONLY_MODEL_LAB_MODULES = frozenset({
    "tests.test_model_lab_cancel_process_identity_product",
    "tests.test_model_lab_cancel_terminal_race_product",
    "tests.test_model_lab_orchestrator_identity_authority_product",
    "tests.test_model_lab_startup_status_race_product",
    "tests.test_model_lab_worker_early_cancel_product",
})
SAFE_EXACT.update(SOURCE_ONLY_P0_MODULES)
# Exact synthetic lifecycle after-cost PnL: no broker or network access.
SOURCE_ONLY_PNL_MODULES = frozenset({
    "tests.test_lifecycle_single_flat_roundtrip_product_20261023",
    # Exact new Product source-only decimal residue and matched-fill-count guards.
    "tests.test_lifecycle_decimal_flatness_product_20261024",
    "tests.test_lifecycle_matched_fill_count_truth_product_20261024",
    # Exact selected source-only regression; Docker network disabled.
    "tests.test_lifecycle_strict_broker_numeric_product_20261025",
    "tests.test_capital_adjusted_price_explicit_failclose_product_20261024",
    # Exact pure futures multiplier fail-close; selected funded PnL #911 source-only.
    "tests.test_capital_explicit_futures_multiplier_failclose_product_20261024",
    # Exact selected funded PnL malformed canonical fill/fallback input fail-close.
    "tests.test_capital_fill_ledger_integrity_product_20261024",
    # One-shot fill/trade generator malformed-row fail-close, pure funded PnL.
    "tests.test_capital_generator_ledger_integrity_product_20261024",
    # Open-position without a chart mark must fail closed, with network disabled.
    "tests.test_capital_curve_fill_time_identity_product_20261024",
    # Exact funded PnL malformed chart-source row fail-close; offline only.
    "tests.test_capital_malformed_chart_rows_product_20261024",
    # Exact selected funded PnL #911 malformed cost schedule (#1032).
    "tests.test_capital_invalid_cost_schedule_product_20261024",
    # Exact funded PnL oversized numeric fail-close, no live/broker inputs.
    "tests.test_capital_oversized_numeric_failclosed_product_20261025",
    # Exact selected financial #911 strict decimal economic input; offline only.
    "tests.test_capital_strict_decimal_economic_input_product_20261025",
    # Exact selected #911 native Decimal nonzero underflow cost fail-close.
    "tests.test_capital_native_decimal_underflow_product_20261025",
    # Selected UI #888 exact UTC fill/chart identity, no broker or network.
    "tests.test_capital_timestamp_binding_product_20261025",
})
SAFE_EXACT.update(SOURCE_ONLY_MODEL_LAB_MODULES)
SAFE_EXACT.update(SOURCE_ONLY_PNL_MODULES)
# Signed Foundry qualification / Pilot quarantine is an exact offline test only.
SOURCE_ONLY_MODEL_ISSUER_MODULES = frozenset({
    "tests.test_foundry_model_promotion_admission_v1",
    # Exact signed limited FORWARD_SANITY boundary and non-approvable stage.
    "tests.test_foundry_model_limited_forward_sanity_product_20261024",
    # Exact GET-only Promotion Review transport and stale-state regression.
    "tests.test_promotion_review_get_http_current_product_20261024",
    # Exact model-native forward identity adapter/preview/Arena/binder regressions; brokerless.
    "tests.test_foundry_model_order_intent_adapter_v1",
    "tests.test_foundry_model_arena_executor_conformance_v1",
    "tests.test_foundry_model_canonical_preview_conformance_v1",
    "tests.test_foundry_model_runtime_binding_v1",
})
SAFE_EXACT.update(SOURCE_ONLY_MODEL_ISSUER_MODULES)
# Exact prebuilt Builder scale and feature-identity guards are pure canonical evaluation.
# Only these two brokerless modules run, always with Docker network disabled.
SOURCE_ONLY_BUILDER_MODULES = frozenset({
    "tests.test_builder_prebuilt_group_logic_guard_product_20261023",
    "tests.test_builder_prebuilt_feature_authority_product_20261025",
    # Exact selected source-only regression; Docker network disabled.
    "tests.test_registry_builder_condition_execution_14th31kn",
    # Exact selected #888 malformed Builder parameter/source_fields fail-close.
    "tests.test_builder_parameter_shape_product_20261025",
    # Enabled literal RHS must reject blank/NaN/inf without zero substitution.
    "tests.test_builder_literal_rhs_finite_product_20261025",
    # Exact reviewed apply-packet broker/live and identity guard, synthetic writer only.
    "tests.test_reviewed_apply_packet_safety_product_20261025",
    # Exact #1076 server-side reviewed Builder HTTP write gate, synthetic/no broker.
    "tests.test_builder_review_http_route_binding_product_20261025",
    # Selected #975 Product #1267/#1269 prebuilt and fresh cadence alias guards.
    "tests.test_builder_prebuilt_timeframe_identity_product_20261027",
})
SAFE_EXACT.update(SOURCE_ONLY_BUILDER_MODULES)
# Exact selected #888 admitted futures row-identity synthetic test, no external data.
SOURCE_ONLY_MARKET_DATA_MODULES = frozenset({
    # Exact #1132 synthetic, signed read-only OHLCV admission tests only.
    # This is NOT the B1 producer or a live/paper broker-session test.
    "tests.test_ibkr_remote_readonly_market_data_consumer_v1",
    "tests.test_admitted_futures_source_strict_identity_product_20261025",
    # Exact selected source-only regression; Docker network disabled.
    "tests.test_futures_signal_only_execution_authority_product_20261025",
})
SAFE_EXACT.update(SOURCE_ONLY_MARKET_DATA_MODULES)
# Exact brokerless selected #975 Product regressions, never a live broker
# probe. Each is source-only and must run inside the networkless test container.
SOURCE_ONLY_SELECTED_PRODUCT_MODULES = frozenset({
    "tests.test_autotuner_parameter_consumption",
    "tests.test_capital_timestamp_binding_product_20261026",
    "tests.test_cloud_operator_snapshot_forward_root_binding_product_20261026",
    "tests.test_cloud_operator_snapshot_health_adapter_v1",
    "tests.test_cloud_operator_snapshot_inventory_readonly_product_20261027",
    "tests.test_crw_backtest_rth_asset_contract_product_20261027",
    "tests.test_survivor_paper_trade_evidence_materializer_v1",
    "tests.test_futures_range_tail_coverage_product_20261027",
    "tests.test_market_feed_range_orchestration_14th31ix",
    # Exact selected P0/forward source-only regressions; no broker credentials or network.
    "tests.test_selected_runtime_live_incumbent_preflight_v1",
    "tests.test_selected_runtime_forward_completed_trade_admission_v1",
    "tests.test_selected_runtime_cloud_daemon_v1",
    # Exact selected #1275 futures-roll cutoff fail-close, mocked/read-only only.
    "tests.test_selected_runtime_futures_roll_maintenance_v1",
})
SAFE_EXACT.update(SOURCE_ONLY_SELECTED_PRODUCT_MODULES)
STATUS_STAGE_MODULES = {
    "tests.test_market_features_provenance_contract",
}

DENY_TOKENS = (
    "broker",
    "ibkr",
    "live",
    "submit",
    "flatten",
    "cancel",
    "selected_runtime",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError("source_materialization_not_object")
    return node


def validate_compute_requirements(raw: Any) -> str:
    """Fail closed on absent, extra or non-approved external compute trust."""
    if not isinstance(raw, dict) or set(raw) != {"trust_mode"}:
        raise ValueError("private_test_compute_requirements_invalid")
    if raw["trust_mode"] != "public_encrypted":
        raise ValueError("private_test_compute_trust_mode_rejected")
    return "public_encrypted"


def validated_modules(raw: str) -> list[str]:
    values = [
        value.strip()
        for value in re.split(r"[\s,]+", str(raw or ""))
        if value.strip()
    ]
    if not values:
        raise ValueError("test_modules_required")
    out: list[str] = []
    for module in values:
        if not MODULE_RE.fullmatch(module):
            raise ValueError("test_module_rejected")
        if module in SAFE_EXACT:
            if module not in out:
                out.append(module)
            continue
        lowered = module.lower()
        if any(token in lowered for token in DENY_TOKENS):
            raise ValueError("test_module_authority_rejected")
        if not module.startswith(SAFE_PREFIXES):
            raise ValueError("test_module_not_allowlisted")
        if module not in out:
            out.append(module)
    return out


def module_file_path(module: str) -> str:
    """Map one already-validated test module to its repository-relative file."""
    if not MODULE_RE.fullmatch(str(module or "")):
        raise ValueError("test_module_rejected")
    return module.replace(".", "/") + ".py"


def pytest_container_command(image_tag: str, module: str) -> list[str]:
    """Return a shell-free Docker command for one exact pytest module file."""
    return [
        "docker",
        "run",
        "--rm",
        # All admitted tests are source-only/brokerless. Never grant a
        # selected private test module network egress merely because its
        # exact name lacks an authority-sensitive token.
        "--network",
        "none",
        "-e",
        "ENABLE_LIVE_TRADING=0",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        image_tag,
        "python",
        "-m",
        "pytest",
        "-q",
        module_file_path(module),
    ]


def validate_source_identity(
    source_root: Path,
    materialization_path: Path,
    expected_source_ref: str,
) -> dict[str, Any]:
    node = _load_json(materialization_path)
    if node.get("schema") != "mmibkr.attested_source_materialization.v2":
        raise RuntimeError("source_materialization_schema_rejected")
    if node.get("ok") is not True:
        raise RuntimeError("source_materialization_not_ok")
    source_sha = str(node.get("source_sha") or "").lower()
    if len(source_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_sha):
        raise RuntimeError("source_sha_rejected")
    if str(node.get("source_ref") or "") != str(expected_source_ref):
        raise RuntimeError("source_ref_mismatch")
    resolved_root = Path(node.get("source_root") or "").resolve()
    if source_root.resolve() != resolved_root:
        raise RuntimeError("source_root_mismatch")
    if not (source_root / "Dockerfile.bot").is_file():
        raise RuntimeError("source_root_incomplete")
    if node.get("private_repository_token_used") is not False:
        raise RuntimeError("private_repository_token_contract_rejected")
    if node.get("broker_credentials_used") is not False:
        raise RuntimeError("broker_credential_contract_rejected")
    if node.get("plaintext_emitted") is not False:
        raise RuntimeError("plaintext_emission_contract_rejected")
    if node.get("live_execution_allowed") is not False:
        raise RuntimeError("live_execution_contract_rejected")
    if node.get("vault_attestation_verified") is not True:
        raise RuntimeError("vault_attestation_contract_rejected")
    if node.get("source_transport") != "fleet_authority_exact_sha_encrypted_snapshot_vault":
        raise RuntimeError("source_transport_contract_rejected")
    manifest_sha = str(node.get("source_manifest_sha256") or "").lower()
    if len(manifest_sha) != 64 or any(ch not in "0123456789abcdef" for ch in manifest_sha):
        raise RuntimeError("source_manifest_sha_rejected")
    return node


def _run_captured(
    command: list[str],
    *,
    cwd: Path | None,
    env: dict[str, str] | None,
    log_path: Path,
    timeout: int,
) -> dict[str, Any]:
    with log_path.open("wb") as handle:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    digest = _sha256(log_path)
    size = log_path.stat().st_size
    failed_test_node_ids: list[str] = []
    if proc.returncode != 0:
        try:
            safe_text = log_path.read_text(encoding="utf-8", errors="replace")
            for raw in safe_text.splitlines():
                line = raw.strip()
                match = re.match(
                    r"^FAILED\s+(tests/test_[A-Za-z0-9_]+\.py::[A-Za-z0-9_:\[\]().,-]+)",
                    line,
                )
                if match:
                    node_id = match.group(1)
                    if node_id not in failed_test_node_ids:
                        failed_test_node_ids.append(node_id)
        except Exception:
            failed_test_node_ids = []
    try:
        log_path.unlink()
    except FileNotFoundError:
        pass
    return {
        "exit_code": int(proc.returncode),
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "captured_output_sha256": digest,
        "captured_output_bytes": size,
        "failed_test_node_ids": failed_test_node_ids,
    }


def run_probe(
    *,
    source_root: Path,
    source_materialization: Path,
    expected_source_ref: str,
    modules: list[str],
    image_tag: str,
) -> dict[str, Any]:
    identity = validate_source_identity(
        source_root,
        source_materialization,
        expected_source_ref,
    )
    docker_target = (
        "status"
        if any(module in STATUS_STAGE_MODULES for module in modules)
        else "bot"
    )
    with tempfile.TemporaryDirectory(prefix="mmibkr-private-test-probe-") as tmp:
        temp = Path(tmp)
        build = _run_captured(
            [
                "docker",
                "build",
                "-f",
                str(source_root / "Dockerfile.bot"),
                "--target",
                docker_target,
                "-t",
                image_tag,
                str(source_root),
            ],
            cwd=None,
            env=os.environ.copy(),
            log_path=temp / "build.log",
            timeout=1800,
        )
        tester_image_tag = image_tag + "-pytest"
        tester_dockerfile = temp / "Dockerfile.pytest"
        tester_dockerfile.write_text(
            "ARG BASE_IMAGE\n"
            "FROM ${BASE_IMAGE}\n"
            f"RUN python -m pip install --no-cache-dir --disable-pip-version-check pytest=={PYTEST_VERSION}\n",
            encoding="utf-8",
        )
        test_environment = {
            "status": "SKIPPED",
            "pytest_version": PYTEST_VERSION,
            "docker_target": docker_target,
            "captured_output_sha256": None,
            "captured_output_bytes": 0,
            "exit_code": None,
        }
        module_rows: list[dict[str, Any]] = []
        try:
            if build["status"] == "PASS":
                test_environment = _run_captured(
                    [
                        "docker",
                        "build",
                        "-f",
                        str(tester_dockerfile),
                        "--build-arg",
                        f"BASE_IMAGE={image_tag}",
                        "-t",
                        tester_image_tag,
                        str(temp),
                    ],
                    cwd=None,
                    env=os.environ.copy(),
                    log_path=temp / "pytest-image-build.log",
                    timeout=600,
                )
                test_environment["pytest_version"] = PYTEST_VERSION
                test_environment["docker_target"] = docker_target
                if test_environment["status"] == "PASS":
                    for index, module in enumerate(modules, start=1):
                        row = _run_captured(
                            pytest_container_command(tester_image_tag, module),
                            cwd=None,
                            env=os.environ.copy(),
                            log_path=temp / f"module-{index:02d}.log",
                            timeout=600,
                        )
                        module_rows.append(
                            {
                                "module": module,
                                "test_file": module_file_path(module),
                                "runner": "pytest",
                                **row,
                            }
                        )
        finally:
            subprocess.run(
                ["docker", "image", "rm", tester_image_tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

        status = (
            "PASS"
            if build["status"] == "PASS"
            and test_environment["status"] == "PASS"
            and len(module_rows) == len(modules)
            and all(row["status"] == "PASS" for row in module_rows)
            else "FAIL"
        )
        return {
            "schema": SCHEMA,
            "status": status,
            "source_identity": {
                "repository": "XoticHaze/mm-IBKR",
                "source_ref": identity["source_ref"],
                "source_sha": identity["source_sha"],
                "source_archive_sha256": identity["source_archive_sha256"],
                "source_archive_bytes": int(identity["source_archive_bytes"]),
                "source_manifest_sha256": identity.get("source_manifest_sha256"),
                "source_transport": identity.get("source_transport"),
                "vault_attestation_verified": identity.get("vault_attestation_verified") is True,
            },
            "build": build,
            "test_environment": test_environment,
            "test_modules": module_rows,
            "authority": {
                "research_only": True,
                "private_repository_token_used": False,
                "broker_credentials_used": False,
                "broker_request_made": False,
                "broker_action": False,
                "strategy_spec_write": False,
                "runtime_activation": False,
                "promotion_mutation": False,
                "live_trading_allowed": False,
            },
            "sanitization": {
                "private_plaintext_published": False,
                "captured_test_output_published": False,
                "output_retained_as_digest_only": True,
            },
        }


def main() -> int:
    # Never echo private CLI args, source paths or nested exception messages.
    # Cleanup is restricted to the one exact workflow-owned temporary root.
    args = None
    image_tag = ""
    try:
        parser = _PublicSafeArgumentParser()
        parser.add_argument("--source-root", required=True)
        parser.add_argument("--source-materialization", required=True)
        parser.add_argument("--source-ref", required=True)
        parser.add_argument("--test-modules", required=True)
        parser.add_argument("--image-tag", default="")
        args = parser.parse_args()
        modules = validated_modules(args.test_modules)
        image_tag = args.image_tag or f"mmibkr-private-test-probe:{os.environ.get('GITHUB_RUN_ID', 'local')}"
        if not re.fullmatch(r"mmibkr-private-test-probe:[A-Za-z0-9._-]{1,100}", image_tag):
            raise ValueError("private_test_probe_image_tag_rejected")
        receipt = run_probe(
            source_root=Path(args.source_root).resolve(),
            source_materialization=Path(args.source_materialization).resolve(),
            expected_source_ref=str(args.source_ref),
            modules=modules,
            image_tag=image_tag,
        )
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    except Exception:
        receipt = {"schema": SCHEMA, "status": "REJECTED"}
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    finally:
        if image_tag and re.fullmatch(r"mmibkr-private-test-probe:[A-Za-z0-9._-]{1,100}", image_tag):
            try:
                subprocess.run(
                    ["docker", "image", "rm", image_tag],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            except OSError:
                pass  # No private CLI exception text on cleanup failure.
        runner_temp = os.environ.get("RUNNER_TEMP", "")
        if args is not None and runner_temp:
            expected = (Path(runner_temp).resolve() / "mmibkr-private-test-probe-source").resolve()
            actual = Path(args.source_root).resolve()
            if actual == expected or expected in actual.parents:
                shutil.rmtree(expected, ignore_errors=True)

    print("MMIBKR_PRIVATE_TEST_PROBE_RECEIPT=" + encoded)
    print("MMIBKR_PRIVATE_TEST_PROBE_RECEIPT_SHA256=" + hashlib.sha256(encoded.encode()).hexdigest())
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
