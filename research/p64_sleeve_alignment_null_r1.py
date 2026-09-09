from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p57_crossasset_parsimonious_r1 as p57
import p47_deep_robustness_r2 as p47

IND=("SOXX","XBI","XHB","KRE","ITA","IGV","IYT","XRT","XOP","IHI")
FACTORS=("mom6","trend200")
BP=50
N=2000
WINDOWS={'full':None,'2015_forward':'2015-01-01','2022_forward':'2022-01-01'}

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); m=base.metrics(r)
    return {'cagr':m['cagr'],'max_drawdown':m['max_drawdown_monthly'],'annualized_vol':m['annualized_vol'],'sharpe_rf0':m['sharpe_rf0']}

def prepare():
    cross,cclose=p57.run(0); ind,iclose=p47.run(IND,FACTORS,0)
    idx=cross.index.intersection(ind.index)
    f=pd.DataFrame(index=idx)
    f['cross']=cross.loc[idx].gross-cross.loc[idx].turnover*BP/10000
    f['cross_matched']=cross.loc[idx].ew
    f['industry']=ind.loc[idx].gross-ind.loc[idx].turnover*BP/10000
    f['industry_matched']=ind.loc[idx].ew
    q=cclose[['QQQ']].resample('ME').last().pct_change().reindex(idx)
    f['qqq']=q['QQQ']
    return f,cclose,iclose

def evaluate(q,seed):
    q=q.dropna().copy(); actual=.5*q.cross+.5*q.industry; matched=.5*q.cross_matched+.5*q.industry_matched
    am=metrics(actual); mm=metrics(matched); qm=metrics(q.qqq)
    rng=np.random.default_rng(seed); n=len(q); shifts=rng.integers(1,n,size=N)
    null_cagr=[]; null_mdd=[]; null_excess=[]
    ia=q.industry.to_numpy(); im=q.industry_matched.to_numpy(); cr=q.cross.to_numpy(); cm=q.cross_matched.to_numpy()
    for s in shifts:
        cand=.5*cr+.5*np.roll(ia,int(s)); ctrl=.5*cm+.5*np.roll(im,int(s))
        x=metrics(cand); y=metrics(ctrl)
        null_cagr.append(x['cagr']); null_mdd.append(x['max_drawdown']); null_excess.append(x['cagr']-y['cagr'])
    nc=np.asarray(null_cagr); nd=np.asarray(null_mdd); ne=np.asarray(null_excess)
    actual_excess=am['cagr']-mm['cagr']
    return {'months':n,'start':str(q.index.min().date()),'end':str(q.index.max().date()),'actual_candidate':am,'matched_control':mm,'qqq':qm,'actual_excess_vs_matched':actual_excess,'actual_excess_vs_qqq':am['cagr']-qm['cagr'],'actual_sleeve_return_correlation':float(q.cross.corr(q.industry)),'null':{'replications':N,'construction':'random non-zero circular shifts of industry sleeve and its matched control; preserves each sleeve sequence/distribution while breaking contemporaneous alignment','candidate_cagr_5_50_95_pct':[float(np.quantile(nc,x)) for x in (.05,.5,.95)],'excess_vs_matched_5_50_95_pct':[float(np.quantile(ne,x)) for x in (.05,.5,.95)],'max_drawdown_5_50_95_pct':[float(np.quantile(nd,x)) for x in (.05,.5,.95)],'p_null_excess_ge_actual':float(np.mean(ne>=actual_excess)),'p_null_drawdown_less_severe_or_equal_actual':float(np.mean(nd>=am['max_drawdown'])),'actual_excess_percentile':float(np.mean(ne<=actual_excess)),'actual_drawdown_percentile_by_severity':float(np.mean(nd<=am['max_drawdown']))}}

def main():
    f,cc,ic=prepare(); out={'schema':'research.p64_sleeve_alignment_null_r1','parent':'P64','hypothesis':'P64 diversification benefit depends on genuine contemporaneous complementarity between its frozen cross-asset and independent-industry sleeves rather than arbitrary averaging of two return streams.','scientific_contract':{'component_cost_bps':BP,'sleeve_weights':[0.5,0.5],'null_replications':N,'matched_control':'50% crossasset EW + 50% independent-industry EW with the same circular shift applied to industry control','opportunity_control':'QQQ','windows':WINDOWS,'no_signal_factor_weight_or_parameter_tuning':True},'tests':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','cross_panel_sha256':base.source_hash(cc),'industry_panel_sha256':base.source_hash(ic)}}
    for i,(name,start) in enumerate(WINDOWS.items(),1): out['tests'][name]=evaluate(f if start is None else f.loc[pd.Timestamp(start):],6400+i)
    r=out['tests']['2022_forward']; out['decision']='P64_COMPLEMENTARITY_SUPPORTED' if r['actual_excess_vs_matched']>0 and r['actual_excess_vs_qqq']>0 and r['null']['actual_excess_percentile']>=.9 else 'P64_COMPLEMENTARITY_NOT_DISTINCT_FROM_ALIGNMENT_NULL'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_sleeve_alignment_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
