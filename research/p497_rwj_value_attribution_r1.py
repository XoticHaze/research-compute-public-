from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
OUT=Path('research/artifacts/p497_rwj_value_attribution_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
TICKERS=['RWJ','IJR','IWN','SPY']; COST=.0025
WINDOWS={'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2010_2014':('2010-01-04','2014-12-31'),'2015_2019':('2015-01-02','2019-12-31'),'2020_plus':('2020-01-02',None)}
raw=yf.download(TICKERS,start='2010-01-01',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
close=close[TICKERS].dropna(how='all')
def cagr(series,start,end=None):
 s=series.loc[series.index>=pd.Timestamp(start)]
 if end: s=s.loc[s.index<=pd.Timestamp(end)]
 s=s.dropna()
 if len(s)<2:return None
 years=(s.index[-1]-s.index[0]).days/365.2425
 if years<=0:return None
 return float((s.iloc[-1]/s.iloc[0])**(1/years)-1-COST/years)
def row(start,end=None):
 vals={t:cagr(close[t],start,end) for t in TICKERS}
 return {**vals,'rwj_minus_ijr':vals['RWJ']-vals['IJR'] if vals['RWJ'] is not None and vals['IJR'] is not None else None,'rwj_minus_iwn':vals['RWJ']-vals['IWN'] if vals['RWJ'] is not None and vals['IWN'] is not None else None,'rwj_minus_spy':vals['RWJ']-vals['SPY'] if vals['RWJ'] is not None and vals['SPY'] is not None else None}
windows={k:row(v) for k,v in WINDOWS.items()}; blocks={k:row(a,b) for k,(a,b) in BLOCKS.items()}
window_value_positive=sum(1 for x in windows.values() if x['rwj_minus_iwn'] is not None and x['rwj_minus_iwn']>0)
block_value_positive=sum(1 for x in blocks.values() if x['rwj_minus_iwn'] is not None and x['rwj_minus_iwn']>0)
window_small_positive=sum(1 for x in windows.values() if x['rwj_minus_ijr'] is not None and x['rwj_minus_ijr']>0)
residual_supported=window_value_positive>=2 and block_value_positive>=2 and window_small_positive==3
decision='RWJ_REVENUE_SPECIFIC_EXCESS_SUPPORTED' if residual_supported else 'RWJ_EXCESS_NOT_DISTINCT_FROM_SMALL_VALUE'
out={'schema':'research.p497_rwj_value_attribution_r1.v1','parent':'REVENUE_WEIGHTING_FUND_FAMILY','workload_id':'P497_RWJ_VALUE_ATTRIBUTION_R1','claim':'Orthogonal falsifier of the supported RWJ matched-small-cap result: determine whether RWJ after-cost excess survives a conventional small-cap-value control (IWN), not merely broad small-cap IJR. Fixed windows/blocks, no product substitution or date rescue.','contract':{'candidate':'RWJ','matched_smallcap':'IJR','value_control':'IWN','broad_opportunity_control':'SPY','endpoint_cost_bps':25,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'RWJ must retain positive after-cost excess over IWN in >=2/3 fixed windows and >=2/3 chronology blocks, while remaining positive vs IJR in all 3 fixed windows.'},'windows':windows,'blocks':blocks,'summary':{'positive_value_windows':window_value_positive,'positive_value_blocks':block_value_positive,'positive_smallcap_windows':window_small_positive},'decision':decision,'scientific_consequence':'If unsupported, retain RWJ matched-small-cap evidence only as value-like exposure and do not call revenue weighting a distinct alpha mechanism; if supported, preserve revenue-specific residual hypothesis for later factor regression/implementation testing.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':out['summary'],'windows':{k:{m:round(v[m]*100,3) for m in ['rwj_minus_ijr','rwj_minus_iwn','rwj_minus_spy']} for k,v in windows.items()},'blocks':{k:{m:round(v[m]*100,3) for m in ['rwj_minus_iwn']} for k,v in blocks.items()}},sort_keys=True))
