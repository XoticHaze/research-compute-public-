from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FUND='SRLN'; CONTROLS=['HYG','SHY']; ALL=[FUND]+CONTROLS
START='2013-01-01'; END='2026-09-10'; COST_BP=10; LOOKBACK=24
WINDOWS={'2015_plus':'2015-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()
def metrics(q):
    q=pd.Series(q,dtype=float).dropna(); n=len(q)
    if n<2:return {'months':int(n),'cagr':None,'maxdd':None,'sharpe_rf0':None}
    eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
fr=r[FUND]; X=r[CONTROLS]; betas=[]
for i in range(len(r)):
    if i<LOOKBACK: betas.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(X.iloc[i-LOOKBACK:i].values,fr.iloc[i-LOOKBACK:i].values,rcond=None)[0]; b=np.clip(b,0,1)
    if b.sum()>1:b=b/b.sum()
    betas.append((float(b[0]),float(b[1])))
b=pd.DataFrame(betas,index=r.index,columns=['b_hyg','b_shy']).shift(1); bench=b.b_hyg*r.HYG+b.b_shy*r.SHY
x=pd.concat([fr.rename('fund'),bench.rename('bench'),r.HYG,r.SHY,b],axis=1).dropna()
if len(x):
    f=COST_BP/10000; x.iloc[0,x.columns.get_loc('fund')]-=f; x.iloc[-1,x.columns.get_loc('fund')]-=f
rows={}
for name,start in WINDOWS.items():
    q=x.loc[x.index>=pd.Timestamp(start)]; a,c,h,s=metrics(q.fund),metrics(q.bench),metrics(q.HYG),metrics(q.SHY)
    folds=[]
    for ix in np.array_split(np.arange(len(q)),5):
        z=q.iloc[ix]
        if len(z)>=2:folds.append(metrics(z.fund)['cagr']-metrics(z.bench)['cagr'])
    rows[name]={'fund':a,'matched':c,'HYG':h,'SHY':s,'matched_excess_cagr':a['cagr']-c['cagr'],'vs_HYG_cagr':a['cagr']-h['cagr'],'positive_matched_folds':sum(v>0 for v in folds),'fold_excess_cagr':folds,'mean_hyg_beta':float(q.b_hyg.mean()),'mean_shy_beta':float(q.b_shy.mean())}
passes=sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in rows.values()); dd_guard=all(v['fund']['maxdd']>=v['matched']['maxdd']-0.03 for v in rows.values()); supported=passes==len(WINDOWS) and dd_guard
decision='P365_BANK_LOAN_IMPLEMENTATION_REPLICATION_SUPPORTED' if supported else 'P365_BANK_LOAN_IMPLEMENTATION_REPLICATION_NOT_CONFIRMED'
res={'schema':'research.p365_srln_bank_loan_replication_r1','parent':'P363_FLOATING_RATE_BANK_LOAN_PREMIUM','claim':'Independent implementation replication of the P363 floating-rate bank-loan claim using prospectively fixed SRLN and the unchanged causal 24-month HYG+SHY matched-control logic. No fund selection among peers, beta-window, clipping, cost, date, allocation, threshold or window search.','contract':{'fund':FUND,'matched_control':'lagged 24m OLS HYG+SHY weights clipped [0,1], normalized only when sum>1','endpoint_cost_bps':COST_BP,'windows':WINDOWS,'gate':'positive matched excess and >=3/5 positive chronology folds in every fixed window, drawdown no worse than matched by >3pp'},'results':rows,'window_pass_count':passes,'drawdown_guard_pass':dd_guard,'decision':decision,'scientific_consequence':'Pass materially strengthens the bank-loan premium family through independent investable implementation replication. Failure preserves P363 BKLN evidence as implementation-specific and rejects broad family promotion; do not search additional loan funds or tune controls.','limitations':['single predeclared replication fund SRLN','Yahoo adjusted-price representation','matched control approximates credit and short-rate exposure but not recovery, seniority, liquidity or floating-rate reset mechanics'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p365_srln_bank_loan_replication_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
