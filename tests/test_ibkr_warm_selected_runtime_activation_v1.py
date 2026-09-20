import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from scripts import ibkr_warm_selected_runtime_activation_v1 as mod


class WarmSelectedRuntimeActivationTests(unittest.TestCase):
    def test_direct_entrypoints_import_repo_package(self):
        root = Path(__file__).resolve().parents[1]
        for script in (
            "scripts/ibkr_warm_selected_runtime_activation_v1.py",
            "scripts/ibkr_remote_selected_runtime_paper_execute_v1.py",
        ):
            proc = subprocess.run(
                [sys.executable, script, "--help"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("usage:", proc.stdout.lower())

    def test_command_recipient_is_run_bound_and_private_key_is_owner_only(self):
        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "recipient-private.b64"
            recipient = mod.generate_command_recipient(run_id="12345", private_key_path=key_path)
            self.assertEqual(recipient["schema"], mod.RECIPIENT_SCHEMA)
            self.assertEqual(recipient["run_id"], "12345")
            self.assertEqual(recipient["authority"], mod.capsule_v2.AUTHORITY)
            self.assertEqual(recipient["harness"], mod.capsule_v2.HARNESS)
            raw_public = base64.b64decode(recipient["recipient_b64"], validate=True)
            self.assertEqual(len(raw_public), 32)
            self.assertEqual(recipient["recipient_key_id"], "sha256:" + hashlib.sha256(raw_public).hexdigest())
            self.assertEqual(stat.S_IMODE(key_path.stat().st_mode), 0o600)

    def test_recipient_publish_fails_closed_on_identity_mismatch(self):
        calls = []

        def publish(**kwargs):
            calls.append(kwargs)

        recipient = {
            "schema": mod.RECIPIENT_SCHEMA,
            "run_id": "999",
            "recipient_b64": "x",
            "recipient_key_id": "sha256:" + "0" * 64,
            "authority": mod.capsule_v2.AUTHORITY,
            "harness": mod.capsule_v2.HARNESS,
        }
        with self.assertRaisesRegex(mod.ActivationError, "run_id"):
            mod.publish_command_recipient(
                token="token",
                repository="XoticHaze/research-compute-public-",
                branch=mod.EXCHANGE_REF,
                run_id="123",
                recipient=recipient,
                publisher=publish,
            )
        self.assertEqual(calls, [])

    def test_chunk_assembly_is_run_scoped_and_digest_checked(self):
        run_id = "123"
        ciphertext = b"encrypted-command-bytes"
        encoded = base64.b64encode(ciphertext).decode("ascii")
        pieces = [encoded[:10], encoded[10:]]
        paths = [
            f"rendezvous/responses/{run_id}/ibkr-remote-paper-000.txt",
            f"rendezvous/responses/{run_id}/ibkr-remote-paper-001.txt",
        ]
        envelope = {
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "chunks": [
                {"path": path, "sha256": hashlib.sha256(piece.encode()).hexdigest(), "chars": len(piece)}
                for path, piece in zip(paths, pieces)
            ],
        }
        mapping = dict(zip(paths, pieces))

        def fetcher(**kwargs):
            return mapping[kwargs["path"]].encode("ascii")

        assembled = mod.assemble_command_ciphertext(
            envelope=envelope,
            token="token",
            repository="repo",
            branch=mod.EXCHANGE_REF,
            run_id=run_id,
            fetcher=fetcher,
        )
        self.assertEqual(assembled, ciphertext)

        bad = json.loads(json.dumps(envelope))
        bad["chunks"][0]["path"] = "rendezvous/responses/other/ibkr-remote-paper-000.txt"
        with self.assertRaisesRegex(mod.ActivationError, "path rejected"):
            mod.assemble_command_ciphertext(
                envelope=bad,
                token="token",
                repository="repo",
                branch=mod.EXCHANGE_REF,
                run_id=run_id,
                fetcher=fetcher,
            )

    def test_canonical_runtime_command_preserves_single_authority_and_cleanup_locks(self):
        with tempfile.TemporaryDirectory() as td:
            cmd = mod.canonical_runtime_docker_command(
                image="mmibkr-warm-proof:123",
                data_dir=Path(td),
                gateway_host="127.0.0.1",
                gateway_port=4002,
            )
        self.assertEqual(cmd[:6], ["docker", "run", "-d", "--name", mod.BOT_CONTAINER, "--network"])
        self.assertIn("host", cmd)
        env = {}
        for index, token in enumerate(cmd[:-1]):
            if token == "-e":
                key, value = cmd[index + 1].split("=", 1)
                env[key] = value
        self.assertEqual(env["ENABLE_LIVE_TRADING"], "0")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53"], "1")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37"], "1")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_FLATTEN_ENABLED_13Z39"], "1")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D"], "0")
        self.assertEqual(env["BOT_SELECTED_RUNTIME_NATURAL_CANDIDATE_14TH31BV_ENABLED"], "0")
        self.assertEqual(env["FUTURES_AUTO_ENABLED"], "0")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_SUBMIT_ENABLED"], "0")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_PLACE_ORDER_ENABLED_13Z27"], "0")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_ALLOW_UNRELATED_OPEN_ORDERS_13Z36B"], "0")
        joined = "\n".join(cmd).lower()
        self.assertNotIn("tws_userid", joined)
        self.assertNotIn("tws_password", joined)
        self.assertNotIn("ibkr_username", joined)
        self.assertNotIn("ibkr_password", joined)

    def test_encrypted_return_publishes_ciphertext_only(self):
        calls = []

        def publish(**kwargs):
            calls.append(kwargs)

        run_id = "123"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            text = base64.b64encode(b"ciphertext-only").decode("ascii")
            local_name = "ibkr-paper-proof-000.txt"
            (root / local_name).write_text(text, encoding="ascii")
            envelope = {
                "run_id": run_id,
                "chunks": [{
                    "path": f"rendezvous/returns/{run_id}/{local_name}",
                    "local_name": local_name,
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "chars": len(text),
                }],
                "ciphertext_sha256": "abc",
                "plaintext_sha256": "def",
            }
            mod.publish_encrypted_return(
                token="token",
                repository="repo",
                branch=mod.EXCHANGE_REF,
                run_id=run_id,
                output_dir=root,
                envelope=envelope,
                publisher=publish,
            )
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0]["path"].endswith(local_name))
        self.assertTrue(calls[1]["path"].endswith("ibkr-paper-proof-envelope.json"))
        self.assertEqual(calls[0]["content"], text)
        self.assertNotIn('"command"', calls[0]["content"])
        self.assertNotIn('"submit"', calls[0]["content"])

    def test_wait_for_command_allows_404_then_accepts_envelope(self):
        state = {"calls": 0}
        expected = {"schema": "x", "chunks": []}

        def fetcher(**kwargs):
            state["calls"] += 1
            if state["calls"] == 1:
                raise HTTPError("url", 404, "missing", hdrs=None, fp=None)
            return json.dumps(expected).encode("utf-8")

        out = mod.wait_for_command_envelope(
            token="token",
            repository="repo",
            branch=mod.EXCHANGE_REF,
            run_id="123",
            timeout_sec=5,
            fetcher=fetcher,
            sleep=lambda _: None,
        )
        self.assertEqual(out, expected)
        self.assertEqual(state["calls"], 2)

    def test_execute_command_delegates_persistent_mode_without_cleanup_policy(self):
        runtime = {"mode": mod.capsule_v2.EXECUTE_MODE, "request_path": "/tmp/request.json"}
        receipt = {"schema": mod.execute_v1.SCHEMA, "ok": True, "status": "PAPER_EXECUTE_RECONCILED"}
        with tempfile.TemporaryDirectory() as td:
            request = Path(td) / "request.json"
            request.write_text("{}", encoding="utf-8")
            runtime["request_path"] = str(request)
            from unittest.mock import patch
            with patch.object(mod.execute_v1, "execute_paper_execute", return_value=receipt) as execute:
                out = mod.execute_command(
                    runtime=runtime,
                    run_id="123",
                    public_head="a" * 40,
                    receipt_path=Path(td) / "receipt.json",
                )
        self.assertEqual(out["status"], "PAPER_EXECUTE_RECONCILED")
        execute.assert_called_once()

    def test_public_activation_source_contains_no_direct_broker_mutation_client(self):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("placeOrder(", source)
        self.assertNotIn("cancelOrder(", source)
        self.assertNotIn("reqGlobalCancel", source)
        self.assertNotIn("from ib_insync", source)
        self.assertIn("proof_v2.execute_paper_proof_v2", source)
        self.assertIn("execute_v1.execute_paper_execute", source)
        self.assertIn('"STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D": "0"', source)
        self.assertIn('"ENABLE_LIVE_TRADING": "0"', source)


if __name__ == "__main__":
    unittest.main()
