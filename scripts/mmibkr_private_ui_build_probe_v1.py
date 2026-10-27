from __future__ import annotations

"""Build one exact private MM-IBKR ui-react tree from Source Vault on public compute.

Plaintext source is materialized only in runner temp by the existing attested
Source Vault consumer. This probe validates exact source identity, installs the
pinned lockfile with lifecycle scripts disabled, executes one explicitly
allowlisted private Node acceptance file, runs Vite directly, and emits only
sanitized digests/status.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any


SCHEMA = "mmibkr.private_ui_build_probe.v1"
ALLOWED_ACCEPTANCE_FILES = {
    "ui-react/src/canonical-market-chart-provenance.acceptance.test.mjs",
    "ui-react/src/lib/pilotStrategySpecHandoff.acceptance.test.mjs",
    "ui-react/src/lib/pilotPromotionAdmissionExport.acceptance.test.mjs",
    # Exact selected #888 Product limited forward-sanity promotion-review fail-close.
    "ui-react/src/lib/promotionReview.test.mjs",
    # Selected MM-IBKR UI #937 source-only contradictory account-scope safety regression.
    "ui-react/src/lib/accountMarginSafety.test.mjs",
    # Selected MM-IBKR UI #949 exact read-only broker cache/cancel guard regression.
    "ui-react/src/components/operatorOrderSnapshot.cancel-guard.test.mjs",
    # Exact selected #888 Pilot bounded matrix and Bot Console conId operator truth.
    "ui-react/src/lib/pilotMatrixPlan.test.mjs",
    "ui-react/src/lib/botConsoleExactAccountHoldings.test.mjs",
    # Selected UI #888 exact account-position/fill/order scope presentation regression.
    "ui-react/src/lib/botConsolePositionTruth.test.mjs",
    # Selected #975 Product #1254 exact Builder coverage truth acceptance.
    "ui-react/src/lib/builderBacktestCoverageReview.test.mjs",
    # Product #1322 blocked exact Pilot handoff presentation, pure Node only.
    "ui-react/src/lib/pilotHandoffPresentationTruth.test.mjs",
    # Exact selected Builder Preview malformed-error semantic parity, source-only Node.
    "ui-react/src/lib/builderPreviewResponse.test.mjs",
    # Exact selected P0/UI #975 account-scoped open-order projection (pure Node).
    "ui-react/src/lib/botConsoleOpenOrdersTruth.test.mjs",
    # Exact legacy Builder local-draft combinator restoration, read-only UI.
    "ui-react/src/lib/builderLocalDraftRestore.test.mjs",
    # Exact selected MM #888@f9ac post-closure rapid-click Builder ID safety.
    "ui-react/src/lib/builderConditionId.test.mjs",
    # Exact selected #888@20e8 operator mode, stale-bar and system evidence truth.
    "ui-react/src/pages/botConsoleModeTruth.test.mjs",
    # Exact selected Builder/CRW/model-digest and operator presentation Node tests.
    "ui-react/src/lib/botConsoleSelectedHoldingsEmpty.product.test.mjs",
    "ui-react/src/lib/historicalRangeReadinessLabel.test.mjs",
    "ui-react/src/lib/builderPersistedReviewTruth.test.mjs",
    "ui-react/src/lib/builderLiteralValue.test.mjs",
    # Exact selected MM #888@d3fe Builder decimal threshold fail-close regression.
    "ui-react/src/lib/builderLiteralValue.decimalAdmission.product.test.mjs",
    "ui-react/src/lib/contractPnlCurrency.test.mjs",
    "ui-react/src/lib/selectedRuntimeBadgeTruth.test.mjs",
    "ui-react/src/components/strategy-builder-reviewed-fetch-guard.test.mjs",
    "ui-react/src/lib/tradingProductReadiness.digest-identity.test.mjs",
    "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.cross-timeframe-capability.test.mjs",
    "ui-react/src/components/CRWStrategyBuilderBacktestWorkbenchBase.local-draft-storage.test.mjs",
    "ui-react/src/pages/BotConsolePage.acceptance.test.mjs",
    # Product #1315 exact paper execution identity and trade-claim tri-state.
    "ui-react/src/pages/ForwardExecutionEvidencePage.acceptance.test.mjs",
    # Product #1301 exact read-only forward unknown-vs-zero evidence consumers.
    "ui-react/src/lib/arenaForwardEvidence.test.mjs",
    "ui-react/src/lib/forwardEvidenceExactIdentity.test.mjs",
    # Selected #975 fe30: exact read-only Bot Console activity/offset identity guard.
    "ui-react/src/lib/botConsoleRecentActivity.test.mjs",
    # Product #1309 read-only persisted paper history date/freshness guard.
    "ui-react/src/lib/paperBoundaryHistory.test.mjs",
}


class _PublicSafeArgumentParser(argparse.ArgumentParser):
    """Reject malformed public CLI without echoing caller-provided private text."""

    def __init__(self) -> None:
        super().__init__(add_help=False)

    def error(self, _message: str) -> None:
        raise ValueError("invalid_public_ui_probe_arguments")


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
    if source_sha != str(expected_source_ref).lower():
        raise RuntimeError("source_sha_ref_mismatch")
    resolved_root = Path(node.get("source_root") or "").resolve()
    if source_root.resolve() != resolved_root:
        raise RuntimeError("source_root_mismatch")
    if not (source_root / "ui-react" / "package.json").is_file():
        raise RuntimeError("private_ui_source_incomplete")
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
    return node


def validate_compute_requirements(raw: Any) -> str:
    """Require policy-derived public-encrypted compute at both existing triggers.

    This is an ingress requirement, NOT signed PLACED issuance or broker authority.
    """
    if not isinstance(raw, dict) or set(raw) != {"trust_mode"}:
        raise ValueError("private_ui_compute_requirements_invalid")
    if raw["trust_mode"] != "public_encrypted":
        raise ValueError("private_ui_compute_trust_mode_rejected")
    return "public_encrypted"


def resolve_ui_request(
    *, event_name: str, dispatch_source_ref: str = "",
    dispatch_acceptance_file: str = "", dispatch_trust_mode: str = "",
    fire: Any = None,
) -> dict[str, str]:
    """One fail-closed resolver for both existing specialized UI CI triggers."""
    if event_name == "workflow_dispatch":
        source_ref = str(dispatch_source_ref or "").strip().lower()
        acceptance = dispatch_acceptance_file
        requirements = {"trust_mode": dispatch_trust_mode}
    elif event_name == "push":
        if not isinstance(fire, dict) or fire.get("schema") != "mmibkr.private_ui_build_probe_fire.v1":
            raise ValueError("private_ui_fire_schema_rejected")
        source_ref = str(fire.get("source_ref") or "").strip().lower()
        acceptance = fire.get("acceptance_file")
        requirements = fire.get("compute_requirements")
    else:
        raise ValueError("private_ui_event_rejected")
    if not re.fullmatch(r"[0-9a-f]{40}", source_ref):
        raise ValueError("private_ui_source_sha_rejected")
    return {
        "source_ref": source_ref,
        "acceptance_file": validate_acceptance_file(acceptance),
        "trust_mode": validate_compute_requirements(requirements),
    }


def validate_acceptance_file(raw: str) -> str:
    value = str(raw or "").strip().replace("\\", "/")
    if value not in ALLOWED_ACCEPTANCE_FILES:
        raise ValueError("ui_acceptance_file_not_allowlisted")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("ui_acceptance_file_path_rejected")
    return value


def validate_package_contract(ui_root: Path) -> dict[str, Any]:
    package = _load_json(ui_root / "package.json")
    lock = _load_json(ui_root / "package-lock.json")
    scripts = package.get("scripts") or {}
    if scripts.get("build") != "vite build":
        raise RuntimeError("ui_build_script_contract_rejected")
    if "prebuild" in scripts or "postbuild" in scripts:
        raise RuntimeError("ui_build_lifecycle_hook_rejected")
    if lock.get("lockfileVersion") != 3:
        raise RuntimeError("ui_lockfile_version_rejected")
    return {
        "build_script": "vite build",
        "lockfile_version": 3,
        "lifecycle_hooks_disabled": True,
    }


_SAFE_VITE_FAILURE_CLASSES = frozenset({
    "IMPORT_RESOLUTION", "EXPORT_BINDING", "SOURCE_SYNTAX",
    "RESOURCE_EXHAUSTION", "BUNDLER_ERROR_OTHER", "UNCLASSIFIED",
})


def _safe_vite_failure_class(raw: str) -> dict[str, Any]:
    """Emit only an allowlisted diagnostic class and hashed repo-relative file path.

    Never print Vite log lines, imports, source excerpts, absolute paths, or
    arbitrary exception text on public encrypted compute.
    """
    kind = (
        "UNRESOLVED_IMPORT" if re.search(r"failed to resolve import|could not resolve", raw, re.I)
        else "TRANSFORM_ERROR" if re.search(r"transform failed|unexpected token|syntax error|\[vite:esbuild\]", raw, re.I)
        else "EXPORT_ERROR" if re.search(r"does not provide an export|not exported", raw, re.I)
        else "BUILD_FAILURE_OTHER"
    )
    result: dict[str, Any] = {"class": kind}
    source_match = re.search(
        r"(?:^|[\s(/])(?P<path>src/(?:[a-zA-Z0-9_.-]+/)*[a-zA-Z0-9_.-]+\.(?:jsx|js|mjs|tsx|ts|css)):(?P<line>[1-9]\d{0,5})(?::(?P<column>\d{1,4}))?",
        raw.replace("\\", "/"),
        re.M,
    )
    if source_match:
        result["source_path_sha256_16"] = hashlib.sha256(
            source_match.group("path").encode("utf-8")
        ).hexdigest()[:16]
        result["source_line"] = int(source_match.group("line"))
    return result


def _safe_vite_receipt_class(raw: str) -> str:
    """Fixed enum only; never return private paths, source, stderr or snippets."""
    value = raw[:65536].lower()
    if any(token in value for token in (
        "could not resolve", "failed to resolve import", "cannot find module",
        "module not found", "could not load",
    )):
        return "IMPORT_RESOLUTION"
    if any(token in value for token in (
        "not exported by", "does not provide an export named",
        "is not exported", "missing export",
    )):
        return "EXPORT_BINDING"
    if any(token in value for token in (
        "unexpected token", "syntax error", "parse error", "transform failed",
    )):
        return "SOURCE_SYNTAX"
    if any(token in value for token in (
        "heap out of memory", "allocation failed", "out of memory",
    )):
        return "RESOURCE_EXHAUSTION"
    if "error during build" in value or "build failed" in value:
        return "BUNDLER_ERROR_OTHER"
    return "UNCLASSIFIED"


def _run_captured(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout: int,
    diagnose_vite: bool = False,
) -> dict[str, Any]:
    with log_path.open("wb") as handle:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=os.environ.copy(),
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    digest = _sha256(log_path)
    size = log_path.stat().st_size
    failure_class = None
    if proc.returncode != 0 and (diagnose_vite or log_path.name == "vite-build.log"):
        try:
            raw = log_path.read_text(encoding="utf-8", errors="replace")
            safe_failure = _safe_vite_failure_class(raw)
            failure_class = _safe_vite_receipt_class(raw)
        except (OSError, UnicodeError, ValueError):
            safe_failure = {"class": "BUILD_FAILURE_OTHER"}
            failure_class = "UNCLASSIFIED"
        print("MMIBKR_PRIVATE_UI_VITE_SAFE_FAILURE=" + json.dumps(
            safe_failure, sort_keys=True, separators=(",", ":")
        ))
    log_path.unlink(missing_ok=True)
    result = {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "exit_code": int(proc.returncode),
        "captured_output_sha256": digest,
        "captured_output_bytes": int(size),
    }
    if diagnose_vite:
        result["_safe_vite_failure_class"] = failure_class
    return result


def _dist_digest(dist: Path) -> tuple[str, int]:
    files = sorted(path for path in dist.rglob("*") if path.is_file())
    h = hashlib.sha256()
    for path in files:
        relative = path.relative_to(dist).as_posix().encode("utf-8")
        raw = path.read_bytes()
        h.update(len(relative).to_bytes(4, "big"))
        h.update(relative)
        h.update(len(raw).to_bytes(8, "big"))
        h.update(raw)
    return h.hexdigest(), len(files)


def run_probe(
    *,
    source_root: Path,
    source_materialization: Path,
    expected_source_ref: str,
    acceptance_file: str,
) -> dict[str, Any]:
    identity = validate_source_identity(
        source_root,
        source_materialization,
        expected_source_ref,
    )
    acceptance_rel = validate_acceptance_file(acceptance_file)
    ui = source_root / "ui-react"
    acceptance_path = source_root / acceptance_rel
    if not acceptance_path.is_file():
        raise RuntimeError("ui_acceptance_file_missing")
    package_contract = validate_package_contract(ui)

    with tempfile.TemporaryDirectory(prefix="mmibkr-private-ui-build-") as td:
        temp = Path(td)
        install = _run_captured(
            ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=ui,
            log_path=temp / "npm-ci.log",
            timeout=1200,
        )
        acceptance = {
            "status": "SKIPPED",
            "exit_code": None,
            "captured_output_sha256": None,
            "captured_output_bytes": 0,
        }
        build = dict(acceptance)
        vite_failure_class = None
        if install["status"] == "PASS":
            acceptance = _run_captured(
                ["node", str(acceptance_path)],
                cwd=source_root,
                log_path=temp / "acceptance.log",
                timeout=300,
            )
        if install["status"] == "PASS" and acceptance["status"] == "PASS":
            vite = ui / "node_modules" / ".bin" / "vite"
            if not vite.is_file():
                raise RuntimeError("vite_binary_missing_after_npm_ci")
            build = _run_captured(
                [str(vite), "build"],
                cwd=ui,
                log_path=temp / "vite-build.log",
                timeout=900,
                diagnose_vite=True,
            )
            vite_failure_class = build.pop("_safe_vite_failure_class", None)

    dist = ui / "dist"
    dist_ok = build["status"] == "PASS" and (dist / "index.html").is_file()
    dist_digest, dist_file_count = _dist_digest(dist) if dist_ok else (None, 0)
    shutil.rmtree(ui / "node_modules", ignore_errors=True)
    shutil.rmtree(dist, ignore_errors=True)

    status = (
        "PASS"
        if install["status"] == "PASS"
        and acceptance["status"] == "PASS"
        and build["status"] == "PASS"
        and dist_ok
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
        "package_contract": package_contract,
        "acceptance_file": acceptance_rel,
        "npm_ci": install,
        "node_acceptance": acceptance,
        "vite_build": build,
        "vite_failure_class": vite_failure_class,
        "dist_index_present": bool(dist_ok),
        "dist_file_count": int(dist_file_count),
        "dist_digest_sha256": dist_digest,
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
            "captured_build_output_published": False,
            "output_retained_as_digest_only": True,
        },
    }


_PUBLIC_RECEIPT_FIELDS = frozenset({
    "schema", "status", "source_identity", "package_contract",
    "acceptance_file", "npm_ci", "node_acceptance", "vite_build",
    "dist_index_present", "dist_file_count", "dist_digest_sha256",
    "vite_failure_class",
    "authority", "sanitization",
})
_PUBLIC_NESTED_FIELDS = {
    "source_identity": frozenset({
        "repository", "source_ref", "source_sha", "source_archive_sha256",
        "source_archive_bytes", "source_manifest_sha256",
        "source_transport", "vault_attestation_verified",
    }),
    "package_contract": frozenset({
        "build_script", "lockfile_version", "lifecycle_hooks_disabled",
    }),
    "npm_ci": frozenset({
        "status", "exit_code", "captured_output_sha256", "captured_output_bytes",
    }),
    "node_acceptance": frozenset({
        "status", "exit_code", "captured_output_sha256", "captured_output_bytes",
    }),
    "vite_build": frozenset({
        "status", "exit_code", "captured_output_sha256", "captured_output_bytes",
    }),
    "authority": frozenset({
        "research_only", "private_repository_token_used",
        "broker_credentials_used", "broker_request_made", "broker_action",
        "strategy_spec_write", "runtime_activation", "promotion_mutation",
        "live_trading_allowed",
    }),
    "sanitization": frozenset({
        "private_plaintext_published", "captured_build_output_published",
        "output_retained_as_digest_only",
    }),
}


def _public_receipt(value: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on unexpected nested fields or non-digest private values."""
    if not isinstance(value, dict) or set(value) != _PUBLIC_RECEIPT_FIELDS:
        raise ValueError("public_receipt_field_set_rejected")
    for key, fields in _PUBLIC_NESTED_FIELDS.items():
        if not isinstance(value[key], dict) or set(value[key]) != fields:
            raise ValueError("public_receipt_nested_field_set_rejected")
    if value["schema"] != SCHEMA or value["status"] not in {"PASS", "FAIL"}:
        raise ValueError("public_receipt_status_rejected")
    if value["acceptance_file"] not in ALLOWED_ACCEPTANCE_FILES:
        raise ValueError("public_receipt_acceptance_rejected")
    identity = value["source_identity"]
    if identity["repository"] != "XoticHaze/mm-IBKR":
        raise ValueError("public_receipt_repository_rejected")
    for field in ("source_ref", "source_sha", "source_archive_sha256"):
        digest = identity[field]
        if not isinstance(digest, str) or len(digest) not in (40, 64) or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("public_receipt_digest_rejected")
    optional = identity["source_manifest_sha256"]
    if optional is not None and (not isinstance(optional, str) or len(optional) != 64 or any(ch not in "0123456789abcdef" for ch in optional)):
        raise ValueError("public_receipt_manifest_digest_rejected")
    if (type(identity["source_archive_bytes"]) is not int or identity["source_archive_bytes"] < 0
            or identity["source_transport"] != "fleet_authority_exact_sha_encrypted_snapshot_vault"
            or identity["vault_attestation_verified"] is not True):
        raise ValueError("public_receipt_source_identity_rejected")
    pkg = value["package_contract"]
    if pkg != {"build_script": "vite build", "lockfile_version": 3, "lifecycle_hooks_disabled": True}:
        raise ValueError("public_receipt_package_rejected")
    for step in ("npm_ci", "node_acceptance", "vite_build"):
        item = value[step]
        digest = item["captured_output_sha256"]
        if (item["status"] not in {"PASS", "FAIL", "SKIPPED"}
                or (item["exit_code"] is not None and type(item["exit_code"]) is not int)
                or type(item["captured_output_bytes"]) is not int or item["captured_output_bytes"] < 0
                or (digest is not None and (not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest)))):
            raise ValueError("public_receipt_step_rejected")
    failure_class = value["vite_failure_class"]
    if value["vite_build"]["status"] == "FAIL":
        if failure_class not in _SAFE_VITE_FAILURE_CLASSES:
            raise ValueError("public_receipt_vite_failure_class_rejected")
    elif failure_class is not None:
        raise ValueError("public_receipt_vite_failure_class_rejected")
    dist = value["dist_digest_sha256"]
    if (type(value["dist_index_present"]) is not bool
            or type(value["dist_file_count"]) is not int or value["dist_file_count"] < 0
            or (dist is not None and (not isinstance(dist, str) or len(dist) != 64 or any(ch not in "0123456789abcdef" for ch in dist)))):
        raise ValueError("public_receipt_dist_rejected")
    if value["authority"] != {
        "research_only": True, "private_repository_token_used": False,
        "broker_credentials_used": False, "broker_request_made": False,
        "broker_action": False, "strategy_spec_write": False,
        "runtime_activation": False, "promotion_mutation": False,
        "live_trading_allowed": False,
    } or value["sanitization"] != {
        "private_plaintext_published": False,
        "captured_build_output_published": False,
        "output_retained_as_digest_only": True,
    }:
        raise ValueError("public_receipt_authority_rejected")
    return value


def main() -> int:
    # No private source paths, arguments, exception messages or nested fields
    # may reach public workflow stdout/stderr, including parse failures.
    try:
        parser = _PublicSafeArgumentParser()
        parser.add_argument("--source-root", required=True)
        parser.add_argument("--source-materialization", required=True)
        parser.add_argument("--source-ref", required=True)
        parser.add_argument("--acceptance-file", required=True)
        args = parser.parse_args()
        receipt = _public_receipt(run_probe(
            source_root=Path(args.source_root).resolve(),
            source_materialization=Path(args.source_materialization).resolve(),
            expected_source_ref=str(args.source_ref),
            acceptance_file=str(args.acceptance_file),
        ))
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    except Exception:
        receipt = {"schema": SCHEMA, "status": "REJECTED"}
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    print("MMIBKR_PRIVATE_UI_BUILD_RECEIPT=" + encoded)
    print(
        "MMIBKR_PRIVATE_UI_BUILD_RECEIPT_SHA256="
        + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    )
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
