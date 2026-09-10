from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

CANDIDATE='JAAA'; MATCHED='SGOV'; BROAD='SPY'; COST_BPS=25
START='2021-01-01'

def prices(tickers):
 x=yf.download(tickers,start=START,auto_adjust=True,progress=False,threads=False)
 c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
 if isinstance(c,pd.Series): c=c.to_frame(tickers[0])
 return c.dropna(how='all')
def stats(s,cost_bps=COST_BPS):
 s=s.dropna(); r=s.pct_change().dropna(); years=(s.index[-1]-s.index[0]).days/365.25
 wealth=(s.iloc[-1]/s.iloc[0])*(1-cost_bps/10000.0)**2
 cagr=wealth**(1/years)-1 if years>0 else float('nan')
 curve=s/s.iloc[0]; dd=(curve/curve.cummax()-1).min(); sh=(r.mean()/r.std()*math.sqrt(252)) if r.std()>0 else float('nan')
 return {'start':str(s.index[0].date()),'end':str(s.index[-1].date()),'n':int(len(s)),'cagr':float(cagr),'max_drawdown':float(dd),'sharpe':float(sh)}
px=prices([CANDIDATE,MATCHED,BROAD]).dropna()
windows=['2021-01-01','2022-01-01','2023-01-01']
res={}
for st in windows:
 z=px.loc[st:]
 cs,ms,bs=stats(z[CANDIDATE]),stats(z[MATCHED]),stats(z[BROAD])
 res[st]={'candidate':cs,'matched':ms,'broad':bs,'matched_excess_cagr':cs['cagr']-ms['cagr'],'broad_excess_cagr':cs['cagr']-bs['cagr']}
folds=[]
for y in [2021,2022,2023,2024,2025]:
 z=px.loc[f'{y}-01-01':f'{y}-12-31']
 if len(z)<120: continue
 cs,ms=stats(z[CANDIDATE]),stats(z[MATCHED])
 folds.append({'year':y,'candidate_cagr':cs['cagr'],'matched_cagr':ms['cagr'],'excess_cagr':cs['cagr']-ms['cagr'],'positive':cs['cagr']>ms['cagr']})
pos=sum(x['positive'] for x in folds)
# Fixed claim: a AAA CLO fund is a durable cash-plus premium only if it beats the matched Treasury cash fund
# after equal endpoint costs in every fixed start window and >=4/5 full-year folds.
pass_gate=all(res[x]['matched_excess_cagr']>0 for x in windows) and len(folds)>=5 and pos>=4
out={'schema':'research.p376_aaa_clo_premium.v1','workload_id':'P376_AAA_CLO_PREMIUM_R1','claim':'Test whether fixed AAA CLO fund JAAA delivers durable after-cost cash-plus excess versus matched 0-3 month Treasury fund SGOV, with SPY only as opportunity-cost context.','candidate':CANDIDATE,'matched_control':MATCHED,'broad_control':BROAD,'cost_bps_each_endpoint':COST_BPS,'data':'Yahoo Finance adjusted prices via yfinance','fixed_windows':res,'calendar_folds':folds,'positive_matched_folds':pos,'decision_rule':'PASS only if after-cost matched excess CAGR is positive from 2021+, 2022+, and 2023+, and at least 4 of five 2021-2025 calendar folds have positive matched excess. No ticker, window, weight, or cost tuning.','decision':'AAA_CLO_CASH_PLUS_PREMIUM_SUPPORTED' if pass_gate else 'AAA_CLO_CASH_PLUS_PREMIUM_NOT_SUPPORTED','scientific_consequence':('Preserve JAAA as implementation-level cash-plus alpha evidence and require an independent CLO implementation/source before broad family promotion.' if pass_gate else 'Reject this fixed JAAA cash-plus formulation without parameter rescue; preserve any risk-shaping observations separately.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p376_aaa_clo_premium_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_matched_folds':pos,'matched_excess':{k:res[k]['matched_excess_cagr'] for k in windows}},sort_keys=True))
