from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cloudflare/fleet-authority/src/source_exchange.js"

class P01FleetSourceAdmissionContractTests(unittest.TestCase):
    def test_p01_exact_source_consumer_is_bounded(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("P01_CRW_DCA_EXACT_VALIDATION_IDENTITY", text)
        self.assertIn(
            "XoticHaze/research-compute-public-/.github/workflows/"
            "p01-crw-dca-ephemeral-rendezvous.yml@refs/heads/main",
            text,
        )
        self.assertIn("P01_CRW_DCA_EXACT_VALIDATION_SOURCE", text)
        self.assertIn("35e6b44e5c2618f780a84c1c204fe14c76bdf0e5", text)
        self.assertIn("P01_CRW_DCA_EXACT_VALIDATION_EXPIRES_AT", text)
        self.assertIn("matchedP01CrwDcaValidation", text)
        self.assertIn("privateArchivePathAllowed", text)
        self.assertNotIn("p01-crw-dca-ephemeral-rendezvous.yml@refs/heads/assistant/", text)

if __name__ == "__main__":
    unittest.main()
