"""No private test fixture, no publication of reversible legacy inputs."""
from __future__ import annotations
import json
import unittest
from scripts.opaque_capsule_exposure_compare_v1 import compare, MARKER

class SyntheticExposureComparisonTests(unittest.TestCase):
    def test_both_upgraded_profiles_outperform_reversible_legacy_transport(self):
        receipt = compare()
        self.assertTrue(receipt["legacy_compressed_session_recoverable_without_key"])
        self.assertEqual(set(receipt["upgraded_profiles"]), {"M1", "A1"})
        for evidence in receipt["upgraded_profiles"].values():
            self.assertTrue(all(evidence.values()))
        self.assertNotIn(MARKER, json.dumps(receipt))
        self.assertFalse(receipt["production_route_admitted"])
        self.assertFalse(receipt["confidential_compute_attested"])

if __name__ == "__main__":
    unittest.main()
