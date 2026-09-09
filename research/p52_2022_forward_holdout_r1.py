from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p47_deep_robustness_r2 as p47

SYMS=p47.BASE; FACTORS=('mom6','trend200')

def main():
    full,close=p47.run(SYMS,FACTORS,0); f=full.loc[pd.Timestamp('2022-01-01'):]; controls=p47.base.load(('SPY','QQQ')); tests={}
    for bps in (25,50,100):
        s=p47.score(f,bps); net=f.gross-f.turnover*bps/10000; cm=p47.base.metrics(net)
        for sym in ('SPY','QQQ'):
            monthly=controls[sym].resample('ME').last().pct_change().reindex(f.index); bm=p47.base.metrics(monthly); s[sym]={'cagr':bm['cagr'],'excess_cagr':cm['cagr']-bm['cagr']}
        tests[str(bps)]=s
    t50=tests['50']; t100=tests['100']; fold_n=len(t50['folds']) if isinstance(t50['folds'],list) else int(t50['folds']); supported=t50['excess_cagr']>0 and t100['excess_cagr']>0 and t50['positive_folds']>=max(2,(fold_n+1)//2)
    out={'schema':'research.p52_2022_forward_holdout_r1','parent':'P52','scientific_contract':{'economics':'unchanged momentum+trend-only industry top-3 monthly composite','holdout':'2022-forward','costs_bps':[25,50,100],'matched_comparator':'same-industry-universe equal weight','opportunity_cost_controls':['SPY','QQQ'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','industry_panel_sha256':p47.base.source_hash(close),'control_panel_sha256':p47.base.source_hash(controls)},'tests':tests,'decision':'P52_RECENT_HOLDOUT_SUPPORTED' if supported else 'P52_RECENT_HOLDOUT_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p52_2022_forward_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'25':tests['25'],'50':tests['50'],'100':tests['100']},sort_keys=True))
if __name__=='__main__': main()
