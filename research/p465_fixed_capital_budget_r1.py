from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY','JAAA','SGOV','AVDV','IDMO','VSS','EFA','DBMF','BIL']; W=.25; COST=.0025
raw=yf.download(T,start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False); c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None); p=.5*(r.SPMO+r.IJS); pc=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
 z=r[['HYG','SHY','SRLN']].iloc[max(0,i-24):i].dropna()
 if len(z)<24: bs.append((np.nan,np.nan)); continue
 b=np.clip(np.linalg.lstsq(z[['HYG','SHY']].values,z.SRLN.values,rcond=None)[0],0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(b))
b=pd.DataFrame(bs,index=r.index,columns=['h','s']).shift(1); lc=b.h*r.HYG+b.s*r.SHY
q=pd.DataFrame({'p':p,'pc':pc,'loan':r.SRLN,'lc':lc,'aaa':r.JAAA,'aaac':r.SGOV,'intl':.5*(r.AVDV+r.IDMO),'intlc':.5*(r.VSS+r.EFA),'dbmf':r.DBMF,'dbmfc':r.BIL}).dropna().loc['2021-01-01':]
def st(s):
 x=s.copy(); x.iloc[0]-=COST; x.iloc[-1]-=COST; w=(1+x).cumprod(); n=len(x); vol=x.std(ddof=1)*math.sqrt(12); neg=x[x<0].std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/vol),'max_drawdown':float((w/w.cummax()-1).min()),'downside_vol':float(neg) if pd.notna(neg) else None}
def ev(z):
 core=.5*z.p+.5*z.loan; corec=.5*z.pc+.5*z.lc
 out={'core':st(core),'core_control':st(corec),'candidate_return_corr_to_core':{}}
 for k,ck in [('aaa','aaac'),('intl','intlc'),('dbmf','dbmfc')]:
  s=(1-W)*core+W*z[k]; ctl=(1-W)*corec+W*z[ck]; a=st(s); c=st(ctl); a['matched_excess_cagr']=a['cagr']-c['cagr']; a['vs_core']={m:a[m]-out['core'][m] for m in ['cagr','sharpe','max_drawdown','downside_vol']}; out[k]=a; out[k+'_control']=c; out['candidate_return_corr_to_core'][k]=float(z[k].corr(core))
 return out
full=ev(q); n=len(q); sizes=[n//3,n//3,n-2*(n//3)]; blocks=[]; off=0
for i,s in enumerate(sizes,1): z=q.iloc[off:off+s]; off+=s; blocks.append({'block':i,'result':ev(z)})
pos={k:sum(b['result'][k]['matched_excess_cagr']>0 for b in blocks) for k in ['aaa','intl','dbmf']}
support={k:(full[k]['matched_excess_cagr']>0 and pos[k]>=2 and sum(full[k]['vs_core'][m]>0 for m in ['cagr','sharpe','max_drawdown'])>=2) for k in ['aaa','intl','dbmf']}
out={'schema':'research.p465_fixed_capital_budget_r1.v1','workload_id':'P465_FIXED_CAPITAL_BUDGET_R1','parent':'FUND_MODEL_SURVIVOR_PORTFOLIO','claim':'Common-sample equal incremental-capital diagnostic: allocate exactly 25% of the frozen P249+P373 core budget to each already-supported candidate asset identity separately (AAA CLO, 50/50 AVDV+IDMO, DBMF), with matched candidate controls, identical costs, chronology, downside and residual-correlation evidence. One fixed dose only; no optimizer.','contract':{'base':'P249+P373 frozen core','incremental_candidate_budget':.25,'AAA':'JAAA with SGOV matched control','international':'50/50 AVDV+IDMO with 50/50 VSS+EFA matched control','managed_futures':'DBMF with BIL matched control','endpoint_cost_bps':25,'weight_grid':False},'coverage':{'months':n,'start':str(q.index[0].date()),'end':str(q.index[-1].date()),'block_sizes':sizes},'full_sample':full,'chronology':blocks,'positive_matched_excess_blocks':pos,'scientific_support':support,'decision_rule':'A candidate is scientifically supported under equal capital only if after-cost matched excess is positive full-sample and >=2/3 chronology blocks, and at least two of CAGR/Sharpe/max-drawdown improve versus the frozen core. Comparative metrics are evidence for Coordinator consumption, not an allocation decision.','decision':'FIXED_CAPITAL_BUDGET_EVIDENCE_READY','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p465_fixed_capital_budget_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'support':support,'positive_blocks':pos,'metrics':{k:{'excess_pp':round(100*full[k]['matched_excess_cagr'],3),'vs_core':full[k]['vs_core'],'corr':full['candidate_return_corr_to_core'][k]} for k in ['aaa','intl','dbmf']}},sort_keys=True))