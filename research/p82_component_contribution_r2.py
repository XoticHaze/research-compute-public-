from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import p82_p64_p36_fixed_blend_r1 as p82
import p66_combination_serial_persistence_r1 as p66

BP=50; WINDOWS={'pre2015':('2005-01-01','2014-12-31'),'2015_forward':('2015-01-01',None),'2022_forward':('2022-01-01',None)}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def mdd(r):
    e=(1+pd.Series(r,dtype=float).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def build():
    p64,_=p66.frame(BP); p36,_=p82.p36_frame()
    a=p64[['candidate','matched']].copy(); a.index=a.index.to_period('M'); a.columns=['p64','p64_matched']
    b=p36[['p36','p36_matched','qqq']].copy(); b.index=b.index.to_period('M')
    f=a.join(b,how='inner'); f.index=f.index.to_timestamp('M')
    f['blend']=0.5*f.p64+0.5*f.p36; f['blend_matched']=0.5*f.p64_matched+0.5*f.p36_matched
    return f

def stats(q):
    blend_vs_q=cagr(q.blend)-cagr(q.qqq); p64_vs_q=cagr(q.p64)-cagr(q.qqq); p36_vs_q=cagr(q.p36)-cagr(q.qqq)
    p64_ex=q.p64-q.p64_matched; p36_ex=q.p36-q.p36_matched
    return {'months':len(q),'blend_cagr':cagr(q.blend),'blend_matched_cagr':cagr(q.blend_matched),'qqq_cagr':cagr(q.qqq),'p64_cagr':cagr(q.p64),'p36_cagr':cagr(q.p36),'blend_excess_vs_matched_cagr':cagr(q.blend)-cagr(q.blend_matched),'blend_excess_vs_qqq_cagr':blend_vs_q,'p64_excess_vs_qqq_cagr':p64_vs_q,'p36_excess_vs_qqq_cagr':p36_vs_q,'blend_mdd':mdd(q.blend),'qqq_mdd':mdd(q.qqq),'p64_mdd':mdd(q.p64),'p36_mdd':mdd(q.p36),'monthly_excess_correlation':float(p64_ex.corr(p36_ex)),'p64_mean_monthly_matched_excess':float(p64_ex.mean()),'p36_mean_monthly_matched_excess':float(p36_ex.mean()),'both_positive_month_fraction':float(((p64_ex>0)&(p36_ex>0)).mean()),'opposite_sign_month_fraction':float(((p64_ex*p36_ex)<0).mean())}

def main():
    f=build(); out={}
    for name,(start,end) in WINDOWS.items():
        q=f.loc[f.index>=pd.Timestamp(start)]
        if end: q=q.loc[q.index<=pd.Timestamp(end)]
        s=stats(q); folds=[]
        for i,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
            z=q.iloc[ids]
            if len(z): folds.append({'fold':i,'blend_vs_qqq':cagr(z.blend)-cagr(z.qqq),'blend_vs_matched':cagr(z.blend)-cagr(z.blend_matched),'p64_vs_qqq':cagr(z.p64)-cagr(z.qqq),'p36_vs_qqq':cagr(z.p36)-cagr(z.qqq)})
        s['positive_folds_blend_vs_qqq']=sum(x['blend_vs_qqq']>0 for x in folds); s['positive_folds_blend_vs_matched']=sum(x['blend_vs_matched']>0 for x in folds); s['folds']=folds; out[name]=s
    recent=out['2022_forward']; complementary=recent['blend_excess_vs_qqq_cagr']>0 and recent['positive_folds_blend_vs_qqq']>=3 and recent['opposite_sign_month_fraction']>=0.25 and recent['monthly_excess_correlation']<0.75
    result={'schema':'research.p82_component_contribution_r2','parent':'P82','scientific_contract':{'components':'unchanged P64 plus P36 SOXX 1-day, each at 50 bps','blend_weights':[0.5,0.5],'windows':WINDOWS,'matched_control':'same fixed component matched controls','opportunity_control':'QQQ','purpose':'attribute pre/post-2015 QQQ opportunity-cost change and test sleeve complementarity without retuning','no_parameter_or_weight_tuning':True},'tests':out,'decision':'P82_COMPONENT_COMPLEMENTARITY_SUPPORTED' if complementary else 'P82_COMPONENT_COMPLEMENTARITY_WEAK'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p82_component_contribution_r2.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
