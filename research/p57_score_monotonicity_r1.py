from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES['crossasset'])
BP=50
DELAY=1
WINDOWS={'full':None,'2015_forward':'2015-01-01','2020_forward':'2020-01-01'}


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def build():
    close=base.load(SYMS).sort_index()
    last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=close.resample('ME').last(); m=m.loc[m.index<=cutoff]
    mom=m[list(SYMS)].pct_change(6)
    trend=(close[list(SYMS)]/close[list(SYMS)].rolling(200,min_periods=160).mean()-1).resample('ME').last().reindex(m.index)
    idx=close.index; prev={s:0. for s in SYMS}; rows=[]
    for i,dt in enumerate(m.index[:-1]):
        if i<6: continue
        b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)]},index=list(SYMS))
        if b.isna().any().any(): continue
        score=b.rank(axis=0,pct=True,method='average').mean(axis=1)
        nxt=m.index[i+1]
        a=idx.get_indexer([dt],method='pad')[0]+DELAY; z=idx.get_indexer([nxt],method='pad')[0]+DELAY
        if min(a,z)<0 or max(a,z)>=len(idx): continue
        r=close.iloc[z][list(SYMS)]/close.iloc[a][list(SYMS)]-1
        if r.isna().any(): continue
        rank_ic=float(score.rank(method='average').corr(r.rank(method='average')))
        chosen=list(score.sort_values(ascending=False).head(2).index)
        rest=[s for s in SYMS if s not in chosen]
        selected=float(r[chosen].mean()); nonselected=float(r[rest].mean()); ew=float(r.mean())
        w={s:(.5 if s in chosen else 0.) for s in SYMS}
        turnover=.5*sum(abs(w[s]-prev[s]) for s in SYMS); prev=w
        net=selected-turnover*BP/10000
        rows.append({'date':idx[z],'rank_ic':rank_ic,'selected':selected,'nonselected':nonselected,'selected_minus_nonselected':selected-nonselected,'net':net,'ew':ew})
    return pd.DataFrame(rows).set_index('date'),close,cutoff


def evaluate(q):
    n=len(q)
    folds=[]
    for i,ids in enumerate(np.array_split(np.arange(n),5),1):
        x=q.iloc[ids]
        folds.append({'fold':i,'mean_rank_ic':float(x.rank_ic.mean()),'selected_minus_nonselected_mean':float(x.selected_minus_nonselected.mean()),'after_cost_excess_cagr':cagr(x.net)-cagr(x.ew)})
    return {'months':n,'mean_rank_ic':float(q.rank_ic.mean()),'median_rank_ic':float(q.rank_ic.median()),'positive_rank_ic_fraction':float((q.rank_ic>0).mean()),'selected_minus_nonselected_mean':float(q.selected_minus_nonselected.mean()),'after_cost_candidate_cagr':cagr(q.net),'matched_ew_cagr':cagr(q.ew),'after_cost_excess_cagr':cagr(q.net)-cagr(q.ew),'positive_ic_folds':sum(f['mean_rank_ic']>0 for f in folds),'positive_spread_folds':sum(f['selected_minus_nonselected_mean']>0 for f in folds),'positive_after_cost_folds':sum(f['after_cost_excess_cagr']>0 for f in folds),'folds':folds}


def main():
    q,close,cutoff=build()
    out={'schema':'research.p57_score_monotonicity_r1','parent':'P57','hypothesis':'If P57 has a genuine cross-sectional selection mechanism rather than only a portfolio-path artifact, the frozen momentum+trend score should rank next-month returns positively and the selected top-2 should outperform the nonselected assets while retaining after-cost excess versus equal weight.','scientific_contract':{'universe':list(SYMS),'factors':['mom6','trend200'],'top_k':2,'execution_delay_trading_days':DELAY,'cost_bps':BP,'matched_control':'same-universe equal weight over identical one-day-delayed intervals','mechanism_tests':['cross-sectional Spearman rank IC','selected top-2 minus nonselected return spread','after-cost top-2 versus equal weight'],'windows':WINDOWS,'chronological_folds':5,'complete_months_only':True,'no_parameter_tuning':True},'windows':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':base.source_hash(close),'last_complete_month_end':str(cutoff.date())}}
    for name,start in WINDOWS.items():
        z=q if start is None else q.loc[pd.Timestamp(start):]
        out['windows'][name]=evaluate(z)
    t=out['windows']['2020_forward']
    out['decision']='P57_SCORE_MECHANISM_SUPPORTED' if t['mean_rank_ic']>0 and t['selected_minus_nonselected_mean']>0 and t['positive_ic_folds']>=3 and t['positive_spread_folds']>=3 else 'P57_SCORE_MECHANISM_WEAK'
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p57_score_monotonicity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))


if __name__=='__main__': main()
