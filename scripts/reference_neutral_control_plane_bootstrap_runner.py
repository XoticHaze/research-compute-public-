from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--receipt",
        default="rendezvous/receipts/reference-neutral-control-plane-bootstrap-r1.json",
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    helper = root / "scripts" / "reference_neutral_control_plane_bootstrap.py"
    proc = subprocess.run(
        [sys.executable, str(helper), "--repo-root", str(root)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    allowed: list[str] = []
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if (
            re.match(r"^(REFERENCE_|EXISTING_|CLOUDFLARE_)[A-Z0-9_]+=.*$", line)
            or " version upload failed HTTP " in line
            or " settings proof failed HTTP " in line
            or " secret binding update failed HTTP " in line
            or line.startswith("Unexpected broker denial status:")
        ):
            allowed.append(line[:500])

    receipt = {
        "schema": "reference.neutral_control_plane.bootstrap_receipt.r1",
        "exit_code": int(proc.returncode),
        "markers": allowed,
        "credential_strategy": "existing_deploy_credential",
        "new_token_created": False,
        "secrets_included": False,
    }
    out = root / args.receipt
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
