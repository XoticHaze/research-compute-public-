from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
FUNDS=['BKLN','SRLN']; CTRLS=['HYG','SHY']; ALL=FUNDS+CTRLS
START='2013-01-01'; END='2026-09-10'; COST_BP=10; LOOKBACK=24
BLOCKS={'2015_2018':('2015-01-01','2018-12-31'),'2019_2022':('2019-01-01','2022-12-31'),'2023_plus':('2023-01-01','2026-09-10')}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()
def metrics(q):
 q=pd.Series(q,dtype=float).dropna(); n=len(q)
 if n<2:return {'months':int(n),'cagr':None,'maxdd':None,'sharpe_rf0':None}
 eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
 return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
out={}
for fund in FUNDS:
 fr=r[fund]; X=r[CTRLS]; bs=[]
 for i in range(len(r)):
  if i<LOOKBACK:bs.append((np.nan,np.nan));continue
  b=np.linalg.lstsq(X.iloc[i-LOOKBACK:i].values,fr.iloc[i-LOOKBACK:i].values,rcond=None)[0]; b=np.clip(b,0,1)
  if b.sum()>1:b=b/b.sum()
  bs.append((float(b[0]),float(b[1])))
 b=pd.DataFrame(bs,index=r.index,columns=['b_hyg','b_shy']).shift(1); bench=b.b_hyg*r.HYG+b.b_shy*r.SHY
 x=pd.DataFrame({'fund':fr,'bench':bench,'HYG':r.HYG,'SHY':r.SHY}).dropna()
 if len(x):
  f=COST_BP/10000; x.iloc[0,x.columns.get_loc('fund')]-=f; x.iloc[-1,x.columns.get_loc('fund')]-=f
 blocks={}
 for name,(a,z) in BLOCKS.items():
  q=x.loc[(x.index>=pd.Timestamp(a))&(x.index<=pd.Timestamp(z))]; fm,bm,hm=metrics(q.fund),metrics(q.bench),metrics(q.HYG)
  blocks[name]={'fund':fm,'matched':bm,'HYG':hm,'matched_excess_cagr':fm['cagr']-bm['cagr'],'vs_HYG_cagr':fm['cagr']-hm['cagr']}
 out[fund]=blocks
block_pass={b: all(out[f][b]['matched_excess_cagr']>0 for f in FUNDS) for b in BLOCKS}; passes=sum(block_pass.values()); supported=passes==3
decision='P366_BANK_LOAN_TEMPORAL_STABILITY_SUPPORTED' if supported else 'P366_BANK_LOAN_TEMPORAL_STABILITY_NOT_BROAD'
res={'schema':'research.p366_bank_loan_calendar_blocks_r1','parent':'P363_P365_FLOATING_RATE_BANK_LOAN_PREMIUM','claim':'Orthogonal temporal-stability falsifier for the already-supported BKLN and SRLN bank-loan implementations. Freeze each prior 24-month HYG+SHY causal matched-control formulation and evaluate non-overlapping 2015-2018, 2019-2022, and 2023+ blocks. No fund, beta-window, cost, date, threshold, allocation or benchmark search.','contract':{'funds':FUNDS,'blocks':BLOCKS,'gate':'both independent implementations have positive matched excess in all three non-overlapping blocks','endpoint_cost_bps':COST_BP},'results':out,'block_pass':block_pass,'block_pass_count':passes,'decision':decision,'scientific_consequence':'Pass upgrades the replicated bank-loan signal with non-overlapping temporal stability. Failure narrows the family to the supported blocks/regimes while preserving prior implementation evidence; do not parameter-rescue.','limitations':['Yahoo adjusted-price representation','calendar blocks are not macro regime labels','matched controls omit loan recovery/seniority/liquidity/reset mechanics'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p366_bank_loan_calendar_blocks_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
