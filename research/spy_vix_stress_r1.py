import json
import numpy as np
import pandas as pd
import yfinance as yf

START='2008-01-01'; COST=0.001
px=yf.download(['SPY','BIL','^VIX'],start=START,auto_adjust=True,progress=False)['Close'].dropna()
# month-end observations causally known at close; trade next month
m=px.resample('ME').last().dropna()
ret=m[['SPY','BIL']].pct_change()
vix=m['^VIX']
# frozen mechanism: high stress at prior month-end => BIL next month, else SPY
stress=(vix.shift(1)>=30)
pos=pd.Series(np.where(stress,'BIL','SPY'),index=m.index)
r=pd.Series(np.where(pos.eq('SPY'),ret['SPY'],ret['BIL']),index=m.index)
turn=pos.ne(pos.shift(1)).astype(float)
cand=r-COST*turn
spy_frac=float(pos.eq('SPY').mean()); bil_frac=1-spy_frac
ctrl=spy_frac*ret['SPY']+bil_frac*ret['BIL']

def metrics(x,start,end=None):
    z=x.loc[start:end].dropna(); n=len(z)
    eq=(1+z).cumprod(); cagr=float(eq.iloc[-1]**(12/n)-1); dd=float((eq/eq.cummax()-1).min())
    return cagr,dd,n
wins={}
for s in ['2012-01-01','2016-01-01','2020-01-01','2022-01-01']:
    ca,cd,n=metrics(cand,s); co,od,_=metrics(ctrl,s); wins[s]={'candidate_after_cost_cagr':ca,'matched_control_cagr':co,'excess_cagr_pp':(ca-co)*100,'candidate_max_drawdown':cd,'control_max_drawdown':od,'months':n}
folds=[]
for s,e in [('2012-01-01','2015-12-31'),('2016-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01',None)]:
    ca,cd,n=metrics(cand,s,e); co,od,_=metrics(ctrl,s,e); folds.append({'start':s,'end':e,'candidate_after_cost_cagr':ca,'matched_control_cagr':co,'excess_cagr_pp':(ca-co)*100,'candidate_max_drawdown':cd,'control_max_drawdown':od,'months':n})
posfold=sum(f['excess_cagr_pp']>0 for f in folds)
support=(wins['2012-01-01']['excess_cagr_pp']>0 and wins['2020-01-01']['excess_cagr_pp']>0 and posfold>=3 and wins['2012-01-01']['candidate_max_drawdown']>=wins['2012-01-01']['control_max_drawdown']-0.05)
out={'classification':'SPY_VIX_STRESS_SUPPORTED' if support else 'SPY_VIX_STRESS_REJECTED','mechanism':'prior-month-end VIX >=30 rotates next month from SPY to BIL','causal_information_time':'prior month-end close only','cost_one_way':COST,'exposure_fractions':{'SPY':spy_frac,'BIL':bil_frac},'matched_control':'static SPY/BIL mix matched to realized strategy exposure fractions','strongest_non_alpha_explanation':'apparent protection is lower static equity beta plus crisis luck; VIX threshold adds no durable timing information','support_rule':'positive after-cost excess 2012+ and 2020+; >=3/4 positive chronology folds; 2012+ DD no worse than control by >5pp','protected_boundary':'no VIX threshold/ticker/cost/date/control/fold rescue','windows':wins,'folds':folds,'positive_folds':posfold}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))
