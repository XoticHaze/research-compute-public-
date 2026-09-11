from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p518_inflation_regime_allocation_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
WINDOWS={'2010_plus':'2010-01-04','2015_plus':'2015-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2010_2013':('2010-01-04','2013-12-31'),'2014_2017':('2014-01-02','2017-12-29'),'2018_2021':('2018-01-02','2021-12-31'),'2022_plus':('2022-01-03',None)}
px=yf.download(['SPY','DBC'],start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
close=(px['Close'] if isinstance(px.columns,pd.MultiIndex) else px)[['SPY','DBC']].resample('ME').last().dropna()
cpi=pd.read_csv('https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL')
cpi['DATE']=pd.to_datetime(cpi['DATE']); cpi['CPIAUCSL']=pd.to_numeric(cpi['CPIAUCSL'],errors='coerce'); cpi=cpi.dropna().set_index('DATE')['CPIAUCSL'].resample('ME').last()
# Signal definition is prospectively fixed: 6m CPI growth exceeds the preceding 6m growth = inflation acceleration.
# Two-month lag approximates publication availability conservatively before allocating the following month.
g6=cpi.pct_change(6); accel=(g6>g6.shift(6)).astype(float).shift(2)
r=close.pct_change(fill_method=None)
frame=r.join(accel.rename('inflation_accel'),how='inner').dropna()
frame['commodity_weight']=frame['inflation_accel']
frame['strategy']=frame['commodity_weight']*frame['DBC']+(1-frame['commodity_weight'])*frame['SPY']
frame['switch']=frame['commodity_weight'].diff().abs().fillna(0)
frame['strategy_net']=frame['strategy']-frame['switch']*COST

def stats(start,end=None):
    x=frame.loc[frame.index>=pd.Timestamp(start)]
    if end: x=x.loc[x.index<=pd.Timestamp(end)]
    if len(x)<12: raise RuntimeError(f'insufficient rows {start} {end}: {len(x)}')
    w=float(x['commodity_weight'].mean()); x=x.copy(); x['matched']=w*x['DBC']+(1-w)*x['SPY']
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
decision='INFLATION_REGIME_ALPHA_SUPPORTED' if supported else 'INFLATION_REGIME_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p518_inflation_regime_allocation_r1.v1','workload_id':'P518_INFLATION_REGIME_ALLOCATION_R1','parent':'MACRO_INFLATION_STATE','claim':'A publication-lagged inflation-acceleration state can improve after-cost SPY/DBC allocation beyond a static matched commodity exposure while preserving broad-market opportunity value.','contract':{'signal':'inflation acceleration when trailing 6m CPI growth > preceding 6m CPI growth','publication_lag_months':2,'assets':['SPY','DBC'],'switch_cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive vs matched static in 3/3 windows, positive vs SPY in >=2/3 windows, positive vs matched in >=3/4 chronology blocks, drawdown improvement in >=2/3 windows','no_signal_lag_asset_window_cost_weight_or_threshold_search':True},'windows':w,'blocks':b,'summary':summary,'decision':decision,'scientific_consequence':'Support only if the fixed publication-lagged macro signal survives matched exposure, chronology, costs, SPY opportunity cost and drawdown gates. Otherwise reject this exact inflation-regime architecture without lag or threshold rescue.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{'vs_matched_pp':round(v['excess_vs_matched_cagr']*100,3),'vs_spy_pp':round(v['excess_vs_spy_cagr']*100,3),'dd_improve_pp':round(v['drawdown_improvement_vs_spy']*100,3),'commodity_weight':round(v['mean_commodity_weight'],3)} for k,v in w.items()},'blocks':{k:round(v['excess_vs_matched_cagr']*100,3) for k,v in b.items()}},sort_keys=True))
