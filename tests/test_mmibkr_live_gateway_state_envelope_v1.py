"""No broker, credentials, network, or orders. Cryptographic state transport."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "warm",ROOT/"scripts/mmibkr_live_gateway_state_envelope_v1.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
MASTER=bytes(range(32))
RUN="38389970525"
SUCCESSOR="38389970526"


def archive(entries=None):
    entries = entries or {"Jts/config.ini": b"synthetic dummy controller settings"}
    f = io.BytesIO()
    with tarfile.open(fileobj=f,mode="w:gz") as tar:
        for name, data in entries.items():
            meta=tarfile.TarInfo(name)
            meta.mode=0o600
            meta.size=len(data)
            tar.addfile(meta,io.BytesIO(data))
    return f.getvalue()


class LiveEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.raw=archive()
        self.ctx=mod.context(RUN)
        self.blob,self.meta=mod.seal(self.raw,self.ctx,MASTER)

    def restore(self,blob=None,meta=None,master=MASTER,successor=SUCCESSOR):
        return mod.unseal(
            self.blob if blob is None else blob,
            self.meta if meta is None else meta,
            master,current_run_id=successor)

    def test_cross_runner_ciphertext_round_trip(self):
        self.assertEqual(self.restore(),self.raw)

    def test_unseal_rejects_wrong_master(self):
        with self.assertRaisesRegex(mod.GateError,"authentication_failed"):
            self.restore(master=b"x"*32)

    def test_ciphertext_tampering_is_detected(self):
        tampered=self.blob[:-1]+bytes([self.blob[-1]^1])
        with self.assertRaisesRegex(mod.GateError,"ciphertext_digest_mismatch"):
            self.restore(blob=tampered)

    def test_decryption_checks_authentication_after_rehashed_tamper(self):
        tampered=self.blob[:-1]+bytes([self.blob[-1]^1])
        meta=dict(self.meta,ciphertext_sha256=mod.sha(tampered))
        with self.assertRaisesRegex(mod.GateError,"authentication_failed"):
            self.restore(blob=tampered,meta=meta)

    def test_reject_same_run_replay(self):
        with self.assertRaisesRegex(mod.GateError,"same_run_not_successor"):
            self.restore(successor=RUN)

    def test_reject_stale_source_or_unpinned_image(self):
        for key,value in (("source_sha","a"*40),("gateway_image","unknown")):
            with self.subTest(key=key):
                ctx=dict(self.ctx,**{key:value})
                with self.assertRaises(mod.GateError):
                    mod.seal(self.raw,ctx,MASTER)

    def test_reject_activation_authority_in_context(self):
        for key in ("orders_allowed","admission_only","paper_account"):
            bad=dict(self.ctx,**{key:not self.ctx[key]})
            with self.subTest(key=key):
                with self.assertRaises(mod.GateError):
                    mod.seal(self.raw,bad,MASTER)

    def test_reject_injected_account_or_token_in_context(self):
        bad=dict(self.ctx,account_id="secret")
        with self.assertRaisesRegex(mod.GateError,"context_fields_not_exact"):
            mod.seal(self.raw,bad,MASTER)

    def test_manifest_has_only_allowed_public_fields(self):
        self.assertEqual(set(self.meta),mod.ENVELOPE_FIELDS)
        encoded=json.dumps(self.meta)
        for forbidden in ("password","account_id","positions","order_rows","TWS_USERID","TWOFACTOR"):
            self.assertNotIn(forbidden,encoded)

    def test_metadata_tampering_rejected(self):
        bad=dict(self.meta,archive_bytes=123)
        with self.assertRaisesRegex(mod.GateError,"archive_digest_mismatch"):
            self.restore(meta=bad)

    def test_metadata_unknown_fields_rejected(self):
        bad=dict(self.meta,tws_password="bad")
        with self.assertRaisesRegex(mod.GateError,"envelope_metadata_not_exact"):
            self.restore(meta=bad)

    def test_no_cleartext_in_ciphertext(self):
        self.assertNotIn(b"synthetic dummy controller settings",self.blob)
        self.assertTrue(self.blob.startswith(mod.MAGIC))

    def test_random_nonce_and_salt_for_every_envelope(self):
        other,othermeta=mod.seal(self.raw,self.ctx,MASTER)
        self.assertNotEqual(self.blob,other)
        self.assertNotEqual(self.meta["salt_b64"],othermeta["salt_b64"])

    def test_reject_symlink_and_traversal_tar(self):
        evil=archive({"../private.key":b"secret"})
        with self.assertRaisesRegex(mod.GateError,"tar_unsafe_path"):
            mod.seal(evil,self.ctx,MASTER)
        f=io.BytesIO()
        with tarfile.open(fileobj=f,mode="w:gz") as tar:
            node=tarfile.TarInfo("unsafe-link")
            node.type=tarfile.SYMTYPE
            node.linkname="/private"
            tar.addfile(node)
        with self.assertRaisesRegex(mod.GateError,"tar_nonregular_entry"):
            mod.seal(f.getvalue(),self.ctx,MASTER)

    def test_reject_plaintext_not_tar(self):
        with self.assertRaisesRegex(mod.GateError,"tar_invalid_archive"):
            mod.seal(b"not an archive",self.ctx,MASTER)

    def test_master_key_must_be_independent_32_bytes(self):
        with self.assertRaisesRegex(mod.GateError,"not_configured"):
            mod.read_master({})
        with self.assertRaisesRegex(mod.GateError,"must_be_32_random_bytes"):
            mod.read_master({mod.MASTER_KEY_ENV:base64.b64encode(b"password").decode()})
        self.assertEqual(mod.read_master(
            {mod.MASTER_KEY_ENV:base64.b64encode(MASTER).decode()}),MASTER)

    def test_file_outputs_are_private_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"secret.enc"
            mod.private_write(p,self.blob)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            with self.assertRaisesRegex(mod.GateError,"refuse_overwrite"):
                mod.private_write(p,b"another")

    def test_cli_outputs_no_sensitive_data_and_no_broker_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            tarfile_path=root/"gateway.tgz"
            tarfile_path.write_bytes(self.raw)
            master_b64=base64.b64encode(MASTER).decode()
            with patch.dict("os.environ",{mod.MASTER_KEY_ENV:master_b64}):
                self.assertEqual(mod.run([
                    "seal","--archive",str(tarfile_path),"--run-id",RUN,
                    "--envelope",str(root/"blob.enc"),
                    "--manifest",str(root/"manifest.json")]),0)
                self.assertEqual(mod.run([
                    "unseal","--envelope",str(root/"blob.enc"),
                    "--manifest",str(root/"manifest.json"),
                    "--current-run-id",SUCCESSOR,
                    "--output-archive",str(root/"restored.tgz")]),0)
            self.assertEqual((root/"restored.tgz").read_bytes(),self.raw)

    def test_wrong_manifest_nonce_rejected(self):
        bad=dict(self.meta,nonce_b64=base64.b64encode(b"0"*12).decode())
        with self.assertRaisesRegex(mod.GateError,"nonce_or_salt_mismatch"):
            self.restore(meta=bad)


if __name__=="__main__":
    unittest.main()
