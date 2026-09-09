from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import sys
sys.path.insert(0,'scripts')
import p13_semiconductor_stock_specific_residual as p13

BASE=tuple(p13.UNIVERSE)
BPS=50


def cagr(x):
    x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)


def maxdd(x):
    x=pd.Series(x,dtype=float).fillna(0); eq=(1+x).cumprod(); return float((eq/eq.cummax()-1).min())


def eval_universe(close,volume,names):
    old=list(p13.UNIVERSE); p13.UNIVERSE=list(names)
    try: periods=p13.build_periods(close,volume)
    finally: p13.UNIVERSE=old
    f=pd.DataFrame([x.__dict__ for x in periods]); f['entry_date']=pd.to_datetime(f.entry_date)
    out={}
    for label,g in [('full',f),('2022_forward',f[f.entry_date>='2022-01-01'])]:
        drag=BPS/10000; rr=g.residual_gross-drag; raw=g.raw_gross-drag
        out[label]={
          'periods':int(len(g)),'residual_cagr':cagr(rr),'raw_cagr':cagr(raw),'smh_cagr':cagr(g.smh_gross),'qqq_cagr':cagr(g.qqq_gross),
          'excess_vs_raw_cagr':cagr(rr)-cagr(raw),'excess_vs_smh_cagr':cagr(rr)-cagr(g.smh_gross),'excess_vs_qqq_cagr':cagr(rr)-cagr(g.qqq_gross),'max_drawdown':maxdd(rr),
          'selection_count_by_name':{n:int(sum(n in row for row in g.residual_names)) for n in names}
        }
    return out


def main():
    tickers=list(BASE)+p13.BENCHMARKS
    raw=yf.download(tickers,start=p13.START,end=p13.END,auto_adjust=True,progress=False,group_by='column',threads=True)
    close=raw['Close'].copy().sort_index().dropna(how='all'); volume=raw['Volume'].copy().sort_index().reindex(close.index)
    base_result=eval_universe(close,volume,BASE)
    variants={n:eval_universe(close,volume,[x for x in BASE if x!=n]) for n in BASE}
    recent=[v['2022_forward'] for v in variants.values()]
    full=[v['full'] for v in variants.values()]
    summary={
      'recent_positive_vs_smh':sum(x['excess_vs_smh_cagr']>0 for x in recent),'recent_positive_vs_raw':sum(x['excess_vs_raw_cagr']>0 for x in recent),'recent_positive_vs_qqq':sum(x['excess_vs_qqq_cagr']>0 for x in recent),
      'recent_worst_excess_vs_smh':min(x['excess_vs_smh_cagr'] for x in recent),'recent_median_excess_vs_smh':float(np.median([x['excess_vs_smh_cagr'] for x in recent])),
      'full_positive_vs_smh':sum(x['excess_vs_smh_cagr']>0 for x in full),'full_positive_vs_raw':sum(x['excess_vs_raw_cagr']>0 for x in full),'full_positive_vs_qqq':sum(x['excess_vs_qqq_cagr']>0 for x in full),
      'full_worst_excess_vs_smh':min(x['excess_vs_smh_cagr'] for x in full)
    }
    decision='P13_NOT_SINGLE_NAME_DOMINATED_SURVIVORSHIP_BLOCK_REMAINS' if summary['recent_positive_vs_smh']>=8 and summary['recent_positive_vs_raw']>=8 and summary['full_positive_vs_smh']>=8 else 'P13_SINGLE_NAME_CONCENTRATION_CAUTION'
    out={'schema':'research.p13_leave_one_name_out_concentration_r1','parent':'P13','hypothesis':'The frozen stock-specific residual top-3 edge is not an artifact of any single current-universe semiconductor name.','contract':{'base_universe':BASE,'leave_one_out':list(BASE),'signal':'unchanged 126-session stock-specific beta residual vs SMH, monthly top-3','cost_bps':BPS,'comparators':['raw momentum top-3','SMH','QQQ'],'windows':['full','2022_forward'],'known_static_current_name_survivorship_block_preserved':True,'no_parameter_search':True},'base':base_result,'variants':variants,'summary':summary,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_leave_one_name_out_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
