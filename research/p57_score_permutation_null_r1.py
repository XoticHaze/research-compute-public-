from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES['crossasset'])
DELAY=1
START=pd.Timestamp('2020-01-01')
N=2000
SEED=570012


def build():
    close=base.load(SYMS).sort_index(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=close.resample('ME').last(); m=m.loc[m.index<=cutoff]
    mom=m[list(SYMS)].pct_change(6); trend=(close[list(SYMS)]/close[list(SYMS)].rolling(200,min_periods=160).mean()-1).resample('ME').last().reindex(m.index)
    idx=close.index; rows=[]
    for i,dt in enumerate(m.index[:-1]):
        if i<6: continue
        b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)]},index=list(SYMS))
        if b.isna().any().any(): continue
        score=b.rank(axis=0,pct=True,method='average').mean(axis=1); nxt=m.index[i+1]
        a=idx.get_indexer([dt],method='pad')[0]+DELAY; z=idx.get_indexer([nxt],method='pad')[0]+DELAY
        if min(a,z)<0 or max(a,z)>=len(idx): continue
        r=close.iloc[z][list(SYMS)]/close.iloc[a][list(SYMS)]-1
        if r.isna().any() or idx[z] < START: continue
        rows.append((idx[z],score.to_numpy(float),r.to_numpy(float)))
    return rows,close,cutoff


def stats(rows,perm=None):
    ics=[]; spreads=[]
    for j,(_,s,r) in enumerate(rows):
        q=s if perm is None else s[perm[j]]
        sr=pd.Series(q).rank(method='average'); rr=pd.Series(r).rank(method='average')
        ics.append(float(sr.corr(rr)))
        top=np.argsort(q)[-2:]; rest=np.array([k for k in range(len(q)) if k not in set(top)])
        spreads.append(float(r[top].mean()-r[rest].mean()))
    return float(np.mean(ics)),float(np.mean(spreads))


def main():
    rows,close,cutoff=build(); obs_ic,obs_spread=stats(rows); rng=np.random.default_rng(SEED)
    null_ic=[]; null_spread=[]
    for _ in range(N):
        perms=[rng.permutation(len(SYMS)) for _ in rows]; a,b=stats(rows,perms); null_ic.append(a); null_spread.append(b)
    ni=np.array(null_ic); ns=np.array(null_spread)
    out={'schema':'research.p57_score_permutation_null_r1','parent':'P57','hypothesis':'If P57 recent-era cross-sectional information is tied to the frozen score-to-asset mapping, random within-month reassignment of that score should rarely match the observed rank IC and selected-minus-nonselected spread.','scientific_contract':{'universe':list(SYMS),'factors':['mom6','trend200'],'top_k':2,'execution_delay_trading_days':DELAY,'window_start':'2020-01-01','null':'within-month score-label permutation preserving each month and realized asset returns','replications':N,'seed':SEED,'no_parameter_tuning':True},'months':len(rows),'observed':{'mean_rank_ic':obs_ic,'selected_minus_nonselected_mean':obs_spread},'null':{'mean_rank_ic_mean':float(ni.mean()),'mean_rank_ic_p95':float(np.quantile(ni,.95)),'p_null_ge_observed_ic':float(np.mean(ni>=obs_ic)),'spread_mean':float(ns.mean()),'spread_p95':float(np.quantile(ns,.95)),'p_null_ge_observed_spread':float(np.mean(ns>=obs_spread))},'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':base.source_hash(close),'last_complete_month_end':str(cutoff.date())}}
    out['decision']='P57_SCORE_MAPPING_NULL_REJECTED' if out['null']['p_null_ge_observed_ic']<=.05 and out['null']['p_null_ge_observed_spread']<=.05 else 'P57_SCORE_MAPPING_NOT_DISTINCT_FROM_NULL'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p57_score_permutation_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
