from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ".github/workflows/secure-compute-harness-v1.yml"
HARNESS_SCRIPT = "scripts/live_reference_harness_v1.py"
BROKER_INDEX = ROOT / "cloudflare/reference-release-broker/src/index.js"
WRANGLER = ROOT / "cloudflare/reference-release-broker/wrangler.jsonc"


def git_show(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> int:
    cfg = json.loads(WRANGLER.read_text(encoding="utf-8"))
    vars_node = cfg["vars"]
    allowed_sha = str(vars_node["ALLOWED_JOB_WORKFLOW_SHA"])
    allowed_ref = str(vars_node["ALLOWED_JOB_WORKFLOW_REF"])

    if not re.fullmatch(r"[0-9a-f]{40}", allowed_sha):
        raise RuntimeError("allowed_harness_sha_invalid")
    if not allowed_ref.endswith("@" + allowed_sha):
        raise RuntimeError("allowed_harness_ref_sha_mismatch")

    workflow = git_show(allowed_sha, WORKFLOW_PATH)
    match = re.search(
        r"repository:\s*XoticHaze/research-compute-public-\s*\n\s*ref:\s*([0-9a-f]{40})",
        workflow,
    )
    if not match:
        raise RuntimeError("pinned_harness_source_ref_missing")
    source_sha = match.group(1)

    harness = git_show(source_sha, HARNESS_SCRIPT)
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td) / "live_reference_harness_v1.py"
        temp.write_text(harness, encoding="utf-8")
        subprocess.run(
            ["python", "-m", "py_compile", str(temp)],
            check=True,
            cwd=ROOT,
        )

    if '"worker_key_id": worker_key_id, "intent": intent' not in harness:
        raise RuntimeError("harness_broker_request_shape_mismatch")
    if 'proof/live/bootstrap-intent.json' not in harness:
        raise RuntimeError("harness_signed_intent_bootstrap_missing")

    expected_url = (
        "https://"
        + str(cfg["name"])
        + ".slenderiq.workers.dev/v1/release"
    )
    if f'BROKER_URL = "{expected_url}"' not in harness:
        raise RuntimeError("harness_broker_url_mismatch")

    broker = BROKER_INDEX.read_text(encoding="utf-8")
    if "new Set(['worker_key_id','intent'])" not in broker:
        raise RuntimeError("broker_request_shape_mismatch")
    if "verifyAuthorityIntent" not in broker:
        raise RuntimeError("broker_intent_verifier_missing")
    if "callerPolicySha256" not in broker:
        raise RuntimeError("broker_caller_policy_binding_missing")
    if "GRANT_LEDGER" not in broker:
        raise RuntimeError("broker_single_use_ledger_missing")

    if cfg.get("workers_dev") is not True:
        raise RuntimeError("neutral_workers_dev_endpoint_disabled")
    if cfg.get("preview_urls") is not False:
        raise RuntimeError("preview_urls_must_be_disabled")
    if cfg.get("keep_vars") is not False:
        raise RuntimeError("keep_vars_must_be_false")

    print("REFERENCE_LIVE_RELEASE_CONTRACT_PASS=1")
    print("PINNED_HARNESS_SHA=" + allowed_sha)
    print("PINNED_HARNESS_SOURCE_SHA=" + source_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
