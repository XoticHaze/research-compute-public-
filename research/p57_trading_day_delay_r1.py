from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES['crossasset'])
DELAYS=(1,2,3,5)
COSTS=(25,50)
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

def run(delay):
    close=base.load(SYMS).sort_index(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=close.resample('ME').last(); m=m.loc[m.index<=cutoff]
    mom=m[list(SYMS)].pct_change(6)
    trend=(close[list(SYMS)]/close[list(SYMS)].rolling(200,min_periods=160).mean()-1).resample('ME').last().reindex(m.index)
    idx=close.index; prev={s:0. for s in SYMS}; rec=[]
    for i,dt in enumerate(m.index[:-1]):
        if i<6: continue
        b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)]},index=list(SYMS))
        if b.isna().any().any(): continue
        score=b.rank(axis=0,pct=True,method='average').mean(axis=1); nxt=m.index[i+1]
        a=idx.get_indexer([dt],method='pad')[0]+delay; z=idx.get_indexer([nxt],method='pad')[0]+delay
        if a<0 or z<0 or a>=len(idx) or z>=len(idx): continue
        r=close.iloc[z][list(SYMS)]/close.iloc[a][list(SYMS)]-1
        if r.isna().any(): continue
        chosen=list(score.sort_values(ascending=False).head(2).index); w={s:(.5 if s in chosen else 0.) for s in SYMS}
        to=.5*sum(abs(w[s]-prev[s]) for s in SYMS)
        rec.append({'date':idx[z],'gross':sum(w[s]*float(r[s]) for s in SYMS),'ew':float(r.mean()),'turnover':to}); prev=w
    return pd.DataFrame(rec).set_index('date'),close,cutoff

def evaluate(q,bp):
    c=q.gross-q.turnover*bp/10000; b=q.ew; f=folds(c,b)
    return {'months':len(q),'candidate_cagr':cagr(c),'matched_ew_cagr':cagr(b),'excess_cagr':cagr(c)-cagr(b),'candidate_mdd':mdd(c),'matched_mdd':mdd(b),'positive_folds':sum(x['excess_cagr']>0 for x in f),'folds':f}

def main():
    out={'schema':'research.p57_trading_day_delay_r1','parent':'P57','hypothesis':'The frozen parsimonious cross-asset momentum+trend top-2 allocator retains after-cost matched alpha when implementation occurs 1/2/3/5 trading days after month-end signal observation.','scientific_contract':{'universe':list(SYMS),'factors':['mom6','trend200'],'top_k':2,'execution_delays_trading_days':list(DELAYS),'costs_bps':list(COSTS),'matched_control':'same-universe equal weight over identical delayed holding intervals','windows':WINDOWS,'chronological_folds':5,'complete_months_only':True,'no_parameter_tuning':True},'delays':{},'source':{'provider':'Yahoo Finance via yfinance; research-only'}}
    hashes={}; cutoffs={}
    for d in DELAYS:
        f,close,cutoff=run(d); hashes[str(d)]=base.source_hash(close); cutoffs[str(d)]=str(cutoff.date()); out['delays'][str(d)]={}
        for name,start in WINDOWS.items():
            q=f if start is None else f.loc[pd.Timestamp(start):]
            out['delays'][str(d)][name]={str(bp):evaluate(q,bp) for bp in COSTS}
    out['source']['panel_sha256_by_delay']=hashes; out['source']['last_complete_month_end_by_delay']=cutoffs
    t=out['delays']['5']['2020_forward']['50']
    out['decision']='P57_TRADING_DAY_DELAY_ROBUSTNESS_SUPPORTED' if t['excess_cagr']>0 and t['positive_folds']>=3 else 'P57_TRADING_DAY_DELAY_WEAKNESS'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p57_trading_day_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
