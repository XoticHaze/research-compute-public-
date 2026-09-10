from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf
CANDIDATE='MNA'; MATCHED='BIL'; BROAD='SPY'; COST_BPS=25; START='2011-01-01'
def stats(s):
 s=s.dropna(); r=s.pct_change().dropna(); years=(s.index[-1]-s.index[0]).days/365.25; wealth=(s.iloc[-1]/s.iloc[0])*(1-COST_BPS/10000.0)**2
 cagr=wealth**(1/years)-1; curve=s/s.iloc[0]; dd=(curve/curve.cummax()-1).min(); sh=(r.mean()/r.std()*math.sqrt(252)) if r.std()>0 else float('nan')
 return {'start':str(s.index[0].date()),'end':str(s.index[-1].date()),'n':int(len(s)),'cagr':float(cagr),'max_drawdown':float(dd),'sharpe':float(sh)}
x=yf.download([CANDIDATE,MATCHED,BROAD],start=START,auto_adjust=True,progress=False,threads=False); c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x; px=c.dropna()
windows=['2012-01-01','2015-01-01','2020-01-01']; res={}
for st in windows:
 z=px.loc[st:]; cs,ms,bs=stats(z[CANDIDATE]),stats(z[MATCHED]),stats(z[BROAD]); res[st]={'candidate':cs,'matched':ms,'broad':bs,'matched_excess_cagr':cs['cagr']-ms['cagr'],'broad_excess_cagr':cs['cagr']-bs['cagr']}
blocks=[('2012-01-01','2014-12-31'),('2015-01-01','2017-12-31'),('2018-01-01','2020-12-31'),('2021-01-01','2023-12-31'),('2024-01-01','2026-12-31')]; folds=[]
for a,b in blocks:
 z=px.loc[a:b]
 if len(z)<120: continue
 cs,ms=stats(z[CANDIDATE]),stats(z[MATCHED]); folds.append({'start':a,'end':b,'excess_cagr':cs['cagr']-ms['cagr'],'positive':cs['cagr']>ms['cagr'],'candidate_max_drawdown':cs['max_drawdown'],'matched_max_drawdown':ms['max_drawdown']})
pos=sum(x['positive'] for x in folds); pass_gate=all(res[x]['matched_excess_cagr']>0 for x in windows) and len(folds)>=5 and pos>=4
out={'schema':'research.p381_merger_arb_premium.v1','workload_id':'P381_MERGER_ARB_PREMIUM_R1','claim':'Test whether fixed merger-arbitrage ETF MNA delivers durable after-cost absolute-return excess over Treasury-bill fund BIL, with SPY only as opportunity-cost context.','candidate':'MNA','matched_control':'BIL','broad_control':'SPY','cost_bps_each_endpoint':COST_BPS,'fixed_windows':res,'chronological_blocks':folds,'positive_matched_blocks':pos,'decision_rule':'PASS only if after-cost matched excess CAGR is positive from 2012+, 2015+, and 2020+, and at least 4/5 fixed non-overlapping blocks are positive. No ticker/window/cost tuning.','decision':'MERGER_ARB_PREMIUM_SUPPORTED' if pass_gate else 'MERGER_ARB_PREMIUM_NOT_SUPPORTED','scientific_consequence':('Preserve MNA as implementation-level event-driven cash-plus evidence and require an independent merger-arbitrage implementation before family support.' if pass_gate else 'Reject the fixed MNA cash-plus formulation as durable all-window alpha; preserve any regime/risk evidence and rotate without parameter rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p381_merger_arb_premium_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_matched_blocks':pos,'matched_excess':{k:res[k]['matched_excess_cagr'] for k in windows}},sort_keys=True))
