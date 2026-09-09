from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p57_crossasset_parsimonious_r1 as p57
import p47_deep_robustness_r2 as p47

IND=("SOXX","XBI","XHB","KRE","ITA","IGV","IYT","XRT","XOP","IHI"); FACTORS=("mom6","trend200"); BP=50

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def build():
    cr,cc=p57.run(0); ir,ic=p47.run(IND,FACTORS,0)
    last=min(pd.Timestamp(cc.index.max()).tz_localize(None) if pd.Timestamp(cc.index.max()).tzinfo else pd.Timestamp(cc.index.max()),pd.Timestamp(ic.index.max()).tz_localize(None) if pd.Timestamp(ic.index.max()).tzinfo else pd.Timestamp(ic.index.max()))
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); cr=cr.loc[cr.index<=cutoff]; ir=ir.loc[ir.index<=cutoff]; idx=cr.index.intersection(ir.index)
    f=pd.DataFrame(index=idx); f['blend']=.5*(cr.loc[idx].gross-cr.loc[idx].turnover*BP/10000)+.5*(ir.loc[idx].gross-ir.loc[idx].turnover*BP/10000)
    qm=cc.QQQ.resample('ME').last(); f['qqq']=qm.pct_change().reindex(idx)
    qtrend=(cc.QQQ/cc.QQQ.rolling(200,min_periods=160).mean()).resample('ME').last().reindex(idx); f['qqq_above_200d']=qtrend>1
    return f,cc,ic,cutoff

def slice_stats(q):
    ex=q.blend-q.qqq
    return {'months':len(q),'blend_cagr':cagr(q.blend),'qqq_cagr':cagr(q.qqq),'excess_cagr_vs_qqq':cagr(q.blend)-cagr(q.qqq),'annualized_mean_relative_return':float(ex.mean()*12)}
def main():
    f,cc,ic,cutoff=build(); tests={}
    for start in ('2015-01-01','2020-01-01','2022-01-01'):
        q=f.loc[pd.Timestamp(start):].dropna(); rows={'all':slice_stats(q),'qqq_above_200d':slice_stats(q[q.qqq_above_200d]),'qqq_below_200d':slice_stats(q[~q.qqq_above_200d])}
        ex=q.blend-q.qqq; strong=ex.nlargest(5).index; rows['remove_five_best_relative_months']=slice_stats(q.loc[~q.index.isin(strong)]); rows['five_best_relative_months']=[str(x.date()) for x in strong]
        tests[start[:4]+'_forward']=rows
    out={'schema':'research.p64_opportunity_cost_regime_r1','parent':'P64','hypothesis':'P64 opportunity-cost weakness versus QQQ is regime-conditional rather than evidence that its matched alpha is economically irrelevant in all states.','scientific_contract':{'component_cost_bps':BP,'sleeve_weights':[.5,.5],'opportunity_control':'QQQ','regime':'QQQ month-end above/below causal trailing 200-session mean','concentration_test':'remove five strongest blend-minus-QQQ months','windows':['2015-forward','2020-forward','2022-forward'],'complete_months_only':True,'no_parameter_tuning':True},'tests':tests,'source':{'provider':'Yahoo Finance via yfinance; research-only','cross_panel_sha256':base.source_hash(cc),'industry_panel_sha256':base.source_hash(ic),'last_complete_month_end':str(cutoff.date())}}
    r=tests['2020_forward']; out['decision']='P64_QQQ_OPPORTUNITY_COST_REGIME_CONDITIONAL' if r['qqq_below_200d']['excess_cagr_vs_qqq']>0 and r['qqq_above_200d']['excess_cagr_vs_qqq']<0 else 'P64_QQQ_OPPORTUNITY_COST_NOT_CLEANLY_REGIME_CONDITIONAL'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_opportunity_cost_regime_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
