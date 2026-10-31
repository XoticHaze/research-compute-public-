"""Brokerless tests for exact original encrypted checkpoint read-only review."""
from __future__ import annotations
import importlib.util
import os
import tempfile
import sys
import types
from pathlib import Path
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/mmibkr_original_live_checkpoint_review_v1.py"


class OriginalReadonlyReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No network or broker, and no key needed for structural denial cases.
        gateway = types.ModuleType("scripts.mmibkr_live_gateway_state_envelope_v1")
        gateway.read_master = lambda: b"x" * 32
        codec = types.ModuleType("scripts.mmibkr_live_runtime_checkpoint_v1")
        codec.unseal = lambda *args: (_ for _ in ()).throw(AssertionError("unseal_unexpected"))
        with patch.dict(sys.modules, {gateway.__name__: gateway, codec.__name__: codec}):
            spec = importlib.util.spec_from_file_location("original_readonly_review", SCRIPT)
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
        pspec = importlib.util.spec_from_file_location("original_vault_publisher", ROOT / "scripts/operator/mmibkr_original_checkpoint_vault_publish_macos_v1.py")
        cls.publisher = importlib.util.module_from_spec(pspec)
        pspec.loader.exec_module(cls.publisher)

    def test_exact_immutable_source_digest(self):
        m = self.mod
        self.assertEqual(m.EXPECTED_CONTEXT_SOURCE, "46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b")
        self.assertEqual(m.EXPECTED_CIPHER_BYTES, 33560349)
        self.assertEqual(m.EXPECTED_CIPHER_SHA256, "7fa732e25dbb9044ba66c8fb9e3f7da4e269434ee7b2708d635f58c7d914bc66")

    def test_tampered_ciphertext_held_before_unseal(self):
        with self.assertRaisesRegex(ValueError, "historical_ciphertext_identity_invalid"):
            self.mod.inspect_exact(b"bad", b"{}", b"x" * 32, "41159917178")

    def test_manifest_producer_mismatch_held(self):
        with self.assertRaisesRegex(ValueError, "historical_producer_identity_mismatch"):
            self.mod._validate_exact_context({"context":{"run_id":"other"}})

    def test_manifest_never_confers_order_authority(self):
        c={"run_id":"39499524894","source_sha":self.mod.EXPECTED_CONTEXT_SOURCE,
           "scope":["AMAT","APH","MNQ"],"order_authority":"live"}
        node={"context":c,"archive_sha256":"a"*64,
              "ciphertext_sha256":self.mod.EXPECTED_CIPHER_SHA256,
              "ciphertext_bytes":self.mod.EXPECTED_CIPHER_BYTES}
        with self.assertRaisesRegex(ValueError, "historical_order_authority_invalid"):
            self.mod._validate_exact_context(node)

    def test_workflow_has_no_owner_or_broker_start(self):
        workflow=(ROOT / ".github/workflows/mmibkr-original-live-checkpoint-review-r1.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("secrets.MMIBKR_LIVE_GATEWAY_WARM_KEY_B64",workflow)
        self.assertNotIn("placeOrder",workflow)
        self.assertNotIn("docker run",workflow)
        self.assertNotIn("pi.release",workflow)
        self.assertNotIn("mmibkr-selected-runtime-live-owner-r1.yml",workflow)
        self.assertNotIn("private-source-token",workflow)
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.confirm_readonly_checkpoint_review }}",workflow)

    def test_public_vault_publish_requires_explicit_approval_before_gh(self):
        p = self.publisher
        with patch.dict(os.environ, {p.CONSENT: ""}, clear=False):
            with patch.object(p, "cmd", side_effect=AssertionError("network_not_allowed")):
                with self.assertRaisesRegex(RuntimeError, "public_encrypted_ciphertext_operator_approval_missing"):
                    p.publish(b"nothing", b"nothing")

    def test_vault_publisher_binds_exact_original_archive(self):
        p=self.publisher
        self.assertEqual(p.ZIP_SHA, "13029f3f99fb4023e34540a34ad162ca9b165cd669b24066ac5672dfcc72f8ad")
        self.assertEqual(p.BRANCH, "mmibkr-source-vault")
        self.assertEqual(p.DEST, "checkpoint-vault/run39499524894")
        self.assertEqual(p.MERGED_PR, "2077")
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "not-original.zip"
            bad.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "original_archive_file_identity_mismatch"):
                p.verify_exact_archive(bad)

    def test_publisher_is_nonforce_and_ciphertext_only(self):
        src=(ROOT / "scripts/operator/mmibkr_original_checkpoint_vault_publish_macos_v1.py").read_text()
        self.assertIn("--publish-after-approved-review", src)
        self.assertIn("mmibkr-source-vault",src)
        self.assertNotIn("--force",src)
        self.assertNotIn("MMIBKR_LIVE_GATEWAY_WARM_KEY_B64",src)
        self.assertNotIn("placeOrder",src)

    def test_no_broker_or_secret_in_main(self):
        src=SCRIPT.read_text()
        self.assertIn("decrypted_plaintext_artifact_published",src)
        self.assertIn("live_order_submit_allowed",src)
        self.assertNotIn("placeOrder",src)
        self.assertNotIn("reqOpenOrders",src)
        self.assertNotIn("docker",src.lower().split('def main')[1])


