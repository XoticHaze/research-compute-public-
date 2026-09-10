from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY']; START='2015-01-01'; END='2026-09-10'; LB=24
BLOCKS={'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01','2026-09-10')}
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False);close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna();r=close.resample('ME').last().pct_change().dropna()
# Freeze P305 excess identity: 50/50 SPMO+IJS minus 50/50 SPY+IJR. No weight/search changes.
p305=.5*(r.SPMO+r.IJS)-.5*(r.SPY+r.IJR)
# Freeze P365 bank-loan matched-control logic for SRLN.
bs=[]
for i in range(len(r)):
 if i<LB:bs.append((np.nan,np.nan));continue
 b=np.linalg.lstsq(r[['HYG','SHY']].iloc[i-LB:i].values,r.SRLN.iloc[i-LB:i].values,rcond=None)[0];b=np.clip(b,0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['b_hyg','b_shy']).shift(1);loan=r.SRLN-(b.b_hyg*r.HYG+b.b_shy*r.SHY)
x=pd.DataFrame({'p305_excess':p305,'loan_excess':loan}).dropna()
def corr(q):return float(q.p305_excess.corr(q.loan_excess)) if len(q)>=6 else None
blocks={}
for n,(a,z) in BLOCKS.items():
 q=x.loc[(x.index>=pd.Timestamp(a))&(x.index<=pd.Timestamp(z))];blocks[n]={'months':len(q),'correlation':corr(q),'p305_mean_ann':float(q.p305_excess.mean()*12),'loan_mean_ann':float(q.loan_excess.mean()*12)}
overall=corr(x);pass_blocks=sum(abs(v['correlation'])<0.4 for v in blocks.values());supported=abs(overall)<0.4 and pass_blocks>=2
res={'schema':'research.p372_bankloan_p305_complementarity_r1','parent':'P305_PLUS_FLOATING_RATE_BANK_LOAN_RESEARCH_COMBINATION','claim':'Scientific complementarity test only, not allocation/ranking: freeze the P305 50/50 SPMO+IJS matched excess and the P365 SRLN causal HYG+SHY residual, then test return-source correlation overall and in three non-overlapping blocks. No weights, products, controls, dates, horizons or thresholds searched.','contract':{'P305_excess':'0.5*(SPMO+IJS)-0.5*(SPY+IJR)','bankloan_excess':'SRLN minus lagged 24m HYG+SHY causal matched control','gate':'abs overall correlation <0.4 and at least 2/3 block abs correlations <0.4','blocks':BLOCKS},'overall_correlation':overall,'blocks':blocks,'block_pass_count':pass_blocks,'decision':'P372_BANKLOAN_P305_COMPLEMENTARITY_SUPPORTED' if supported else 'P372_BANKLOAN_P305_COMPLEMENTARITY_NOT_SUPPORTED','scientific_consequence':'Pass supports genuinely distinct scientific return sources suitable for later portfolio-authority evaluation; it does not choose weights or rank portfolios. Failure keeps both prior survivors but rejects an independence claim.','limitations':['Yahoo adjusted-price representation','SRLN history limits common sample','correlation is linear dependence only'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p372_bankloan_p305_complementarity_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(res,sort_keys=True))
