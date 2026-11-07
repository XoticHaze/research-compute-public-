"""Private owner custody + atomic signing-issuance replay tests, synthetic only."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.operator import reference_private_grant_custody_v1 as custody
from scripts.reference_private_intent_authority_adapter_v1 import (
    PrivateIntentPolicy, NotAuthorized, issue_once,
)


class PrivateGrantCustodyTests(unittest.TestCase):
    def make_custody(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        mock = patch.object(custody.Path, 'home', return_value=home)
        mock.start()
        self.addCleanup(mock.stop)
        root = home / '.local/share/commandcenter/private-grant-authority-v1'
        return root

    def test_first_issuance_creates_only_private_grant_signer_and_journal(self):
        root = self.make_custody()
        key_id = custody.initialize(root)
        self.assertEqual(custody.status(root), key_id)
        self.assertEqual((root / custody.PRIVATE).stat().st_mode & 0o777, 0o600)
        self.assertEqual((root / custody.JOURNAL).stat().st_mode & 0o777, 0o600)
        self.assertEqual((root / custody.KEY_ID).read_text().strip(), key_id)
        self.assertEqual(sorted(p.name for p in root.iterdir()), sorted([
            custody.PRIVATE, custody.PUBLIC, custody.KEY_ID, custody.JOURNAL
        ]))
        with self.assertRaisesRegex(custody.Held, 'ALREADY_PRESENT'):
            custody.initialize(root)

    def test_atomic_one_use_journal_survives_new_connection_and_duplicate(self):
        root = self.make_custody()
        custody.initialize(root)
        first = custody.PrivateIntentSQLiteJournal(root)
        second = custody.PrivateIntentSQLiteJournal(root)
        self.assertTrue(first.consume_once(grant_id='grant-'+'1'*20, payload_sha256='a'*64))
        self.assertFalse(second.consume_once(grant_id='grant-'+'1'*20, payload_sha256='a'*64))
        self.assertTrue(second.consume_once(grant_id='grant-'+'2'*20, payload_sha256='b'*64))

    def test_actual_signed_live_intent_requires_real_create_once_private_journal(self):
        root = self.make_custody()
        key_id = custody.initialize(root)
        grant = 'grant-'+'7'*20
        now = 1700000000
        policy = PrivateIntentPolicy(
            authority_public_b64=(root/custody.PUBLIC).read_text().strip(),
            authority_key_id=key_id, broker_key_id='sha256:'+'c'*64,
            harness_sha='d'*40, caller_policy_sha256='e'*64, max_seconds=300)
        node = {
            'grant_id':grant, 'caller_policy_sha256':'e'*64,
            'harness_sha':'d'*40, 'broker_key_id':'sha256:'+'c'*64,
            'not_before':now-10, 'intent_not_after':now+200,
        }
        def issue():
            return issue_once(node, policy=policy,
                              protected_private_key_b64=(root/custody.PRIVATE).read_text().strip(),
                              journal=custody.PrivateIntentSQLiteJournal(root), clock=lambda:now)
        wrapper = issue()
        self.assertEqual(wrapper['signer_key_id'], key_id)
        self.assertNotIn((root/custody.PRIVATE).read_text().strip(), str(wrapper))
        with self.assertRaisesRegex(NotAuthorized, 'PRIVATE_INTENT_ISSUE_REJECTED'):
            issue()

    def test_permission_or_key_tampering_fails_closed(self):
        root = self.make_custody()
        custody.initialize(root)
        (root/custody.PRIVATE).chmod(0o644)
        with self.assertRaisesRegex(custody.Held, 'FILE_UNVERIFIED'):
            custody.status(root)


if __name__ == '__main__':
    unittest.main()
