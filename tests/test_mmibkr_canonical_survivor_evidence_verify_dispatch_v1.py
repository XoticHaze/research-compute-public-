from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


COMPLETED_SOURCE = """
def verify_bundle(bundle):
    safe=not bool(bundle.get('unsafe'))
    passed=bool(bundle.get('completed_ok'))
    return {
      'schema':'mm.survivor_completed_trade_evidence_contract.v1',
      'state':'PASS' if passed else 'FAIL_CLOSED',
      'targets':[{'symbol':'AMAT','state':'COMPLETED_TRADE_EVIDENCE_VISIBLE' if passed else 'EVIDENCE_INCOMPLETE'}],
      'semantics':'input availability only; no promotion',
      'authority_boundary':{
        'strategy_spec_mutation':False,'runtime_authority_change':False,'data_authority_change':False,
        'broker_submission':False,'order_sizing_change':False,'capital_allocation_change':False,
        'live_trading_change':False if safe else True,
      },
    }
"""

OPERATOR_SOURCE = """
def verify_bundle(bundle):
    passed=bool(bundle.get('operator_ok'))
    return {
      'schema':'mm.survivor_forward_operator_contract_receipt.v1',
      'state':'PASS' if passed else 'FAIL_CLOSED',
      'targets':[{'symbol':'MNQ','state':'OPERATOR_CONTRACT_COMPLETE' if passed else 'EVIDENCE_INCOMPLETE'}],
      'authority_boundary':{
        'strategy_spec_mutation':False,'runtime_authority_change':False,'broker_submission':False,
        'order_sizing_change':False,'capital_allocation_change':False,'live_trading_change':False,
      },
    }
"""

PAPER_SOURCE = """
def verify(intents, ledger_rows, *, survivors_only=True):
    passed=bool(intents and ledger_rows and all(row.get('meta',{}).get('strategy_spec_digest') for row in intents))
    return {
      'schema':'mm.survivor_paper_trade_evidence_verification.v1',
      'status':'PASS' if passed else 'BLOCKED',
      'materialization':{
        'schema':'fixture','rows_materialized':1 if passed else 0,'rows_ignored':0,
        'unmatched_rows':0 if passed else len(ledger_rows),'conflict_rows':0,
      },
      'acceptance':{'status':'PASS' if passed else 'BLOCKED','bridge_ready_rows':1 if passed else 0,'rows':[]},
      'producer_evidence_inference':False,'selected_runtime_backfill':False,
      'strategy_spec_mutation':False,'runtime_authority_change':False,
      'broker_submission':False,'live_trading_change':False,
      'survivors_only_echo':survivors_only,
    }
"""


class CanonicalSurvivorEvidenceVerifyDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td=tempfile.TemporaryDirectory()
        self.root=Path(self.td.name)
        self.source_root=self.root/'mm-source'
        op=self.source_root/'scripts'/'operator'
        op.mkdir(parents=True)
        (self.source_root/'scripts'/'__init__.py').write_text('',encoding='utf-8')
        (op/'__init__.py').write_text('',encoding='utf-8')
        sources={
            'verify_survivor_completed_trade_evidence_v1.py':COMPLETED_SOURCE,
            'verify_survivor_forward_operator_contract_v1.py':OPERATOR_SOURCE,
            'verify_survivor_paper_trade_evidence_v1.py':PAPER_SOURCE,
            'materialize_survivor_paper_trade_evidence_v1.py':'SAFE=True\n',
            'audit_survivor_paper_trade_acceptance_v1.py':'SAFE=True\n',
        }
        self.blobs={}
        for name,text in sources.items():
            target=op/name
            target.write_text(text,encoding='utf-8')
            self.blobs[name]=git_blob_sha1(target.read_bytes())

        self.commit='a'*40
        self.archive='b'*64
        self.source_receipt={
            'schema':mod.SOURCE_RECEIPT_SCHEMA,
            'mmibkr_repository':mod.SOURCE_REPOSITORY,
            'requested_source_ref':self.commit,
            'mmibkr_head':self.commit,
            'source_archive_sha256':self.archive,
            'source_root':str(self.source_root.resolve()),
            'broker_credentials_materialized':False,
            'tws_credentials_required':False,
            'source_token_emitted':False,
            'paper_or_live_authority':False,
        }
        self.input_root=self.root/'inputs';self.input_root.mkdir()
        self.completed=self.input_root/'completed.json'
        self.operator=self.input_root/'operator.json'
        self.intents=self.input_root/'intents.jsonl'
        self.ledger=self.input_root/'ledger.csv'
        self.completed.write_text(json.dumps({'rows':{'AMAT':{}},'completed_ok':True}),encoding='utf-8')
        self.operator.write_text(json.dumps({'rows':{'MNQ':{}},'operator_ok':True}),encoding='utf-8')
        self.intents.write_text(
            json.dumps({'strategy_id':'crw_score_multi_mode','symbol':'MNQ','timeframe':'12Min',
                        'meta':{'strategy_spec_digest':'spec-1'}})+'\n',
            encoding='utf-8',
        )
        self.ledger.write_text('strategy_id,symbol,timeframe,net_pnl\ncrw_score_multi_mode,MNQ,12Min,42.0\n',encoding='utf-8')
        self.receipt_dir=self.root/'runtime-state'

    def tearDown(self)->None:
        self.td.cleanup()

    @staticmethod
    def ref(path:Path)->dict:
        raw=path.read_bytes()
        return {'scope':'input_root','relative_path':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}

    def ep(self,kind:str)->dict:
        mapping={
          'completed_trade_bundle':('verify_survivor_completed_trade_evidence_v1.py','verify_bundle'),
          'operator_contract_bundle':('verify_survivor_forward_operator_contract_v1.py','verify_bundle'),
          'paper_trade_pairing':('verify_survivor_paper_trade_evidence_v1.py','verify'),
        }
        name,callable_name=mapping[kind]
        return {
          'path':'scripts/operator/'+name,
          'module':'scripts.operator.'+name.removesuffix('.py'),
          'callable':callable_name,
          'git_blob_sha1':self.blobs[name],
        }

    def request(self,kind:str)->dict:
        if kind=='completed_trade_bundle':
            args={'verification_kind':kind,'bundle':self.ref(self.completed),'max_rows':100}
        elif kind=='operator_contract_bundle':
            args={'verification_kind':kind,'bundle':self.ref(self.operator),'max_rows':100}
        else:
            args={'verification_kind':kind,'intents':self.ref(self.intents),'ledger':self.ref(self.ledger),
                  'survivors_only':True,'max_rows':100}
        return {
          'schema':mod.REQUEST_SCHEMA,'job_id':'verify-'+kind.replace('_','-'),
          'capability_id':'SURVIVOR_EVIDENCE_VERIFY',
          'mmibkr':{'repository':mod.SOURCE_REPOSITORY,'commit':self.commit,'source_archive_sha256':self.archive},
          'entrypoint':self.ep(kind),'arguments':args,
          'resources':{'max_wall_seconds':60,'max_output_bytes':500000},
          'authority':mod.AUTHORITY,'forbidden_authorities':dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def execute(self,req):
        return mod.execute_request(
            req,source_root=self.source_root,source_receipt=self.source_receipt,
            input_root=self.input_root,receipt_dir=self.receipt_dir,
        )

    def test_all_three_private_verifier_layers_share_one_public_capability(self):
        completed=self.execute(self.request('completed_trade_bundle'))['receipt']['result']
        operator=self.execute(self.request('operator_contract_bundle'))['receipt']['result']
        paper=self.execute(self.request('paper_trade_pairing'))['receipt']['result']
        for result,kind in (
            (completed,'completed_trade_bundle'),
            (operator,'operator_contract_bundle'),
            (paper,'paper_trade_pairing'),
        ):
            self.assertEqual(result['schema'],'mmibkr.survivor_evidence_verification.v1')
            self.assertEqual(result['verification_kind'],kind)
            self.assertEqual(result['verification_state'],'PASS')
            self.assertTrue(result['passed'])
            self.assertFalse(result['safety']['promotion_mutation'])
            self.assertFalse(result['safety']['capital_allocation'])
            self.assertFalse(result['safety']['broker_submit'])
            self.assertFalse(result['safety']['live_trading'])
            self.assertEqual(len(result['artifacts']),1)
            self.assertNotIn(str(self.root),json.dumps(result,sort_keys=True))

    def test_fail_closed_verifier_truth_is_completed_evidence_not_executor_failure(self):
        self.completed.write_text(json.dumps({'rows':{'AMAT':{}},'completed_ok':False}),encoding='utf-8')
        result=self.execute(self.request('completed_trade_bundle'))['receipt']['result']
        self.assertEqual(result['verification_state'],'FAIL_CLOSED')
        self.assertFalse(result['passed'])
        self.assertEqual(result['verification']['state'],'FAIL_CLOSED')

        self.intents.write_text(json.dumps({'meta':{}})+'\n',encoding='utf-8')
        result=self.execute(self.request('paper_trade_pairing'))['receipt']['result']
        self.assertEqual(result['verification_state'],'BLOCKED')
        self.assertFalse(result['passed'])
        self.assertEqual(result['verification']['status'],'BLOCKED')

    def test_mode_specific_entrypoint_hash_and_input_hash_fail_closed(self):
        req=self.request('completed_trade_bundle')
        req['entrypoint']=self.ep('operator_contract_bundle')
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'entrypoint path does not match capability registry'):
            self.execute(req)

        req=self.request('operator_contract_bundle')
        req['arguments']['bundle']['sha256']='c'*64
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'sha256 mismatch'):
            self.execute(req)

    def test_private_authority_drift_is_rejected(self):
        self.completed.write_text(json.dumps({'rows':{},'completed_ok':True,'unsafe':True}),encoding='utf-8')
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'authority boundary rejected'):
            self.execute(self.request('completed_trade_bundle'))

    def test_row_bounds_and_paper_boolean_contract_fail_closed(self):
        payload={'rows':{str(i):{} for i in range(3)},'operator_ok':True}
        self.operator.write_text(json.dumps(payload),encoding='utf-8')
        req=self.request('operator_contract_bundle');req['arguments']['max_rows']=2
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'bundle row bound exceeded'):
            self.execute(req)

        req=self.request('paper_trade_pairing');req['arguments']['survivors_only']='yes'
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'survivors_only must be boolean'):
            self.execute(req)

    def test_cached_verification_artifact_tamper_is_detected(self):
        req=self.request('operator_contract_bundle')
        first=self.execute(req);second=self.execute(req)
        self.assertTrue(second['cache_hit'])
        result=first['receipt']['result'];fp=first['receipt']['job_fingerprint']
        target=self.receipt_dir/'artifacts'/fp/result['artifacts'][0]['relative_path']
        target.write_text('tampered\n',encoding='utf-8')
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'artifact hash mismatch'):
            self.execute(req)


if __name__=='__main__':
    unittest.main()
