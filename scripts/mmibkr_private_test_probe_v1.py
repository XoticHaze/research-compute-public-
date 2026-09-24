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


SCHEMA = "mmibkr.private_test_probe_receipt.v1"
PYTEST_VERSION = "8.4.2"
MODULE_RE = re.compile(r"^tests\.test_[A-Za-z0-9_]+$")
SAFE_PREFIXES = (
    "tests.test_autotuner_",
)
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
    "tests.test_publish_canonical_feature_sidecar",
    "tests.test_materialize_admitted_futures_source_canonical",
    "tests.test_materialize_admitted_futures_dated_contract",
    "tests.test_crw_tradingview_dual_execution_replay_14th31js",
    "tests.test_builder_feature_rhs_comparison_14th31ky",
    "tests.test_crw_backtest_futures_timestamp_14th31kf",
    "tests.test_news_publication_time_integrity_20260902",
    "tests.test_news_publication_time_integration_patch_20260902",
    "tests.test_news_scorecard_cycle_break_14th31fd_r18",
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
            raise ValueError(f"test_module_rejected:{module}")
        if module in SAFE_EXACT:
            if module not in out:
                out.append(module)
            continue
        lowered = module.lower()
        if any(token in lowered for token in DENY_TOKENS):
            raise ValueError(f"test_module_authority_rejected:{module}")
        if not module.startswith(SAFE_PREFIXES):
            raise ValueError(f"test_module_not_allowlisted:{module}")
        if module not in out:
            out.append(module)
    return out


def module_file_path(module: str) -> str:
    """Map one already-validated test module to its repository-relative file."""
    if not MODULE_RE.fullmatch(str(module or "")):
        raise ValueError(f"test_module_rejected:{module}")
    return module.replace(".", "/") + ".py"


def pytest_container_command(image_tag: str, module: str) -> list[str]:
    """Return a shell-free Docker command for one exact pytest module file."""
    return [
        "docker",
        "run",
        "--rm",
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
    try:
        log_path.unlink()
    except FileNotFoundError:
        pass
    return {
        "exit_code": int(proc.returncode),
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "captured_output_sha256": digest,
        "captured_output_bytes": size,
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
    with tempfile.TemporaryDirectory(prefix="mmibkr-private-test-probe-") as tmp:
        temp = Path(tmp)
        build = _run_captured(
            [
                "docker",
                "build",
                "-f",
                str(source_root / "Dockerfile.bot"),
                "--target",
                "bot",
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-materialization", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--test-modules", required=True)
    parser.add_argument("--image-tag", default="")
    args = parser.parse_args()

    modules = validated_modules(args.test_modules)
    image_tag = args.image_tag or f"mmibkr-private-test-probe:{os.environ.get('GITHUB_RUN_ID', 'local')}"
    receipt: dict[str, Any]
    try:
        receipt = run_probe(
            source_root=Path(args.source_root).resolve(),
            source_materialization=Path(args.source_materialization).resolve(),
            expected_source_ref=str(args.source_ref),
            modules=modules,
            image_tag=image_tag,
        )
    finally:
        subprocess.run(
            ["docker", "image", "rm", image_tag],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        shutil.rmtree(Path(args.source_root).resolve().parent, ignore_errors=True)

    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    print("MMIBKR_PRIVATE_TEST_PROBE_RECEIPT=" + encoded)
    print("MMIBKR_PRIVATE_TEST_PROBE_RECEIPT_SHA256=" + hashlib.sha256(encoded.encode()).hexdigest())
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
