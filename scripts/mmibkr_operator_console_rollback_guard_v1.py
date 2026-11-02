"""Exact-version, fail-closed Cloudflare Worker rollback guard."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")
ROOT = Path(os.environ["RUNNER_TEMP"])
BEFORE = ROOT / "mmibkr-worker-before-version"
AFTER = ROOT / "mmibkr-worker-after-version"


def active_version():
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account or not token:
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_AUTH_MISSING=1")
    url = ("https://api.cloudflare.com/client/v4/accounts/" + account
           + "/workers/scripts/mmibkr-operator-console/deployments?per_page=1")
    req = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "mmibkr-operator-console-version-guard-r1",
    })
    try:
        with urlopen(req, timeout=20) as response:
            body = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_VERSION_READ_FAILED=1") from None
    rows = ((body.get("result") or {}).get("deployments")
            if isinstance(body, dict) and body.get("success") is True else None)
    versions = (rows[0].get("versions") if isinstance(rows, list) and rows
                and isinstance(rows[0], dict) else None)
    if not isinstance(versions, list) or len(versions) != 1 or not isinstance(versions[0], dict):
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_SPLIT_OR_MISSING=1")
    entry = versions[0]
    version = entry.get("version_id")
    if (not isinstance(version, str) or not UUID.fullmatch(version.lower())
            or entry.get("percentage") != 100):
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_VERSION_INVALID=1")
    return version.lower()


def pinned(path):
    if not path.is_file() or path.is_symlink():
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_PIN_MISSING=1")
    value = path.read_text(encoding="ascii").strip()
    if not UUID.fullmatch(value):
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_PIN_INVALID=1")
    return value


def persist(path, value):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as out:
        out.write(value + "\n")


def main(mode):
    if mode == "capture-before":
        persist(BEFORE, active_version())
        print("MMIBKR_WORKER_ROLLBACK_PREDEPLOY_PIN=READY")
    elif mode == "verify-before":
        if active_version() != pinned(BEFORE):
            raise SystemExit("MMIBKR_WORKER_PREDEPLOY_CONCURRENT_CHANGE_HELD=1")
        print("MMIBKR_WORKER_PREDEPLOY_VERSION_STABLE=1")
    elif mode == "capture-after":
        old = pinned(BEFORE)
        new = active_version()
        if new == old:
            raise SystemExit("MMIBKR_WORKER_DEPLOY_NO_NEW_VERSION=1")
        persist(AFTER, new)
        print("MMIBKR_WORKER_ROLLBACK_POSTDEPLOY_PIN=READY")
    elif mode == "rollback-if-matching":
        if not AFTER.is_file():
            print("MMIBKR_WORKER_ROLLBACK=HELD_NO_POSTDEPLOY_PIN")
            return
        old, new = pinned(BEFORE), pinned(AFTER)
        if active_version() != new:
            raise SystemExit("MMIBKR_WORKER_ROLLBACK_CONCURRENT_CHANGE_HELD=1")
        try:
            subprocess.run([
                "npx", "--yes", "wrangler@4.131.2", "rollback", old,
                "--config", "cloudflare/operator-console/wrangler.jsonc",
                "--message", "Restore pinned prior version after failed release proof",
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            raise SystemExit("MMIBKR_WORKER_ROLLBACK_COMMAND_FAILED=1") from None
        if active_version() != old:
            raise SystemExit("MMIBKR_WORKER_ROLLBACK_READBACK_FAILED=1")
        print("MMIBKR_WORKER_ROLLBACK=PINNED_PREVIOUS_VERSION_RESTORED")
    else:
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_MODE_INVALID=1")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("MMIBKR_WORKER_ROLLBACK_MODE_REQUIRED=1")
    main(sys.argv[1])
