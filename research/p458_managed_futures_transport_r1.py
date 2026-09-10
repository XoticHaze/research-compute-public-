from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY','DBMF','KMLM','BIL']; START='2015-01-01'; END='2026-09-11'; LB=24; EP=.0025
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw; m=c[T].resample('ME').last(); r=m.pct_change(fill_method=None)
p305=.5*(r.SPMO+r.IJS); p305ctl=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
 w=r[['HYG','SHY','SRLN']].iloc[max(0,i-LB):i].dropna()
 if len(w)<LB: bs.append((np.nan,np.nan)); continue
 b=np.linalg.lstsq(w[['HYG','SHY']].values,w.SRLN.values,rcond=None)[0]; b=np.clip(b,0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1); loanctl=b.hyg*r.HYG+b.shy*r.SHY
q=pd.DataFrame({'p305':p305,'p305ctl':p305ctl,'loan':r.SRLN,'loanctl':loanctl,'dbmf':r.DBMF,'kmlm':r.KMLM,'bil':r.BIL}).dropna()
idx=q.index; n=len(q); periods=idx.to_period('M').astype(int); contiguous=bool(np.all(np.diff(periods)==1)); sizes=[n//3,n//3,n-2*(n//3)]; eligible=n>=54 and contiguous and min(sizes)>=18
if not eligible:
 out={'schema':'research.p458_managed_futures_transport_r1.v1','decision':'COVERAGE_GATE_FAILED','common_months':n,'contiguous':contiguous,'block_sizes':sizes}; Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p458_managed_futures_transport_r1.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out)); raise SystemExit(0)
blocks=[]; off=0
for i,sz in enumerate(sizes,1): z=idx[off:off+sz]; off+=sz; blocks.append((f'block_{i}',z[0],z[-1]))
def st(s):
 x=pd.Series(s,dtype=float).dropna().copy(); x.iloc[0]-=EP; x.iloc[-1]-=EP; n=len(x); w=(1+x).cumprod(); vol=x.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(z):
 core=.5*z.p305+.5*z.loan; corectl=.5*z.p305ctl+.5*z.loanctl
 db=.75*z.p305+.25*z.dbmf; km=.75*z.p305+.25*z.kmlm; ctl=.75*z.p305ctl+.25*z.bil
 out={k:st(v) for k,v in [('core',core),('corectl',corectl),('dbmf25',db),('kmlm25',km),('mfctl',ctl)]}
 out['dbmf25']['matched_excess_cagr']=out['dbmf25']['cagr']-out['mfctl']['cagr']; out['kmlm25']['matched_excess_cagr']=out['kmlm25']['cagr']-out['mfctl']['cagr']
 out['kmlm_vs_core']={k:out['kmlm25'][k]-out['core'][k] for k in ['cagr','sharpe','max_drawdown']}; out['kmlm_vs_dbmf']={k:out['kmlm25'][k]-out['dbmf25'][k] for k in ['cagr','sharpe','max_drawdown']}; return out
full=ev(q); chrono={name:ev(q.loc[a:b]) for name,a,b in blocks}; pos=sum(v['kmlm25']['matched_excess_cagr']>0 for v in chrono.values())
supported=full['kmlm25']['matched_excess_cagr']>0 and pos>=2 and any(full['kmlm_vs_core'][k]>0 for k in ['cagr','sharpe','max_drawdown'])
decision='MANAGED_FUTURES_COMPLEMENT_TRANSPORT_SUPPORTED' if supported else 'MANAGED_FUTURES_COMPLEMENT_TRANSPORT_NOT_SUPPORTED'
out={'schema':'research.p458_managed_futures_transport_r1.v1','workload_id':'P458_MANAGED_FUTURES_TRANSPORT_R1','claim':'Orthogonal representation falsifier: replace DBMF only with independent managed-futures ETF KMLM at the same frozen 25% sleeve size and ask whether P305 managed-futures complementarity transports on the common post-launch sample. This is not a weight search or product rescue.','coverage':{'common_months':n,'contiguous':contiguous,'block_sizes':sizes,'first_common_month':str(idx[0].date()),'last_common_month':str(idx[-1].date())},'contract':{'dbmf_reference':'75% P305 + 25% DBMF','transport':'75% P305 + 25% KMLM','matched_control':'75% P305 control + 25% BIL','core':'50% P305 + 50% causal P373/SRLN','endpoint_cost_bps':25,'weight_grid':False,'no_rescue':True},'full_sample':full,'chronology':chrono,'positive_kmlm_matched_excess_blocks':pos,'decision_rule':'Transport only if KMLM25 after-cost matched excess is positive full sample and >=2/3 chronology blocks and improves at least one CAGR/Sharpe/maxDD dimension versus the frozen core. DBMF outperformance is reported but is not required for transport.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p458_managed_futures_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'months':n,'kmlm_excess_pp':round(100*full['kmlm25']['matched_excess_cagr'],3),'positive_blocks':pos,'kmlm_vs_core':full['kmlm_vs_core'],'kmlm_vs_dbmf':full['kmlm_vs_dbmf']},sort_keys=True))