if __name__ == "__main__":
    unittest.main()

class CapsuleRoundtrip(unittest.TestCase):
    def test_botdata_only_encrypted_recipient_return(self):
        import base64
        import hashlib
        import io
        import json
        import tarfile
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from scripts.mmibkr_original_checkpoint_botdata_capsule_v1 import seal_quarantine, INFO
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            for name, value in [('gateway/credentials.txt',b'SHOULD_NOT_ESCAPE'),('bot_data/strategy_runtime/ledger.json',b'{"entries":[]}')]:
                ti=tarfile.TarInfo(name)
                ti.size=len(value)
                tf.addfile(ti, io.BytesIO(value))
        recipient=x25519.X25519PrivateKey.generate()
        public=recipient.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        body,env=seal_quarantine(buf.getvalue(),base64.b64encode(public).decode(),'41159917178')
        fields={k:env[k] for k in ('schema','producer_run','historical_source_sha','selected_pi_source_sha','consumer_run','recipient_key_id','root_import_authorized','live_submission_authorized','gateway_excluded')}
        aad=json.dumps(fields,sort_keys=True,separators=(',',':')).encode()
        ephemeral=x25519.X25519PublicKey.from_public_bytes(base64.b64decode(env['sender_public_b64']))
        shared=recipient.exchange(ephemeral)
        key=HKDF(algorithm=hashes.SHA256(),length=32,salt=base64.b64decode(env['salt_b64']),info=INFO+aad).derive(shared)
        tar=AESGCM(key).decrypt(base64.b64decode(env['nonce_b64']),body,aad)
        self.assertNotIn('plaintext_sha256',env)
        self.assertNotIn('plaintext_bytes',env)
        self.assertNotIn('botdata_file_count',env)
        self.assertNotIn('recipient_public_fingerprint',env)
        with tarfile.open(fileobj=io.BytesIO(tar),mode='r:gz') as tf:
            names=tf.getnames()
            self.assertEqual(names,['bot_data/strategy_runtime/ledger.json'])
        self.assertFalse(env['root_import_authorized'])
        self.assertFalse(env['live_submission_authorized'])
        self.assertTrue(env['gateway_excluded'])

    def test_gateway_only_checkpoint_cannot_create_quarantine(self):
        import io,tarfile
        from scripts.mmibkr_original_checkpoint_botdata_capsule_v1 import make_botdata_tar
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            info=tarfile.TarInfo('gateway/credentials.txt');info.size=3
            tf.addfile(info,io.BytesIO(b'xxx'))
        with self.assertRaisesRegex(ValueError,'botdata_files_missing'):
            make_botdata_tar(buf.getvalue())

    def test_duplicate_botdata_tar_members_fail_closed(self):
        import io, tarfile
        from scripts.mmibkr_original_checkpoint_botdata_capsule_v1 import make_botdata_tar
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w:gz') as tf:
            for _ in range(2):
                m=tarfile.TarInfo('bot_data/ledger.json')
                m.size=2
                tf.addfile(m,io.BytesIO(b'{}'))
        with self.assertRaisesRegex(ValueError,'historical_botdata_duplicate_member'):
            make_botdata_tar(archive.getvalue())

    def test_noncanonical_botdata_paths_fail_closed(self):
        import io, tarfile
        from scripts.mmibkr_original_checkpoint_botdata_capsule_v1 import make_botdata_tar
        for path in ('bot_data//ledger.json','bot_data/./ledger.json','bot_data/../ledger.json',r'bot_data\ledger.json'):
            if not path.startswith('bot_data/'):
                continue
            with self.subTest(path=path):
                archive=io.BytesIO()
                with tarfile.open(fileobj=archive,mode='w:gz') as tf:
                    m=tarfile.TarInfo(path)
                    m.size=2
                    tf.addfile(m,io.BytesIO(b'{}'))
                with self.assertRaisesRegex(ValueError,'historical_botdata_path_invalid'):
                    make_botdata_tar(archive.getvalue())

    def test_public_outputs_reject_plaintext_derived_metadata(self):
        from scripts.mmibkr_original_checkpoint_botdata_capsule_v1 import seal_quarantine
        import io,tarfile,base64
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives import serialization
        recipient=x25519.X25519PrivateKey.generate()
        pub=base64.b64encode(recipient.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w:gz') as tf:
            payload=b'SECRET_PRIVATE_SENTINEL_DATA_XOTIC'
            member=tarfile.TarInfo('bot_data/secret.txt'); member.size=len(payload)
            tf.addfile(member,io.BytesIO(payload))
        ciphertext,envelope=seal_quarantine(raw.getvalue(),pub,'41159917178')
        public=__import__('json').dumps(envelope,sort_keys=True).encode()
        for forbidden in ('plaintext_sha256','plaintext_bytes','botdata_file_count','found_historical_state', 'recipient_public_fingerprint'):
            self.assertNotIn(forbidden, envelope)
        self.assertNotIn(b'SECRET_PRIVATE_SENTINEL_DATA_XOTIC',public)
        self.assertNotIn(b'SECRET_PRIVATE_SENTINEL_DATA_XOTIC',ciphertext)

    def test_sanitized_report_is_only_fixed_no_submit_flags(self):
        import importlib.util,sys,types
        from unittest.mock import patch
        repo=Path(__file__).resolve().parents[1]
        gateway=types.ModuleType('scripts.mmibkr_live_gateway_state_envelope_v1')
        gateway.read_master=lambda: b'0'*32
        codec=types.ModuleType('scripts.mmibkr_live_runtime_checkpoint_v1')
        codec.unseal=lambda *args:b''
        with patch.dict(sys.modules,{gateway.__name__:gateway,codec.__name__:codec}):
            spec=importlib.util.spec_from_file_location('original_readonly_review_sentinel',repo/'scripts/mmibkr_original_live_checkpoint_review_v1.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        # Public source must have no dynamic private archive field inventory.
        src=(repo/'scripts/mmibkr_original_live_checkpoint_review_v1.py').read_text()
        self.assertNotIn('"found_historical_state":',src)
        self.assertNotIn('"authenticated_plaintext_sha256":',src)
        self.assertNotIn("EXPECTED_RAW_SHA256",src)
        self.assertNotIn('result["recipient_key_id"]',src)
