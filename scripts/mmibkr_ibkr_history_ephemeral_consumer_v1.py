from __future__ import annotations

"""Fixed public-compute consumer for the MM-IBKR CC44 IBKR history one-shot.

The public runner receives only a run-bound encrypted JSON payload containing
short-lived private-repo read credentials and IBKR paper credentials. It clones one
pinned private source commit, launches the repo's existing IB Gateway Compose service
in paper/read-only mode, and runs the existing history_fetcher.oneshot acquisition.
It has no order, cancel, flatten, runtime-promotion or canonical-data write authority.
"""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

from mmibkr_ephemeral_scoped_v1 import decrypt_assembled_ciphertext

ENVELOPE_SCHEMA = "mmibkr-ibkr-history-ephemeral-x25519-v1"
PRIVATE_SCHEMA = "mmibkr-ibkr-history-private-input-v1"
AUTHORITY = "history_acquisition_only"
HARNESS = "mmibkr_ibkr_history_cc44_v1"
SOURCE_REPO = "XoticHaze/mm-IBKR-beta"
SOURCE_SHA = "3c9ef5e24a6bbb062dd3cfce01c95c1517659229"
GATEWAY_IMAGE = "ghcr.io/gnzsnz/ib-gateway:10.49.1c"
CLIENT_ID = 1971
PRIVATE_FIELDS = {
    "schema",
    "source_read_token",
    "tws_userid",
    "tws_password",
    "tws_userid_paper",
    "tws_password_paper",
}


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 1800, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def _must(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1][:240] if detail else f"rc={proc.returncode}"
        raise RuntimeError(f"{label} failed: {tail}")


def _load_private(plaintext: bytes) -> dict[str, str]:
    try:
        node = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("MM-IBKR history private input is not valid UTF-8 JSON") from exc
    if not isinstance(node, dict) or set(node) != PRIVATE_FIELDS:
        raise RuntimeError("MM-IBKR history private input field set mismatch")
    if node.get("schema") != PRIVATE_SCHEMA:
        raise RuntimeError("MM-IBKR history private input schema mismatch")
    for key in ("source_read_token", "tws_userid", "tws_password"):
        if not isinstance(node.get(key), str) or not node[key].strip():
            raise RuntimeError(f"MM-IBKR history private input missing {key}")
    for key in ("tws_userid_paper", "tws_password_paper"):
        if not isinstance(node.get(key), str):
            raise RuntimeError(f"MM-IBKR history private input invalid {key}")
    return {str(k): str(v) for k, v in node.items()}


def _clone_pinned(private: dict[str, str], root: Path) -> Path:
    repo = root / "mmibkr"
    cred = root / "git-credentials"
    gitconfig = root / "gitconfig"
    token = urllib.parse.quote(private["source_read_token"], safe="")
    cred.write_text(f"https://x-access-token:{token}@github.com\n", encoding="utf-8")
    os.chmod(cred, 0o600)
    gitconfig.write_text(f"[credential]\n\thelper = store --file={cred}\n", encoding="utf-8")
    os.chmod(gitconfig, 0o600)
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", f"https://github.com/{SOURCE_REPO}.git", str(repo)],
            env=env,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=600,
            check=False,
        )
        _must(proc, "private source clone")
        proc = subprocess.run(
            ["git", "-C", str(repo), "checkout", "--detach", SOURCE_SHA],
            env=env,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=600,
            check=False,
        )
        _must(proc, "pinned source checkout")
    finally:
        cred.unlink(missing_ok=True)
        gitconfig.unlink(missing_ok=True)

    head = _run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=30)
    _must(head, "source identity")
    if head.stdout.strip() != SOURCE_SHA:
        raise RuntimeError("MM-IBKR history source SHA mismatch")
    dirty = _run(["git", "status", "--porcelain"], cwd=repo, timeout=30)
    _must(dirty, "source cleanliness")
    if dirty.stdout.strip():
        raise RuntimeError("MM-IBKR history source checkout is not clean")
    required = [repo / "history_fetcher" / "oneshot.py", repo / "Dockerfile.bot", repo / "docker-compose.yml"]
    if not all(path.is_file() for path in required):
        raise RuntimeError("MM-IBKR history pinned source is missing required acquisition files")
    return repo


