from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY']; START='2015-01-01'; END='2026-09-10'; LB=24; COST=0.001
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False); close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna(); r=close.resample('ME').last().pct_change().dropna()
# Freeze the current direct-utility core leader representation from P305/P249 evidence: equal 50/50 SPMO+IJS, with exact matched 50/50 SPY+IJR control. No weight search.
p249=.5*(r.SPMO+r.IJS); p249_ctl=.5*(r.SPY+r.IJR)
# Freeze replicated bank-loan survivor as SRLN and P365 causal 24m HYG+SHY control. No fund/control/window search.
bs=[]
for i in range(len(r)):
 if i<LB: bs.append((np.nan,np.nan)); continue
 b=np.linalg.lstsq(r[['HYG','SHY']].iloc[i-LB:i].values,r.SRLN.iloc[i-LB:i].values,rcond=None)[0]; b=np.clip(b,0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1); loan_ctl=b.hyg*r.HYG+b.shy*r.SHY
x=pd.DataFrame({'p249':p249,'p249_ctl':p249_ctl,'loan':r.SRLN,'loan_ctl':loan_ctl}).dropna(); x.iloc[0]-=COST; x.iloc[-1]-=COST
# Fixed equal-capital comparison is diagnostic only; no allocation authority. Opportunity role is judged by standalone utility and diversification evidence, not optimized weights.
def stats(s):
 wealth=(1+s).cumprod(); years=len(s)/12; cagr=float(wealth.iloc[-1]**(1/years)-1); vol=float(s.std()*np.sqrt(12)); sharpe=float(s.mean()*12/vol) if vol else None; dd=float((wealth/wealth.cummax()-1).min()); return {'cagr':cagr,'vol':vol,'sharpe':sharpe,'max_drawdown':dd}
windows={'2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}; outw={}
for n,a in windows.items():
 q=x.loc[x.index>=a]; ps=stats(q.p249); ls=stats(q.loan); pc=stats(q.p249_ctl); lc=stats(q.loan_ctl); outw[n]={'months':len(q),'p249':ps,'bank_loan':ls,'p249_matched':pc,'bank_loan_matched':lc,'p249_matched_excess_cagr':ps['cagr']-pc['cagr'],'bank_loan_matched_excess_cagr':ls['cagr']-lc['cagr'],'bank_loan_minus_p249_cagr':ls['cagr']-ps['cagr'],'bank_loan_minus_p249_sharpe':ls['sharpe']-ps['sharpe'],'bank_loan_minus_p249_drawdown':ls['max_drawdown']-ps['max_drawdown']}
# Incremental diversification: compare fixed 50/50 P249+loan against fixed 50/50 matched controls. This is scientific utility evidence, not a portfolio weight recommendation.
blend=.5*x.p249+.5*x.loan; blend_ctl=.5*x.p249_ctl+.5*x.loan_ctl; bs0=stats(blend); bc0=stats(blend_ctl); ps0=stats(x.p249); ls0=stats(x.loan)
# Predeclared role rule: DISPLACES only if loan beats P249 CAGR and Sharpe with no worse drawdown in 2/3 windows; COMPLEMENTS if loan retains positive matched excess in 2/3 windows and fixed blend has positive matched excess plus better Sharpe or drawdown than P249; otherwise standalone shadow/demoted caveat.
displace=sum(v['bank_loan_minus_p249_cagr']>0 and v['bank_loan_minus_p249_sharpe']>0 and v['bank_loan_minus_p249_drawdown']>=0 for v in outw.values())>=2
loan_alpha=sum(v['bank_loan_matched_excess_cagr']>0 for v in outw.values())>=2
blend_excess=bs0['cagr']-bc0['cagr']; complements=loan_alpha and blend_excess>0 and (bs0['sharpe']>ps0['sharpe'] or bs0['max_drawdown']>ps0['max_drawdown'])
role='DISPLACES' if displace else ('COMPLEMENTS' if complements else ('STANDALONE_SHADOW' if loan_alpha else 'DEMOTED_WITH_CAVEAT'))
res={'schema':'research.p373_bankloan_p249_opportunity_gate_r1','parent':'FLOATING_RATE_BANK_LOAN_PREMIUM_VS_P249','claim':'Frozen common-sample scientific opportunity-cost gate: replicated SRLN bank-loan survivor versus current P249 direct-utility core representation, with exact matched controls, risk-adjusted utility, downside and a fixed equal-capital blend diagnostic. No fund/control/window/cost/weight/threshold search.','cost_endpoint_each_side':COST,'windows':outw,'full_sample':{'p249':ps0,'bank_loan':ls0,'fixed_50_50_blend':bs0,'fixed_50_50_matched_control':bc0,'blend_matched_excess_cagr':blend_excess,'p249_bankloan_return_correlation':float(x.p249.corr(x.loan))},'decision':role,'decision_rule':'DISPLACES iff bank loan beats P249 CAGR+Sharpe with no worse drawdown in >=2/3 fixed windows; else COMPLEMENTS iff bank loan has positive own matched excess in >=2/3 windows and fixed 50/50 blend has positive matched excess plus improves P249 Sharpe or drawdown; else STANDALONE_SHADOW if own matched alpha persists, otherwise DEMOTED_WITH_CAVEAT.','scientific_consequence':'Scientific role evidence only. Preserve prior standalone survivor evidence on a portfolio-role failure. Coordinator owns any portfolio ranking/allocation consequence.','limitations':['Yahoo adjusted-price representation','SRLN common history starts later','fixed equal-capital blend is a diagnostic, not optimized allocation'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p373_bankloan_p249_opportunity_gate_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(res,sort_keys=True))
