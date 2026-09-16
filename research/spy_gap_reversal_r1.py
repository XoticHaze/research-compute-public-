import json
import numpy as np
import pandas as pd
import yfinance as yf

COST=0.001
START='2011-01-01'
# Frozen R1: previous close -> today's open gap <= -1.0%, buy SPY at open and exit same close.
# Control: static open-to-close SPY exposure scaled to realized strategy participation.
d=yf.download('SPY',start=START,auto_adjust=True,progress=False)
if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
d=d[['Open','Close']].dropna()
d['gap']=d.Open/d.Close.shift(1)-1
d['oc']=d.Close/d.Open-1
d=d.dropna()
sig=(d.gap<=-0.01).astype(float)
turn=sig.diff().abs().fillna(sig.abs())
cand=sig*d.oc-turn*COST
frac=float(sig.mean())
ctrl=frac*d.oc

def metrics(r):
    eq=(1+r).cumprod(); years=len(r)/252
    cagr=float(eq.iloc[-1]**(1/years)-1) if years>0 else None
    dd=float((eq/eq.cummax()-1).min())
    return cagr,dd

def slice_metrics(start,end=None):
    m=(d.index>=start) if end is None else ((d.index>=start)&(d.index<=end))
    c,dd=metrics(cand[m]); b,bdd=metrics(ctrl[m])
    return {'candidate_after_cost_cagr':c,'matched_control_cagr':b,'excess_cagr_pp':100*(c-b),'candidate_max_drawdown':dd,'control_max_drawdown':bdd,'days':int(m.sum())}
windows={s:slice_metrics(s) for s in ['2012-01-01','2016-01-01','2020-01-01','2022-01-01']}
fold_ranges=[('2012-01-01','2015-12-31'),('2016-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01',None)]
folds=[]
for s,e in fold_ranges:
    x=slice_metrics(s,e); x.update({'start':s,'end':e}); folds.append(x)
pos=sum(x['excess_cagr_pp']>0 for x in folds)
support=(windows['2012-01-01']['excess_cagr_pp']>0 and windows['2020-01-01']['excess_cagr_pp']>0 and pos>=3 and windows['2012-01-01']['candidate_max_drawdown']>=windows['2012-01-01']['control_max_drawdown']-0.05)
out={'classification':'SPY_GAP_REVERSAL_SUPPORTED' if support else 'SPY_GAP_REVERSAL_REJECTED','mechanism':'today open gap vs prior close <= -1.0%; buy SPY open, exit same close','causal_information_time':'today open after prior close; trade at observed open','cost_one_way':COST,'participation_fraction':frac,'matched_control':'static SPY open-to-close exposure scaled to realized strategy participation','strongest_non_alpha_explanation':'gap days merely concentrate unconditional intraday equity beta/volatility; threshold adds no durable reversal information','support_rule':'positive after-cost excess 2012+ and 2020+; >=3/4 positive chronology folds; 2012+ DD no worse than control by >5pp','protected_boundary':'no gap threshold/ticker/holding-period/cost/date/control/fold rescue','windows':windows,'folds':folds,'positive_folds':pos}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))
