from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np

EXPECTED_PANEL='a5f7f8eb3ce1ad9b185df661701623681c7b918edb55d31d188f4dc886650253'
EXPECTED_FP='e6b63d26f01d7b21f752a9bb32cd6866f2551e7dfe9aeb59363d6a9a6a59f64f'

def cagr(vals):
    x=np.asarray(vals,float); return float(np.prod(1+x)**(12/len(x))-1)

def stats(rows):
    return {
      'months':len(rows),
      'candidate_cagr':cagr([r['candidate_net_50bp'] for r in rows]),
      'equal_weight_cagr':cagr([r['equal_weight'] for r in rows]),
      'smh_cagr':cagr([r['smh'] for r in rows]),
      'qqq_cagr':cagr([r['qqq'] for r in rows])
    }

def main():
    src=json.loads(Path('input/p13_frozen_contract_replay_r1.json').read_text())
    if src['panel_sha256']!=EXPECTED_PANEL: raise RuntimeError(f"panel metadata mismatch {src['panel_sha256']}")
    rows=src['monthly_records']
    fp=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if fp!=EXPECTED_FP: raise RuntimeError(f'fingerprint mismatch {fp}')
    full=stats(rows); recent=stats([r for r in rows if r['entry_date']>='2022-01-01'])
    for label,actual,expected in [('full',full,src['full']),('2022_forward',recent,src['2022_forward'])]:
        for k in ('months','candidate_cagr','equal_weight_cagr','smh_cagr','qqq_cagr'):
            if k=='months':
                if actual[k]!=expected[k]: raise RuntimeError(f'{label} {k} mismatch')
            elif abs(actual[k]-expected[k])>1e-12: raise RuntimeError(f'{label} {k} mismatch {actual[k]} {expected[k]}')
    out={
      'schema':'research.p13_immutable_record_replay_r3','parent':'P13',
      'source_run_id':34325797529,'source_artifact_id':10093700209,
      'source_artifact_digest':'sha256:ba47b2758caab74554f843741982848a53b8e0cd0f40a365546533fce643536e',
      'panel_sha256_metadata':src['panel_sha256'],'selection_return_fingerprint_sha256':fp,
      'full':full,'2022_forward':recent,
      'decision':'P13_IMMUTABLE_MONTHLY_RECORD_REPLAY_EXACT_MATCH',
      'interpretation':'The artifact monthly eligibility/selection/return record is an exact deterministic replay boundary even though its 12-significant-digit CSV is insufficient to reproduce the in-memory selection fingerprint.'
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p13_immutable_record_replay_r3.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
