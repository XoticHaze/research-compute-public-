from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p520_breakeven_inflation_allocation_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
WINDOWS={'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2010_2013':('2010-01-04','2013-12-31'),'2014_2017':('2014-01-02','2017-12-29'),'2018_2021':('2018-01-02','2021-12-31'),'2022_plus':('2022-01-03',None)}
px=yf.download(['SPY','DBC'],start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
close=(px['Close'] if isinstance(px.columns,pd.MultiIndex) else px)[['SPY','DBC']].resample('ME').last().dropna()
bei=pd.read_csv('https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE')
date_col='DATE' if 'DATE' in bei.columns else ('observation_date' if 'observation_date' in bei.columns else bei.columns[0])
bei[date_col]=pd.to_datetime(bei[date_col]); bei['T10YIE']=pd.to_numeric(bei['T10YIE'],errors='coerce'); bei=bei.dropna().set_index(date_col)['T10YIE'].resample('ME').last()
# Distinct independent source validation of the inflation-state clue: rising 10y breakeven over the completed prior 6 months -> DBC next month, otherwise SPY.
sig=(bei.diff(6)>0).astype(float).shift(1)
r=close.pct_change(fill_method=None)
frame=r.join(sig.rename('commodity'),how='inner').dropna()
frame['strategy']=frame['commodity']*frame['DBC']+(1-frame['commodity'])*frame['SPY']
frame['switch']=frame['commodity'].diff().abs().fillna(0)
frame['strategy_net']=frame['strategy']-frame['switch']*COST

def stats(start,end=None):
    x=frame.loc[frame.index>=pd.Timestamp(start)]
    if end: x=x.loc[x.index<=pd.Timestamp(end)]
    if len(x)<12: raise RuntimeError(f'insufficient rows {start} {end}: {len(x)}')
    w=float(x['commodity'].mean()); x=x.copy(); x['matched']=w*x['DBC']+(1-w)*x['SPY']
    def perf(col):
        rr=x[col].to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/12
        cagr=float(wealth[-1]**(1/yrs)-1); peak=np.maximum.accumulate(wealth); dd=wealth/peak-1
        vol=float(np.std(rr,ddof=1)*np.sqrt(12)); sharpe=float(np.mean(rr)*12/vol) if vol>0 else None
        return {'cagr':cagr,'max_drawdown':float(dd.min()),'annualized_vol':vol,'sharpe':sharpe}
    ps,pm,pp=perf('strategy_net'),perf('matched'),perf('SPY')
    return {'months':int(len(x)),'mean_commodity_weight':w,'switches':int((x['switch']>0).sum()),'strategy':ps,'matched_static':pm,'spy':pp,'excess_vs_matched_cagr':ps['cagr']-pm['cagr'],'excess_vs_spy_cagr':ps['cagr']-pp['cagr'],'drawdown_improvement_vs_spy':ps['max_drawdown']-pp['max_drawdown']}

w={k:stats(v) for k,v in WINDOWS.items()}; b={k:stats(a,z) for k,(a,z) in BLOCKS.items()}
summary={'positive_vs_matched_windows':sum(v['excess_vs_matched_cagr']>0 for v in w.values()),'positive_vs_spy_windows':sum(v['excess_vs_spy_cagr']>0 for v in w.values()),'positive_vs_matched_blocks':sum(v['excess_vs_matched_cagr']>0 for v in b.values()),'drawdown_improved_windows':sum(v['drawdown_improvement_vs_spy']>0 for v in w.values())}
supported=summary['positive_vs_matched_windows']==3 and summary['positive_vs_spy_windows']>=2 and summary['positive_vs_matched_blocks']>=3 and summary['drawdown_improved_windows']>=2
decision='BREAKEVEN_INFLATION_ALPHA_SUPPORTED' if supported else 'BREAKEVEN_INFLATION_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p520_breakeven_inflation_allocation_r1.v1','workload_id':'P520_BREAKEVEN_INFLATION_ALLOCATION_R1','parent':'MARKET_IMPLIED_INFLATION_STATE','claim':'A market-implied inflation state using the completed-month six-month direction of 10-year breakeven inflation can improve after-cost SPY/DBC allocation beyond a matched static commodity exposure. This is an independent-source validation of the inflation-state clue, not a parameter rescue of P518.','contract':{'source':'FRED T10YIE market-implied 10-year breakeven inflation','signal':'commodity_on iff completed-month T10YIE minus its six-month-prior level > 0, applied one month later','assets':['SPY','DBC'],'switch_cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive vs matched static in 3/3 windows, positive vs SPY in >=2/3 windows, positive vs matched in >=3/4 chronology blocks, drawdown improvement in >=2/3 windows','no_source_signal_lookback_asset_window_cost_weight_or_threshold_search':True},'windows':w,'blocks':b,'summary':summary,'decision':decision,'scientific_consequence':'If supported, preserve as independent market-source evidence that inflation state has cross-asset timing value; if unsupported, do not rescue by changing breakeven horizon, lookback, threshold, assets, dates, costs, or weights.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{'vs_matched_pp':round(v['excess_vs_matched_cagr']*100,3),'vs_spy_pp':round(v['excess_vs_spy_cagr']*100,3),'dd_improve_pp':round(v['drawdown_improvement_vs_spy']*100,3),'commodity_weight':round(v['mean_commodity_weight'],3)} for k,v in w.items()},'blocks':{k:round(v['excess_vs_matched_cagr']*100,3) for k,v in b.items()}},sort_keys=True))
