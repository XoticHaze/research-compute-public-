from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import research.fresh_scarcity_confirmation_20260905 as base

CONTRACT=Path('research/semiconductor_nonlinear_fresh_confirmation_contract_20260905.json')
OUT=Path('semiconductor_nonlinear_fresh_source_preflight_20260905.json')

def main():
    c=json.loads(CONTRACT.read_text())
    fresh=tuple(c['fresh_confirmation_universe']); train=tuple(c['train_universe']); context=tuple(c['context'])
    assert set(fresh).isdisjoint(train)
    assert set(fresh).isdisjoint(c['spent_external_universe_pr253'])
    assert set(fresh).isdisjoint(c['spent_external_universe_pr273'])
    symbols=(*train,*fresh,*context); raw={s:base.load(s) for s in symbols}
    last={s:d.iloc[-1].timestamp.isoformat() for s,d in raw.items()}; first={s:d.iloc[0].timestamp.isoformat() for s,d in raw.items()}; rows={s:int(len(d)) for s,d in raw.items()}
    cutoff=min(d.iloc[-1].timestamp for d in raw.values()); sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]
    cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    result={'schema':'public_compute.semiconductor_nonlinear_fresh_source_preflight.v1','status':'PASS' if len(cal)>=1500 else 'FAIL','fresh_universe':list(fresh),'source_rows':rows,'source_first':first,'source_last':last,'common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),'target_returns_computed':False,'model_executed':False,'contract_frozen_before_preflight':True,'research_only':True}
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print('SEMICONDUCTOR_NONLINEAR_FRESH_SOURCE_PREFLIGHT='+json.dumps(result,sort_keys=True))
    if len(cal)<1500: raise RuntimeError(f'insufficient common calendar={len(cal)}')
if __name__=='__main__': main()
