"""Memory-backed scratch policy for ordinary public compute runners.

Limits *guest* plaintext persistence only. Does not claim privileged-host isolation,
hardware attestation, swap behavior outside the guest, or secure RAM erasure.
The script never reads, prints, or persists any private payload.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path

ROOT = Path("/dev/shm")
PREFIX = "cc-public-rendezvous-"
MAX_RUN_DIGITS = 24


class ScratchRejected(RuntimeError):
    pass


def _mounted_tmpfs(mounts: str) -> bool:
    """Require /dev/shm itself to be a tmpfs mount, not a disk symlink."""
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1] == str(ROOT) and fields[2] == "tmpfs":
            return True
    return False


def _swap_is_off(swaps: str) -> bool:
    lines = [line for line in swaps.splitlines() if line.strip()]
    return len(lines) == 1 and lines[0].split()[:2] == ["Filename", "Type"]


def _environment_safe() -> None:
    try:
        mounts = Path("/proc/mounts").read_text(encoding="utf-8")
        swaps = Path("/proc/swaps").read_text(encoding="utf-8")
    except OSError as exc:
        raise ScratchRejected("kernel_mount_observation_unavailable") from exc
    if not ROOT.is_dir() or ROOT.is_symlink() or not _mounted_tmpfs(mounts):
        raise ScratchRejected("memory_mount_unavailable")
    if not _swap_is_off(swaps):
        raise ScratchRejected("guest_swap_not_disabled")


def _run_id() -> str:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[0-9]{1,24}", run_id):
        raise ScratchRejected("run_identity_unavailable")
    return run_id


def _validate_path(path: Path) -> None:
    if path.parent != ROOT or not path.name.startswith(PREFIX + _run_id() + "-"):
        raise ScratchRejected("scratch_path_rejected")
    if path.is_symlink() or not path.is_dir():
        raise ScratchRejected("scratch_directory_missing")
    info = path.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ScratchRejected("scratch_ownership_rejected")


def initialize() -> str:
    _environment_safe()
    run_id = _run_id()
    path = Path(tempfile.mkdtemp(prefix=PREFIX + run_id + "-", dir=str(ROOT)))
    os.chmod(path, 0o700)
    _validate_path(path)
    return str(path)


def check() -> None:
    _environment_safe()
    selected = os.environ.get("TMPDIR", "")
    if not selected:
        raise ScratchRejected("scratch_not_bound")
    _validate_path(Path(selected))
    if tempfile.gettempdir() != selected:
        raise ScratchRejected("tempfile_binding_rejected")
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise ScratchRejected("bytecode_cache_not_disabled")
    if os.environ.get("PUBLIC_COMPUTE_REQUIRE_RAM_SCRATCH") != "1":
        raise ScratchRejected("policy_not_required")


def cleanup() -> None:
    selected = os.environ.get("TMPDIR", "")
    if not selected:
        return
    path = Path(selected)
    _validate_path(path)
    shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("init", "check", "cleanup"))
    args = parser.parse_args()
    try:
        if args.operation == "init":
            print(initialize())
        elif args.operation == "check":
            check()
            print("PUBLIC_COMPUTE_RAM_SCRATCH=PASS")
        else:
            cleanup()
            print("PUBLIC_COMPUTE_RAM_SCRATCH_CLEANUP=PASS")
        return 0
    except (ScratchRejected, OSError, ValueError):
        print("PUBLIC_COMPUTE_RAM_SCRATCH=FAIL_CLOSED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
