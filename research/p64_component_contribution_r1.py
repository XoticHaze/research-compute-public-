from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p57_crossasset_parsimonious_r1 as p57
import p47_deep_robustness_r2 as p47

IND=("SOXX","XBI","XHB","KRE","ITA","IGV","IYT","XRT","XOP","IHI")
FACTORS=("mom6","trend200"); BP=50
WINDOWS={'full':None,'2015_forward':'2015-01-01','2020_forward':'2020-01-01','2022_forward':'2022-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def mdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); return float((e/e.cummax()-1).min()) if len(e) else float('nan')
def folds(a,b):
    vals=[]
    for i,ids in enumerate(np.array_split(np.arange(len(a)),5),1):
        x=a.iloc[ids]; y=b.iloc[ids]; vals.append({'fold':i,'excess_cagr':cagr(x)-cagr(y)})
    return vals

def build():
    cross,cc=p57.run(0); ind,ic=p47.run(IND,FACTORS,0)
    last=min(pd.Timestamp(cc.index.max()).tz_localize(None) if pd.Timestamp(cc.index.max()).tzinfo else pd.Timestamp(cc.index.max()),pd.Timestamp(ic.index.max()).tz_localize(None) if pd.Timestamp(ic.index.max()).tzinfo else pd.Timestamp(ic.index.max()))
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    cross=cross.loc[cross.index<=cutoff]; ind=ind.loc[ind.index<=cutoff]; idx=cross.index.intersection(ind.index)
    f=pd.DataFrame(index=idx); f['cross']=cross.loc[idx].gross-cross.loc[idx].turnover*BP/10000; f['cross_ctrl']=cross.loc[idx].ew; f['industry']=ind.loc[idx].gross-ind.loc[idx].turnover*BP/10000; f['industry_ctrl']=ind.loc[idx].ew
    q=cc[['QQQ']].resample('ME').last().pct_change().reindex(idx); f['qqq']=q.QQQ
    return f,cc,ic,cutoff

def eval(q):
    blend=.5*q.cross+.5*q.industry; ctrl=.5*q.cross_ctrl+.5*q.industry_ctrl
    cx=q.cross-q.cross_ctrl; ix=q.industry-q.industry_ctrl; bf=folds(blend,ctrl)
    return {'months':len(q),'blend_cagr':cagr(blend),'matched_cagr':cagr(ctrl),'qqq_cagr':cagr(q.qqq),'blend_excess_vs_matched':cagr(blend)-cagr(ctrl),'blend_excess_vs_qqq':cagr(blend)-cagr(q.qqq),'blend_mdd':mdd(blend),'matched_mdd':mdd(ctrl),'cross_sleeve_excess_cagr':cagr(q.cross)-cagr(q.cross_ctrl),'industry_sleeve_excess_cagr':cagr(q.industry)-cagr(q.industry_ctrl),'cross_sleeve_cagr':cagr(q.cross),'industry_sleeve_cagr':cagr(q.industry),'cross_excess_annualized_mean':float(cx.mean()*12),'industry_excess_annualized_mean':float(ix.mean()*12),'excess_stream_correlation':float(cx.corr(ix)),'opposite_sign_excess_fraction':float(((cx*ix)<0).mean()),'positive_blend_folds':sum(x['excess_cagr']>0 for x in bf),'blend_folds':bf}

def main():
    f,cc,ic,cutoff=build(); out={'schema':'research.p64_component_contribution_r1','parent':'P64','hypothesis':'P64 recent matched alpha is contributed by both frozen sleeves rather than being an averaging artifact carried by only one sleeve.','scientific_contract':{'component_cost_bps':BP,'sleeve_weights':[.5,.5],'crossasset':'P57 frozen momentum+trend top-2','industry':'independent industry momentum+trend top-3','matched_control':'50% crossasset EW + 50% industry EW','opportunity_control':'QQQ','windows':WINDOWS,'chronological_folds':5,'complete_months_only':True,'no_parameter_tuning':True},'tests':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','cross_panel_sha256':base.source_hash(cc),'industry_panel_sha256':base.source_hash(ic),'last_complete_month_end':str(cutoff.date())}}
    for name,start in WINDOWS.items(): out['tests'][name]=eval(f if start is None else f.loc[pd.Timestamp(start):])
    r=out['tests']['2022_forward']; out['decision']='P64_BOTH_SLEEVES_CONTRIBUTE_RECENT_ALPHA' if r['cross_sleeve_excess_cagr']>0 and r['industry_sleeve_excess_cagr']>0 else 'P64_RECENT_ALPHA_SLEEVE_CONCENTRATED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_component_contribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
