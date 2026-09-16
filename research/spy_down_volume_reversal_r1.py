from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/spy_down_volume_reversal_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
raw=yf.download(['SPY','BIL'],start='2012-01-01',end='2026-09-12',auto_adjust=True,progress=False,threads=False)
if isinstance(raw.columns,pd.MultiIndex):
    close=raw['Close'][['SPY','BIL']].dropna(); open_=raw['Open'][['SPY','BIL']].reindex(close.index); volume=raw['Volume']['SPY'].reindex(close.index)
else:
    close=raw[['SPY','BIL']].dropna(); open_=raw[['SPY','BIL']].reindex(close.index); volume=raw['Volume'].reindex(close.index)
cc=close.pct_change(fill_method=None).SPY
prior_med=volume.shift(1).rolling(20,min_periods=20).median()
signal=((cc<=-.01)&(volume>=2.0*prior_med)).shift(1).fillna(False)
spy_oc=close.SPY/open_.SPY-1
bil_oc=close.BIL/open_.BIL-1
frame=pd.DataFrame({'spy':spy_oc,'bil':bil_oc,'equity':signal.astype(float)}).dropna()
frame['gross']=frame.equity*frame.spy+(1-frame.equity)*frame.bil
frame['net']=frame.gross-frame.equity*(2*COST)

def stats(start,end=None):
    x=frame.loc[frame.index>=pd.Timestamp(start)].copy()
    if end: x=x.loc[x.index<=pd.Timestamp(end)]
    w=float(x.equity.mean()); x['matched']=w*x.spy+(1-w)*x.bil
    def perf(c):
        rr=x[c].to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/252
        cagr=float(wealth[-1]**(1/yrs)-1); peak=np.maximum.accumulate(wealth)
        return {'cagr':cagr,'max_drawdown':float((wealth/peak-1).min())}
    a,b=perf('net'),perf('matched')
    return {'days':len(x),'participation':w,'candidate':a,'matched':b,'excess_cagr_pp':(a['cagr']-b['cagr'])*100}
windows={k:stats(v) for k,v in {'2012_plus':'2012-02-01','2018_plus':'2018-01-02','2022_plus':'2022-01-03'}.items()}
blocks={k:stats(a,z) for k,(a,z) in {'2012_2015':('2012-02-01','2015-12-31'),'2016_2019':('2016-01-04','2019-12-31'),'2020_2022':('2020-01-02','2022-12-30'),'2023_plus':('2023-01-03',None)}.items()}
pos_blocks=sum(v['excess_cagr_pp']>0 for v in blocks.values())
supported=all(v['excess_cagr_pp']>0 for v in windows.values()) and pos_blocks>=3 and windows['2012_plus']['candidate']['max_drawdown']>=windows['2012_plus']['matched']['max_drawdown']-.05
decision='SPY_DOWN_VOLUME_REVERSAL_SUPPORTED' if supported else 'SPY_DOWN_VOLUME_REVERSAL_REJECTED'
out={'schema':'research.spy_down_volume_reversal_r1.v1','decision':decision,'claim':'A completed SPY down session with exceptional volume predicts next-session open-to-close reversal beyond equal-participation static beta after costs.','causal_information_time':'signal uses only completed prior-session SPY close-to-close return, volume, and prior 20-session volume history; trade enters next session open and exits same close','mechanism':'after SPY return <=-1% with volume >=2x prior-20-session median, buy SPY next open and exit same close; otherwise BIL open-to-close','cost_one_way':COST,'matched_control':'static SPY/BIL open-to-close exposure matched to realized strategy participation','strongest_non_alpha_explanation':'exceptional down-volume merely tags high-volatility selloffs; any next-day bounce is unconditional intraday equity beta or sampling noise rather than durable reversal information','nearest_prior_art_and_distinction':'Clears rejected positive-volume continuation because sign and hypothesized mechanism are capitulation/reversal, not flow continuation; clears P186 momentum; clears #792 and overnight-gap reversal because the signal is completed prior-session close+volume, not current overnight gap ranking.','support_rule':'positive excess in 2012+, 2018+, 2022+; >=3/4 positive chronology blocks; 2012+ drawdown no worse than matched control by >5pp','protected_boundary':'no return threshold/volume multiple/lookback/ticker/holding-period/cost/date/control/block rescue','opportunity_cost':'one A child; rejection releases this capitulation/reversal lineage rather than tuning it','windows':windows,'blocks':blocks,'positive_blocks':pos_blocks,'scientific_consequence':'Support advances only to independent replication with frozen rule; reject releases lineage with no nearby rescue.'}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print('RESULT_JSON='+json.dumps(out,sort_keys=True))
