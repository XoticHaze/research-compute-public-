from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/spy_volume_shock_continuation_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
raw=yf.download(['SPY','BIL'],start='2012-01-01',end='2026-09-12',auto_adjust=True,progress=False,threads=False)
if isinstance(raw.columns,pd.MultiIndex):
    close=raw['Close'][['SPY','BIL']].dropna(); volume=raw['Volume']['SPY'].reindex(close.index)
else:
    close=raw[['SPY','BIL']].dropna(); volume=raw['Volume'].reindex(close.index)
r=close.pct_change(fill_method=None)
spy_ret=r.SPY
# Frozen causal flow signal: after a completed SPY session with positive >=1% close-to-close return and volume >=2x the prior 20-session median, own SPY for the next close-to-close session; BIL otherwise.
prior_med=volume.shift(1).rolling(20,min_periods=20).median()
shock=((spy_ret>=.01)&(volume>=2.0*prior_med)).shift(1).fillna(False)
frame=pd.DataFrame({'spy':r.SPY,'bil':r.BIL,'equity':shock.astype(float)}).dropna()
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
windows={k:stats(v) for k,v in {'2012_plus':'2012-02-01','2018_plus':'2018-01-02','2022_plus':'2022-01-03'}.items()}
blocks={k:stats(a,z) for k,(a,z) in {'2012_2015':('2012-02-01','2015-12-31'),'2016_2019':('2016-01-04','2019-12-31'),'2020_2022':('2020-01-02','2022-12-30'),'2023_plus':('2023-01-03',None)}.items()}
pos_blocks=sum(v['excess_cagr_pp']>0 for v in blocks.values())
supported=all(v['excess_cagr_pp']>0 for v in windows.values()) and pos_blocks>=3 and windows['2012_plus']['candidate']['max_drawdown']>=windows['2012_plus']['matched']['max_drawdown']-.05
decision='SPY_VOLUME_SHOCK_CONTINUATION_SUPPORTED' if supported else 'SPY_VOLUME_SHOCK_CONTINUATION_REJECTED'
out={'schema':'research.spy_volume_shock_continuation_r1.v1','decision':decision,'claim':'A completed-session positive price move confirmed by exceptional trading volume predicts next-session SPY continuation beyond equal-equity-exposure static beta after costs.','causal_information_time':'signal uses only completed prior-session SPY close, volume, and prior 20-session volume history; position applies one session later','mechanism':'after SPY return >=1% with volume >=2x prior-20-session median, hold SPY next session; BIL otherwise','cost_one_way':COST,'matched_control':'static SPY/BIL exposure matched to realized strategy participation','strongest_non_alpha_explanation':'exceptional volume merely tags high-volatility beta days; any next-day return is unconditional equity exposure or sampling noise, not persistent flow continuation','nearest_prior_art_and_distinction':'Clears P186 tactical price momentum because volume is the causal discriminator and horizon is one session; clears #792 and SPY gap reversal because signal is completed-session close+volume rather than overnight gap/open-to-close reversal; clears turn-of-month/calendar and VIX stress families because no calendar or volatility-index state is used.','support_rule':'positive excess in 2012+, 2018+, 2022+; >=3/4 positive chronology blocks; 2012+ drawdown no worse than matched control by >5pp','protected_boundary':'no return threshold/volume multiple/lookback/ticker/holding-period/cost/date/control/block rescue','opportunity_cost':'one A child; rejection releases the volume-confirmed continuation lineage rather than tuning it','windows':windows,'blocks':blocks,'positive_blocks':pos_blocks,'scientific_consequence':'Support advances only to independent replication with the frozen rule; reject releases this lineage with no nearby volume/return-threshold rescue.'}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True))
print('RESULT_JSON='+json.dumps(out,sort_keys=True))
