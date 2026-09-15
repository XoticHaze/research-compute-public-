from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import research.semiconductor_path_head_predictability_20260905 as ph

OUT = Path('semiconductor_mfe_breadth_audit_20260905.json')
TARGET = 'mfe20_bps'


def metric(pred, truth, baseline):
    pred=np.asarray(pred,float); truth=np.asarray(truth,float); baseline=np.asarray(baseline,float)
    return {
        'rows': int(len(truth)),
        'spearman': ph.sp(pred, truth),
        'mae': float(np.mean(np.abs(pred-truth))),
        'median_baseline_mae': float(np.mean(np.abs(baseline-truth))),
        'mae_improvement_vs_median': float(np.mean(np.abs(baseline-truth))-np.mean(np.abs(pred-truth))),
    }


def main():
    base=ph.base
    symbols=(*base.TRAIN,*base.CONTEXT)
    raw={s:base.load(s) for s in symbols}
    cutoff=min(d.iloc[-1].timestamp for d in raw.values())
    sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]
    cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    old=base.FRESH;base.FRESH=()
    try:data=base.engineer(prices,cal)
    finally:base.FRESH=old
    folds=base.folds(len(cal)); frame=ph.build_rows(data,prices,cal,folds)

    rows=[]
    for fold in range(2,7):
        start,_=folds[fold-1]; purge=ph.DELAY+ph.HOLD
        train=frame[frame.signal_i<start-purge].copy(); test=frame[frame.fold==fold].copy()
        m=ph.model(); m.fit(train[base.FULL].to_numpy(float),train[TARGET].to_numpy(float))
        pred=m.predict(test[base.FULL].to_numpy(float)); med=float(np.median(train[TARGET]))
        tmp=test[['symbol',TARGET]].copy(); tmp['pred']=pred; tmp['baseline']=med; tmp['fold']=fold
        rows.append(tmp)
    scored=pd.concat(rows,ignore_index=True)

    per_symbol={}
    for symbol in base.TRAIN:
        part=scored[scored.symbol==symbol]
        per_symbol[symbol]=metric(part.pred,part[TARGET],part.baseline)
        per_symbol[symbol]['positive_spearman_folds']=sum(
            (metric(g.pred,g[TARGET],g.baseline)['spearman'] or -1)>0 for _,g in part.groupby('fold')
        )
        per_symbol[symbol]['mae_better_folds']=sum(
            metric(g.pred,g[TARGET],g.baseline)['mae_improvement_vs_median']>0 for _,g in part.groupby('fold')
        )

    loo={}
    for drop in base.TRAIN:
        part=scored[scored.symbol!=drop]
        loo[drop]=metric(part.pred,part[TARGET],part.baseline)

    positive_symbols=sum(int(v['spearman'] is not None and v['spearman']>0) for v in per_symbol.values())
    broad_symbols=sum(int(v['positive_spearman_folds']>=3) for v in per_symbol.values())
    mae_symbols=sum(int(v['mae_improvement_vs_median']>0) for v in per_symbol.values())
    loo_positive=all(v['spearman'] is not None and v['spearman']>0 for v in loo.values())
    decision = 'MFE_SIGNAL_BROAD_ENOUGH_FOR_NEXT_ARCHITECTURE' if positive_symbols>=5 and broad_symbols>=4 and loo_positive else 'MFE_SIGNAL_CONCENTRATED_OR_UNSTABLE'
    out={
        'schema':'public_compute.semiconductor_mfe_breadth_audit.v1',
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_head':'9b20f7caf31ed031bbae0d75651ba0ef026c4c06',
        'development_universe':list(base.TRAIN),
        'target':TARGET,
        'external_panels_loaded':False,
        'per_symbol':per_symbol,
        'leave_one_symbol_out':loo,
        'summary':{
            'positive_spearman_symbols':positive_symbols,
            'symbols_with_positive_spearman_in_at_least_3_folds':broad_symbols,
            'symbols_with_mae_improvement':mae_symbols,
            'all_leave_one_symbol_out_spearman_positive':loo_positive,
        },
        'decision':decision,
        'research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False,
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('SEMICONDUCTOR_MFE_BREADTH='+json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
