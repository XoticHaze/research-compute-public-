from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/spy_turn_of_month_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
raw=yf.download(['SPY','BIL'],start='2012-01-01',end='2026-09-12',auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[['SPY','BIL']].dropna()
r=close.pct_change(fill_method=None).dropna()
# Frozen calendar mechanism: own SPY for the close-to-close returns of the last trading day of each month and first three trading days of the next month; BIL otherwise.
period=r.index.to_period('M')
pos=pd.Series(False,index=r.index)
for p in period.unique():
    idx=r.index[period==p]
    if len(idx):
        pos.loc[idx[-1:]]=True
        pos.loc[idx[:3]]=True
frame=pd.DataFrame({'spy':r.SPY,'bil':r.BIL,'equity':pos.astype(float)}).dropna()
frame['gross']=frame.equity*frame.spy+(1-frame.equity)*frame.bil
frame['switch']=frame.equity.diff().abs().fillna(0)
frame['net']=frame.gross-frame['switch']*COST

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
windows={k:stats(v) for k,v in {'2012_plus':'2012-01-03','2018_plus':'2018-01-02','2022_plus':'2022-01-03'}.items()}
blocks={k:stats(a,z) for k,(a,z) in {'2012_2015':('2012-01-03','2015-12-31'),'2016_2019':('2016-01-04','2019-12-31'),'2020_2022':('2020-01-02','2022-12-30'),'2023_plus':('2023-01-03',None)}.items()}
pos_blocks=sum(v['excess_cagr_pp']>0 for v in blocks.values())
supported=all(v['excess_cagr_pp']>0 for v in windows.values()) and pos_blocks>=3 and windows['2012_plus']['candidate']['max_drawdown']>=windows['2012_plus']['matched']['max_drawdown']-.05
decision='SPY_TURN_OF_MONTH_ALPHA_SUPPORTED' if supported else 'SPY_TURN_OF_MONTH_ALPHA_REJECTED'
out={'schema':'research.spy_turn_of_month_r1.v1','decision':decision,'claim':'A fixed turn-of-month calendar window adds after-cost SPY return beyond equal-equity-exposure static SPY/BIL beta.','causal_information_time':'calendar position known before each session; close-to-close holding decision fixed before return','mechanism':'SPY on last trading day plus first three trading days of each month; BIL otherwise','cost_one_way':COST,'matched_control':'static SPY/BIL exposure matched to realized strategy participation','strongest_non_alpha_explanation':'calendar window merely concentrates unconditional equity beta and sampling luck; timing adds no durable information','support_rule':'positive excess in 2012+, 2018+, 2022+; >=3/4 positive chronology blocks; 2012+ drawdown no worse than matched control by >5pp','protected_boundary':'no day-count/window/ticker/cost/date/control/block rescue','windows':windows,'blocks':blocks,'positive_blocks':pos_blocks,'scientific_consequence':'Support only if the fixed calendar rule survives matched exposure, costs, chronology, and drawdown gates; otherwise reject without nearby calendar-window rescue.'}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True))
print('RESULT_JSON='+json.dumps(out,sort_keys=True))