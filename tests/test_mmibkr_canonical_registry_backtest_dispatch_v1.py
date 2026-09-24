from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


BRIDGE_SOURCE = """
import hashlib,json
def normalize_strategy_spec(payload):
    raw=dict(payload or {})
    nested=raw.get('strategy_spec')
    spec=dict(nested) if isinstance(nested,dict) else dict(raw)
    strategy_id=str(spec.get('strategy_id') or raw.get('strategy_id') or '').strip()
    symbol=str(spec.get('symbol') or raw.get('symbol') or '').strip().upper()
    timeframe=str(spec.get('timeframe') or raw.get('timeframe') or '').strip()
    params=spec.get('parameters')
    if not isinstance(params,dict): params={}
    if not strategy_id or not symbol or not timeframe: raise ValueError('identity required')
    spec['strategy_id']=strategy_id;spec['symbol']=symbol;spec['timeframe']=timeframe;spec['parameters']=dict(params)
    digest=hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'strategy_spec':spec,'strategy_spec_digest':digest,'source_payload':raw}
"""


REGISTRY_SOURCE = """
from pathlib import Path
import csv,json,hashlib
ROOT=Path(__file__).resolve().parent
GENERIC_ENGINE_ID='registry_signal_pair_backtest_fixture'
class MACrossover: pass
class Breakout: pass
class Crw: pass
REGISTRY={'ma_crossover':MACrossover,'breakout':Breakout,'crw_score_multi_mode':Crw}
def _resolve_strategy_id(value):
    requested=str(value or '').strip()
    return requested,requested

def _write_csv(path,fieldnames,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as h:
        w=csv.DictWriter(h,fieldnames=fieldnames);w.writeheader()
        for row in rows:w.writerow(row)

def run_strategy_backtest(payload,data_root):
    nested=dict(payload.get('strategy_spec') or {})
    strategy=str(nested.get('strategy_id') or payload.get('strategy_id') or '')
    symbol=str(nested.get('symbol') or payload.get('symbol') or '').upper()
    timeframe=str(nested.get('timeframe') or payload.get('timeframe') or '')
    asset=str(nested.get('asset_type') or payload.get('asset_type') or 'stocks')
    if payload.get('submit') is not False or payload.get('execute') is not False or payload.get('live_allowed') is not False:
        raise RuntimeError('unsafe overlay reached canonical owner')
    if strategy not in REGISTRY:
        return {'registry_dispatch':True,'ok':False,'status':'unknown_strategy','strategy_id':strategy,
                'safety':{'broker_submit':False,'cancel':False,'replace':False,'live_unlock':False,'backtest_only':True}}
    source=Path(data_root)/asset/symbol/(timeframe+'.csv')
    if not source.is_file():
        return {'registry_dispatch':True,'ok':True,'status':'data_missing','strategy_id':strategy,
                'safety':{'broker_submit':False,'cancel':False,'replace':False,'live_unlock':False,'backtest_only':True}}
    with source.open(newline='',encoding='utf-8') as handle:\n        rows=list(csv.DictReader(handle))
    safety={'broker_submit':False,'cancel':False,'replace':False,'live_unlock':False,'backtest_only':True}
    net=12.5 if strategy=='ma_crossover' else (21.0 if strategy=='breakout' else 17.0)
    if strategy=='crw_score_multi_mode':
        repo_root=Path(__file__).resolve().parent
        art=repo_root/'artifacts'/'crw-fixture'
        trade_fields=['symbol','net_pnl']
        event_fields=['symbol','signal']
        _write_csv(art/'trade_rows.csv',trade_fields,[{'symbol':symbol,'net_pnl':net}])
        _write_csv(art/'condition_event_rows.csv',event_fields,[{'symbol':symbol,'signal':'BUY'}])
        _write_csv(art/'simulation_trade_rows.csv',trade_fields,[{'symbol':symbol,'net_pnl':net-1}])
        _write_csv(art/'simulation_condition_event_rows.csv',event_fields,[{'symbol':symbol,'signal':'BUY'}])
        _write_csv(art/'dca_fill_rows.csv',['symbol','tier'],[])
        return {
            'registry_dispatch':True,'ok':True,'status':'ok','contract_version':'crw_backtest_summary_route_13z',
            'backtest_engine':'crw_backtest_summary_route_13z','strategy_id':strategy,'requested_strategy_id':strategy,
            'symbols':[symbol],'timeframe':timeframe,'asset_type':asset,'parameter_hash':'fixture',
            'total_trades':1,'closed_trade_count':1,'open_trade_count':0,'open_trade_mark_to_market':0.0,
            'win_rate':1.0,'profit_factor':None,'avg_win':net,'avg_loss':0.0,'gross_pnl':net+1,'net_pnl':net,
            'max_drawdown':0.0,'exposure':0.5,'symbol_count':1,'trade_row_count':1,'event_row_count':1,
            'cost_model':{'commission':0.0},'data_coverage':[{'symbol':symbol,'source_path':str(source),'effective_bar_count':len(rows)}],
            'symbol_rows':[{'symbol':symbol,'status':'ok','bar_count':len(rows),'total_trades':1,'net_pnl':net}],
            'trade_rows':[{'symbol':symbol,'net_pnl':net}],
            'condition_event_rows':[{'symbol':symbol,'signal':'BUY'}],
            'simulation_trade_rows':[{'symbol':symbol,'net_pnl':net-1}],
            'simulation_condition_event_rows':[{'symbol':symbol,'signal':'BUY'}],
            'dca_fill_rows':[],
            'artifact_dir':'artifacts/crw-fixture',
            'safety':safety,
        }
    artifact=ROOT/'artifacts'/('run-'+strategy)
    trades=[
        {'symbol':symbol,'timeframe':timeframe,'asset_type':asset,'strategy_id':strategy,'side':'LONG','qty':'1',
         'entry_timestamp':'2026-09-23T14:30:00Z','exit_timestamp':'2026-09-23T15:00:00Z','entry_price':'100',
         'exit_price':'110','entry_adjusted_price':'100','exit_adjusted_price':'110','entry_commission':'0',
         'exit_commission':'0','gross_pnl':str(net),'net_pnl':str(net),'bars_held':'2'}
    ]
    events=[
        {'symbol':symbol,'timeframe':timeframe,'asset_type':asset,'strategy_id':strategy,'timestamp':'2026-09-23T14:30:00Z',
         'bar_index':'1','signal':'BUY','raw_signal':'BUY','price':'100','position_before_or_after':'long',
         'applied':'True','reason':'opened_long','meta':json.dumps({'family':strategy})}
    ]
    _write_csv(artifact/'trade_rows.csv',list(trades[0]),trades)
    _write_csv(artifact/'condition_event_rows.csv',list(events[0]),events)
    return {
        'registry_dispatch':True,'ok':True,'status':'ok','dispatch_contract_version':'strategy_registry_backtest_dispatch_fixture',
        'backtest_engine':GENERIC_ENGINE_ID,'strategy_id':strategy,'requested_strategy_id':strategy,
        'symbols':[symbol],'timeframe':timeframe,'asset_type':asset,'parameter_hash':hashlib.sha256(strategy.encode()).hexdigest()[:16],
        'feature_manifest':{'strategy_id':strategy,'dataset':{'source_path':str(source)},'features':['EMA_2','EMA_3']},
        'total_trades':1,'closed_trade_count':1,'open_trade_count':0,'open_trade_mark_to_market':0.0,
        'win_rate':1.0,'profit_factor':None,'avg_win':net,'avg_loss':0.0,'gross_pnl':net,'net_pnl':net,
        'max_drawdown':1.0,'exposure':0.4,'symbol_count':1,'trade_row_count':1,'event_row_count':1,
        'data_coverage':[{'symbol':symbol,'source_path':str(source),'effective_bar_count':len(rows)}],
        'cost_model':{'commission_per_unit':0.0},
        'symbol_rows':[{'symbol':symbol,'timeframe':timeframe,'asset_type':asset,'strategy_id':strategy,'status':'ok',
            'bar_count':len(rows),'total_trades':1,'closed_trade_count':1,'open_trade_count':0,'net_pnl':net,
            'gross_pnl':net,'max_drawdown':1.0,'exposure':0.4,'event_count':1,
            'data':{'source_path':str(source),'row_count':len(rows),'source_row_count':len(rows),
                    'coverage':{'effective_bar_count':len(rows),'source_path':str(source)}}}],
        'trade_rows':trades,'condition_event_rows':events,'chart_rows':[],
        'artifact_dir':str(artifact.relative_to(ROOT)),'safety':safety,
    }
"""


class CanonicalRegistryBacktestDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td=tempfile.TemporaryDirectory()
        self.root=Path(self.td.name)
        self.source_root=self.root/'mm-source'
        self.source_root.mkdir()
        (self.source_root/'autotuner_strategy_bridge.py').write_text(BRIDGE_SOURCE,encoding='utf-8')
        registry=self.source_root/'strategy_backtest_registry.py'
        registry.write_text(REGISTRY_SOURCE,encoding='utf-8')
        self.entry_blob=git_blob_sha1(registry.read_bytes())

        placeholders={
            'strategies/__init__.py':'REGISTRY={}\\n',
            'strategies/event_bus.py':'def build_strategy_definition(*a,**k): return None\\n',
            'strategy_builder_condition_contract_14th31kn.py':'SAFE=True\\n',
            'feature_contract.py':'SAFE=True\\n',
            'scripts/operator/crw_backtest_summary_13z.py':'def run_backtest(*a,**k): return {}\\n',
        }
        for rel,text in placeholders.items():
            target=self.source_root/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(text,encoding='utf-8')

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
        self.input_root=self.root/'inputs'
        self.input_root.mkdir()
        self.dataset=self.input_root/'test-15min.csv'
        self.dataset.write_text(
            'timestamp,open,high,low,close,volume,EMA_2,EMA_3\\n'
            '2026-09-23T14:30:00Z,100,101,99,100,1000,1,2\\n'
            '2026-09-23T14:45:00Z,101,102,100,101,1100,3,2\\n'
            '2026-09-23T15:00:00Z,110,111,109,110,1200,1,2\\n',
            encoding='utf-8',
        )
        self.receipt_dir=self.root/'runtime-state'

    def tearDown(self)->None:
        self.td.cleanup()

    def dataset_ref(self)->dict:
        raw=self.dataset.read_bytes()
        return {'scope':'input_root','relative_path':self.dataset.name,
                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}

    def request(self,strategy_id='ma_crossover')->dict:
        return {
            'schema':mod.REQUEST_SCHEMA,
            'job_id':'registry-'+strategy_id.replace('_','-'),
            'capability_id':'REGISTRY_BACKTEST',
            'mmibkr':{'repository':mod.SOURCE_REPOSITORY,'commit':self.commit,'source_archive_sha256':self.archive},
            'entrypoint':{'path':'strategy_backtest_registry.py','module':'strategy_backtest_registry',
                          'callable':'run_strategy_backtest','git_blob_sha1':self.entry_blob},
            'arguments':{
                'strategy_spec':{
                    'strategy_id':strategy_id,'symbol':'TEST','timeframe':'15Min','asset_type':'stocks',
                    'parameters':{'MA_FAST':2,'MA_SLOW':3,'qty':1},
                },
                'dataset':self.dataset_ref(),
                'requested_start':'2026-09-23T14:30:00Z',
                'requested_end':'2026-09-23T15:00:00Z',
            },
            'resources':{'max_wall_seconds':60,'max_output_bytes':500000},
            'authority':mod.AUTHORITY,
            'forbidden_authorities':dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def execute(self,req=None):
        return mod.execute_request(
            req or self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )

    def test_two_non_crw_families_share_one_capability_and_consume_family_identity(self):
        ma=self.execute(self.request('ma_crossover'))['receipt']['result']
        bo=self.execute(self.request('breakout'))['receipt']['result']
        self.assertEqual(ma['schema'],'mmibkr.registry_backtest.v1')
        self.assertEqual(bo['schema'],'mmibkr.registry_backtest.v1')
        self.assertEqual(ma['strategy_id'],'ma_crossover')
        self.assertEqual(bo['strategy_id'],'breakout')
        self.assertEqual(ma['summary']['net_pnl'],12.5)
        self.assertEqual(bo['summary']['net_pnl'],21.0)
        self.assertEqual(ma['trade_row_count'],1)
        self.assertEqual(ma['condition_event_row_count'],1)
        self.assertEqual(len(ma['artifacts']),3)
        self.assertFalse(ma['safety']['broker_submit'])
        self.assertFalse(ma['safety']['runtime_activation'])
        self.assertTrue(ma['safety']['backtest_only'])
        rendered=json.dumps(ma,sort_keys=True)
        self.assertNotIn(str(self.root),rendered)
        self.assertNotIn('source_path',rendered)
        artifact_root=self.receipt_dir/'artifacts'/self.execute(self.request('ma_crossover'))['receipt']['job_fingerprint']
        for node in ma['artifacts']:
            target=artifact_root/node['relative_path']
            self.assertTrue(target.is_file())
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),node['sha256'])

    def test_primary_crw_still_uses_existing_crw_evidence_sanitizer(self):
        result=self.execute(self.request('crw_score_multi_mode'))['receipt']['result']
        self.assertEqual(result['strategy_id'],'crw_score_multi_mode')
        self.assertEqual(result['backtest_engine'],'crw_backtest_summary_route_13z')
        crw=result['engine_result']
        self.assertEqual(crw['status'],'ok')
        self.assertEqual(crw['net_pnl'],17.0)
        self.assertEqual(crw['row_artifact_counts']['trade_rows'],1)
        self.assertEqual(crw['row_artifact_counts']['simulation_trade_rows'],1)
        self.assertEqual(len(result['artifacts']),5)
        self.assertFalse(result['safety']['broker_submit'])
        self.assertNotIn(str(self.root),json.dumps(result,sort_keys=True))

    def test_dataset_hash_unknown_family_execution_overlay_and_time_range_fail_closed(self):
        req=self.request()
        req['arguments']['dataset']['sha256']='c'*64
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'sha256 mismatch'):
            self.execute(req)

        with self.assertRaisesRegex(mod.CanonicalDispatchError,'unknown strategy_id'):
            self.execute(self.request('does_not_exist'))

        req=self.request()
        req['arguments']['strategy_spec']['submit']=True
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'forbids execution authority field'):
            self.execute(req)

        req=self.request()
        req['arguments']['requested_start']='2026-09-24T15:00:00Z'
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'must not exceed'):
            self.execute(req)

    def test_requires_receipt_storage_and_cached_evidence_tamper_fails_closed(self):
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'requires receipt_dir'):
            mod.execute_request(
                self.request(),source_root=self.source_root,source_receipt=self.source_receipt,
                input_root=self.input_root,
            )
        first=self.execute()
        second=self.execute()
        self.assertTrue(second['cache_hit'])
        result=first['receipt']['result']
        artifact_root=self.receipt_dir/'artifacts'/first['receipt']['job_fingerprint']
        target=artifact_root/result['artifacts'][0]['relative_path']
        target.write_text('tampered\\n',encoding='utf-8')
        with self.assertRaisesRegex(mod.CanonicalDispatchError,'artifact hash mismatch'):
            self.execute()


if __name__=='__main__':
    unittest.main()
