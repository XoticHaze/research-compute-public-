import json, math
import numpy as np
import pandas as pd
import yfinance as yf

SYMS = ['GLD','BIL']
START = '2007-01-01'
COST = 0.001
WINDOWS = ['2012-01-01','2016-01-01','2020-01-01','2022-01-01']
FOLDS = [('2012-01-01','2015-12-31'),('2016-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01',None)]

px = yf.download(SYMS, start=START, auto_adjust=True, progress=False)['Close'].dropna()
month = px.resample('ME').last()
# causal information: prior month-end GLD 10-month total return decides next month allocation
sig = (month.GLD / month.GLD.shift(10) - 1).shift(1) > 0
mr = month.pct_change().dropna()
sig = sig.reindex(mr.index).fillna(False)
turn = sig.astype(int).diff().abs().fillna(sig.astype(int))
cand = np.where(sig, mr.GLD, mr.BIL) - turn * COST
# matched control: static GLD/BIL exposure matched to realized risk-on fraction, same monthly observations
w = float(sig.mean())
ctrl = w * mr.GLD + (1-w) * mr.BIL
cand = pd.Series(cand,index=mr.index,name='candidate')
ctrl = pd.Series(ctrl,index=mr.index,name='control')

def stats(r):
    if len(r)<12: return {'cagr':None,'max_dd':None}
    wealth=(1+r).cumprod(); years=len(r)/12
    return {'cagr':float(wealth.iloc[-1]**(1/years)-1),'max_dd':float((wealth/wealth.cummax()-1).min())}

def slice_result(start,end=None):
    c=cand.loc[start:end]; k=ctrl.loc[start:end]; sc=stats(c); sk=stats(k)
    return {'start':start,'end':end,'months':len(c),'candidate_after_cost_cagr':sc['cagr'],'matched_control_cagr':sk['cagr'],'excess_cagr_pp':100*(sc['cagr']-sk['cagr']),'candidate_max_drawdown':sc['max_dd'],'control_max_drawdown':sk['max_dd']}

windows={s:slice_result(s) for s in WINDOWS}
folds=[slice_result(a,b) for a,b in FOLDS]
positive_folds=sum(x['excess_cagr_pp']>0 for x in folds)
support=(windows['2012-01-01']['excess_cagr_pp']>0 and windows['2020-01-01']['excess_cagr_pp']>0 and positive_folds>=3 and windows['2012-01-01']['candidate_max_drawdown'] >= windows['2012-01-01']['control_max_drawdown']-0.05)
out={'classification':'GLD_ABSOLUTE_TREND_SUPPORTED' if support else 'GLD_ABSOLUTE_TREND_REJECTED','mechanism':'prior-month-end 10-month GLD absolute momentum; next month GLD if positive else BIL','causal_information_time':'prior month-end only','cost_one_way':COST,'matched_control':'static GLD/BIL mix matched to realized risk-on fraction','risk_on_fraction':w,'windows':windows,'folds':folds,'positive_folds':positive_folds,'support_rule':'positive after-cost excess 2012+ and 2020+; >=3/4 positive chronology folds; 2012+ DD no worse than control by >5pp','protected_boundary':'no lookback/ticker/cost/date/control/threshold rescue'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))
