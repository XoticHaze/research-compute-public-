"""Bounded private replay contract. All frozen 'models' here are synthetic stubs.

The tests verify the orchestrator wiring and its fail-closed boundaries, NOT
historical research alpha, private source parity or an authentic provider vintage.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILE = ROOT / 'scripts' / 'forward_native_bounded_replay_r1.py'
spec = importlib.util.spec_from_file_location('bounded_replay', FILE)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

TEST_NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
DATES = ['2026-10-12', '2026-10-13', '2026-11-04']
TRAIN = ('AMAT','APH','KLAC','LRCX','TXN','NXPI','ADI')
EXT = ('NVDA','AMD','MU','AVGO','MRVL','MCHP')
ALL = TRAIN+EXT


def request(dates=None):
    return {'schema':r.SCHEMA, 'program_id':r.PROGRAM, 'source_ref':r.SOURCE_REF,
            'evidence_class':'HISTORICAL_REPLAY_NO_PROSPECTIVE_CREDIT',
            'decision_dates':dates if dates is not None else DATES}


def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


class BoundedReplay(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = pathlib.Path(self.td.name)
        p = self.root / 'research/semiconductor_external_forward_standalone_20260910.py'
        put(p, '''
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--asof');p.add_argument('--output');a=p.parse_args()
D=a.asof; TRAIN=['AMAT','APH','KLAC','LRCX','TXN','NXPI','ADI']; EXT=['NVDA','AMD','MU','AVGO','MRVL','MCHP']
allrows=[{'symbol':s,'bar_date':D,'predicted_fixed20_net_value_bps':float(i+1 if i%2==0 else -i-1),
 'positive_value_opportunity':i%2==0,'external_target_history_used_in_fit':False if s in EXT else None} for i,s in enumerate(TRAIN+EXT)]
o={'schema':'foundry.research.semiconductor_external_forward.v1','generation_bar_date':D,'research_only':True,
 'monthly_fit':{'month':D[:7],'fit_anchor_date':D[:7]+'-01','safe_last_training_signal_date':D[:7]+'-01',
 'resolved_session_purge':21,'train_universe':TRAIN,'external_target_rows':0},
 'source_last_dates':{s:D for s in TRAIN+EXT+['SMH','QQQ']},'observations':allrows,
 'boundaries':{k:False for k in ('runtime_mutation','broker_authority','sizing_authority','promotion_authority','live_trading_authority')}}
Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(o))
''')
        p = self.root / 'research/semiconductor_three_book_forward_20260910.py'
        put(p, '''
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--prediction');p.add_argument('--contract');p.add_argument('--output');a=p.parse_args()
n=json.loads(Path(a.prediction).read_text());d=n['generation_bar_date'];pos=[x['symbol'] for x in n['observations'] if x['positive_value_opportunity']]
b={'schema':'foundry.research.semiconductor_three_book_forward_snapshot.v1','signal_date':d,'authority':'research_only_no_broker_no_promotion',
 'execution':{'delay_sessions':1,'hold_sessions':20,'max_concurrent_cohorts':20},
 'ticker_book':{'status':'PAPER_COHORT_READY','cohort_target_weights_nav':{s:0.05/len(pos) for s in pos}},
 'industry_book':{'status':'PAPER_COHORT_READY','instrument':'SMH','cohort_target_weight_nav':0.05*len(pos)/len(n['observations'])},
 'options_book':{'status':'FAIL_CLOSED','trade_authorized':False},
 'boundaries':{'broker_orders':False,'live_trading_authority':False,'promotion_authority':False,'historical_rule_tuning':False}}
Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(b))
''')
        contract = {'prospective_start_signal_date':'2026-09-10','source_prediction_schema':'foundry.research.semiconductor_external_forward.v1',
                    'scientific_boundaries':{'execution_delay_sessions':1,'hold_sessions':20,'stock_round_trip_cost_bps':25}}
        put(self.root/'research/semiconductor_three_book_forward_contract_20260910.json',json.dumps(contract))
        self.adapter = self.root / 'adapter.py'
        put(self.adapter, '''
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--program');p.add_argument('--input');p.add_argument('--book');p.add_argument('--output');a=p.parse_args()
n=json.loads(Path(a.input).read_text());b=json.loads(Path(a.book).read_text());rows=n['observations'];pred={x['symbol']:x['predicted_fixed20_net_value_bps'] for x in rows}
o={'schema':'foundry.forward_program_adapter.v1','program_id':a.program,'signal_date':n['generation_bar_date'],
 'signal':{'predicted_fixed20_net_value_bps':pred,'positive_symbols':[x['symbol'] for x in rows if x['positive_value_opportunity']]},
 'paper_action':{'ticker_book':b['ticker_book']},
 'validation':{'scientific_forward_credit':True},
 'boundaries':{'broker_action':False,'live_trading_change':False,'promotion_authority':False,'runtime_mutation':False}}
Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(o))
''')

    def test_bounded_three_date_loop_retains_monthly_fit(self):
        files = r.execute_bounded(self.root,self.adapter,request(),now_utc=TEST_NOW)
        native, books, adapters = [json.loads(x.read_text()) for x in files]
        self.assertEqual(native['decision_dates'],DATES)
        self.assertEqual([x['content']['monthly_fit']['month'] for x in native['records']],['2026-10','2026-10','2026-11'])
        self.assertEqual(adapters['evidence_class'],'HISTORICAL_REPLAY_NO_PROSPECTIVE_CREDIT')
        self.assertEqual(adapters['kind'],'adapter')
        self.assertEqual(len(adapters['records']),3)
        for record in adapters['records']:
            self.assertEqual(record['content_sha256'],r._digest(record['content']))
            self.assertEqual(record['signal_date'],record['content']['signal_date'])
            self.assertEqual(record['content']['validation']['scientific_forward_credit'],True)
        self.assertTrue(all(x['content']['execution']['hold_sessions']==20 for x in books['records']))

    def test_original_source_modules_not_mutated(self):
        source = self.root/'research/semiconductor_external_forward_standalone_20260910.py'
        old = hashlib.sha256(source.read_bytes()).hexdigest()
        r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)
        self.assertEqual(old,hashlib.sha256(source.read_bytes()).hexdigest())

    def test_invalid_duplicate_out_of_order_future_and_limit(self):
        cases=[['2026-10-12','2026-10-12'],['2026-10-13','2026-10-12'],
               ['2026-10-12']*5,['2026-11-07'],['2026-09-09'],[]]
        for dates in cases:
            with self.subTest(dates=dates), self.assertRaises(ValueError):
                r.validate_request(request(dates),TEST_NOW)

    def test_fail_closed_unsettled_ny_close(self):
        before=datetime(2026,11,5,22,29,tzinfo=timezone.utc)
        self.assertLess(r._completed_et(before),'2026-11-05')
        with self.assertRaisesRegex(ValueError,'outside settled'):
            r.validate_request(request(['2026-11-05']),before)

    def test_reject_extra_flags_and_wrong_authority(self):
        for variant in ({**request(),'broker_submit':True}, {**request(),'source_ref':'other'},
                        {**request(),'evidence_class':'ORIGINAL_TIMESTAMPED'}):
            with self.assertRaises(ValueError): r.validate_request(variant,TEST_NOW)

    def test_reject_source_session_lagged_to_previous_date(self):
        source=self.root/'research/semiconductor_external_forward_standalone_20260910.py'
        source.write_text(source.read_text().replace("{s:D for s in TRAIN+EXT+['SMH','QQQ']}","{s:('2026-10-09' if s=='QQQ' else D) for s in TRAIN+EXT+['SMH','QQQ']}"))
        with self.assertRaisesRegex(RuntimeError,'source session not complete'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_reject_monthly_purge_or_fit_drift(self):
        p=self.root/'research/semiconductor_external_forward_standalone_20260910.py'
        p.write_text(p.read_text().replace("'resolved_session_purge':21","'resolved_session_purge':20"))
        with self.assertRaisesRegex(RuntimeError,'monthly fit'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_reject_positive_mask_drift(self):
        p=self.root/'research/semiconductor_external_forward_standalone_20260910.py'
        p.write_text(p.read_text().replace("'positive_value_opportunity':i%2==0", "'positive_value_opportunity':True"))
        with self.assertRaisesRegex(RuntimeError,'positive-value'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_reject_broker_authority(self):
        p=self.root/'research/semiconductor_three_book_forward_20260910.py'
        p.write_text(p.read_text().replace("'broker_orders':False", "'broker_orders':True"))
        with self.assertRaisesRegex(RuntimeError,'escalated authority'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_reject_adapted_forecast_mutation(self):
        p=self.adapter
        p.write_text(p.read_text().replace("'predicted_fixed20_net_value_bps':pred", "'predicted_fixed20_net_value_bps':{k:v+5 for k,v in pred.items()}"))
        with self.assertRaisesRegex(RuntimeError,'changed frozen'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_reject_frozen_book_missing_positive_weight(self):
        p=self.root/'research/semiconductor_three_book_forward_20260910.py'
        p.write_text(p.read_text().replace("{s:0.05/len(pos) for s in pos}", "{pos[0]:0.05}"))
        with self.assertRaisesRegex(RuntimeError,'positive selection'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_reject_option_trade_enabled(self):
        p=self.root/'research/semiconductor_three_book_forward_20260910.py'
        p.write_text(p.read_text().replace("'trade_authorized':False", "'trade_authorized':True"))
        with self.assertRaisesRegex(RuntimeError,'option authority'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_reject_breadth_sector_weight_drift(self):
        p=self.root/'research/semiconductor_three_book_forward_20260910.py'
        p.write_text(p.read_text().replace("0.05*len(pos)/len(n['observations'])", "0.001"))
        with self.assertRaisesRegex(RuntimeError,'breadth-to-sector'):
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)

    def test_no_private_source_in_public_stdout(self):
        p=self.root/'research/semiconductor_external_forward_standalone_20260910.py'
        p.write_text(p.read_text().replace("Path(a.output).parent", "print('SENSITIVE_SYNTHETIC_SECRET');Path(a.output).parent"))
        with mock.patch.object(r,'_execute_fixed', wraps=r._execute_fixed) as execute:
            r.execute_bounded(self.root,self.adapter,request(['2026-10-12']),now_utc=TEST_NOW)
            self.assertEqual(execute.call_count,3)


if __name__ == '__main__': unittest.main()