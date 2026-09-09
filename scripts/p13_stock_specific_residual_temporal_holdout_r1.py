from __future__ import annotations
import json
import numpy as np
import pandas as pd
import p13_semiconductor_stock_specific_residual as p13


def compounded(x):
    x=pd.Series(x,dtype=float).dropna()
    return float((1+x).prod()-1)


def cagr(x):
    x=pd.Series(x,dtype=float).dropna()
    return float((1+x).prod()**(12/len(x))-1)


def maxdd(x):
    eq=(1+pd.Series(x,dtype=float).fillna(0)).cumprod()
    return float((eq/eq.cummax()-1).min())


def summarize(frame,bp):
    drag=bp/10000.0
    r=frame.residual_gross-drag; raw=frame.raw_gross-drag; ew=frame.equal_weight_gross; smh=frame.smh_gross; qqq=frame.qqq_gross
    pos=0
    for ids in np.array_split(np.arange(len(frame)),min(5,len(frame))):
        g=frame.iloc[ids]; pos += cagr(g.residual_gross-drag)-cagr(g.smh_gross)>0
    return {
      'periods':int(len(frame)), 'start':str(pd.Timestamp(frame.entry_date.min()).date()), 'end':str(pd.Timestamp(frame.exit_date.max()).date()),
      'residual_cagr':cagr(r), 'raw_cagr':cagr(raw), 'equal_weight_cagr':cagr(ew), 'smh_cagr':cagr(smh), 'qqq_cagr':cagr(qqq),
      'excess_vs_raw_cagr':cagr(r)-cagr(raw), 'excess_vs_equal_weight_cagr':cagr(r)-cagr(ew), 'excess_vs_smh_cagr':cagr(r)-cagr(smh), 'excess_vs_qqq_cagr':cagr(r)-cagr(qqq),
      'max_drawdown':maxdd(r), 'smh_max_drawdown':maxdd(smh), 'positive_folds_vs_smh':int(pos)
    }


def main():
    close,volume=p13.download(); periods=p13.build_periods(close,volume)
    frame=pd.DataFrame([x.__dict__ for x in periods]); frame['entry_date']=pd.to_datetime(frame.entry_date); frame['exit_date']=pd.to_datetime(frame.exit_date)
    windows={'2019_2021':frame[(frame.entry_date>='2019-01-01')&(frame.entry_date<'2022-01-01')], '2022_forward':frame[frame.entry_date>='2022-01-01'], 'full':frame}
    tests={k:{str(bp):summarize(v,bp) for bp in (25,50)} for k,v in windows.items() if len(v)>=12}
    h=tests['2022_forward']['50']
    state='P13_RECENT_TEMPORAL_SUPPORT_SURVIVORSHIP_CAUTION' if h['excess_vs_raw_cagr']>0 and h['excess_vs_smh_cagr']>0 and h['excess_vs_equal_weight_cagr']>0 and h['positive_folds_vs_smh']>=3 else 'P13_RECENT_TEMPORAL_NOT_SUPPORTED'
    out={'schema':'research.p13_stock_specific_residual_temporal_holdout_r1','parent':'P13','scientific_contract':{'frozen_signal':'126-session stock-specific beta residual momentum, top-3, monthly','holdouts':['2019-2021','2022-forward'],'costs_bps':[25,50],'comparators':['raw momentum top-3','equal-weight same-name universe','SMH','QQQ'],'no_parameter_search':True,'known_survivorship_risk_preserved':True},'tests':tests,'decision':state}
    print('P13_TEMPORAL_HOLDOUT_RECEIPT='+json.dumps(out,sort_keys=True))
    open('p13-temporal-holdout-receipt.json','w').write(json.dumps(out,indent=2,sort_keys=True))

if __name__=='__main__': main()
