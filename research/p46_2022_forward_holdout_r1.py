from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

def main():
    close=base.load(p46.SYMBOLS); full=p46.returns(close,p46.FACTORS); f=full.loc[pd.Timestamp('2022-01-01'):]
    tests={str(b):p46.score(f,b) for b in (25,50,100)}
    c25=tests['25']; c50=tests['50']; c100=tests['100']; fold_n=len(c50['folds']) if isinstance(c50['folds'],list) else int(c50['folds'])
    out={'schema':'research.p46_2022_forward_holdout_r1','parent':'P46','scientific_contract':{'economics':'unchanged four-factor crossasset top-2 monthly composite','holdout':'2022-forward','costs_bps':[25,50,100],'matched_comparator':'same-universe equal weight','opportunity_cost_controls':['SPY','QQQ'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P46_RECENT_HOLDOUT_SUPPORTED' if c50['excess_cagr']>0 and c100['excess_cagr']>0 and c50['positive_folds']>=max(2,(fold_n+1)//2) else 'P46_RECENT_HOLDOUT_REQUIRES_CAUTION'}
    for bps in (25,50,100):
        net=f.gross-f.turnover*bps/10000
        for sym in ('SPY','QQQ'):
            monthly=close[sym].resample('ME').last().pct_change().reindex(f.index)
            cm=base.metrics(net); bm=base.metrics(monthly)
            out['tests'][str(bps)][sym]={'cagr':bm['cagr'],'excess_cagr':cm['cagr']-bm['cagr']}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_2022_forward_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print('P46_2022_FORWARD='+json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
