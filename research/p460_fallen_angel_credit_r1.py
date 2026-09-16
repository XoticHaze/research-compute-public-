from __future__ import annotations
import json,math
from pathlib import Path
import pandas as pd,yfinance as yf
T=['ANGL','FALN','HYG','SPY']; START='2012-01-01'; END='2026-09-11'; COST=.001
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw; r=c[T].resample('ME').last().pct_change(fill_method=None)
WINDOWS=['2013-01-01','2018-01-01','2020-01-01','2022-01-01']
def stats(s):
 x=s.dropna().copy()
 if len(x)<24:return None
 x.iloc[0]-=COST; x.iloc[-1]-=COST; w=(1+x).cumprod(); n=len(x); vol=x.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def pair(t,start):
 z=r[[t,'HYG']].loc[start:].dropna(); a=stats(z[t]); b=stats(z.HYG)
 if not a or not b:return None
 return {'candidate':a,'hyg':b,'after_cost_excess_cagr':a['cagr']-b['cagr']}
res={t:{s:pair(t,s) for s in WINDOWS} for t in ['ANGL','FALN']}
# Common chronology since FALN is available: split monthly common history into three contiguous blocks.
q=r[['ANGL','FALN','HYG']].dropna(); n=len(q); sizes=[n//3,n//3,n-2*(n//3)]; blocks=[]; off=0
for i,sz in enumerate(sizes,1):
 z=q.iloc[off:off+sz]; off+=sz
 blocks.append({'block':i,'start':str(z.index[0].date()),'end':str(z.index[-1].date()),'ANGL':pair_block(z,'ANGL') if False else None})
def block_pair(z,t):
 a=stats(z[t]); b=stats(z.HYG); return {'candidate':a,'hyg':b,'after_cost_excess_cagr':a['cagr']-b['cagr']}
blocks=[]; off=0
for i,sz in enumerate(sizes,1):
 z=q.iloc[off:off+sz]; off+=sz; blocks.append({'block':i,'start':str(z.index[0].date()),'end':str(z.index[-1].date()),'ANGL':block_pair(z,'ANGL'),'FALN':block_pair(z,'FALN')})
pos={t:sum(b[t]['after_cost_excess_cagr']>0 for b in blocks) for t in ['ANGL','FALN']}
fixed_positive={t:sum(1 for s in WINDOWS if res[t][s] and res[t][s]['after_cost_excess_cagr']>0) for t in ['ANGL','FALN']}
supported=(fixed_positive['ANGL']>=3 and pos['ANGL']>=2 and fixed_positive['FALN']>=2 and pos['FALN']>=2)
decision='FALLEN_ANGEL_CREDIT_PREMIUM_SUPPORTED' if supported else 'FALLEN_ANGEL_CREDIT_PREMIUM_NOT_SUPPORTED'
out={'schema':'research.p460_fallen_angel_credit_r1.v1','workload_id':'P460_FALLEN_ANGEL_CREDIT_R1','claim':'Prospectively test fallen-angel high-yield credit as a distinct liquid fund alpha architecture using ANGL and independent FALN against matched broad high-yield HYG, fixed 10bp endpoint friction, fixed long windows and common-history chronology. No fund/date/cost/threshold tuning.','contract':{'candidates':['ANGL','FALN'],'matched_control':'HYG','broad_market_context':'SPY not used as matched credit control','windows':WINDOWS,'endpoint_cost_bps':10,'no_parameter_search':True},'fixed_windows':res,'common_history':{'months':n,'start':str(q.index[0].date()),'end':str(q.index[-1].date()),'blocks':blocks},'positive_fixed_windows':fixed_positive,'positive_chronology_blocks':pos,'decision_rule':'Support only if ANGL has positive after-cost HYG excess in >=3/4 fixed windows and >=2/3 common chronology blocks, while independent FALN is positive in >=2 eligible fixed windows and >=2/3 chronology blocks.','decision':decision,'scientific_consequence':('Preserve fallen-angel credit as an independent candidate family for direct opportunity-cost/complementarity testing; do not optimize fund weights.' if supported else 'Rotate away from simple fallen-angel ETF credit premium without product/date/cost rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p460_fallen_angel_credit_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'positive_fixed_windows':fixed_positive,'positive_blocks':pos,'ANGL_latest_excess_pp':round(100*res['ANGL']['2022-01-01']['after_cost_excess_cagr'],3) if res['ANGL']['2022-01-01'] else None,'FALN_latest_excess_pp':round(100*res['FALN']['2022-01-01']['after_cost_excess_cagr'],3) if res['FALN']['2022-01-01'] else None},sort_keys=True))
