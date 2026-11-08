from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json
import unittest
from cryptography.hazmat.primitives.asymmetric import x25519
P=Path(__file__).resolve().parents[1]/'scripts'/'mmibkr_pi_credential_handoff_v1.py'
spec=importlib.util.spec_from_file_location('pi',P)
pi=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pi)
GOOD=b'TWS_USERID=testuser\nTWS_PASSWORD=private_dummy\nMMIBKR_PRODUCTION_LIVE_ACCOUNT=U000TEST\nMMIBKR_ACCOUNT_MODE=production_live\nTRADING_MODE=live\nREAD_ONLY_API=no\nENABLE_LIVE_TRADING=1\nTWS_SERVER=not-real.example\n'
class TestHandoff(unittest.TestCase):
    def setUp(self):
        self.pr=x25519.X25519PrivateKey.generate()
        self.pub=pi.get_public(self.pr)
    def test_roundtrip_clamps_writable_to_read_only(self):
        cap=pi.encrypt_envelope(GOOD,self.pub,'1234567890')
        raw=pi.decrypt_envelope(cap,self.pr)
        self.assertIn(b'READ_ONLY_API=yes\n',raw)
        self.assertIn(b'ENABLE_LIVE_TRADING=0\n',raw)
        self.assertNotIn(b'READ_ONLY_API=no',raw)
        self.assertNotIn(b'ENABLE_LIVE_TRADING=1',raw)
        self.assertNotIn(b'private_dummy',json.dumps(cap).encode())
    def test_tamper_rejected(self):
        cap=pi.encrypt_envelope(GOOD,self.pub,'1234567890')
        cap['run_id']='1234567891'
        with self.assertRaises(Exception):pi.decrypt_envelope(cap,self.pr)
    def test_wrong_recipient_rejected(self):
        cap=pi.encrypt_envelope(GOOD,self.pub,'1234567890')
        with self.assertRaisesRegex(ValueError,'recipient_mismatch'):
            pi.decrypt_envelope(cap,x25519.X25519PrivateKey.generate())
    def test_paper_rejected(self):
        with self.assertRaisesRegex(ValueError,'paper_account_rejected'):
            pi.encrypt_envelope(GOOD.replace(b'U000TEST',b'DU000TEST'),self.pub,'1234567890')
    def test_bad_mode_rejected(self):
        with self.assertRaisesRegex(ValueError,'wrong_account_mode'):
            pi.encrypt_envelope(GOOD.replace(b'TRADING_MODE=live',b'TRADING_MODE=paper'),self.pub,'1234567890')
    def test_sender_cannot_force_writable(self):
        cap=pi.encrypt_envelope(GOOD,self.pub,'1234567890')
        text=pi.decrypt_envelope(cap,self.pr)
        self.assertEqual(pi.parse_env(text)['READ_ONLY_API'],'yes')
    def test_init_no_overwrite(self):
        with TemporaryDirectory() as d:
            pr=Path(d)/'private.key';pu=Path(d)/'public.b64'
            pi.init(pr,pu)
            self.assertEqual(pr.stat().st_mode&0o777,0o600)
            self.assertEqual(len(pi.raw64(pu.read_text().strip(),32,'pub')),32)
            with self.assertRaises(ValueError):pi.init(pr,pu)
if __name__=='__main__':unittest.main()
