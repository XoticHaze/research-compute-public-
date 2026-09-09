from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p66_combination_serial_persistence_r1 as p66

def cagr(x):
    x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1) if len(x) else float('nan')

def main():
    out={'schema':'research.p64_recent_holdout_r1','parent':'P64','scientific_contract':{'candidate':'unchanged fixed 50/50 parsimonious cross-asset + independent-industry blend','start':'2022-01-01','costs_bps':[25,50,100],'comparators':['exact matched static blend','QQQ'],'chronological_folds':5,'no_parameter_or_weight_tuning':True},'tests':{}}
    for bp in (25,50,100):
        fr,_=p66.frame(bp); fr=fr.loc[fr.index>=pd.Timestamp('2022-01-01')].copy(); folds=[]
        for i,ids in enumerate(np.array_split(np.arange(len(fr)),5),1):
            q=fr.iloc[ids]
            folds.append({'fold':i,'start':str(q.index.min().date()),'end':str(q.index.max().date()),'excess_vs_matched':cagr(q.candidate)-cagr(q.matched),'excess_vs_qqq':cagr(q.candidate)-cagr(q.qqq)})
        out['tests'][str(bp)]={'months':len(fr),'candidate_cagr':cagr(fr.candidate),'matched_cagr':cagr(fr.matched),'qqq_cagr':cagr(fr.qqq),'excess_vs_matched':cagr(fr.candidate)-cagr(fr.matched),'excess_vs_qqq':cagr(fr.candidate)-cagr(fr.qqq),'positive_folds_vs_matched':sum(x['excess_vs_matched']>0 for x in folds),'positive_folds_vs_qqq':sum(x['excess_vs_qqq']>0 for x in folds),'folds':folds}
    p=out['tests']['50']; out['decision']='P64_RECENT_HOLDOUT_SUPPORTED' if p['excess_vs_matched']>0 and p['positive_folds_vs_matched']>=3 else 'P64_RECENT_HOLDOUT_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_recent_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
