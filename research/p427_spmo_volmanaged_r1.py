from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SPMO','BIL','SPY']; TARGET=.15; TURN_COST=.001; EP=.0025
raw=yf.download(T,start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
c=c[T].dropna(); dr=c.pct_change(fill_method=None)
month_end=c.resample('ME').last(); mr=month_end.pct_change(fill_method=None).dropna()
rv=dr.SPMO.rolling(63,min_periods=50).std()*np.sqrt(252)
rv_m=rv.resample('ME').last(); w=(TARGET/rv_m).clip(lower=0,upper=1).shift(1).reindex(mr.index).ffill()
q=pd.DataFrame(index=mr.index); q['w']=w; q['spmo']=mr.SPMO; q['bil']=mr.BIL; q['spy']=mr.SPY; q=q.dropna()
q['gross']=q.w*q.spmo+(1-q.w)*q.bil
q['turnover']=q.w.diff().abs().fillna(q.w.abs())
q['strategy']=q.gross-TURN_COST*q.turnover

def ep(s):
 y=s.copy()
 if len(y): y.iloc[0]-=EP; y.iloc[-1]-=EP
 return y
def stats(s):
 z=ep(s.dropna()); n=len(z)
 if n<3:return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None,'vol':None}
 wealth=(1+z).cumprod(); vol=z.std(ddof=1)*np.sqrt(12); ann=z.mean()*12
 return {'months':n,'cagr':float(wealth.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((wealth/wealth.cummax()-1).min()),'vol':float(vol)}
def reg(a,b,rf):
 z=pd.concat([a-rf,b-rf],axis=1).dropna(); z.columns=['y','x']
 if len(z)<12:return {'months':len(z),'beta':None,'alpha_pp_annual':None}
 X=np.column_stack([np.ones(len(z)),z.x.values]); coef=np.linalg.lstsq(X,z.y.values,rcond=None)[0]
 return {'months':len(z),'beta':float(coef[1]),'alpha_pp_annual':float(1200*coef[0])}
def ev(a,b=None):
 z=q.loc[a:b]; s=stats(z.strategy); base=stats(z.spmo); opp=stats(z.spy); rr=reg(z.strategy,z.spmo,z.bil)
 return {'strategy':s,'spmo_base':base,'spy_opportunity':opp,'regression':rr,'cagr_delta_vs_spmo_pp':100*(s['cagr']-base['cagr']),'sharpe_delta_vs_spmo':s['sharpe']-base['sharpe'],'maxdd_improvement_vs_spmo_pp':100*(s['max_drawdown']-base['max_drawdown']),'average_spmo_weight':float(z.w.mean()),'annualized_one_way_turnover':float(z.turnover.mean()*12)}
windows={k:ev(v) for k,v in {'2017+':'2017-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
blocks={k:ev(a,b) for k,(a,b) in {'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}.items()}
pos=sum(v['regression']['alpha_pp_annual'] is not None and v['regression']['alpha_pp_annual']>0 for v in blocks.values())
full=ev('2017-01-01'); supported=all(v['regression']['alpha_pp_annual'] is not None and v['regression']['alpha_pp_annual']>0 for v in windows.values()) and pos>=2 and full['maxdd_improvement_vs_spmo_pp']>=5
decision='SPMO_VOLATILITY_MANAGEMENT_SUPPORTED' if supported else 'SPMO_VOLATILITY_MANAGEMENT_NOT_SUPPORTED'
out={'schema':'research.p427_spmo_volmanaged_r1.v1','workload_id':'P427_SPMO_VOLMANAGED_R1','claim':'A fixed causal no-leverage 15% target-volatility overlay on SPMO, funded by BIL and charged explicit turnover plus endpoint costs, can add beta-adjusted alpha while improving drawdown versus unmodified SPMO.','contract':{'target_annual_vol':TARGET,'realized_vol_lookback_trading_days':63,'signal_lag_months':1,'max_spmo_weight':1.0,'turnover_cost_bps_per_one_way_dollar':10,'endpoint_cost_bps_each':25},'full':full,'windows':windows,'blocks':blocks,'positive_alpha_blocks':pos,'decision_rule':'SUPPORTED only if after-cost annualized regression alpha versus SPMO excess over BIL is positive in 2017+/2020+/2022+, >=2/3 fixed chronology blocks have positive alpha, and full max drawdown improves by >=5 pp. Lower beta alone cannot pass.','decision':decision,'scientific_consequence':('A causal risk-managed improvement to the SPMO survivor earns scoped support and requires an orthogonal source/parameter-free stress test.' if supported else 'Preserve SPMO survivor evidence unchanged; reject this exact 15%/63-day no-leverage volatility-management overlay and do not tune target vol or lookback to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p427_spmo_volmanaged_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'full_alpha_pp':round(full['regression']['alpha_pp_annual'],3),'full_cagr_delta_pp':round(full['cagr_delta_vs_spmo_pp'],3),'full_sharpe_delta':round(full['sharpe_delta_vs_spmo'],3),'full_maxdd_improvement_pp':round(full['maxdd_improvement_vs_spmo_pp'],3),'avg_weight':round(full['average_spmo_weight'],3),'annual_turnover':round(full['annualized_one_way_turnover'],3),'block_alpha_pp':[round(v['regression']['alpha_pp_annual'],3) for v in blocks.values()]},sort_keys=True))
