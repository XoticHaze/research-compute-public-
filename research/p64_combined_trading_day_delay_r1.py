from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p57_trading_day_delay_r1 as p57
import p52_execution_delay_r1 as p52

DELAYS=(1,2,3,5)
BP=50
WINDOWS={'full':None,'2015_forward':'2015-01-01','2020_forward':'2020-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def mdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); return float((e/e.cummax()-1).min()) if len(e) else float('nan')
def folds(a,b):
    out=[]
    for i,ids in enumerate(np.array_split(np.arange(len(a)),5),1):
        x=a.iloc[ids]; y=b.iloc[ids]; out.append({'fold':i,'excess_cagr':cagr(x)-cagr(y)})
    return out

def qqq_delayed(close, delay):
    close=close.sort_index(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=close.resample('ME').last(); m=m.loc[m.index<=cutoff]; idx=close.index; rec=[]
    for i,dt in enumerate(m.index[:-1]):
        if i<6: continue
        nxt=m.index[i+1]; a=idx.get_indexer([dt],method='pad')[0]+delay; z=idx.get_indexer([nxt],method='pad')[0]+delay
        if a<0 or z<0 or a>=len(idx) or z>=len(idx): continue
        rec.append((idx[z],float(close.QQQ.iloc[z]/close.QQQ.iloc[a]-1)))
    return pd.Series(dict(rec),dtype=float,name='qqq')

def evaluate(q):
    f=folds(q.candidate,q.matched)
    return {'months':len(q),'candidate_cagr':cagr(q.candidate),'matched_cagr':cagr(q.matched),'qqq_cagr':cagr(q.qqq),'excess_cagr_vs_matched':cagr(q.candidate)-cagr(q.matched),'excess_cagr_vs_qqq':cagr(q.candidate)-cagr(q.qqq),'candidate_mdd':mdd(q.candidate),'matched_mdd':mdd(q.matched),'qqq_mdd':mdd(q.qqq),'positive_matched_folds':sum(x['excess_cagr']>0 for x in f),'matched_folds':f}

def main():
    out={'schema':'research.p64_combined_trading_day_delay_r1','parent':'P64','hypothesis':'The fixed 50/50 P64 blend retains after-cost matched alpha and economically acceptable opportunity cost when both frozen sleeves are implemented 1/2/3/5 trading days after month-end signal observation.','scientific_contract':{'cross_sleeve':'P57 frozen momentum+trend top-2','industry_sleeve':'P52 frozen momentum+trend top-3','sleeve_weights':[0.5,0.5],'component_cost_bps':BP,'execution_delays_trading_days':list(DELAYS),'matched_control':'50% crossasset EW + 50% industry EW over identical delayed intervals','opportunity_control':'QQQ over identical delayed intervals','windows':WINDOWS,'chronological_folds':5,'no_parameter_weight_or_delay_tuning':True},'delays':{},'source':{'provider':'Yahoo Finance via yfinance; research-only'}}
    for d in DELAYS:
        cf,cc,_=p57.run(d); inf,ic,_=p52.run(d); idx=cf.index.intersection(inf.index)
        q=pd.DataFrame(index=idx); q['candidate']=.5*(cf.loc[idx].gross-cf.loc[idx].turnover*BP/10000)+.5*(inf.loc[idx].gross-inf.loc[idx].turnover*BP/10000); q['matched']=.5*cf.loc[idx].ew+.5*inf.loc[idx].ew; q['qqq']=qqq_delayed(cc,d).reindex(idx); q=q.dropna()
        out['delays'][str(d)]={}
        for name,start in WINDOWS.items(): out['delays'][str(d)][name]=evaluate(q if start is None else q.loc[pd.Timestamp(start):])
        out['source'][f'cross_panel_sha256_delay_{d}']=p57.base.source_hash(cc); out['source'][f'industry_panel_sha256_delay_{d}']=p52.base.source_hash(ic)
    t=out['delays']['5']['2020_forward']; out['decision']='P64_COMBINED_DELAY_RECENTLY_SUPPORTED' if t['excess_cagr_vs_matched']>0 and t['positive_matched_folds']>=3 and t['excess_cagr_vs_qqq']>=-0.01 else 'P64_COMBINED_DELAY_WEAKNESS'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_combined_trading_day_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
