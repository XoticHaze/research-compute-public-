from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p82_execution_delay_adjudicator_r1 as p82

DELAY=5
BP=50
ROLL_MONTHS=(24,36)
START='2015-01-01'


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def maxdd(r):
    r=pd.Series(r,dtype=float).dropna()
    eq=(1+r).cumprod()
    return float((eq/eq.cummax()-1).min()) if len(eq) else float('nan')


def rolling_excess(q, months):
    rows=[]
    for end in range(months, len(q)+1):
        z=q.iloc[end-months:end]
        rows.append({
            'end': str(z.index[-1].date()),
            'excess_vs_matched': cagr(z.candidate)-cagr(z.matched),
            'excess_vs_qqq': cagr(z.candidate)-cagr(z.qqq),
        })
    a=np.array([r['excess_vs_matched'] for r in rows],dtype=float)
    b=np.array([r['excess_vs_qqq'] for r in rows],dtype=float)
    return {
        'months': months,
        'window_count': len(rows),
        'positive_share_vs_matched': float(np.mean(a>0)),
        'positive_share_vs_qqq': float(np.mean(b>0)),
        'median_excess_vs_matched': float(np.median(a)),
        'median_excess_vs_qqq': float(np.median(b)),
        'worst_excess_vs_matched': float(np.min(a)),
        'worst_excess_vs_qqq': float(np.min(b)),
    }


def annual(q):
    out=[]
    for year,g in q.groupby(q.index.year):
        if len(g) < 10: continue
        out.append({
            'year': int(year),
            'months': int(len(g)),
            'excess_vs_matched': cagr(g.candidate)-cagr(g.matched),
            'excess_vs_qqq': cagr(g.candidate)-cagr(g.qqq),
        })
    return out


def main():
    f,close=p82.blend(DELAY)
    q=f.loc[f.index>=pd.Timestamp(START)].dropna()
    annual_rows=annual(q)
    out={
        'schema':'research.p82_rolling_chronology_r1',
        'parent':'P82',
        'hypothesis':'The fixed five-trading-day delayed P82 blend has broadly persistent after-cost excess through time rather than only a favorable aggregate endpoint.',
        'scientific_contract':{
            'delay_trading_days':DELAY,
            'component_cost_bps':BP,
            'start':START,
            'rolling_windows_months':list(ROLL_MONTHS),
            'controls':['fixed matched blend','QQQ'],
            'no_signal_weight_window_or_threshold_tuning':True,
        },
        'aggregate':{
            'months':int(len(q)),
            'cagr_candidate':cagr(q.candidate),
            'cagr_matched':cagr(q.matched),
            'cagr_qqq':cagr(q.qqq),
            'excess_vs_matched':cagr(q.candidate)-cagr(q.matched),
            'excess_vs_qqq':cagr(q.candidate)-cagr(q.qqq),
            'maxdd_candidate':maxdd(q.candidate),
            'maxdd_matched':maxdd(q.matched),
            'maxdd_qqq':maxdd(q.qqq),
        },
        'rolling':{str(m):rolling_excess(q,m) for m in ROLL_MONTHS},
        'annual':annual_rows,
        'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':p82.base.source_hash(close)},
    }
    r36=out['rolling']['36']
    annual_match=np.mean([x['excess_vs_matched']>0 for x in annual_rows]) if annual_rows else 0
    annual_qqq=np.mean([x['excess_vs_qqq']>0 for x in annual_rows]) if annual_rows else 0
    out['annual_positive_share_vs_matched']=float(annual_match)
    out['annual_positive_share_vs_qqq']=float(annual_qqq)
    out['decision']='P82_DELAY_EDGE_CHRONOLOGY_SUPPORTED' if (r36['positive_share_vs_matched']>=0.70 and r36['positive_share_vs_qqq']>=0.60 and annual_match>=0.60 and annual_qqq>=0.50) else 'P82_DELAY_EDGE_CHRONOLOGY_WEAK'
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p82_rolling_chronology_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
