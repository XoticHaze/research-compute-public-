import json
import numpy as np
import pandas as pd
import yfinance as yf

SYMS=['SPY','IEF','BIL']
START='2007-01-01'
COST=0.001
WINDOWS=['2012-01-01','2016-01-01','2020-01-01','2022-01-01']
FOLDS=[('2012-01-01','2015-12-31'),('2016-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01',None)]

px=yf.download(SYMS,start=START,auto_adjust=True,progress=False)['Close'].dropna()
month=px.resample('ME').last(); mr=month.pct_change().dropna()
# Causal: at prior month-end rank trailing 12m SPY vs IEF; hold winner next month.
score=pd.DataFrame({'SPY':month.SPY/month.SPY.shift(12)-1,'IEF':month.IEF/month.IEF.shift(12)-1}).shift(1).reindex(mr.index)
choice=np.where(score.SPY>=score.IEF,'SPY','IEF')
valid=score.notna().all(axis=1)
choice=pd.Series(choice,index=mr.index).where(valid,'BIL')
turn=choice.ne(choice.shift()).astype(float); turn.iloc[0]=1.0
cand=pd.Series([mr.loc[d,c] for d,c in choice.items()],index=mr.index)-turn*COST
# Matched control preserves realized SPY/IEF/BIL exposure fractions but removes timing.
w={s:float((choice==s).mean()) for s in SYMS}
ctrl=sum(w[s]*mr[s] for s in SYMS)

def stats(r):
    if len(r)<12:return {'cagr':None,'max_dd':None}
    wealth=(1+r).cumprod(); years=len(r)/12
    return {'cagr':float(wealth.iloc[-1]**(1/years)-1),'max_dd':float((wealth/wealth.cummax()-1).min())}
def sl(a,b=None):
    c=cand.loc[a:b]; k=ctrl.loc[a:b]; sc=stats(c); sk=stats(k)
    return {'start':a,'end':b,'months':len(c),'candidate_after_cost_cagr':sc['cagr'],'matched_control_cagr':sk['cagr'],'excess_cagr_pp':100*(sc['cagr']-sk['cagr']),'candidate_max_drawdown':sc['max_dd'],'control_max_drawdown':sk['max_dd']}
windows={s:sl(s) for s in WINDOWS}; folds=[sl(a,b) for a,b in FOLDS]; pos=sum(x['excess_cagr_pp']>0 for x in folds)
support=(windows['2012-01-01']['excess_cagr_pp']>0 and windows['2020-01-01']['excess_cagr_pp']>0 and pos>=3 and windows['2012-01-01']['candidate_max_drawdown']>=windows['2012-01-01']['control_max_drawdown']-0.05)
out={'classification':'CROSS_ASSET_RELATIVE_MOMENTUM_SUPPORTED' if support else 'CROSS_ASSET_RELATIVE_MOMENTUM_REJECTED','mechanism':'prior-month-end 12m relative momentum selects SPY or IEF for next month','strongest_non_alpha_explanation':'apparent performance is static equity-duration mixture plus regime luck; relative ranking adds no durable timing information','causal_information_time':'prior month-end only','cost_one_way':COST,'matched_control':'static SPY/IEF/BIL mix matched to realized strategy exposure fractions','exposure_fractions':w,'windows':windows,'folds':folds,'positive_folds':pos,'support_rule':'positive after-cost excess 2012+ and 2020+; >=3/4 positive chronology folds; 2012+ DD no worse than control by >5pp','protected_boundary':'no lookback/ticker/ranking/cost/date/control/fold rescue'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))
