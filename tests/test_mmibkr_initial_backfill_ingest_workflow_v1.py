from __future__ import annotations

from pathlib import Path
import contextlib
import hashlib
import io
import json
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class InitialBackfillCanonicalIngestWorkflowTests(unittest.TestCase):
    def test_exact_proven_public_artifact_is_pinned(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("INITIAL_BACKFILL_RUN_ID: '40665095081'", text)
        self.assertIn(
            "INITIAL_BACKFILL_ARTIFACT: ibkr-cloudflare-readonly-b1-40665095081",
            text,
        )
        self.assertIn('gh run download "$INITIAL_BACKFILL_RUN_ID"', text)
        self.assertIn("--name \"$INITIAL_BACKFILL_ARTIFACT\"", text)

    def test_artifact_crosses_existing_private_canonical_ingest_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        end = text.index("- name: Run bounded selected-runtime cloud owner")
        section = text[start:end]

        self.assertIn(
            "scripts/operator/selected_runtime_initial_backfill_ingest_v1.py",
            section,
        )
        self.assertIn("-w /app", section)
        self.assertIn("-e PYTHONPATH=/app", section)
        self.assertIn("--data-root /app/data", section)
        self.assertIn("--bars /input/ibkr-forward-bars-v2.jsonl", section)
        self.assertIn("--handoff /input/ibkr-post-auth-handoff.json", section)
        self.assertIn(
            "--fleet-receipt /input/ibkr-cloudflare-envelope-receipt.json",
            section,
        )
        self.assertIn("all_warmups_ready", section)
        self.assertIn("MMIBKR_INITIAL_BACKFILL_INGEST=accepted", section)
        self.assertLess(
            text.index(
                "- name: Consume proven initial selected-runtime backfill through canonical ingest"
            ),
            text.index("- name: Run bounded selected-runtime cloud owner"),
        )

    def test_container_python_heredoc_probes_keep_stdin_attached(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        end = text.index("- name: Run bounded selected-runtime cloud owner")
        section = text[start:end]
        self.assertGreaterEqual(section.count("docker run --rm -i"), 2)
        self.assertNotIn("docker run --rm \\\n            -v \"$RUNNER_TEMP/mmibkr-data:/app/data:ro\"", section)

    def test_warmup_and_authority_guards_are_fail_closed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        end = text.index("- name: Run bounded selected-runtime cloud owner")
        section = text[start:end]

        self.assertIn("AMAT target coverage below warmup", section)
        self.assertIn("APH target coverage below warmup", section)
        self.assertIn("MNQ source coverage below warmup", section)
        self.assertIn("MNQ target coverage below warmup", section)
        self.assertIn("broker_action", section)
        self.assertIn("runtime_execution_contract_mutated", section)
        self.assertIn("live_execution_allowed", section)
        self.assertNotIn("placeOrder", section)
        self.assertNotIn("cancelOrder", section)
        self.assertNotIn("globalCancel", section)

    def test_warmup_reuse_crossbinds_index_to_exact_ingest_runtime_contracts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("- name: Consume proven initial selected-runtime backfill through canonical ingest")
        end = text.index("- name: Run bounded selected-runtime cloud owner")
        section = text[start:end]
        self.assertIn(
            "from scripts.operator.selected_runtime_signal_history_contract_v1 import contract_digest",
            section,
        )
        self.assertIn("row.get('selected_execution_contract_digest') != contract_digest(selected_contract)", section)
        self.assertIn("row.get('symbol') != symbol", section)
        self.assertIn("row.get('target_timeframe') != source.get('target_timeframe')", section)
        self.assertIn("len(set(runtime_ids)) != 3 or set(rows) != set(runtime_ids)", section)
        self.assertIn("'execution_authority_included', 'execution_contract_values_included'", section)

    def test_existing_canonical_checkpoint_is_restored_before_ingest_and_saved_after(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        restore = text.index("- name: Restore canonical market-data and terminal-continuity state")
        ingest = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        owner = text.index("- name: Run bounded selected-runtime cloud owner")
        checkpoint = text.index("- name: Build sanitized successor checkpoint")
        save = text.index("- name: Save sanitized successor checkpoint cache")

        self.assertLess(restore, ingest)
        self.assertLess(ingest, owner)
        self.assertLess(owner, checkpoint)
        self.assertLess(checkpoint, save)
        self.assertIn("CHECKPOINT_CACHE_PREFIX: mmibkr-selected-runtime-cloud-checkpoint-v1-", text)

    def test_sanitized_session_receipt_records_the_crossing(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_READY", text)
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_PERFORMED", text)
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_PUBLIC_RUN_ID", text)
        self.assertIn("receipt['initial_backfill_ingest']", text)
        self.assertIn("'artifact_name': 'ibkr-cloudflare-readonly-b1-40665095081'", text)
        self.assertIn("'broker_action': False", text)
        self.assertIn("'runtime_execution_contract_mutated': False", text)
        self.assertIn("'live_execution_allowed': False", text)


    def test_warmup_reuse_probe_rejects_crossfile_runtime_or_digest_drift(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("if reuse_rows=\"$(docker run --rm -i")
        probe_start = text.index("          import json\n", start)
        probe_end = text.index("          PY\n", probe_start)
        probe = textwrap.dedent(text[probe_start:probe_end])
        import_line = (
            "from scripts.operator.selected_runtime_signal_history_contract_v1 "
            "import contract_digest\n"
        )
        self.assertIn(import_line, probe)
        # Replace only the private image's canonical import with a synthetic
        # digest helper. This never loads private source or market data.
        probe = probe.replace(import_line, "")
        def digest(contract):
            raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
            return "sha256:" + hashlib.sha256(raw).hexdigest()

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            index_path = root / "signal.json"
            ingest_path = root / "ingest.json"
            probe = probe.replace(
                "/app/data/strategy_runtime/selected_runtime_signal_history_contracts_v1/latest.json",
                str(index_path),
            ).replace(
                "/app/data/strategy_runtime/selected_runtime_initial_backfill_v1/latest.json",
                str(ingest_path),
            )
            symbols = {}
            rows = {}
            for symbol, tf, cls in (("AMAT", "15Min", "STK"),
                                    ("APH", "15Min", "STK"),
                                    ("MNQ", "12Min", "FUT")):
                runtime_id = "synthetic_" + symbol.lower()
                contract = {"conId": len(symbol), "symbol": symbol, "secType": cls}
                symbols[symbol] = {
                    "runtime_id": runtime_id,
                    "instrument_class": cls,
                    "target_timeframe": tf,
                    "source_timeframe": "1Min",
                    "selected_execution_contract": contract,
                    "warmup": {"ready": True, "continuity_covered": True},
                    "source_rows": 5000,
                    "target_rows": 500,
                }
                rows[runtime_id] = {
                    "runtime_id": runtime_id,
                    "symbol": symbol,
                    "instrument_class": cls,
                    "target_timeframe": tf,
                    "source_timeframe": "1Min",
                    "selected_execution_contract_digest": digest(contract),
                    "warmup_ready": True,
                }
            index = {
                "schema": "mmibkr.selected_runtime_signal_history_contracts.v1",
                "ok": True, "public_run_id": "40665095081",
                "runtime_count": 3, "runtimes": rows,
                **{flag: False for flag in (
                    "execution_authority_included", "execution_contract_values_included",
                    "account_state_included", "positions_included", "orders_included",
                    "credentials_included", "broker_action",
                )},
            }
            ingest = {
                "schema": "mmibkr.selected_runtime_initial_backfill_ingest.v1",
                "ok": True, "all_warmups_ready": True,
                "artifact": {"public_run_id": "40665095081"},
                "symbols": symbols, "broker_action": False,
                "runtime_execution_contract_mutated": False,
                "live_execution_allowed": False,
            }
            def evaluate():
                index_path.write_text(json.dumps(index), encoding="utf-8")
                ingest_path.write_text(json.dumps(ingest), encoding="utf-8")
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    exec(compile(probe, "<synthetic-warmup-reuse>", "exec"),
                         {"contract_digest": digest})
                return output.getvalue()

            self.assertIn("MNQ_SOURCE_ROWS=5000", evaluate())
            rows["synthetic_mnq"]["symbol"] = "APH"
            with self.assertRaises(SystemExit):
                evaluate()
            rows["synthetic_mnq"]["symbol"] = "MNQ"
            rows["synthetic_mnq"]["selected_execution_contract_digest"] = "sha256:" + "0" * 64
            with self.assertRaises(SystemExit):
                evaluate()


if __name__ == "__main__":
    unittest.main()
