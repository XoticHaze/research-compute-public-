from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "cb28771e5fd3aa610d8fcf2ef683596a1cfabd51"


class CloudOwnerReusableVaultContractTests(unittest.TestCase):
    def test_owner_uses_reusable_vault_and_ephemeral_same_repo_control_token(self):
        text = (ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-r1.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/mmibkr_source_vault_consumer_v1.py", text)
        self.assertIn("--public-repo XoticHaze/mm-ibkr-runtime", text)
        self.assertIn("--public-branch mmibkr-source-vault", text)
        self.assertIn(SOURCE_SHA, text)
        self.assertIn("IBKR_REMOTE_EXCHANGE_TOKEN: ${{ github.token }}", text)
        self.assertNotIn("secrets.IBKR_REMOTE_EXCHANGE_TOKEN", text)
        self.assertNotIn("python scripts/mmibkr_cloud_source_exchange_consumer_v1.py", text)
        self.assertIn("ENABLE_LIVE_TRADING=0", text)

    def test_watchdog_restarts_exact_accepted_source_not_private_main(self):
        text = (ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-watchdog-r1.yml").read_text(encoding="utf-8")
        self.assertIn("'source_ref':'" + SOURCE_SHA + "'", text)
        self.assertNotIn("'source_ref':'main'", text)


if __name__ == "__main__":
    unittest.main()
