from __future__ import annotations
import json
from pathlib import Path
import numpy as np


def cagr(vals):
    x=np.asarray(vals,float)
    return float(np.prod(1+x)**(12/len(x))-1) if len(x) else float('nan')


def summary(rows, mask):
    idx=np.asarray(mask,bool)
    cand=np.asarray([r['candidate_net_50bp'] for r in rows],float)[idx]
    ew=np.asarray([r['equal_weight'] for r in rows],float)[idx]
    smh=np.asarray([r['smh'] for r in rows],float)[idx]
    qqq=np.asarray([r['qqq'] for r in rows],float)[idx]
    return {
        'months':int(idx.sum()),
        'candidate_cagr':cagr(cand),
        'equal_weight_cagr':cagr(ew),
        'smh_cagr':cagr(smh),
        'qqq_cagr':cagr(qqq),
        'excess_vs_equal_weight_cagr':cagr(cand)-cagr(ew),
        'excess_vs_smh_cagr':cagr(cand)-cagr(smh),
        'excess_vs_qqq_cagr':cagr(cand)-cagr(qqq),
        'mean_monthly_excess_vs_equal_weight':float(np.mean(cand-ew)),
        'mean_monthly_excess_vs_smh':float(np.mean(cand-smh)),
    }


def main():
    src=json.loads(Path('input/p13_frozen_contract_replay_r1.json').read_text())
    rows=src['monthly_records']
    years=np.asarray([int(r['signal_date'][:4]) for r in rows])
    smh=np.asarray([r['smh'] for r in rows],float)
    qqq=np.asarray([r['qqq'] for r in rows],float)
    allmask=np.ones(len(rows),dtype=bool)

    regimes={
        'smh_nonpositive_realized_month': summary(rows, smh<=0),
        'smh_positive_realized_month': summary(rows, smh>0),
        'qqq_nonpositive_realized_month': summary(rows, qqq<=0),
        'qqq_positive_realized_month': summary(rows, qqq>0),
    }

    loyo={}
    for y in sorted(set(years.tolist())):
        mask=years!=y
        loyo[str(y)]=summary(rows,mask)
    loyo_ew=np.asarray([v['excess_vs_equal_weight_cagr'] for v in loyo.values()],float)
    loyo_smh=np.asarray([v['excess_vs_smh_cagr'] for v in loyo.values()],float)

    per_year={}
    for y in sorted(set(years.tolist())):
        per_year[str(y)]=summary(rows,years==y)

    full=summary(rows,allmask)
    downside_weak=(regimes['smh_nonpositive_realized_month']['mean_monthly_excess_vs_equal_weight']<=0)
    loyo_unstable=(float((loyo_ew>0).mean())<0.8 or float(loyo_ew.min())<=0)
    state='P13_REGIME_OR_YEAR_CONCENTRATED' if (downside_weak or loyo_unstable) else 'P13_REGIME_LOYO_ROBUST'
    out={
        'schema':'research.p13_immutable_regime_loyo_r5',
        'parent':'P13',
        'hypothesis':'P13 matched-universe after-cost alpha is not merely concentrated in positive semiconductor-market months or a small set of calendar years.',
        'scientific_contract':{
            'source_run_id':34325797529,
            'source_artifact_id':10093700209,
            'selection_return_fingerprint_sha256':src['selection_return_fingerprint_sha256'],
            'candidate_cost_bps':50,
            'regime_attribution_only_not_a_trading_filter':True,
            'realized_regime_fields':['SMH monthly return sign','QQQ monthly return sign'],
            'leave_one_calendar_year_out':True,
            'no_market_data_redownload':True,
            'no_parameter_or_regime_tuning':True,
        },
        'full':full,
        'regimes':regimes,
        'per_year':per_year,
        'leave_one_year_out':loyo,
        'loyo_summary':{
            'years':len(loyo),
            'positive_fraction_vs_equal_weight':float((loyo_ew>0).mean()),
            'worst_excess_vs_equal_weight_cagr':float(loyo_ew.min()),
            'median_excess_vs_equal_weight_cagr':float(np.median(loyo_ew)),
            'positive_fraction_vs_smh':float((loyo_smh>0).mean()),
            'worst_excess_vs_smh_cagr':float(loyo_smh.min()),
        },
        'decision':state,
        'interpretation_rule':'Realized market-sign groups are ex-post attribution only. A conditional result cannot be converted into an executable regime filter without a separate prior-observable specification and new holdout.',
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p13_immutable_regime_loyo_r5.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__':
    main()
