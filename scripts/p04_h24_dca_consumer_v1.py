from __future__ import annotations
import argparse,base64,hashlib,io,json,zipfile
from pathlib import Path
from urllib.request import Request,urlopen
import numpy as np
import pandas as pd
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA='p04-h24-dca-ephemeral-x25519-v1'
HARNESS='p04_h24_dca_v1'

def _download_verified(url: str, expected_sha256: str) -> bytes:
 req=Request(url,headers={'User-Agent':'p04-h24-dca-consumer-v1'})
 with urlopen(req,timeout=120) as response:
  data=response.read()
 actual=hashlib.sha256(data).hexdigest()
 if actual!=expected_sha256: raise SystemExit(f'artifact sha mismatch: {actual}')
 return data

def _artifact_bytes(node, prefix):
 inline=f'{prefix}_zip_b64'
 url=f'{prefix}_url'
 digest=f'{prefix}_sha256'
 if inline in node:
  return base64.b64decode(node[inline])
 if url in node and digest in node:
  return _download_verified(str(node[url]),str(node[digest]))
 raise SystemExit(f'missing {prefix} artifact payload')

def main():
 p=argparse.ArgumentParser(); p.add_argument('--envelope',required=True); p.add_argument('--ciphertext',required=True); p.add_argument('--private-key',required=True); p.add_argument('--run-id',required=True); p.add_argument('--response-root',required=True); a=p.parse_args()
 env=json.loads(Path(a.envelope).read_text())
 raw=decrypt_assembled_ciphertext(envelope=env,ciphertext=Path(a.ciphertext).read_bytes(),private_key_path=Path(a.private_key),expected_schema=SCHEMA,expected_run_id=a.run_id,expected_harness=HARNESS,response_root=a.response_root)
 node=json.loads(raw)
 if node.get('schema')!='p04-h24-dca-private-payload-v1' or node.get('authority')!='research_only': raise SystemExit('payload contract mismatch')
 allowed_inline={'schema','authority','h24_zip_b64','lifecycle_zip_b64'}
 allowed_urls={'schema','authority','h24_url','h24_sha256','lifecycle_url','lifecycle_sha256'}
 if set(node) not in (allowed_inline,allowed_urls): raise SystemExit('payload contract field mismatch')
 hz=zipfile.ZipFile(io.BytesIO(_artifact_bytes(node,'h24'))); lz=zipfile.ZipFile(io.BytesIO(_artifact_bytes(node,'lifecycle')))
 h=pd.read_csv(hz.open('research/results/mnq_h24_oos_risk_surface_20260903/mnq-h24-oos-risk-surface.csv'))
 t=pd.read_csv(lz.open('result/mnq-crw-lifecycle-trades-canonical_-2.8.csv'))
 h['timestamp']=pd.to_datetime(h['timestamp'],utc=True); periods=sorted(h['period'].dropna().unique())
 events=[]
 for _,r in t.iterrows():
  dcas=[x for x in json.loads(r['fills_json']) if x.get('kind')=='dca']
  for tier,f in enumerate(dcas,1):
   ts=pd.to_datetime(f['timestamp'],utc=True); m=h[(h.timestamp==ts)&(h.source_contract==r.source_contract)]
   if len(m)!=1: events.append({'timestamp':ts.isoformat(),'joined':False}); continue
   q=m.iloc[0]; prior=h[h.period<q.period]['pred_long_mae_z_h24'].dropna(); cuts=None if prior.empty else np.quantile(prior,[.2,.4,.6,.8])
   risk=float(q.pred_long_mae_z_h24); bucket=None if cuts is None else int(1+sum(risk>x for x in cuts))
   events.append({'timestamp':ts.isoformat(),'joined':True,'period':q.period,'tier':tier,'risk':risk,'bucket':bucket,'terminal_points':float(r.exit_price-f['price'])})
 e=pd.DataFrame([x for x in events if x.get('joined') and x.get('bucket') is not None])
 costs={}
 for c in (0.0,1.0,2.0):
  y=e.assign(net=e.terminal_points-c)
  hi=y[y.bucket==5]; lo=y[y.bucket<5]
  costs[str(c)]={'all_n':int(len(y)),'all_sum':float(y.net.sum()),'high_risk_n':int(len(hi)),'high_risk_mean':float(hi.net.mean()),'high_risk_sum':float(hi.net.sum()),'lower_risk_n':int(len(lo)),'lower_risk_mean':float(lo.net.mean()),'lower_risk_sum':float(lo.net.sum()),'high_minus_lower_mean':float(hi.net.mean()-lo.net.mean())}
 fold=[]
 for per,g in e.groupby('period'):
  hi=g[g.bucket==5]; lo=g[g.bucket<5]
  if len(hi) and len(lo): fold.append({'period':per,'high_n':int(len(hi)),'lower_n':int(len(lo)),'high_mean':float(hi.terminal_points.mean()),'lower_mean':float(lo.terminal_points.mean()),'high_worse':bool(hi.terminal_points.mean()<lo.terminal_points.mean())})
 comparable=len(fold); worse=sum(x['high_worse'] for x in fold)
 decision='H24_DCA_RISK_DIRECTION_NOT_SUPPORTED' if comparable and worse*2<=comparable else ('H24_DCA_RISK_DIRECTION_PROMISING' if comparable else 'INSUFFICIENT_COMPARABLE_FOLDS')
 receipt={'schema':'p04-h24-dca-receipt-v1','authority':'research_only','source_events':len(events),'exact_joined':sum(bool(x.get('joined')) for x in events),'bucketed_events':int(len(e)),'cost_scenarios_points':costs,'comparable_periods':comparable,'high_risk_worse_periods':worse,'folds':fold,'decision':decision,'strategy_spec_write':False,'runtime_activation':False,'broker_submit':False,'promotion_authority':False,'live_trading_change':False}
 print('P04_H24_DCA_RECEIPT='+json.dumps(receipt,sort_keys=True))
if __name__=='__main__': main()
