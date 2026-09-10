from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','DBMF','BIL','SRLN','HYG','SHY']; START='2015-01-01'; END='2026-09-11'; LB=24; EP=.0025
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False); c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=c[T].resample('ME').last(); r=m.pct_change(fill_method=None)
p305=.5*(r.SPMO+r.IJS); p305ctl=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
 w=r[['HYG','SHY','SRLN']].iloc[max(0,i-LB):i].dropna()
 if len(w)<LB: bs.append((np.nan,np.nan)); continue
 b=np.linalg.lstsq(w[['HYG','SHY']].values,w.SRLN.values,rcond=None)[0]; b=np.clip(b,0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1); loanctl=b.hyg*r.HYG+b.shy*r.SHY
q=pd.DataFrame({'p305':p305,'p305ctl':p305ctl,'dbmf':r.DBMF,'bil':r.BIL,'srln':r.SRLN,'loanctl':loanctl}).dropna()
idx=q.index; n=len(q); periods=idx.to_period('M').astype(int); contiguous=bool(np.all(np.diff(periods)==1)); sizes=[n//3,n//3,n-2*(n//3)]; eligible=n>=60 and contiguous and min(sizes)>=18
if not eligible:
 out={'schema':'research.p305_dbmf_capital_efficiency_r1','decision':'COVERAGE_GATE_FAILED','common_months':n,'contiguous':contiguous,'block_sizes':sizes}; Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p305_dbmf_capital_efficiency_r1.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out)); raise SystemExit(0)
blocks=[]; off=0
for i,sz in enumerate(sizes,1): z=idx[off:off+sz]; off+=sz; blocks.append((f'block_{i}',z[0],z[-1]))
def ep(s):
 y=pd.Series(s,dtype=float).copy(); y.iloc[0]-=EP; y.iloc[-1]-=EP; return y
def st(s):
 x=ep(s.dropna()); n=len(x); w=(1+x).cumprod(); vol=x.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(z):
 base=.5*z.p305+.5*z.srln; basectl=.5*z.p305ctl+.5*z.loanctl
 full=.5*z.p305+.5*z.dbmf; fullctl=.5*z.p305ctl+.5*z.bil
 half=.75*z.p305+.25*z.dbmf; halfctl=.75*z.p305ctl+.25*z.bil
 s={k:st(v) for k,v in [('base',base),('base_ctl',basectl),('full',full),('full_ctl',fullctl),('half',half),('half_ctl',halfctl)]}
 s['full_excess']=s['full']['cagr']-s['full_ctl']['cagr']; s['half_excess']=s['half']['cagr']-s['half_ctl']['cagr']
 s['half_retention']=s['half_excess']/s['full_excess'] if s['full_excess'] else None
 s['half_vs_base']={k:s['half'][k]-s['base'][k] for k in ['cagr','sharpe','max_drawdown']}
 s['full_vs_base']={k:s['full'][k]-s['base'][k] for k in ['cagr','sharpe','max_drawdown']}
 return s
full=ev(q); chrono={name:ev(q.loc[a:b]) for name,a,b in blocks}; pos=sum(v['half_excess']>0 for v in chrono.values())
efficient=full['half_excess']>0 and full['half_retention'] is not None and full['half_retention']>=.60 and pos>=2 and any(full['half_vs_base'][k]>0 for k in ['cagr','sharpe','max_drawdown'])
decision='HALF_DOSE_CAPITAL_EFFICIENCY_SUPPORTED' if efficient else 'HALF_DOSE_CAPITAL_EFFICIENCY_NOT_SUPPORTED'
out={'schema':'research.p305_dbmf_capital_efficiency_r1.v1','workload_id':'P305_DBMF_CAPITAL_EFFICIENCY_R1','claim':'Test whether a single predeclared half-dose 25% DBMF allocation retains a majority of the frozen 50% DBMF matched-alpha benefit while preserving chronology and useful core-stack economics. This is a capital-efficiency discriminator, not a weight search.','coverage':{'common_months':n,'contiguous':contiguous,'block_sizes':sizes},'contract':{'full':'50% P305 + 50% DBMF','half_dose':'75% P305 + 25% DBMF','base':'50% P305 + 50% SRLN','matched_controls':'P305 control, BIL for DBMF, causal HYG+SHY for SRLN','endpoint_cost_bps':25,'only_challenger_weight_tested':.25,'grid_search':False,'no_rescue':True},'full_sample':full,'chronology':chrono,'positive_half_dose_blocks':pos,'decision_rule':'Support only if half-dose matched excess >0, retains >=60% of full-dose matched excess while using half as much DBMF capital, is positive in >=2/3 chronology blocks, and improves at least one CAGR/Sharpe/maxDD dimension versus frozen core.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p305_dbmf_capital_efficiency_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'half_excess_pp':round(100*full['half_excess'],3),'full_excess_pp':round(100*full['full_excess'],3),'retention':round(full['half_retention'],3),'positive_blocks':pos,'half_vs_base':full['half_vs_base']},sort_keys=True))
