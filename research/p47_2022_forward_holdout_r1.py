from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p47_temporal_factor_discriminators_r1 as p47

def main():
    close=base.load(p47.SYMBOLS); full=p47.rets(close,p47.FACTORS); f=full.loc[pd.Timestamp('2022-01-01'):]
    tests={str(b):p47.score(f,b) for b in (25,50,100)}
    for bps in (25,50,100):
        net=f.gross-f.turnover*bps/10000
        cm=base.metrics(net)
        for sym in ('SPY','QQQ'):
            monthly=close[sym].resample('ME').last().pct_change().reindex(f.index)
            bm=base.metrics(monthly)
            tests[str(bps)][sym]={'cagr':bm['cagr'],'excess_cagr':cm['cagr']-bm['cagr']}
    t25=tests['25']; t50=tests['50']; t100=tests['100']; fold_n=len(t50['folds']) if isinstance(t50['folds'],list) else int(t50['folds'])
    supported=t50['excess_cagr']>0 and t100['excess_cagr']>0 and t50['positive_folds']>=max(2,(fold_n+1)//2)
    out={'schema':'research.p47_2022_forward_holdout_r1','parent':'P47','scientific_contract':{'economics':'unchanged four-factor industry top-3 monthly composite','holdout':'2022-forward','costs_bps':[25,50,100],'matched_comparator':'same-universe equal weight','opportunity_cost_controls':['SPY','QQQ'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P47_RECENT_HOLDOUT_SUPPORTED' if supported else 'P47_RECENT_HOLDOUT_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p47_2022_forward_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print('P47_2022_FORWARD='+json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
