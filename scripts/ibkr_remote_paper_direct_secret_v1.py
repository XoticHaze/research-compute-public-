from __future__ import annotations

"""Materialize the MM-IBKR remote paper runtime from protected Actions secrets.

This is the host-independent ingress used when the private-repository Actions
producer cannot attach a runner. Secret values are read only from environment
variables supplied by the Actions secret store, private MM-IBKR source is
resolved to an exact SHA and downloaded into RUNNER_TEMP, and only paper,
read-only session reconciliation is admitted.
"""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from ibkr_remote_paper_capsule_v1 import SOURCE_REPOSITORY, _safe_extract_tar, _write_private

MAX_SOURCE_ARCHIVE_BYTES = 350_000_000


def _required_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"required protected environment variable missing: {name}")
    return value


def _api_json(url: str, *, token: str) -> tuple[int, dict]:
    req = Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mm-ibkr-public-secret-ingress/1",
        },
    )
    try:
        with urlopen(req, timeout=60) as response:
            raw = response.read()
            status = int(response.getcode())
    except HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        body = {}
    return status, body if isinstance(body, dict) else {}


def resolve_private_head(source_token: str, ref: str) -> str:
    status, body = _api_json(
        f"https://api.github.com/repos/{SOURCE_REPOSITORY}/commits/{quote(ref, safe='')}",
        token=source_token,
    )
    head = str(body.get("sha") or "").strip().lower()
    if status != 200 or len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise RuntimeError("failed to resolve exact private MM-IBKR head")
    return head


def fetch_private_archive(source_token: str, head: str, destination: Path) -> str:
    url = f"https://api.github.com/repos/{SOURCE_REPOSITORY}/tarball/{head}"
    req = Request(
        url,
        headers={
            "Authorization": "Bearer " + source_token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mm-ibkr-public-secret-ingress/1",
        },
    )
    digest = hashlib.sha256()
    total = 0
    with urlopen(req, timeout=120) as response, destination.open("wb") as sink:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in {"api.github.com", "codeload.github.com"}:
            raise RuntimeError("private source archive redirect host rejected")
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_SOURCE_ARCHIVE_BYTES:
                raise RuntimeError("private source archive exceeds byte cap")
            digest.update(block)
            sink.write(block)
    if total <= 0:
        raise RuntimeError("private source archive empty")
    os.chmod(destination, 0o600)
    return digest.hexdigest()


def materialize(*, runner_temp: Path, source_ref: str) -> dict:
    username = _required_env("IBKR_REMOTE_TWS_USERID")
    password = _required_env("IBKR_REMOTE_TWS_PASSWORD")
    source_token = _required_env("IBKR_REMOTE_SOURCE_TOKEN")

    head = resolve_private_head(source_token, source_ref)
    archive = runner_temp / "mm-ibkr-source.tar.gz"
    archive_sha256 = fetch_private_archive(source_token, head, archive)
    source_root = _safe_extract_tar(archive, runner_temp / "mm-ibkr-source")

    gateway_env = runner_temp / "ibkr-gateway.env"
    _write_private(
        gateway_env,
        "\n".join(
            [
                "TWS_USERID=" + username,
                "TWS_PASSWORD=" + password,
                "TRADING_MODE=paper",
                "READ_ONLY_API=yes",
                "TWS_ACCEPT_INCOMING=accept",
                "TWOFA_TIMEOUT_ACTION=exit",
                "RELOGIN_AFTER_TWOFA_TIMEOUT=no",
                "SAVE_TWS_SETTINGS=no",
                "ENABLE_VNC=false",
                "",
            ]
        ),
    )

    request_path = runner_temp / "ibkr-submit-request.json"
    _write_private(request_path, "{}\n")
    runtime = {
        "schema": "mm-ibkr-remote-paper-materialization-v1",
        "mode": "session_reconcile",
        "mmibkr_repository": SOURCE_REPOSITORY,
        "mmibkr_head": head,
        "source_archive_sha256": archive_sha256,
        "source_root": str(source_root),
        "gateway_env_path": str(gateway_env),
        "request_path": str(request_path),
        "read_only_api": "yes",
        "cleanup": {
            "cancel_open_order": False,
            "flatten_filled_position": False,
            "require_zero_baseline": False,
            "allow_global_cancel": False,
        },
        "paper_only": True,
        "live_trading_change": False,
        "host_dependency": False,
        "secrets_in_receipt": False,
        "credential_ingress": "github_actions_protected_secrets",
    }
    runtime_path = runner_temp / "ibkr-runtime.json"
    _write_private(runtime_path, json.dumps(runtime, sort_keys=True) + "\n")
    return runtime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-temp", required=True)
    parser.add_argument("--source-ref", default="main")
    args = parser.parse_args()
    runtime = materialize(runner_temp=Path(args.runner_temp), source_ref=args.source_ref)
    print(
        "IBKR_REMOTE_DIRECT_SECRET_MATERIALIZED="
        + json.dumps(
            {
                key: runtime[key]
                for key in (
                    "schema",
                    "mode",
                    "mmibkr_repository",
                    "mmibkr_head",
                    "source_archive_sha256",
                    "read_only_api",
                    "paper_only",
                    "live_trading_change",
                    "host_dependency",
                    "secrets_in_receipt",
                    "credential_ingress",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
