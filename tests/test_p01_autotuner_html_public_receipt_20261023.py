"""Synthetic-only public-log allowlist regression for the existing P01 HTML consumer.

No original corpus, live broker, source exchange or confidential job execution.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts import p01_autotuner_html_consumer_v1 as consumer

SENTINEL = 'PRIVATE_NESTED_SENTINEL_NEVER_PUBLIC_20261023'


def valid_receipt():
    return {
        'schema': consumer.RECEIPT_SCHEMA,
        'authority': consumer.AUTHORITY,
        'harness': consumer.HARNESS,
        'mm_head_sha': consumer.MM_HEAD_SHA,
        'status': 'PASS',
        'runtime_count': 2,
        'snapshot_sha256': 'a'*64,
        'html_sha256': 'b'*64,
        'automatic_promotion': False,
        'strategy_spec_write': False,
        'runtime_activation': False,
        'broker_submit': False,
        'live_unlock': False,
    }


class PublicReceiptAllowlistTests(unittest.TestCase):
    def run_cli(self, *, result=None, error=None):
        out, err = StringIO(), StringIO()
        argv = ['p01_autotuner_html_consumer_v1.py', '--envelope', 'synthetic.json',
                '--private-key', 'synthetic.key', '--run-id', 'synthetic-run']
        with (patch('sys.argv', argv),
              patch.object(consumer, 'consume', return_value=result, side_effect=error),
              redirect_stdout(out), redirect_stderr(err)):
            code = consumer.main()
        return code, out.getvalue(), err.getvalue()

    def test_valid_success_is_exact_fixed_field_public_receipt(self):
        value = valid_receipt()
        code, out, err = self.run_cli(result=value)
        self.assertEqual(code, 0)
        self.assertEqual(err, '')
        self.assertTrue(out.startswith('P01_AUTOTUNER_HTML_RECEIPT='))
        emitted = json.loads(out.split('=', 1)[1])
        self.assertEqual(emitted, value)
        self.assertEqual(set(emitted), consumer._PUBLIC_KEYS)

    def test_nested_private_field_is_rejected_without_echo(self):
        value = valid_receipt()
        value['untrusted_nested'] = {'key': {'value': SENTINEL}}
        code, out, err = self.run_cli(result=value)
        self.assertEqual(code, 1)
        self.assertEqual(err, '')
        self.assertNotIn(SENTINEL, out + err)
        self.assertEqual(json.loads(out.split('=', 1)[1]),
                         {'schema': consumer.RECEIPT_SCHEMA, 'status': 'REJECTED'})

    def test_exception_with_private_key_path_is_not_logged(self):
        def unsafe_input(*_args):
            consumer.reject_authority({SENTINEL: {'broker_submit': True}})
        code, out, err = self.run_cli(error=unsafe_input)
        self.assertEqual(code, 1)
        self.assertNotIn(SENTINEL, out + err)
        self.assertEqual(err, '')
        self.assertEqual(json.loads(out.split('=', 1)[1])['status'], 'REJECTED')

    def test_exception_message_is_never_public(self):
        code, out, err = self.run_cli(error=RuntimeError(SENTINEL))
        self.assertEqual(code, 1)
        self.assertNotIn(SENTINEL, out + err)
        self.assertEqual(err, '')

    def test_tar_member_types_and_duplicate_normalized_paths_fail_preextract(self):
        import tarfile
        from pathlib import Path
        regular = tarfile.TarInfo('manifest.json')
        regular.type = tarfile.REGTYPE
        regular.size = 4
        directory = tarfile.TarInfo('input/')
        directory.type = tarfile.DIRTYPE
        self.assertTrue(consumer.safe_tar_members([regular, directory]))
        for kind in (tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE,
                     tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(kind=kind):
                unsafe = tarfile.TarInfo('private_member')
                unsafe.type = kind
                self.assertFalse(consumer.safe_tar_members([regular, unsafe]))
        alias = tarfile.TarInfo('./manifest.json')
        alias.type = tarfile.REGTYPE
        self.assertFalse(consumer.safe_tar_members([regular, alias]))
        self.assertFalse(consumer.safe_tar_members([regular, regular]))
        oversized = tarfile.TarInfo('oversized')
        oversized.type = tarfile.REGTYPE
        oversized.size = consumer.MAX_MEMBER_BYTES + 1
        self.assertFalse(consumer.safe_tar_members([oversized]))

    def test_noncanonical_types_digests_and_authority_fail_closed(self):
        variants = [('runtime_count', True), ('runtime_count', 0),
                    ('runtime_count', 2.5), ('snapshot_sha256', SENTINEL),
                    ('html_sha256', 'C'*64), ('broker_submit', 0),
                    ('mm_head_sha', SENTINEL)]
        for key, bad in variants:
            with self.subTest(key=key, bad=str(bad)):
                value = valid_receipt()
                value[key] = bad
                code, out, err = self.run_cli(result=value)
                self.assertEqual(code, 1)
                self.assertNotIn(SENTINEL, out + err)
                self.assertEqual(err, '')


if __name__ == '__main__':
    unittest.main()
