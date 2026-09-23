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
MODULE_RE = re.compile(r"^tests\.test_[A-Za-z0-9_]+$")
SAFE_PREFIXES = (
    "tests.test_autotuner_",
)
SAFE_EXACT = {
    "tests.test_strategy_backtest_registry_dispatch",
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
        lowered = module.lower()
        if any(token in lowered for token in DENY_TOKENS):
            raise ValueError(f"test_module_authority_rejected:{module}")
        if not (module in SAFE_EXACT or module.startswith(SAFE_PREFIXES)):
            raise ValueError(f"test_module_not_allowlisted:{module}")
        if module not in out:
            out.append(module)
    return out


def validate_source_identity(
    source_root: Path,
    materialization_path: Path,
    expected_source_ref: str,
) -> dict[str, Any]:
    node = _load_json(materialization_path)
    if node.get("schema") != "mmibkr.cloud_source_materialization.v1":
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
        module_rows: list[dict[str, Any]] = []
        if build["status"] == "PASS":
            for index, module in enumerate(modules, start=1):
                row = _run_captured(
                    [
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
                        "unittest",
                        "-q",
                        module,
                    ],
                    cwd=None,
                    env=os.environ.copy(),
                    log_path=temp / f"module-{index:02d}.log",
                    timeout=600,
                )
                module_rows.append({"module": module, **row})

        status = (
            "PASS"
            if build["status"] == "PASS"
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
                "producer_identity": identity.get("producer_identity"),
            },
            "build": build,
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
