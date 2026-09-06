from __future__ import annotations
import argparse,base64,io,json,zipfile
from pathlib import Path
import pandas as pd
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA='p04-max-one-dca-policy-ephemeral-x25519-v1'
HARNESS='p04_max_one_dca_policy_v1'
PAYLOAD_SCHEMA='p04-max-one-dca-policy-private-payload-v1'
CSV='result/mnq-crw-lifecycle-trades-canonical_-2.8.csv'

def main():
 p=argparse.ArgumentParser(); p.add_argument('--envelope',required=True); p.add_argument('--ciphertext',required=True); p.add_argument('--private-key',required=True); p.add_argument('--run-id',required=True); p.add_argument('--response-root',required=True); a=p.parse_args()
 env=json.loads(Path(a.envelope).read_text())
 raw=decrypt_assembled_ciphertext(envelope=env,ciphertext=Path(a.ciphertext).read_bytes(),private_key_path=Path(a.private_key),expected_schema=SCHEMA,expected_run_id=a.run_id,expected_harness=HARNESS,response_root=a.response_root)
 node=json.loads(raw)
 if set(node)!={'schema','authority','lifecycle_zip_b64'} or node['schema']!=PAYLOAD_SCHEMA or node['authority']!='research_only': raise SystemExit('payload contract mismatch')
 z=zipfile.ZipFile(io.BytesIO(base64.b64decode(node['lifecycle_zip_b64'])))
 if CSV not in z.namelist(): raise SystemExit('canonical lifecycle csv missing')
 t=pd.read_csv(z.open(CSV)); rows=[]; tier2=[]
 for _,r in t.iterrows():
  fills=json.loads(r['fills_json']); dcas=[x for x in fills if x.get('kind')=='dca']; t2=0.0; t2year=None
  if len(dcas)>=2:
   t2=float(r.exit_price)-float(dcas[1]['price']); t2year=int(pd.to_datetime(dcas[1]['timestamp'],utc=True).year); tier2.append({'year':t2year,'terminal':t2,'skip_delta':-t2})
  rows.append({'full_qty':int(r.final_qty),'full_gross':float(r.gross_contract_points),'max1_gross':float(r.gross_contract_points)-t2})
 e=pd.DataFrame(rows); d=pd.DataFrame(tier2); costs={}
 for c in (0.0,1.0,2.0):
  full=e.full_gross-c*e.full_qty; max1=e.max1_gross-c*e.full_qty.clip(upper=2)
  costs[str(c)]={'full_sum':float(full.sum()),'max_one_dca_sum':float(max1.sum()),'delta_sum':float((max1-full).sum()),'full_mean_trade':float(full.mean()),'max_one_dca_mean_trade':float(max1.mean())}
 folds=[]
 for year,g in d.groupby('year'):
  folds.append({'year':int(year),'tier2_n':int(len(g)),'full_minus_max1_tier2_sum':float(g.terminal.sum()),'max1_minus_full_delta':float(g.skip_delta.sum()),'max1_better':bool(g.skip_delta.sum()>0)})
 comparable=len(folds); better=sum(x['max1_better'] for x in folds); positive=[x['max1_minus_full_delta'] for x in folds if x['max1_minus_full_delta']>0]; positive_sum=sum(positive); max_positive_share=(max(positive)/positive_sum) if positive_sum else 1.0
 all_cost_positive=all(costs[str(c)]['delta_sum']>0 for c in (0.0,1.0,2.0))
 if comparable<4 or len(d)<8: decision='INSUFFICIENT_COMPARABLE_FOLDS'
 elif better>=3 and all_cost_positive and max_positive_share<=0.60: decision='MAX_ONE_DCA_POLICY_PROMISING'
 else: decision='MAX_ONE_DCA_POLICY_NOT_SUPPORTED'
 receipt={'schema':'p04-max-one-dca-policy-receipt-v1','authority':'research_only','trade_n':int(len(e)),'tier2_add_n':int(len(d)),'comparable_tier2_years':comparable,'max1_better_years':better,'max_positive_year_share':float(max_positive_share),'cost_scenarios_points':costs,'folds':folds,'decision':decision,'drawdown_counterfactual_available':False,'drawdown_evidence_gap':'canonical lifecycle summary does not contain a max-one-DCA counterfactual MTM path','strategy_spec_write':False,'runtime_activation':False,'broker_submit':False,'promotion_authority':False,'live_trading_change':False}
 print('P04_MAX_ONE_DCA_POLICY_RECEIPT='+json.dumps(receipt,sort_keys=True))
if __name__=='__main__': main()
