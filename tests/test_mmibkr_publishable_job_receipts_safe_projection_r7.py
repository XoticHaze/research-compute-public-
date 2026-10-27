from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts import mmibkr_publishable_job_receipts_v1 as mod

class SafeProjectionR7(unittest.TestCase):
    def fixture(self):
        private='PRIVATE_STRATEGYSPEC_SENTINEL_20261020'
        result={'nested':{'strategy_spec':{'secret':private}},'private_return':{'source':private}}
        sha=hashlib.sha256(mod._compact(result)).hexdigest()
        fp='a'*64
        state={'state':'completed','job_fingerprint':fp,'result_sha256':sha}
        receipt={'schema':mod.JOB_SCHEMA,'job_id':'PRIVATE_JOB_ID_SECRET_20261020','job_fingerprint':fp,
                 'status':'completed','capability_id':'CRW_BACKTEST',
                 'authority':{'research_only':True,**{key:False for key in mod.FORBIDDEN}},
                 'result_sha256':sha,'result':result,'mmibkr':{'private_source':private}}
        return private,state,receipt

    def test_nested_private_fields_do_not_reach_fixed_public_projection(self):
        secret,state,receipt=self.fixture()
        out=mod.project_safe_public_job_receipt(job_id='PRIVATE_JOB_ID_SECRET_20261020',state=state,receipt=receipt)
        self.assertEqual(set(out),{'schema','job_id','job_fingerprint','capability_id','status',
                                  'result_sha256','private_receipt_sha256','authority'})
        self.assertNotIn(secret,json.dumps(out))
        self.assertNotIn('PRIVATE_JOB_ID_SECRET_20261020',json.dumps(out))
        self.assertEqual(out['job_id'],'job-'+'a'*64)
        self.assertNotIn('result',out)
        self.assertNotIn('mmibkr',out)

    def test_reject_scalar_capability_injection(self):
        _,state,receipt=self.fixture()
        receipt['capability_id']='PRIVATE_SECRET'
        with self.assertRaisesRegex(ValueError,'capability_identity_rejected'):
            mod.project_safe_public_job_receipt(job_id='PRIVATE_JOB_ID_SECRET_20261020',state=state,receipt=receipt)

    def test_reject_nested_result_tamper_without_digest_update(self):
        _,state,receipt=self.fixture()
        receipt['result']['nested']['strategy_spec']['secret']='TAMPER'
        with self.assertRaisesRegex(ValueError,'content_digest_mismatch'):
            mod.project_safe_public_job_receipt(job_id='PRIVATE_JOB_ID_SECRET_20261020',state=state,receipt=receipt)

    def test_reject_authority_escalation(self):
        _,state,receipt=self.fixture()
        receipt['authority']['broker_submit']=True
        with self.assertRaisesRegex(ValueError,'authority_escalation'):
            mod.project_safe_public_job_receipt(job_id='PRIVATE_JOB_ID_SECRET_20261020',state=state,receipt=receipt)

    def test_stage_remains_failclosed_before_private_file_read(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with self.assertRaisesRegex(RuntimeError,'two_sided_private_result_return_not_admitted'):
                mod.stage(root/'nonexistent-terminal',root/'nonexistent-receipts',root/'public')
            self.assertFalse((root/'public').exists())

if __name__=='__main__':unittest.main()
