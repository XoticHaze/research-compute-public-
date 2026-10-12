"""Synthetic and real mount preflight for memory-only public rendezvous scratch."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import public_compute_memory_scratch_v1 as guard


class PublicComputeMemoryScratchTests(unittest.TestCase):
    def test_tmpfs_mount_required(self):
        yes = "tmpfs /dev/shm tmpfs rw,nosuid,nodev 0 0\n"
        no = "/dev/sda1 /dev/shm ext4 rw 0 0\n"
        self.assertTrue(guard._mounted_tmpfs(yes))
        self.assertFalse(guard._mounted_tmpfs(no))
        self.assertFalse(guard._mounted_tmpfs("tmpfs /tmp tmpfs rw 0 0\n"))

    def test_guest_swap_must_be_disabled(self):
        header = "Filename\tType\tSize\tUsed\tPriority\n"
        self.assertTrue(guard._swap_is_off(header))
        self.assertFalse(guard._swap_is_off(header + "/swapfile file 1048576 0 -2\n"))
        self.assertFalse(guard._swap_is_off(""))

    def test_run_identity_fail_closed(self):
        for run_id in ("", "abc", "../../etc", "123/456", "0" * 25):
            with self.subTest(run_id=run_id), patch.dict(os.environ, {"GITHUB_RUN_ID": run_id}):
                with self.assertRaises(guard.ScratchRejected):
                    guard._run_id()
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "38232080214"}):
            self.assertEqual(guard._run_id(), "38232080214")

    def test_metadata_path_rejects_outside_root(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            for selected in ("/tmp/plaintext", "/dev/shm/not-owned", "/dev/shm/cc-public-rendezvous-321-abc"):
                with self.subTest(path=selected):
                    with self.assertRaises(guard.ScratchRejected):
                        guard._validate_path(Path(selected))

    def test_end_to_end_tmpfs_mount_and_cleanup(self):
        # Run this only when the *actual* execution host supports the policy.
        # This is a guest test and cannot establish host/TEE confidentiality.
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "918273645"}):
            path = guard.initialize()
            prior_tempdir = tempfile.tempdir
            try:
                with patch.dict(os.environ, {
                    "TMPDIR": path,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PUBLIC_COMPUTE_REQUIRE_RAM_SCRATCH": "1",
                }):
                    tempfile.tempdir = None
                    guard.check()
                    fd, payload_name = tempfile.mkstemp(dir=None)
                    os.close(fd)
                    payload_path = Path(payload_name)
                    try:
                        self.assertEqual(payload_path.parent, Path(path))
                        payload_path.write_bytes(b"synthetic-only-not-PHI")
                    finally:
                        payload_path.unlink(missing_ok=True)
                    with patch.dict(os.environ, {"PYTHONDONTWRITEBYTECODE": "0"}):
                        with self.assertRaises(guard.ScratchRejected):
                            guard.check()
                    guard.cleanup()
                    self.assertFalse(Path(path).exists())
            finally:
                tempfile.tempdir = prior_tempdir
                # Cleanup even on assertion failure, but only within validated run root.
                if Path(path).exists():
                    with patch.dict(os.environ, {"TMPDIR": path}):
                        guard.cleanup()

    def test_existing_workflow_never_places_private_material_in_runner_temp(self):
        workflow = Path(".github/workflows/commandcenter-ledger-ephemeral-rendezvous.yml").read_text()
        self.assertIn("scripts/public_compute_memory_scratch_v1.py init", workflow)
        self.assertIn("scripts/public_compute_memory_scratch_v1.py check", workflow)
        self.assertIn("scripts/public_compute_memory_scratch_v1.py cleanup", workflow)
        self.assertIn("PUBLIC_COMPUTE_REQUIRE_RAM_SCRATCH=1", workflow)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("ulimit -c 0", workflow)
        self.assertNotIn("RUNNER_TEMP", workflow)
        self.assertLess(workflow.index("memory_scratch_v1.py init"),
                        workflow.index("Generate one-run recipient"))
        self.assertLess(workflow.index("memory_scratch_v1.py check"),
                        workflow.index("commandcenter_neutral_gate_ephemeral_consumer_v1.py"))


if __name__ == "__main__":
    unittest.main()
