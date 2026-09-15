import json, math
import pandas as pd
import yfinance as yf

TICKERS=['SPY','HYG','IEF']; COST=0.001
px=yf.download(TICKERS,start='2007-01-01',auto_adjust=True,progress=False)['Close'].dropna()
m=px.resample('ME').last().dropna(); r=m.pct_change().dropna()
ratio=m.HYG/m.IEF
signal=(ratio.pct_change(3)>0).shift(1).reindex(r.index).fillna(False)
# Credit appetite known at prior month-end: own SPY when HYG/IEF 3m momentum positive, otherwise IEF.
w=pd.DataFrame({'SPY':signal.astype(float),'IEF':(~signal).astype(float)},index=r.index)
turn=w.diff().abs().sum(axis=1).fillna(0)/2
cand=w.SPY*r.SPY+w.IEF*r.IEF-COST*turn
ctrl6040=.6*r.SPY+.4*r.IEF
spy=r.SPY

def stats(x):
    x=x.dropna(); n=len(x); wealth=(1+x).cumprod(); yrs=n/12
    cagr=wealth.iloc[-1]**(1/yrs)-1 if yrs>0 else float('nan')
    dd=(wealth/wealth.cummax()-1).min()
    return {'months':n,'cagr':cagr,'maxdd':dd}

def window(start,end=None):
    mask=cand.index>=pd.Timestamp(start)
    if end: mask &= cand.index<=pd.Timestamp(end)
    c,ctl,s=cand[mask],ctrl6040[mask],spy[mask]
    a,b,d=stats(c),stats(ctl),stats(s)
    return {'candidate_after_cost':a,'control_60_40':b,'spy':d,'excess_vs_60_40_pp':100*(a['cagr']-b['cagr']),'excess_vs_spy_pp':100*(a['cagr']-d['cagr'])}
windows={k:window(k+'-01-01') for k in ['2008','2012','2016','2020','2022']}
fold_ranges=[('2008-01-01','2012-12-31'),('2013-01-01','2016-12-31'),('2017-01-01','2020-12-31'),('2021-01-01',None)]
folds=[window(a,b) for a,b in fold_ranges]
pos=sum(x['excess_vs_60_40_pp']>0 for x in folds)
support=windows['2012']['excess_vs_60_40_pp']>0 and windows['2020']['excess_vs_60_40_pp']>0 and pos>=3
out={'experiment_id':'CREDIT_RISK_REGIME_R1','frozen':{'signal':'prior-month-end HYG/IEF 3-month momentum > 0','risk_on':'SPY','risk_off':'IEF','cost_one_way':COST,'matched_control':'60% SPY + 40% IEF monthly','secondary_control':'SPY','no_rescue':True},'windows':windows,'folds':folds,'positive_excess_folds_vs_60_40':pos,'decision':'CREDIT_RISK_REGIME_SUPPORTED' if support else 'CREDIT_RISK_REGIME_REJECTED'}
print(json.dumps(out,indent=2))
open('credit_risk_regime_r1_result.json','w').write(json.dumps(out,indent=2))
