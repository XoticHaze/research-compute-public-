from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

BP=50

def cagr(x):
    x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)
def evaluate(close):
    a=p46.returns(close,p46.FACTORS); net=a.gross-a.turnover*(BP/10000); active=net-a.ew
    blob=pd.DataFrame({'net':net,'ew':a.ew,'turnover':a.turnover}).to_csv(date_format='%Y-%m-%d',float_format='%.12g').encode()
    out={'return_fingerprint':hashlib.sha256(blob).hexdigest(),'full':{'months':int(net.notna().sum()),'candidate_cagr':cagr(net),'equal_weight_cagr':cagr(a.ew),'excess_cagr':cagr(net)-cagr(a.ew),'mean_monthly_active':float(active.mean())}}
    ix=net.index>=pd.Timestamp('2022-01-01'); out['2022_forward']={'months':int(net[ix].notna().sum()),'candidate_cagr':cagr(net[ix]),'equal_weight_cagr':cagr(a.ew[ix]),'excess_cagr':cagr(net[ix])-cagr(a.ew[ix]),'mean_monthly_active':float(active[ix].mean())}
    return out

def main():
    pulls=[]
    for i in range(6):
        close=base.load(p46.SYMBOLS); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms].sort_index().sort_index(axis=1)
        pulls.append({'repeat':i+1,'panel_hash':base.source_hash(close),'economics':evaluate(close)})
    full=[x['economics']['full']['excess_cagr'] for x in pulls]; recent=[x['economics']['2022_forward']['excess_cagr'] for x in pulls]; fps=[x['economics']['return_fingerprint'] for x in pulls]
    material=(max(full)-min(full)>0.001) or (max(recent)-min(recent)>0.001) or len(set(fps))>1
    out={'schema':'research.p46_economic_repeatability_r1','parent':'P46','scientific_contract':{'model':'unchanged fixed four-factor top-2 selector','matched_control':'same-universe equal weight','cost_bps':BP,'identical_source_pull_repeats':6,'material_excess_cagr_tolerance':0.001,'no_parameter_or_weight_tuning':True},'pulls':pulls,'unique_panel_hashes':len(set(x['panel_hash'] for x in pulls)),'unique_return_fingerprints':len(set(fps)),'full_excess_cagr_range':[min(full),max(full)],'recent_excess_cagr_range':[min(recent),max(recent)],'decision':'P46_MUTABLE_SOURCE_ECONOMICALLY_UNSTABLE' if material else 'P46_HASH_DRIFT_ECONOMICALLY_IMMATERIAL_WITHIN_TEST'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_economic_repeatability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
