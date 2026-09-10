from __future__ import annotations
import hashlib, io, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import fixed_multifactor_cross_sectional_r1 as base
import p82_execution_delay_adjudicator_r1 as p82

DELAY=5
BP=50
START='2015-01-01'


def stooq_load(symbols: tuple[str,...]) -> pd.DataFrame:
    requested=tuple(dict.fromkeys((*symbols,'SPY','QQQ')))
    out=[]
    session=requests.Session(); session.headers.update({'User-Agent':'Mozilla/5.0 research-replication'})
    for sym in requested:
        url=f'https://stooq.com/q/d/l/?s={sym.lower()}.us&i=d&d1=20050101&d2=20260901'
        r=session.get(url,timeout=30); r.raise_for_status()
        if 'No data' in r.text or len(r.text)<100:
            raise RuntimeError(f'stooq_no_data:{sym}:{r.text[:80]}')
        df=pd.read_csv(io.StringIO(r.text))
        if 'Date' not in df or 'Close' not in df: raise RuntimeError(f'stooq_schema:{sym}:{list(df.columns)}')
        s=pd.Series(df.Close.astype(float).values,index=pd.to_datetime(df.Date),name=sym).sort_index()
        out.append(s); time.sleep(0.15)
    close=pd.concat(out,axis=1).sort_index().ffill().dropna()
    if close.empty: raise RuntimeError('stooq_empty_common_panel')
    return close


def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def maxdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); return float((e/e.cummax()-1).min()) if len(e) else float('nan')

def evalq(q):
    folds=[]
    for i,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
        z=q.iloc[ids]
        folds.append({'fold':i,'vs_matched':cagr(z.candidate)-cagr(z.matched),'vs_qqq':cagr(z.candidate)-cagr(z.qqq)})
    return {'months':int(len(q)),'candidate_cagr':cagr(q.candidate),'matched_cagr':cagr(q.matched),'qqq_cagr':cagr(q.qqq),'excess_vs_matched':cagr(q.candidate)-cagr(q.matched),'excess_vs_qqq':cagr(q.candidate)-cagr(q.qqq),'candidate_maxdd':maxdd(q.candidate),'matched_maxdd':maxdd(q.matched),'qqq_maxdd':maxdd(q.qqq),'positive_folds_vs_matched':sum(x['vs_matched']>0 for x in folds),'positive_folds_vs_qqq':sum(x['vs_qqq']>0 for x in folds),'folds':folds}


def main():
    original=base.load
    base.load=stooq_load
    try:
        f,close=p82.blend(DELAY)
    finally:
        base.load=original
    q=f.loc[f.index>=pd.Timestamp(START)].dropna()
    panel_sha=hashlib.sha256(close.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()
    res=evalq(q)
    out={'schema':'research.p178_p82_stooq_source_replication_r1','parent':'P82','hypothesis':'P82 five-day-delayed aggregate excess survives a genuinely independent Stooq price-history representation with the model, component weights, costs, signals, and chronology fixed.','scientific_contract':{'source':'Stooq direct daily CSV','delay_trading_days':DELAY,'component_cost_bps':BP,'sleeve_weights':[0.5,0.5],'start':START,'controls':['fixed matched blend','QQQ'],'chronological_folds':5,'no_signal_weight_window_threshold_or_proxy_tuning':True,'adjudication':'source representation only'},'source':{'provider':'Stooq direct CSV; research-only','panel_sha256':panel_sha,'last_date':str(close.index.max().date())},'result':res}
    out['decision']='P82_INDEPENDENT_SOURCE_SUPPORTED' if (res['excess_vs_matched']>0 and res['excess_vs_qqq']>0 and res['positive_folds_vs_matched']>=3) else 'P82_INDEPENDENT_SOURCE_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p178_p82_stooq_source_replication_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
