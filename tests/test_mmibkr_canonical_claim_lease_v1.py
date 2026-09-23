from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_mmibkr_canonical_workload_dispatch_v1 import CanonicalWorkloadDispatchTests
from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


class CanonicalClaimLeaseTests(CanonicalWorkloadDispatchTests):
    def _claim_path(self, request: dict, receipt_dir: Path) -> tuple[Path, str]:
        validated = mod.validate_request(request, self.source_root, self.source_receipt)
        fingerprint = mod.sha(validated)
        path = receipt_dir / "claims" / f"{fingerprint}.claim"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path, fingerprint

    def test_active_claim_fails_closed_without_duplicate_execution(self):
        receipt_dir = self.root / "lease-active"
        req = self.request("lease-active")
        claim, fingerprint = self._claim_path(req, receipt_dir)
        claim.write_text(
            json.dumps(
                {
                    "schema": mod.CLAIM_SCHEMA,
                    "job_id": "lease-active",
                    "job_fingerprint": fingerprint,
                    "claim_token": "other-owner",
                    "pid": 999999,
                    "lease_seconds": 120,
                    "claimed_at_epoch": time.time(),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "lease is active"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                receipt_dir=receipt_dir,
            )

    def test_stale_claim_is_archived_and_recovered(self):
        receipt_dir = self.root / "lease-stale"
        req = self.request("lease-stale")
        claim, fingerprint = self._claim_path(req, receipt_dir)
        claim.write_text(
            json.dumps(
                {
                    "schema": mod.CLAIM_SCHEMA,
                    "job_id": "lease-stale",
                    "job_fingerprint": fingerprint,
                    "claim_token": "dead-owner",
                    "pid": 999999,
                    "lease_seconds": 5,
                    "claimed_at_epoch": time.time() - 300,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        old = time.time() - 300
        os.utime(claim, (old, old))

        result = mod.execute_request(
            req,
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=receipt_dir,
        )
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["receipt"]["status"], "completed")
        stale = list((receipt_dir / "claims" / "stale").glob(f"{fingerprint}.*.claim"))
        self.assertEqual(len(stale), 1)
        self.assertFalse(claim.exists())

    def test_handled_execution_failure_releases_owned_claim_for_immediate_retry(self):
        receipt_dir = self.root / "lease-handled-failure"
        req = self.request("lease-handled-failure")
        claim, _ = self._claim_path(req, receipt_dir)

        with patch.object(
            mod,
            "safe_execute_valid",
            side_effect=mod.CanonicalDispatchError("fixture execution failure"),
        ):
            with self.assertRaisesRegex(mod.CanonicalDispatchError, "fixture execution failure"):
                mod.execute_request(
                    req,
                    source_root=self.source_root,
                    source_receipt=self.source_receipt,
                    receipt_dir=receipt_dir,
                )

        self.assertFalse(claim.exists())
        retry = mod.execute_request(
            req,
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=receipt_dir,
        )
        self.assertFalse(retry["cache_hit"])
        self.assertEqual(retry["receipt"]["status"], "completed")

    def test_foreign_or_malformed_claim_never_gets_reclaimed(self):
        receipt_dir = self.root / "lease-foreign"
        req = self.request("lease-foreign")
        claim, _ = self._claim_path(req, receipt_dir)
        claim.write_text('{"schema":"unexpected"}\n', encoding="utf-8")
        old = time.time() - 300
        os.utime(claim, (old, old))

        with self.assertRaisesRegex(mod.CanonicalDispatchError, "identity mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                receipt_dir=receipt_dir,
            )


if __name__ == "__main__":
    unittest.main()
