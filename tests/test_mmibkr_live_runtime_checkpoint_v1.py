"""Offline tests for the encrypted MM-IBKR runtime handoff."""
import io
import os
import tarfile
import unittest
from scripts.mmibkr_live_runtime_checkpoint_v1 import context, seal, unseal


def sample_archive():
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, payload in (
            ("gateway/native-state.txt", b"sample"),
            ("bot_data/order-state.json", b"{}"),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    return output.getvalue()


class CheckpointTests(unittest.TestCase):
    def test_seal_and_restore_across_distinct_runs(self):
        key = os.urandom(32)
        raw = sample_archive()
        encrypted, manifest = seal(raw, "39200000001", key)
        self.assertEqual(unseal(encrypted, manifest, "39200000002", key), raw)

    def test_handoff_does_not_grant_order_authority(self):
        c = context("39200000001")
        self.assertEqual(c["scope"], ["AMAT", "APH", "MNQ"])
        self.assertEqual(c["order_authority"], "none_checkpoint_requires_fresh_canonical_admission")

    def test_reject_same_run_and_wrong_key(self):
        key = os.urandom(32)
        encrypted, manifest = seal(sample_archive(), "39200000001", key)
        with self.assertRaises(ValueError):
            unseal(encrypted, manifest, "39200000001", key)
        with self.assertRaises(ValueError):
            unseal(encrypted, manifest, "39200000002", os.urandom(32))

    def test_reject_invalid_payload(self):
        key = os.urandom(32)
        encrypted, manifest = seal(sample_archive(), "39200000001", key)
        with self.assertRaises(ValueError):
            unseal(encrypted[:-1], manifest, "39200000002", key)


if __name__ == "__main__":
    unittest.main()
