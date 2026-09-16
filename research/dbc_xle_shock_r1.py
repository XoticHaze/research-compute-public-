from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/dbc_xle_shock_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
raw=yf.download(['DBC','XLE','SPY'],start='2010-01-01',end='2026-09-12',auto_adjust=True,progress=False,threads=False)
close=raw['Close'][['DBC','XLE','SPY']].dropna() if isinstance(raw.columns,pd.MultiIndex) else raw[['DBC','XLE','SPY']].dropna()
monthly=close.resample('ME').last()
r=monthly.pct_change(fill_method=None)
signal=(r.DBC.shift(1)>=.05).astype(float)
frame=pd.DataFrame({'xle':r.XLE,'spy':r.SPY,'energy':signal}).dropna()
turn=frame.energy.diff().abs().fillna(frame.energy)
frame['net']=frame.energy*frame.xle+(1-frame.energy)*frame.spy-turn*COST

def stats(start,end=None):
    x=frame.loc[frame.index>=pd.Timestamp(start)].copy()
    if end: x=x.loc[x.index<=pd.Timestamp(end)]
    w=float(x.energy.mean()); x['matched']=w*x.xle+(1-w)*x.spy
    def perf(c):
        rr=x[c].to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/12
        cagr=float(wealth[-1]**(1/yrs)-1); peak=np.maximum.accumulate(wealth)
        return {'cagr':cagr,'max_drawdown':float((wealth/peak-1).min())}
    a,b=perf('net'),perf('matched')
    return {'months':len(x),'xle_participation':w,'candidate':a,'matched':b,'excess_cagr_pp':(a['cagr']-b['cagr'])*100}
windows={k:stats(v) for k,v in {'2012_plus':'2012-01-31','2018_plus':'2018-01-31','2022_plus':'2022-01-31'}.items()}
blocks={k:stats(a,z) for k,(a,z) in {'2012_2015':('2012-01-31','2015-12-31'),'2016_2019':('2016-01-31','2019-12-31'),'2020_2022':('2020-01-31','2022-12-31'),'2023_plus':('2023-01-31',None)}.items()}
pos=sum(v['excess_cagr_pp']>0 for v in blocks.values())
supported=all(v['excess_cagr_pp']>0 for v in windows.values()) and pos>=3 and windows['2012_plus']['candidate']['max_drawdown']>=windows['2012_plus']['matched']['max_drawdown']-.05
decision='DBC_XLE_SHOCK_SUPPORTED' if supported else 'DBC_XLE_SHOCK_REJECTED'
out={'schema':'research.dbc_xle_shock_r1.v1','decision':decision,'claim':'A completed-month broad commodity shock predicts next-month energy-equity excess beyond static XLE/SPY exposure after costs.','causal_information_time':'DBC monthly return is known only after completed month-end; allocation applies to following month.','mechanism':'if prior completed-month DBC return >=5%, hold XLE next month; otherwise SPY.','cost_one_way':COST,'matched_control':'static XLE/SPY mixture matched to realized XLE participation in each evaluation slice','strongest_non_alpha_explanation':'commodity shocks merely coincide with unconditional energy beta/regime luck; static XLE/SPY exposure explains returns without timing information','nearest_prior_art_and_distinction':'Distinct from GLD absolute trend, sector dispersion/reversal, sector overnight gaps, SPY gap/volume/calendar/VIX, and P186 price momentum: causal input is broad commodity inflation shock and target is next-month energy-sector relative return.','support_rule':'positive after-cost excess in 2012+, 2018+, 2022+; >=3/4 positive chronology blocks; 2012+ drawdown no worse than matched control by >5pp','protected_boundary':'no DBC threshold/ticker/substitute commodity/energy ETF/horizon/cost/date/control/block rescue','opportunity_cost':'one A child; reject releases commodity-shock-to-energy timing lineage','windows':windows,'blocks':blocks,'positive_blocks':pos,'scientific_consequence':'Support advances only to independent replication; reject releases lineage without nearby rescue.'}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print('RESULT_JSON='+json.dumps(out,sort_keys=True))