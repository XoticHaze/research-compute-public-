from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

KNOWN={'random_null':'97c4e1fbc057c23def7dc3d834efe30d9e1029d1545f52ab520c5a8a7018f9dc','signal_lag':'a3ff060452750539be2a01ec64cb1599e890503bdfe68bc8c1ad2bc81f6eb385'}

def pull():
    close=base.load(p46.SYMBOLS); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms].sort_index().sort_index(axis=1)
    return close,base.source_hash(close)

def main():
    pulls=[]; first=None
    for i in range(6):
        close,h=pull();
        if first is None: first=close
        pulls.append({'repeat':i+1,'hash':h,'shape':[int(close.shape[0]),int(close.shape[1])],'na_cells':int(close.isna().sum().sum()),'matches_known':[k for k,v in KNOWN.items() if v==h]})
    hashes=[x['hash'] for x in pulls]; current=hashes[0]
    out={'schema':'research.p46_source_repeatability_r1','parent':'P46','scientific_contract':{'same_exact_complete_month_source_request_repeats':6,'known_same_firing_panel_hashes':KNOWN,'no_model_mutation':True},'pulls':pulls,'unique_hashes_within_execution':len(set(hashes)),'current_hash':current,'matches_prior_same_firing_hashes':[k for k,v in KNOWN.items() if v==current],'cross_execution_hash_conflict':len(set(list(KNOWN.values())+[current]))>1,'decision':'P46_SOURCE_REPEATABLE_WITHIN_RUN_BUT_CROSS_EXECUTION_CHANGED' if len(set(hashes))==1 and current not in KNOWN.values() else ('P46_SOURCE_REPEATABLE_AND_MATCHES_PRIOR' if len(set(hashes))==1 else 'P46_SOURCE_NOT_REPEATABLE_WITHIN_RUN')}
    Path('artifacts').mkdir(exist_ok=True); first.to_csv('artifacts/p46_adjusted_close_snapshot.csv',date_format='%Y-%m-%d',float_format='%.12g'); Path('artifacts/p46_source_repeatability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
