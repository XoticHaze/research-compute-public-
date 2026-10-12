import os
import unittest
from unittest.mock import patch

from scripts import ibkr_paper_warning_rescue_v1 as rescue


class ExactPaperWarningRescueTests(unittest.TestCase):
    def test_paper_only_warning_and_scoped_explicit_consent(self):
        modal = [("Warning", True)]
        labels = [("Warning", "This is not a brokerage account. You are using simulated trading.")]
        buttons = {"OK", "I understand", "Paper Log In"}
        self.assertEqual(
            rescue.select_exact_paper_warning(modal, labels, buttons),
            ("Warning", "I understand"),
        )

    def test_unknown_warning_must_not_be_accepted(self):
        modal = [("Warning", True)]
        labels = [("Warning", "Please accept updated legal terms.")]
        self.assertIsNone(
            rescue.select_exact_paper_warning(modal, labels, {"I agree", "OK"})
        )

    def test_no_blanket_ok_or_login_click(self):
        modal = [("Warning", True)]
        labels = [("Warning", "This is not a brokerage account.")]
        self.assertIsNone(
            rescue.select_exact_paper_warning(modal, labels, {"OK", "Paper Log In"})
        )

    def test_paper_text_in_non_modal_or_other_window_must_not_authorize(self):
        self.assertIsNone(
            rescue.select_exact_paper_warning(
                [("Warning", True)],
                [("IBKR Gateway", "This is not a brokerage account.")],
                {"I agree"},
            )
        )
        self.assertIsNone(
            rescue.select_exact_paper_warning(
                [("Warning", False)],
                [("Warning", "This is not a brokerage account.")],
                {"I agree"},
            )
        )

    def test_ambiguous_modal_rejected(self):
        self.assertIsNone(
            rescue.select_exact_paper_warning(
                [("Warning", True), ("Paper account notice", True)],
                [
                    ("Warning", "This is not a brokerage account."),
                    ("Paper account notice", "This is a paper account."),
                ],
                {"I understand"},
            )
        )

    def test_no_live_execution_even_if_dialog_present(self):
        with patch.dict(
            os.environ,
            {"TRADING_MODE": "live", "IBKR_PAPER_DISCLAIMER_RESCUE": "1"},
        ), patch.object(rescue, "agent_request", side_effect=AssertionError("agent called")):
            self.assertEqual(rescue.run(apply=True), 0)

    def test_paper_not_enabled_is_passive(self):
        with patch.dict(
            os.environ,
            {"TRADING_MODE": "paper", "IBKR_PAPER_DISCLAIMER_RESCUE": "0"},
        ), patch.object(rescue, "agent_request", side_effect=AssertionError("agent called")):
            self.assertEqual(rescue.run(apply=True), 0)

    def test_exact_modal_click_only_by_window(self):
        replies = iter([
            "JDialog | Warning | modal=true\nEND\n",
            "[Warning] This is not a brokerage account.\nEND\n",
            "button I understand\nbutton OK\nEND\n",
            "OK clicked\n",
        ])
        with patch.dict(
            os.environ,
            {"TRADING_MODE": "paper", "IBKR_PAPER_DISCLAIMER_RESCUE": "1"},
        ), patch.object(rescue, "agent_request", side_effect=lambda *a, **k: next(replies)) as agent:
            self.assertEqual(rescue.run(apply=True), 0)
        self.assertEqual(agent.call_args.args[0], "CLICK_IN_WIN Warning|I understand")

    def test_no_click_when_agent_unavailable(self):
        with patch.dict(
            os.environ,
            {"TRADING_MODE": "paper", "IBKR_PAPER_DISCLAIMER_RESCUE": "1"},
        ), patch.object(rescue, "agent_request", side_effect=TimeoutError):
            self.assertEqual(rescue.run(apply=True), 0)


if __name__ == "__main__":
    unittest.main()
