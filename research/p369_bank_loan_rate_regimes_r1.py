from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
FUNDS=['BKLN','SRLN']; ALL=FUNDS+['HYG','SHY','IEF']; START='2013-01-01'; END='2026-09-10'; LB=24; COST=10
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()
# State is fixed ex ante from prior six completed monthly IEF returns. Negative six-month IEF return is rate-up proxy; nonnegative is rate-down/flat proxy. State is lagged one month.
state=(close['IEF'].resample('ME').last().pct_change(6)<0).shift(1).rename('rate_up_proxy')
def m(q):
 q=pd.Series(q,dtype=float).dropna(); n=len(q)
 if n<2:return {'months':int(n),'cagr':None,'mean_monthly':None,'maxdd':None}
 e=(1+q).cumprod(); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'mean_monthly':float(q.mean()),'maxdd':float((e/e.cummax()-1).min())}
out={}
for fund in FUNDS:
 fr=r[fund]; X=r[['HYG','SHY']]; bs=[]
 for i in range(len(r)):
  if i<LB:bs.append((np.nan,np.nan));continue
  b=np.linalg.lstsq(X.iloc[i-LB:i].values,fr.iloc[i-LB:i].values,rcond=None)[0];b=np.clip(b,0,1)
  if b.sum()>1:b=b/b.sum()
  bs.append(tuple(map(float,b)))
 b=pd.DataFrame(bs,index=r.index,columns=['b_hyg','b_shy']).shift(1); bench=b.b_hyg*r.HYG+b.b_shy*r.SHY
 x=pd.concat([fr.rename('fund'),bench.rename('bench'),state],axis=1).dropna();f=COST/10000
 if len(x):x.iloc[0,x.columns.get_loc('fund')]-=f;x.iloc[-1,x.columns.get_loc('fund')]-=f
 x['resid']=x.fund-x.bench
 regimes={}
 for key,mask in [('rate_up_proxy',x.rate_up_proxy.astype(bool)),('rate_down_or_flat_proxy',~x.rate_up_proxy.astype(bool))]:
  q=x.loc[mask]; resid=q.resid
  years=sorted(set(q.index.year)); yearly=[]
  for y in years:
   z=resid[q.index.year==y]
   if len(z)>=3:yearly.append(float(z.mean()))
  regimes[key]={'fund':m(q.fund),'matched':m(q.bench),'residual_mean_monthly':float(resid.mean()),'annualized_arithmetic_residual':float(resid.mean()*12),'positive_year_slices':sum(v>0 for v in yearly),'year_slice_count':len(yearly),'year_slice_means':yearly}
 out[fund]=regimes
# Mechanism gate is intentionally not "rate-up only". A durable family should retain positive residual in both states for both implementations; stronger rate-up residual is supportive mechanism context but not required.
all_positive=all(out[f][s]['residual_mean_monthly']>0 for f in FUNDS for s in ['rate_up_proxy','rate_down_or_flat_proxy'])
year_support=all(out[f][s]['positive_year_slices']>=max(1,math.ceil(out[f][s]['year_slice_count']/2)) for f in FUNDS for s in ['rate_up_proxy','rate_down_or_flat_proxy'])
rate_up_stronger=all(out[f]['rate_up_proxy']['residual_mean_monthly']>out[f]['rate_down_or_flat_proxy']['residual_mean_monthly'] for f in FUNDS)
supported=all_positive and year_support
res={'schema':'research.p369_bank_loan_rate_regimes_r1','parent':'P363_P365_P366_FLOATING_RATE_BANK_LOAN_PREMIUM','claim':'Mechanism-level orthogonal falsifier: freeze both supported bank-loan implementations and their causal HYG+SHY matched controls, then split residual returns by a prospectively fixed prior-six-month IEF sign as a market-price proxy for rising-rate versus falling/flat-rate states. No rate threshold, horizon, fund, benchmark, beta-window, cost, date, allocation or regime search.','contract':{'state':'prior 6-month IEF total return <0, lagged one month = rate_up_proxy','gate':'both BKLN and SRLN retain positive matched residual in both states and at least half available year slices are positive in each state','mechanism_context':'rate-up residual > rate-down residual is recorded but not required','endpoint_cost_bps':COST},'results':out,'all_state_residuals_positive':all_positive,'year_slice_support':year_support,'rate_up_residual_stronger_both':rate_up_stronger,'decision':'P369_BANK_LOAN_CROSS_RATE_STATE_STABILITY_SUPPORTED' if supported else 'P369_BANK_LOAN_RATE_STATE_WEAKNESS_DETECTED','scientific_consequence':'Pass strengthens the family as residual alpha not confined to one rate direction; whether rate-up is stronger informs mechanism only. Failure narrows supported scope to passing rate state(s) while preserving P363/P365/P366 evidence; no parameter rescue.','limitations':['IEF six-month return is a market-price proxy for rate direction, not a direct Treasury-yield series','Yahoo adjusted-price representation','state months are non-contiguous so CAGR is descriptive only; residual mean and year slices are primary','matched control omits recovery, liquidity, seniority and reset mechanics'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p369_bank_loan_rate_regimes_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(res,sort_keys=True))
