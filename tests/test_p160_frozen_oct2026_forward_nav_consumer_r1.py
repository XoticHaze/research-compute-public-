"""Pure synthetic P160 forward NAV acceptance, no provider or market I/O."""
import unittest
import pandas as pd
from research.p160_frozen_oct2026_forward_nav_consumer_r1 import score, TARGET, MATCHED, SYMBOLS

FROZEN={
 'program_id':'P160_FIXED_P46_P47_COMBINATION','signal_month_end':'2026-09-30',
 'generated_at':'2026-10-01T09:11:36.822010+00:00','state':'PROSPECTIVE_ELIGIBLE',
 'frozen_identity':{'source_ref':'c575e02aba939b283c0aa409d9bc21f000c0762c',
                    'source_blob_sha':'89d8e4c004536310e588623203e8e23e8aac15d9',
                    'primary_cost_bps':50.0},
 'paper_action':{'target_weights':TARGET,'matched_control_weights':MATCHED}
}


def panel():
 rows=[]
 for d in ('2026-10-01','2026-10-02'):
  for s in SYMBOLS:
   rows.append({'date':d,'symbol':s,'open':100.0,'close':102.0 if d=='2026-10-02' and s in TARGET else 100.0})
 return pd.DataFrame(rows)


def run(p=None,f=None,s=None,basis='yahoo_auto_adjust_ohlc'):
 return score(f or FROZEN,p if p is not None else panel(),s or ['2026-10-01','2026-10-02'],
              entry_open_utc='2026-10-01T13:30:00+00:00',adjustment_basis=basis,
              asof_date=(s[-1] if s else '2026-10-02'))


class P160ForwardTests(unittest.TestCase):
 def test_exact_frozen_cost_and_no_daily_rebalance(self):
  r=run()
  self.assertAlmostEqual(r['terminal_nav']['candidate'],1.02-.0025,places=9)
  self.assertAlmostEqual(r['terminal_nav']['matched'],1+.02*sum(MATCHED[s] for s in TARGET),places=9)
  self.assertEqual(r['observed_sessions'],2)
  self.assertFalse(r['alpha_replacement_credit'])
  self.assertFalse(r['terminal_exit_cost_charged'])
  self.assertEqual(r['initial_candidate_cost_bps'],25.0)
  self.assertFalse(r['matched_and_opportunity_costs_in_original'])
 def test_missing_entire_completed_session_rejected(self):
  with self.assertRaisesRegex(ValueError,'MEMBER_COUNT'):run(s=['2026-10-01','2026-10-02','2026-10-05'])
 def test_missing_single_symbol_rejected(self):
  with self.assertRaisesRegex(ValueError,'MEMBER_COUNT'):run(p=panel().iloc[:-1])
 def test_duplicate_member_rejected(self):
  with self.assertRaisesRegex(ValueError,'DUPLICATE'):run(p=pd.concat([panel(),panel().iloc[:1]]))
 def test_raw_price_basis_rejected(self):
  with self.assertRaisesRegex(ValueError,'ADJUSTED'):run(basis='unadjusted')
 def test_post_outcome_signal_change_rejected(self):
  f={**FROZEN,'generated_at':'2026-10-01T15:00:00+00:00'}
  with self.assertRaisesRegex(ValueError,'PREENTRY'):run(f=f)
 def test_unauthorized_next_month_without_new_signal_rejected(self):
  with self.assertRaisesRegex(ValueError,'NEXT_MONTH'):run(s=['2026-10-01','2026-11-02'])
 def test_pinned_original_half_l1_cost_parity(self):
  r=run()
  # Original P160 ev: .5*(a - .5*50/10000)+.5*(b - .5*50/10000)
  original_month_return=.5*(.02-.5*50/10000)+.5*(.02-.5*50/10000)
  self.assertAlmostEqual(r['terminal_nav']['candidate']-1,original_month_return,places=12)
 def test_post_asof_price_member_rejected(self):
  p=pd.concat([panel(),pd.DataFrame([{'date':'2026-10-05','symbol':'SPY','open':100.,'close':100.}])])
  with self.assertRaisesRegex(ValueError,'POST_ASOF'):run(p=p)
 def test_negative_or_nan_price_rejected(self):
  p=panel();p.loc[0,'open']=-1
  with self.assertRaisesRegex(ValueError,'NONFINITE'):run(p=p)

if __name__=='__main__':unittest.main()
