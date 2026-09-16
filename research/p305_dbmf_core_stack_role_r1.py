from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SPMO','IJS','SPY','IJR','DBMF','BIL','SRLN','HYG','SHY']; START='2015-01-01'; END='2026-09-10'; LB=24; EP=.0025
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().dropna().pct_change().dropna()
p305=.5*(r.SPMO+r.IJS); p305ctl=.5*(r.SPY+r.IJR); challenger=.5*p305+.5*r.DBMF; challenger_ctl=.5*p305ctl+.5*r.BIL
bs=[]
for i in range(len(r)):
    if i<LB: bs.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(r[['HYG','SHY']].iloc[i-LB:i].values,r.SRLN.iloc[i-LB:i].values,rcond=None)[0]; b=np.clip(b,0,1)
    if b.sum()>1:b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1); loanctl=b.hyg*r.HYG+b.shy*r.SHY
core=.5*p305+.5*r.SRLN; corectl=.5*p305ctl+.5*loanctl
x=pd.DataFrame({'p305':p305,'dbmf':r.DBMF,'challenger':challenger,'challenger_ctl':challenger_ctl,'core':core,'core_ctl':corectl}).dropna().loc['2020-01-01':]
def ep(s):
    y=s.copy()
    if len(y):y.iloc[0]-=EP;y.iloc[-1]-=EP
    return y
def stats(s):
    q=ep(pd.Series(s,dtype=float).dropna()); n=len(q)
    if n<2:return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None,'vol':None}
    w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12); ann=q.mean()*12
    return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min()),'vol':float(vol)}
def corr(a,b):
    z=pd.concat([a,b],axis=1).dropna(); v=z.iloc[:,0].corr(z.iloc[:,1]) if len(z)>=3 else np.nan
    return float(v) if pd.notna(v) else None
def roll_excess(q,n=12):
    a=(1+q.challenger).rolling(n).apply(np.prod,raw=True)-1; b=(1+q.challenger_ctl).rolling(n).apply(np.prod,raw=True)-1; z=(a-b).dropna()
    return {'windows':len(z),'positive_fraction':float((z>0).mean()) if len(z) else None,'median_excess':float(z.median()) if len(z) else None,'worst_excess':float(z.min()) if len(z) else None}
def ev(q):
    ch,ctl,co,coctl=stats(q.challenger),stats(q.challenger_ctl),stats(q.core),stats(q.core_ctl); neg=q.loc[q.core<0]
    return {'challenger':ch,'matched_control':ctl,'core_stack':co,'core_stack_control':coctl,'challenger_matched_excess_cagr':ch['cagr']-ctl['cagr'] if ch['cagr'] is not None else None,'core_matched_excess_cagr':co['cagr']-coctl['cagr'] if co['cagr'] is not None else None,'opportunity_cost_vs_core':{'cagr_delta':ch['cagr']-co['cagr'],'sharpe_delta':ch['sharpe']-co['sharpe'],'maxdd_delta':ch['max_drawdown']-co['max_drawdown']},'correlation':{'challenger_core':corr(q.challenger,q.core),'dbmf_p305':corr(q.dbmf,q.p305)},'downside_corr_when_core_negative':corr(neg.challenger,neg.core),'rolling_12m_matched_excess':roll_excess(q)}
blocks={'2020_2021':('2020-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
full=ev(x); sub={k:ev(x.loc[a:b]) for k,(a,b) in blocks.items()}; coverage=all(v['challenger']['months']>=12 for v in sub.values()); pos=sum((v['challenger_matched_excess_cagr'] or -1)>0 for v in sub.values()); opp=full['opportunity_cost_vs_core']; roll=full['rolling_12m_matched_excess']
if coverage and full['challenger_matched_excess_cagr']>0 and pos>=2 and roll['positive_fraction'] is not None and roll['positive_fraction']>=.65 and (opp['cagr_delta']>0 or opp['sharpe_delta']>0 or opp['maxdd_delta']>0): decision='MARGINAL_PORTFOLIO_UTILITY_SUPPORTED'
elif coverage and full['challenger_matched_excess_cagr']>0 and opp['cagr_delta']<0 and opp['sharpe_delta']<0 and opp['maxdd_delta']<=0: decision='SHADOW_ONLY_OPPORTUNITY_COST_DOMINATED'
elif not coverage: decision='NEEDS_CONFIRMATION_COVERAGE'
else: decision='NEEDS_CONFIRMATION'
out={'schema':'research.p305_dbmf_core_stack_role_r1','workload_id':'P305_DBMF_PORTFOLIO_ROLE_R1','claim':'Test whether frozen 50% P305 + 50% DBMF provides marginal after-cost utility versus the established P249/P373 core stack without weight/product/window/cost rescue.','contract':{'challenger':'50% P305 + 50% DBMF','p305':'50% SPMO + 50% IJS','p305_control':'50% SPY + 50% IJR','dbmf_control':'BIL','core_stack':'50% P249/P305 representation + 50% P373 SRLN','p373_control':'causal prior-24m HYG+SHY','endpoint_cost_bps_each':25,'blocks':blocks},'full_sample':full,'chronology':sub,'coverage_ok':coverage,'positive_challenger_blocks':pos,'decision_rule':'Support marginal utility only with valid chronology, positive matched excess full sample and >=2/3 blocks, >=65% positive rolling 12m matched excess, and at least one CAGR/Sharpe/maxDD improvement versus the fixed core stack. No rescue.','decision':decision,'scientific_consequence':'Preserve P305 and DBMF standalone/family evidence regardless of portfolio-role result. Coordinator retains ranking and allocation authority.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p305_dbmf_core_stack_role_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'months':full['challenger']['months'],'matched_excess_pp':round(100*full['challenger_matched_excess_cagr'],3),'opportunity_cost_vs_core':{k:round(v,4) for k,v in opp.items()},'rolling_positive_fraction':roll['positive_fraction']},sort_keys=True))