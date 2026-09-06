from __future__ import annotations
import argparse,base64,io,json,zipfile
from pathlib import Path
import pandas as pd
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA='p04-dca-tier-economics-ephemeral-x25519-v1'
HARNESS='p04_dca_tier_economics_v1'
PAYLOAD_SCHEMA='p04-dca-tier-economics-private-payload-v1'
CSV='result/mnq-crw-lifecycle-trades-canonical_-2.8.csv'

def main():
 p=argparse.ArgumentParser(); p.add_argument('--envelope',required=True); p.add_argument('--ciphertext',required=True); p.add_argument('--private-key',required=True); p.add_argument('--run-id',required=True); p.add_argument('--response-root',required=True); a=p.parse_args()
 env=json.loads(Path(a.envelope).read_text())
 raw=decrypt_assembled_ciphertext(envelope=env,ciphertext=Path(a.ciphertext).read_bytes(),private_key_path=Path(a.private_key),expected_schema=SCHEMA,expected_run_id=a.run_id,expected_harness=HARNESS,response_root=a.response_root)
 node=json.loads(raw)
 if set(node)!={'schema','authority','lifecycle_zip_b64'} or node['schema']!=PAYLOAD_SCHEMA or node['authority']!='research_only': raise SystemExit('payload contract mismatch')
 z=zipfile.ZipFile(io.BytesIO(base64.b64decode(node['lifecycle_zip_b64'])))
 if CSV not in z.namelist(): raise SystemExit('canonical lifecycle csv missing')
 t=pd.read_csv(z.open(CSV)); events=[]
 for _,r in t.iterrows():
  fills=json.loads(r['fills_json']); dcas=[x for x in fills if x.get('kind')=='dca']
  for tier,f in enumerate(dcas,1):
   ts=pd.to_datetime(f['timestamp'],utc=True); gross=float(r['exit_price'])-float(f['price'])
   events.append({'year':int(ts.year),'tier':tier,'gross':gross})
 e=pd.DataFrame(events)
 costs={}
 for c in (0.0,1.0,2.0):
  y=e.assign(net=e.gross-c); out={}
  for tier in (1,2):
   g=y[y.tier==tier]; out[str(tier)]={'n':int(len(g)),'mean':float(g.net.mean()),'median':float(g.net.median()),'sum':float(g.net.sum()),'profitable_n':int((g.net>0).sum()),'losing_n':int((g.net<0).sum())}
  out['tier2_minus_tier1_mean']=float(out['2']['mean']-out['1']['mean']); costs[str(c)]=out
 folds=[]
 for year,g in e.groupby('year'):
  a1=g[g.tier==1].gross; a2=g[g.tier==2].gross
  if len(a1) and len(a2): folds.append({'year':int(year),'tier1_n':int(len(a1)),'tier1_mean':float(a1.mean()),'tier2_n':int(len(a2)),'tier2_mean':float(a2.mean()),'tier2_minus_tier1':float(a2.mean()-a1.mean()),'tier2_worse':bool(a2.mean()<a1.mean())})
 comparable=len(folds); worse=sum(x['tier2_worse'] for x in folds); tier2_n=int((e.tier==2).sum())
 if comparable<3 or tier2_n<8: decision='INSUFFICIENT_COMPARABLE_FOLDS'
 elif worse==comparable and all(costs[str(c)]['tier2_minus_tier1_mean']<0 for c in (0.0,1.0,2.0)): decision='DCA_TIER2_RESERVE_RELEASE_PROMISING'
 else: decision='DCA_TIER2_RESERVE_RELEASE_NOT_SUPPORTED'
 t2=e[e.tier==2]
 receipt={'schema':'p04-dca-tier-economics-receipt-v1','authority':'research_only','source_dca_events':int(len(e)),'tier1_n':int((e.tier==1).sum()),'tier2_n':tier2_n,'comparable_years':comparable,'tier2_worse_years':worse,'folds':folds,'cost_scenarios_points':costs,'skip_tier2_gross_delta_points':float(-t2.gross.sum()),'tier2_losing_adds':int((t2.gross<0).sum()),'tier2_profitable_adds':int((t2.gross>0).sum()),'tier2_share_of_dca_adds':float(tier2_n/len(e)),'decision':decision,'strategy_spec_write':False,'runtime_activation':False,'broker_submit':False,'promotion_authority':False,'live_trading_change':False}
 print('P04_DCA_TIER_ECONOMICS_RECEIPT='+json.dumps(receipt,sort_keys=True))
if __name__=='__main__': main()
