import json
import numpy as np
import pandas as pd
import yfinance as yf

START='2000-01-01'; COST_BPS=10.0
px=yf.download('SPY',start=START,auto_adjust=True,progress=False)['Close']
if isinstance(px,pd.DataFrame): px=px.iloc[:,0]
r=px.pct_change().dropna()
df=pd.DataFrame({'r':r})
df['month']=df.index.to_period('M')
df['ord']=df.groupby('month').cumcount()
df['n']=df.groupby('month')['r'].transform('size')
df['from_end']=df['n']-1-df['ord']
# Frozen calendar rule: last trading day of month plus first three trading days of next month.
df['tom']=(df['from_end']==0)|(df['ord']<=2)
# Matched exposure-count placebo: trading days 8-11 of each month, same four-day monthly exposure budget.
df['placebo']=(df['ord']>=7)&(df['ord']<=10)

def strat(mask):
    gross=df['r'].where(mask,0.0)
    # one entry and one exit per monthly block, 10bp each way
    months=df['month']
    entry=mask & (~mask.shift(1,fill_value=False) | (months!=months.shift(1)))
    exit_=mask & (~mask.shift(-1,fill_value=False) | (months!=months.shift(-1)))
    return gross - (COST_BPS/10000.0)*(entry.astype(float)+exit_.astype(float))

df['cand']=strat(df['tom']); df['ctrl']=strat(df['placebo'])

def metrics(s):
    eq=(1+s).cumprod(); yrs=len(s)/252
    cagr=eq.iloc[-1]**(1/yrs)-1 if yrs>0 else np.nan
    dd=(eq/eq.cummax()-1).min()
    return {'cagr':float(cagr),'max_dd':float(dd),'total':float(eq.iloc[-1]-1)}

def window(start):
    x=df.loc[start:]
    a=metrics(x['cand']); b=metrics(x['ctrl'])
    return {'candidate':a,'control':b,'excess_cagr':a['cagr']-b['cagr']}
windows={k:window(k) for k in ['2004-01-01','2008-01-01','2012-01-01','2016-01-01','2020-01-01','2022-01-01']}
years=sorted(df.index.year.unique()); cuts=np.array_split(years,4); folds=[]
for ys in cuts:
    x=df[df.index.year.isin(ys)]; a=metrics(x['cand']); b=metrics(x['ctrl']); folds.append({'years':[int(ys[0]),int(ys[-1])],'excess_cagr':a['cagr']-b['cagr']})
pos=sum(f['excess_cagr']>0 for f in folds)
support=windows['2012-01-01']['excess_cagr']>0 and windows['2020-01-01']['excess_cagr']>0 and pos>=3 and windows['2012-01-01']['candidate']['max_dd']>=windows['2012-01-01']['control']['max_dd']-0.05
result={'experiment':'SPY_TURN_MONTH_R1','mechanism':'calendar liquidity/payroll/flows concentrated at month boundary','non_alpha':'generic equity beta plus arbitrary calendar placement','causal_time':'calendar position known before each session; close return realized after selection','signal':'last trading day plus first 3 trading days of month','control':'days 8-11 same month, equal exposure count and identical costs','cost_bps_one_way':COST_BPS,'windows':windows,'chronology_folds':folds,'positive_folds':pos,'classification':'SPY_TURN_MONTH_SUPPORTED' if support else 'SPY_TURN_MONTH_REJECTED','protected_boundary':'no day-set, ticker, cost, date, control, or fold rescue'}
print(json.dumps(result,indent=2))
open('spy_turn_month_r1_result.json','w').write(json.dumps(result,indent=2))
