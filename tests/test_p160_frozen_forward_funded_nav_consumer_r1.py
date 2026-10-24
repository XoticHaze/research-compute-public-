import copy
import unittest
from p160_frozen_forward_funded_nav_consumer_r1 import UNIVERSE, score_frozen_p160


class P160FrozenConsumerTests(unittest.TestCase):
    def setUp(self):
        self.signal = {
            'program_id':'P160_FIXED_P46_P47_COMBINATION',
            'frozen_identity':{'source_blob_sha':'89d8e4c004536310e588623203e8e23e8aac15d9','primary_cost_bps':50.0},
            'signal_month_end':'2026-09-30','generated_at':'2026-10-01T09:11:36.822010+00:00',
            'timing':{'same_close_execution_prohibited':True},
            'paper_action':{'target_weights':{'IGV':1/6,'IWM':1/6,'QQQ':0.25,'SPY':0.25,'XBI':1/6},
                            'matched_control_weights':{s:(0.1 if s in ('SPY','QQQ','TLT','GLD','DBC') else 0.0625) for s in UNIVERSE}}
        }
        self.rows = []
        for day,price in [('2026-10-01',100),('2026-10-02',101)]:
            for sym in UNIVERSE:
                self.rows.append({'date':day,'symbol':sym,'open':price,'close':price,
                                  'session_open_utc':f'{day}T13:30:00Z',
                                  'session_close_utc':f'{day}T20:00:00Z','completed':True})
        self.kwargs={'frozen_signal':self.signal,'completed_bars':self.rows,'observed_at_utc':'2026-10-03T01:00:00Z',
                     'price_basis':'raw_sip','source_provider':'synthetic_test',
                     'expected_common_session_dates':['2026-10-01','2026-10-02'],
                     'expected_entry_day':'2026-10-01'}

    def test_cost_funding_and_matched(self):
        x=score_frozen_p160(**self.kwargs)
        self.assertEqual(x['forward']['completed_sessions'],2)
        self.assertAlmostEqual(x['economics']['target']['net_return_bps'],50.0)
        self.assertAlmostEqual(x['relative_bps']['target_minus_matched'],0.0)
        self.assertFalse(x['authority']['allocation'])
        self.assertIn('NO_SCIENTIFIC_PROMOTION',x['stage'])

    def test_no_same_close_or_future_data(self):
        k=copy.deepcopy(self.kwargs)
        k['frozen_signal']['generated_at']='2026-10-01T21:00:00Z'
        with self.assertRaisesRegex(ValueError,'signal issued after'):
            score_frozen_p160(**k)
        k=copy.deepcopy(self.kwargs)
        k['observed_at_utc']='2026-10-02T19:00:00Z'
        with self.assertRaisesRegex(ValueError,'unclosed'):
            score_frozen_p160(**k)

    def test_missing_duplicate_or_incomplete_bar_fail_closed(self):
        k=copy.deepcopy(self.kwargs)
        k['completed_bars']=k['completed_bars'][:-1]
        with self.assertRaisesRegex(ValueError,'missing common'):
            score_frozen_p160(**k)
        k=copy.deepcopy(self.kwargs)
        k['completed_bars'].append(copy.deepcopy(k['completed_bars'][-1]))
        with self.assertRaisesRegex(ValueError,'duplicate'):
            score_frozen_p160(**k)
        k=copy.deepcopy(self.kwargs)
        k['completed_bars'][0]['completed']=False
        with self.assertRaisesRegex(ValueError,'incomplete'):
            score_frozen_p160(**k)

    def test_missing_calendar_session_and_wrong_entry_fail_closed(self):
        k=copy.deepcopy(self.kwargs)
        k['expected_common_session_dates']=['2026-10-01','2026-10-02','2026-10-05']
        with self.assertRaisesRegex(ValueError,'missing or extra expected'):
            score_frozen_p160(**k)
        k=copy.deepcopy(self.kwargs)
        k['expected_entry_day']='2026-10-02'
        with self.assertRaisesRegex(ValueError,'entry day differs'):
            score_frozen_p160(**k)

    def test_frozen_identity_and_full_universe(self):
        k=copy.deepcopy(self.kwargs)
        k['frozen_signal']['frozen_identity']['source_blob_sha']='changed'
        with self.assertRaisesRegex(ValueError,'identity'):
            score_frozen_p160(**k)
        k=copy.deepcopy(self.kwargs)
        del k['frozen_signal']['paper_action']['matched_control_weights']['DBC']
        with self.assertRaises(ValueError):
            score_frozen_p160(**k)

if __name__=='__main__':
    unittest.main()