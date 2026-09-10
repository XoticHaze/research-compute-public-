from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf
CANDIDATE='HYD'; MATCHED='MUB'; BROAD='AGG'; COST_BPS=25; START='2011-01-01'
def stats(s):
 s=s.dropna(); r=s.pct_change().dropna(); years=(s.index[-1]-s.index[0]).days/365.25; wealth=(s.iloc[-1]/s.iloc[0])*(1-COST_BPS/10000.0)**2
 cagr=wealth**(1/years)-1; curve=s/s.iloc[0]; dd=(curve/curve.cummax()-1).min(); sh=(r.mean()/r.std()*math.sqrt(252)) if r.std()>0 else float('nan')
 return {'start':str(s.index[0].date()),'end':str(s.index[-1].date()),'n':int(len(s)),'cagr':float(cagr),'max_drawdown':float(dd),'sharpe':float(sh)}
x=yf.download([CANDIDATE,MATCHED,BROAD],start=START,auto_adjust=True,progress=False,threads=False)
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x; px=c.dropna()
windows=['2012-01-01','2015-01-01','2020-01-01']; res={}
for st in windows:
 z=px.loc[st:]; cs,ms,bs=stats(z[CANDIDATE]),stats(z[MATCHED]),stats(z[BROAD]); res[st]={'candidate':cs,'matched':ms,'broad':bs,'matched_excess_cagr':cs['cagr']-ms['cagr'],'broad_excess_cagr':cs['cagr']-bs['cagr']}
blocks=[('2012-01-01','2014-12-31'),('2015-01-01','2017-12-31'),('2018-01-01','2020-12-31'),('2021-01-01','2023-12-31'),('2024-01-01','2026-12-31')]; folds=[]
for a,b in blocks:
 z=px.loc[a:b]
 if len(z)<120: continue
 cs,ms=stats(z[CANDIDATE]),stats(z[MATCHED]); folds.append({'start':a,'end':b,'candidate_cagr':cs['cagr'],'matched_cagr':ms['cagr'],'excess_cagr':cs['cagr']-ms['cagr'],'positive':cs['cagr']>ms['cagr'],'candidate_max_drawdown':cs['max_drawdown'],'matched_max_drawdown':ms['max_drawdown']})
pos=sum(x['positive'] for x in folds); pass_gate=all(res[x]['matched_excess_cagr']>0 for x in windows) and len(folds)>=5 and pos>=4
out={'schema':'research.p379_hy_muni_premium.v1','workload_id':'P379_HY_MUNI_PREMIUM_R1','claim':'Test whether fixed high-yield municipal bond fund HYD delivers durable after-cost excess versus investment-grade municipal fund MUB, with AGG as broad fixed-income opportunity-cost context.','candidate':'HYD','matched_control':'MUB','broad_control':'AGG','cost_bps_each_endpoint':COST_BPS,'fixed_windows':res,'chronological_blocks':folds,'positive_matched_blocks':pos,'decision_rule':'PASS only if after-cost matched excess CAGR is positive from 2012+, 2015+, and 2020+, and at least 4/5 fixed non-overlapping chronological blocks have positive matched excess. Report drawdown; no ticker/window/cost tuning.','decision':'HY_MUNI_PREMIUM_SUPPORTED' if pass_gate else 'HY_MUNI_PREMIUM_NOT_SUPPORTED','scientific_consequence':('Preserve HYD as implementation-level high-yield municipal premium evidence; require independent implementation or source before broad family support.' if pass_gate else 'Reject this fixed high-yield muni premium formulation without parameter rescue; distinguish any isolated regime/risk-shaping evidence.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p379_hy_muni_premium_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_matched_blocks':pos,'matched_excess':{k:res[k]['matched_excess_cagr'] for k in windows}},sort_keys=True))