def _write_gateway_env(repo: Path, private: dict[str, str]) -> Path:
    path = repo / "ibkr-gateway" / ".env.ibkr"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = {
        "TWS_USERID": private["tws_userid"],
        "TWS_PASSWORD": private["tws_password"],
        "TWS_USERID_PAPER": private["tws_userid_paper"],
        "TWS_PASSWORD_PAPER": private["tws_password_paper"],
        "TRADING_MODE": "paper",
        "READ_ONLY_API": "yes",
        "TWS_ACCEPT_INCOMING": "accept",
        "TWOFA_TIMEOUT_ACTION": "exit",
        "ENABLE_VNC": "false",
    }
    if any("\n" in value or "\r" in value for value in rows.values()):
        raise RuntimeError("MM-IBKR gateway private input contains newline")
    path.write_text("".join(f"{key}={value}\n" for key, value in rows.items()), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _compose(repo: Path, project: str, *args: str, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return _run(["docker", "compose", "-p", project, *args], cwd=repo, timeout=timeout)


def _wait_gateway(timeout_sec: int = 300) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        proc = _run(["docker", "inspect", "-f", "{{.State.Health.Status}}", "ibkr-gateway"], timeout=15)
        if proc.returncode == 0 and proc.stdout.strip() == "healthy":
            return
        time.sleep(5)
    raise RuntimeError("MM-IBKR IB Gateway did not become healthy")


def _sanitize_request(item: dict[str, Any]) -> dict[str, Any]:
    request = dict(item.get("request") or {})
    result = dict(item.get("result") or {}) if isinstance(item.get("result"), dict) else {}
    error = str(item.get("error") or "")
    return {
        "mode": request.get("mode"),
        "timeframe": request.get("timeframe"),
        "ok": bool(item.get("ok")),
        "rows": result.get("rows") or result.get("row_count"),
        "available_start": result.get("available_start") or result.get("start"),
        "available_end": result.get("available_end") or result.get("end"),
        "staging_changed": bool(item.get("staging_changed")),
        "canonical_changed_observed": bool(item.get("canonical_changed_observed")),
        "error_type": error.split(":", 1)[0][:96] if error else None,
    }


def execute(private: dict[str, str], run_id: str) -> dict[str, Any]:
    project = "mmibkrhist" + hashlib.sha256(str(run_id).encode()).hexdigest()[:10]
    with tempfile.TemporaryDirectory(prefix="mmibkr-history-") as td:
        root = Path(td)
        repo = _clone_pinned(private, root)
        gateway_env = _write_gateway_env(repo, private)
        staging = root / "staging"
        canonical = root / "canonical"
        staging.mkdir()
        canonical.mkdir()
        result_path = staging / "cc44_history_oneshot_result.json"

        try:
            build = _compose(repo, project, "build", "bot", timeout=2400)
            _must(build, "history bot image build")
            up = _compose(repo, project, "up", "-d", "ibgw", timeout=600)
            _must(up, "read-only paper gateway start")
            _wait_gateway()

            history = _compose(
                repo,
                project,
                "run",
                "--rm",
                "--no-deps",
                "-e",
                "HISTORY_FETCHER_IB_HOST=127.0.0.1",
                "-e",
                "HISTORY_FETCHER_IB_PORT=4002",
                "-e",
                f"HISTORY_FETCHER_CLIENT_ID={CLIENT_ID}",
                "-e",
                "HISTORY_FETCHER_DATA_ROOT=/app/staging",
                "-e",
                "HISTORY_FETCHER_CANONICAL_DATA_ROOT=/app/canonical-data",
                "-e",
                "HISTORY_FETCHER_RESULT_PATH=/app/staging/cc44_history_oneshot_result.json",
                "-v",
                f"{staging}:/app/staging",
                "-v",
                f"{canonical}:/app/canonical-data:ro",
                "bot",
                "python",
                "-m",
                "history_fetcher.oneshot",
                timeout=2400,
            )
            if not result_path.exists():
                raise RuntimeError(f"history one-shot produced no result artifact (rc={history.returncode})")
            raw = json.loads(result_path.read_text(encoding="utf-8"))
            requests = [_sanitize_request(dict(x or {})) for x in list(raw.get("requests") or [])]
            canonical_unchanged = not any(bool(x.get("canonical_changed_observed")) for x in requests)
            strict_pass = bool(
                history.returncode == 0
                and raw.get("ib_connected")
                and raw.get("required_requests_ok")
                and canonical_unchanged
                and len(requests) == 3
            )
            partial = bool(not strict_pass and canonical_unchanged and any(x.get("ok") for x in requests))
            return {
                "schema": "mmibkr-ibkr-history-public-compute-receipt-v1",
                "authority": AUTHORITY,
                "harness": HARNESS,
                "status": "PASS" if strict_pass else ("PARTIAL" if partial else "FAIL"),
                "run_id": str(run_id),
                "source_repo": SOURCE_REPO,
                "source_sha": SOURCE_SHA,
                "gateway_image": GATEWAY_IMAGE,
                "paper_mode_forced": True,
                "gateway_read_only_forced": True,
                "history_client_id": CLIENT_ID,
                "canonical_write_authority": False,
                "broker_order_authority": False,
                "live_trading_change": False,
                "ib_connected": bool(raw.get("ib_connected")),
                "required_requests_ok": bool(raw.get("required_requests_ok")),
                "canonical_unchanged": canonical_unchanged,
                "request_count": len(requests),
                "requests": requests,
            }
        finally:
            try:
                _compose(repo, project, "down", "--remove-orphans", "-v", timeout=180)
            except Exception:
                pass
            gateway_env.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--ciphertext", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--response-root", required=True)
    args = parser.parse_args()

    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    ciphertext = Path(args.ciphertext).read_bytes()
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=ciphertext,
        private_key_path=Path(args.private_key),
        expected_schema=ENVELOPE_SCHEMA,
        expected_run_id=str(args.run_id),
        expected_authority=AUTHORITY,
        expected_harness=HARNESS,
        response_root=str(args.response_root),
    )
    private = _load_private(plaintext)
    try:
        receipt = execute(private, str(args.run_id))
    finally:
        private.clear()
        plaintext = b""
    print("MMIBKR_IBKR_HISTORY_RECEIPT=" + json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if receipt["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
