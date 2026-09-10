from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY','DBMF','BIL','JAAA','SGOV','AVDV','IDMO','VSS','EFA']
START='2015-01-01'; END='2026-09-11'; LB=24
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=c[T].resample('ME').last(); r=m.pct_change(fill_method=None)
p249=.5*(r.SPMO+r.IJS); p249ctl=.5*(r.SPY+r.IJR)
intl=.5*(r.AVDV+r.IDMO); intlctl=.5*(r.VSS+r.EFA)
bs=[]
for i in range(len(r)):
 w=r[['HYG','SHY','SRLN']].iloc[max(0,i-LB):i].dropna()
 if len(w)<LB: bs.append((np.nan,np.nan)); continue
 b=np.linalg.lstsq(w[['HYG','SHY']].values,w.SRLN.values,rcond=None)[0]; b=np.clip(b,0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1); loanctl=b.hyg*r.HYG+b.shy*r.SHY
q=pd.DataFrame({'p249':p249,'p249ctl':p249ctl,'loan':r.SRLN,'loanctl':loanctl,'dbmf':r.DBMF,'bil':r.BIL,'clo':r.JAAA,'cloctl':r.SGOV,'intl':intl,'intlctl':intlctl}).dropna().loc['2021-01-01':]
idx=q.index; n=len(q); periods=idx.to_period('M').astype(int); contiguous=bool(np.all(np.diff(periods)==1)); sizes=[n//3,n//3,n-2*(n//3)]; eligible=n>=54 and contiguous and min(sizes)>=18
if not eligible:
 out={'schema':'research.p455_dbmf_vs_complements_r1.v1','decision':'COVERAGE_GATE_FAILED','common_months':n,'contiguous':contiguous,'block_sizes':sizes}; Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p455_dbmf_vs_complements_r1.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out)); raise SystemExit(0)
blocks=[]; off=0
for i,sz in enumerate(sizes,1): z=idx[off:off+sz]; off+=sz; blocks.append((f'block_{i}',z[0],z[-1]))
def ep(s,c):
 y=pd.Series(s,dtype=float).copy(); y.iloc[0]-=c; y.iloc[-1]-=c; return y
def st(s,c):
 x=ep(s.dropna(),c); n=len(x); w=(1+x).cumprod(); vol=x.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(z):
 core=.5*z.p249+.5*z.loan; corectl=.5*z.p249ctl+.5*z.loanctl
 db=.75*z.p249+.25*z.dbmf; dbctl=.75*z.p249ctl+.25*z.bil
 aaa=(z.p249+z.loan+z.clo)/3; aaactl=(z.p249ctl+z.loanctl+z.cloctl)/3
 ai=(z.p249+z.loan+z.intl)/3; aictl=(z.p249ctl+z.loanctl+z.intlctl)/3
 joint=(z.p249+z.loan+z.clo+z.intl)/4; jointctl=(z.p249ctl+z.loanctl+z.cloctl+z.intlctl)/4
 pairs={'core':(core,corectl,.001),'dbmf25':(db,dbctl,.0025),'aaa':(aaa,aaactl,.0025),'intl':(ai,aictl,.0025),'joint':(joint,jointctl,.0025)}
 out={}
 for k,(s,ctl,cost) in pairs.items():
  a=st(s,cost); b=st(ctl,cost); out[k]=a; out[k+'_ctl']=b; out[k]['matched_excess_cagr']=a['cagr']-b['cagr']
 out['dbmf_vs']={k:{m:out['dbmf25'][m]-out[k][m] for m in ['cagr','sharpe','max_drawdown']} for k in ['core','aaa','intl','joint']}
 return out
full=ev(q); chrono={name:ev(q.loc[a:b]) for name,a,b in blocks}
pos={k:sum(v[k]['matched_excess_cagr']>0 for v in chrono.values()) for k in ['dbmf25','aaa','intl','joint']}
# Scientific support means DBMF25 preserves matched alpha in >=2/3 blocks and is not jointly dominated by every confirmed complement on CAGR+Sharpe.
dominated=[]
for k in ['aaa','intl','joint']:
 d=full['dbmf_vs'][k]; dominated.append(d['cagr']<0 and d['sharpe']<0)
supported=full['dbmf25']['matched_excess_cagr']>0 and pos['dbmf25']>=2 and not all(dominated)
decision='DBMF25_REMAINS_DISTINCT_COMPETITIVE_CHALLENGER' if supported else 'DBMF25_OPPORTUNITY_COST_NOT_SUPPORTED'
out={'schema':'research.p455_dbmf_vs_complements_r1.v1','workload_id':'P455_DBMF_VS_COMPLEMENTS_R1','claim':'Frozen direct opportunity-cost discriminator: compare the already-supported 75% P249 + 25% DBMF capital-efficient challenger against frozen core, AAA CLO, AVDV+IDMO, and their joint complement on one common coverage-valid sample. No weight/product/date/control tuning.','coverage':{'common_months':n,'contiguous':contiguous,'block_sizes':sizes},'contract':{'dbmf25':'75% P249 + 25% DBMF','core':'50% P249 + 50% causal P373/SRLN','aaa':'equal P249 + SRLN + JAAA','intl':'equal P249 + SRLN + 50/50 AVDV+IDMO','joint':'equal P249 + SRLN + JAAA + 50/50 AVDV+IDMO','matched_controls':'SPY/IJR, causal HYG/SHY, BIL, SGOV, VSS/EFA','no_optimization':True},'full_sample':full,'chronology':chrono,'positive_matched_excess_blocks':pos,'decision_rule':'Preserve DBMF25 as a distinct competitive challenger only if matched excess is positive full-sample and >=2/3 chronology blocks, and it is not CAGR+Sharpe dominated by every confirmed complement. This does not select an allocation.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p455_dbmf_vs_complements_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'months':n,'dbmf25_excess_pp':round(100*full['dbmf25']['matched_excess_cagr'],3),'positive_blocks':pos['dbmf25'],'dbmf_vs':full['dbmf_vs']},sort_keys=True))
