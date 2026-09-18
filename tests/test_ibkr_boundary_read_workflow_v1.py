from pathlib import Path
import unittest


WORKFLOW = Path(".github/workflows/ibkr-cloudflare-readonly-b1-r1.yml")


class BoundaryReadWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_optional_boundary_input_is_readonly_snapshot_only(self):
        self.assertIn("snapshot_not_before_utc:", self.text)
        self.assertIn("IBKR_WARM_READ_RETURN_REQUESTED == '1'", self.text)
        self.assertIn("inputs.snapshot_not_before_utc != ''", self.text)

        wait = self.text.index("name: Wait for optional completed-bar snapshot boundary")
        handoff = self.text.index("name: Materialize canonical post-auth broker and forward-data handoff")
        encrypt = self.text.index("name: Encrypt optional detailed warm read snapshot for private consumer")
        self.assertLess(wait, handoff)
        self.assertLess(handoff, encrypt)

    def test_boundary_wait_is_bounded_and_requires_explicit_time(self):
        self.assertIn("snapshot_not_before_utc must be ISO-8601", self.text)
        self.assertIn("snapshot_not_before_utc must include an explicit UTC offset", self.text)
        self.assertIn("snapshot boundary is more than 600 seconds in the future", self.text)
        self.assertIn("snapshot boundary is more than 60 seconds stale", self.text)
        self.assertIn("time.sleep(delay)", self.text)
        self.assertIn("IBKR_SNAPSHOT_BOUNDARY_REACHED_UTC=", self.text)

    def test_boundary_feature_does_not_make_readonly_gateway_writable(self):
        self.assertIn(
            "IBKR_WARM_READ_RETURN_REQUESTED: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'readonly'",
            self.text,
        )
        writable = self.text.index('if [ "$IBKR_PAPER_PROOF_MODE" = "1" ] || [ "$IBKR_PAPER_EXECUTE_MODE" = "1" ]; then')
        block = self.text[writable:writable + 220]
        self.assertIn("api_read_only=no", block)
        self.assertNotIn("snapshot_not_before_utc", block)

    def test_boundary_wait_happens_after_gateway_ready(self):
        ready = self.text.index("IBKR_GATEWAY_API_READY=1")
        wait = self.text.index("name: Wait for optional completed-bar snapshot boundary")
        self.assertLess(ready, wait)


if __name__ == "__main__":
    unittest.main()
