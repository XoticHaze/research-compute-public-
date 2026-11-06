"""No fabricated prospective credit, no silent date gaps, no future-data signal selection."""
import importlib.util
from datetime import date, timedelta
import json
import pathlib
import tempfile
import unittest

MOD_PATH = pathlib.Path(__file__).resolve().parents[1] / 'research' / 'forward_decision_continuity_r1.py'
spec = importlib.util.spec_from_file_location('continuity', MOD_PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def frozen_model():
    return {
        'program_id': 'SEMICONDUCTOR_SHARED_RIDGE',
        'frozen_model_ref': 'sha256:original-model',
        'first_eligible_decision_date': '2026-10-12',
        'cadence': 'DAILY_CLOSE',
        'execution_delay_sessions': 1,
        'holding_horizon_sessions': 2,
        'qualifier': 'SEMICONDUCTOR_POSITIVE_VALUE',
    }


def adapter(day, values, weights):
    positive = [k for k, v in values.items() if v > 0]
    return {
        'schema': c.ADAPTER_SCHEMA,
        'program_id': 'SEMICONDUCTOR_SHARED_RIDGE',
        'signal_date': day,
        'signal': {
            'positive_symbols': positive,
            'predicted_fixed20_net_value_bps': values,
        },
        'paper_action': {'ticker_book': {
            'status': 'PAPER_COHORT_READY',
            'cohort_target_weights_nav': weights,
        }},
        'validation': {'scientific_forward_credit': True},
        'boundaries': {k: False for k in ('broker_action', 'live_trading_change', 'promotion_authority', 'runtime_mutation')},
    }


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.adapters = self.root / 'adapters' / 'SEMICONDUCTOR_SHARED_RIDGE'
        self.adapters.mkdir(parents=True)
        self.manifest = {
            'schema': c.MANIFEST_SCHEMA,
            'asof': '2026-10-15',
            'market_sessions': ['2026-10-12','2026-10-13','2026-10-14','2026-10-15','2026-10-16'],
            'models': [frozen_model()],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, day, values, weights, prov=None):
        path = self.adapters / (day + '.json')
        path.write_text(json.dumps(adapter(day, values, weights)))
        if prov:
            prov['adapter_sha256'] = c._hash(path)
            prov['frozen_model_ref'] = self.manifest['models'][0]['frozen_model_ref']
            (self.adapters / (day + '.provenance.json')).write_text(json.dumps(prov))

    def build(self, prior=None):
        return c.build(self.manifest, self.adapters.parent, prior)

    def test_qualifying_and_empty_decisions_gap_visible(self):
        self.write('2026-10-12', {'AMAT': 30,'NVDA': -2}, {'AMAT': .05},
                   {'evidence_class':'REPLAYED_ASOF', 'replayed_at':'2026-11-05T23:00:00Z'})
        self.write('2026-10-14', {'AMAT': -1,'NVDA': -2}, {})
        report = self.build()
        self.assertEqual(report['summary']['SEMICONDUCTOR_SHARED_RIDGE']['expected_decisions'], 4)
        self.assertEqual(report['summary']['SEMICONDUCTOR_SHARED_RIDGE']['missing_predictions'], 2)
        d = report['decisions']
        self.assertEqual(d[0]['decision'], 'QUALIFY')
        self.assertEqual(d[0]['entry_date'], '2026-10-13')
        self.assertEqual(d[0]['horizon_end_date'], '2026-10-15')
        self.assertEqual(d[0]['holding_sessions_elapsed_asof'], 2)
        self.assertEqual(d[0]['evidence_class'], 'HISTORICAL_REPLAY_NO_PROSPECTIVE_CREDIT')
        self.assertFalse(d[0]['scientific_forward_credit_granted_by_this_tool'])
        self.assertEqual(d[2]['decision'], 'NO_ENTRY')

    def test_canonical_prior_schema_and_rejected_entry_fails_closed(self):
        rejected={'schema':'research.forward_prospective_cohort_ledger_r1','cohorts':[
          {'program_id':'SEMICONDUCTOR_SHARED_RIDGE','signal_date':'2026-10-12',
           'source_adapter_sha256':'sha256:source','cohort_id':'reject',
           'status':'LATE_REGISTRATION_REJECTED','symbols':['AMAT']}]}
        x=self.build(rejected)['decisions'][0]
        self.assertEqual(x['decision'],'REJECTED_PROSPECTIVE')
        self.assertIsNone(x['entry_date'])
        self.assertEqual(x['evidence_class'],'CANONICAL_REJECTED_NO_PROSPECTIVE_CREDIT')
        with self.assertRaisesRegex(ValueError,'schema mismatch'):
            self.build({'cohorts':rejected['cohorts']})

    def test_recovered_dated_adapter_mismatch_to_canonical_fails_closed(self):
        self.write('2026-10-12', {'AMAT':10}, {'AMAT':.05})
        prior={'schema':'research.forward_prospective_cohort_ledger_r1','cohorts':[
          {'program_id':'SEMICONDUCTOR_SHARED_RIDGE','signal_date':'2026-10-12',
           'source_adapter_sha256':'bad-prior-hash','cohort_id':'original',
           'status':'RESOLVED','symbols':['AMAT']}]}
        x=self.build(prior)['decisions'][0]
        self.assertEqual(x['decision'],'LINEAGE_CONFLICT_NO_CREDIT')
        self.assertEqual(x['canonical_cohort_id'],'original')
        self.assertIsNone(x['entry_date'])

    def test_prior_cohort_preserved_without_adapter(self):
        prior = {'schema':'research.forward_prospective_cohort_ledger_r1','cohorts':[{'program_id':'SEMICONDUCTOR_SHARED_RIDGE', 'signal_date':'2026-10-12',
                             'source_adapter_sha256':'abc', 'cohort_id':'existing', 'status':'RESOLVED',
                             'symbols':['AMAT']}]}
        d=self.build(prior)['decisions'][0]
        self.assertEqual(d['canonical_cohort_id'], 'existing')
        self.assertEqual(d['decision'], 'PRIOR_ADMITTED_COHORT')
        self.assertTrue(d['evidence_class'].startswith('CANONICAL_ORIGINAL'))

    def test_timestamped_receipt_is_not_auto_credit(self):
        self.write('2026-10-12', {'AMAT':10}, {'AMAT':.05},
                   {'evidence_class':'ORIGINAL_TIMESTAMPED','original_observed_at':'2026-10-12T21:00:00Z'})
        r=self.build()['decisions'][0]
        self.assertEqual(r['evidence_class'],'ORIGINAL_RECEIPT_NEEDS_ISSUER_VERIFICATION')
        self.assertFalse(r['scientific_forward_credit_granted_by_this_tool'])

    def test_late_original_timestamp_rejected_for_prospective_credit(self):
        self.write('2026-10-12', {'AMAT':10}, {'AMAT':.05},
                   {'evidence_class':'ORIGINAL_TIMESTAMPED','original_observed_at':'2026-10-14T12:00:00Z'})
        r=self.build()['decisions'][0]
        self.assertEqual(r['evidence_class'],'LATE_ORIGINAL_RECEIPT_NO_PROSPECTIVE_CREDIT')
        self.assertFalse(r['scientific_forward_credit_granted_by_this_tool'])

    def test_frozen_non_daily_decision_calendar(self):
        self.manifest['models'][0]['cadence']='FROZEN_DATED_DECISIONS'
        self.manifest['models'][0]['frozen_decision_dates']=['2026-10-12','2026-10-15']
        r=self.build()
        self.assertEqual(r['summary']['SEMICONDUCTOR_SHARED_RIDGE']['expected_decisions'],2)
        self.assertEqual([d['signal_date'] for d in r['decisions']],['2026-10-12','2026-10-15'])
        self.manifest['models'][0]['frozen_decision_dates']=['2026-10-15','2026-10-12']
        with self.assertRaisesRegex(ValueError,'distinct/ascending'):
            self.build()

    def test_homebuilders_frozen_individual_horizons_and_costs(self):
        start=date(2026,1,2)
        sessions=[]
        for i in range(98):
            day=start+timedelta(days=i)
            if day.weekday()<5:
                sessions.append(day.isoformat())
        self.manifest={
            'schema':c.MANIFEST_SCHEMA,
            'asof':sessions[-1],
            'market_sessions':sessions,
            'models':[{
                'program_id':'HOMEBUILDERS','frozen_model_ref':'foundry:homebuilder-duration',
                'first_eligible_decision_date':sessions[0],
                'cadence':'FROZEN_DATED_DECISIONS',
                'frozen_decision_dates':[sessions[0]],
                'execution_delay_sessions':1,'holding_horizon_sessions':60,
                'qualifier':'HOMEBUILDERS_ADMITTED',
                'stock_round_trip_cost_bps':25,'sector_round_trip_cost_bps':10,
            }]
        }
        hb=self.root/'adapters'/'HOMEBUILDERS';hb.mkdir(parents=True)
        signal={
            'schema':c.ADAPTER_SCHEMA,'program_id':'HOMEBUILDERS','signal_date':sessions[0],
            'signal':{'admitted_symbols':['CCS','MHO'],
                      'duration_horizon_sessions_by_symbol':{'CCS':5,'MHO':60}},
            'boundaries':{k:False for k in ('broker_action','live_trading_change','promotion_authority','runtime_mutation')},
        }
        (hb/(sessions[0]+'.json')).write_text(json.dumps(signal))
        prices={sessions[1]:{'CCS':100,'MHO':100,'ITB':100},
                sessions[6]:{'CCS':110,'MHO':110,'ITB':104},
                sessions[61]:{'CCS':111,'MHO':120,'ITB':105}}
        tape={'schema':c.PRICE_SCHEMA,'adjustment':'ADJUSTED_CLOSE',
              'source_ref':'owned:homebuilders-test','market_data_asof':sessions[-1],
              'prices':prices}
        report=c.build(self.manifest,self.adapters.parent,price_tape=tape)
        row=report['decisions'][0]
        self.assertEqual(row['decision'],'QUALIFY')
        self.assertEqual(row['symbol_horizon_end_dates']['CCS'],sessions[6])
        self.assertEqual(row['symbol_horizon_end_dates']['MHO'],sessions[61])
        value=row['economic_simulation']
        self.assertEqual(value['state'],'RESOLVED_HISTORICAL_SIMULATION')
        self.assertEqual(len(value['observations']),2)
        self.assertEqual(value['observations'][0]['excess_vs_itb_matched_net_bps'],585)
        self.assertEqual(value['observations'][1]['excess_vs_itb_matched_net_bps'],1485)

    def test_after_cost_h20_resolver_and_matched_benchmarks(self):
        self.manifest['models'][0]['stock_round_trip_cost_bps']=25
        self.manifest['models'][0]['sector_round_trip_cost_bps']=10
        self.write('2026-10-12', {'AMAT':100,'NVDA':-20}, {'AMAT':.05})
        tape={
            'schema':c.PRICE_SCHEMA,
            'adjustment':'ADJUSTED_CLOSE',
            'source_ref':'owned:adjusted-close-fixture',
            'market_data_asof':'2026-10-15',
            'prices': {
                '2026-10-13': {'AMAT':100,'NVDA':100,'SMH':100},
                '2026-10-15': {'AMAT':110,'NVDA':98,'SMH':104},
            }
        }
        mark=c.build(self.manifest,self.adapters.parent,price_tape=tape)['decisions'][0]['economic_simulation']
        self.assertEqual(mark['state'],'RESOLVED_HISTORICAL_SIMULATION')
        self.assertEqual(mark['model_book_net_if_flattened_bps'],975)
        self.assertEqual(mark['matched_smh_net_bps'],390)
        self.assertEqual(mark['model_minus_matched_smh_net_bps'],585)
        self.assertEqual(mark['matched_equal_weight_universe_net_bps'],375)
        self.assertEqual(mark['model_minus_matched_equal_weight_net_bps'],600)
        self.assertFalse(mark['first_seen_prospective_credit'])

    def test_price_tape_future_bar_and_missing_cost_fail_closed(self):
        self.write('2026-10-12', {'AMAT':100}, {'AMAT':.05})
        tape={ 'schema':c.PRICE_SCHEMA,'adjustment':'ADJUSTED_CLOSE',
               'source_ref':'owned:test', 'market_data_asof':'2026-10-15',
               'prices': {'2026-10-13':{'AMAT':100,'SMH':100},
                          '2026-10-15':{'AMAT':110,'SMH':103}}}
        mark=c.build(self.manifest,self.adapters.parent,price_tape=tape)['decisions'][0]['economic_simulation']
        self.assertEqual(mark['state'],'MISSING_FROZEN_COST_CONTRACT')
        tape['prices']['2026-10-16']={'AMAT':400,'SMH':400}
        with self.assertRaisesRegex(ValueError,'future session'):
            c.build(self.manifest,self.adapters.parent,price_tape=tape)

    def test_hash_mismatch_fails(self):
        self.write('2026-10-12', {'AMAT': 10}, {'AMAT': .05},
                   {'evidence_class':'REPLAYED_ASOF','replayed_at':'2026-11-05T23:00:00Z'})
        path=self.adapters/'2026-10-12.json'
        path.write_text(json.dumps(adapter('2026-10-12', {'AMAT':-50}, {})))
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            self.build()

    def test_model_signal_selection_and_frozen_book_fail_closed(self):
        self.write('2026-10-12', {'AMAT':12,'NVDA':5}, {'AMAT':.05})
        d=self.build()['decisions'][0]
        self.assertEqual(d['decision'],'ADMISSION_INCOMPLETE')
        p=self.adapters/'2026-10-12.json'
        x=json.loads(p.read_text());x['signal']['positive_symbols']=['AMAT'];p.write_text(json.dumps(x))
        with self.assertRaisesRegex(ValueError,'positive mask'):
            self.build()

    def test_calendar_duplicate_and_invalid_boundary_rejected(self):
        self.manifest['market_sessions'].append('2026-10-16')
        with self.assertRaisesRegex(ValueError,'unique and ascending'):
            self.build()
        self.manifest['market_sessions'].pop()
        self.write('2026-10-12', {'AMAT':1}, {'AMAT':.05})
        path=self.adapters/'2026-10-12.json';d=json.loads(path.read_text());d['boundaries']['broker_action']=True
        path.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'unsafe adapter boundary'):
            self.build()

if __name__ == '__main__':
    unittest.main()