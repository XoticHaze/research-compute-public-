from __future__ import annotations

"""Materialize one exact private MM-IBKR source tree without broker credentials.

The public orchestrator needs private source only so it can run MM-owned planning,
strategy evaluation, roll maintenance, and encrypted B1 dispatch. TWS credentials
remain exclusively on broker-bearing B1 surfaces.
"""

import argparse
import json
import os
from pathlib import Path

from ibkr_remote_paper_capsule_v1 import _safe_extract_tar
from ibkr_remote_paper_direct_secret_v1 import (
    SOURCE_REPOSITORY,
    _required_env,
    fetch_private_archive,
    resolve_private_head,
)


SCHEMA = "mmibkr.private_source_materialization.v1"


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def materialize(
    *,
    runner_temp: Path,
    source_ref: str,
    source_token: str | None = None,
) -> dict:
    token = str(source_token or "").strip() or _required_env(
        "IBKR_REMOTE_SOURCE_TOKEN"
    )
    requested_ref = str(source_ref or "").strip()
    if not requested_ref:
        raise RuntimeError("private source ref is required")

    head = resolve_private_head(token, requested_ref)
    archive = runner_temp / "mm-ibkr-source.tar.gz"
    archive_sha256 = fetch_private_archive(token, head, archive)
    source_root = _safe_extract_tar(
        archive,
        runner_temp / "mm-ibkr-source",
    )
    runtime = {
        "schema": SCHEMA,
        "mmibkr_repository": SOURCE_REPOSITORY,
        "requested_source_ref": requested_ref,
        "mmibkr_head": head,
        "source_archive_sha256": archive_sha256,
        "source_root": str(source_root),
        "broker_credentials_materialized": False,
        "tws_credentials_required": False,
        "source_token_emitted": False,
        "paper_or_live_authority": False,
    }
    runtime_path = runner_temp / "mmibkr-private-source.json"
    _write_private(
        runtime_path,
        json.dumps(runtime, sort_keys=True) + "\n",
    )
    return {**runtime, "runtime_path": str(runtime_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-temp", required=True)
    parser.add_argument("--source-ref", required=True)
    args = parser.parse_args()

    result = materialize(
        runner_temp=Path(args.runner_temp),
        source_ref=args.source_ref,
    )
    printable = {
        key: result[key]
        for key in (
            "schema",
            "mmibkr_repository",
            "requested_source_ref",
            "mmibkr_head",
            "source_archive_sha256",
            "source_root",
            "broker_credentials_materialized",
            "tws_credentials_required",
            "source_token_emitted",
            "paper_or_live_authority",
            "runtime_path",
        )
    }
    print(json.dumps(printable, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
