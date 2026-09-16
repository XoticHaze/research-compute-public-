import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY','ANGL','FALN']; COST=.0025
x=yf.download(T,start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().pct_change(fill_method=None)
p249=.5*(r.SPMO+r.IJS); pctl=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
 w=r[['HYG','SHY','SRLN']].iloc[max(0,i-24):i].dropna()
 if len(w)<24: bs.append((np.nan,np.nan)); continue
 b=np.clip(np.linalg.lstsq(w[['HYG','SHY']].values,w.SRLN.values,rcond=None)[0],0,1)
 if b.sum()>1: b=b/b.sum()
 bs.append(tuple(b))
b=pd.DataFrame(bs,index=r.index,columns=['h','s']).shift(1); loanctl=b.h*r.HYG+b.s*r.SHY
q=pd.DataFrame({'p':p249,'pc':pctl,'loan':r.SRLN,'lc':loanctl,'angl':r.ANGL,'faln':r.FALN,'hyg':r.HYG}).dropna()
def st(s):
 s=s.copy(); s.iloc[0]-=COST; s.iloc[-1]-=COST; w=(1+s).cumprod(); n=len(s); v=s.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(s.mean()*12/v),'max_drawdown':float((w/w.cummax()-1).min())}
def ev(z):
 core=.5*z.p+.5*z.loan; ctl=.75*z.pc+.25*z.hyg
 out={'core':st(core),'angl25':st(.75*z.p+.25*z.angl),'faln25':st(.75*z.p+.25*z.faln),'ctl':st(ctl)}
 for k in ['angl25','faln25']:
  out[k]['matched_excess_cagr']=out[k]['cagr']-out['ctl']['cagr']
  out[k]['vs_core']={m:out[k][m]-out['core'][m] for m in ['cagr','sharpe','max_drawdown']}
 out['credit_return_corr']={'ANGL_vs_SRLN':float(z.angl.corr(z.loan)),'FALN_vs_SRLN':float(z.faln.corr(z.loan)),'ANGL_vs_HYG':float(z.angl.corr(z.hyg)),'FALN_vs_HYG':float(z.faln.corr(z.hyg))}
 return out
full=ev(q); n=len(q); sizes=[n//3,n//3,n-2*(n//3)]; blocks=[]; off=0
for i,s in enumerate(sizes,1):
 z=q.iloc[off:off+s]; off+=s; blocks.append({'block':i,'result':ev(z)})
pos={k:sum(b['result'][k]['matched_excess_cagr']>0 for b in blocks) for k in ['angl25','faln25']}
support={k:(full[k]['matched_excess_cagr']>0 and pos[k]>=2 and sum(full[k]['vs_core'][m]>0 for m in ['cagr','sharpe','max_drawdown'])>=2) for k in ['angl25','faln25']}
d='FALLEN_ANGEL_DISTINCT_CREDIT_ROLE_SUPPORTED' if any(support.values()) else 'FALLEN_ANGEL_DISTINCT_CREDIT_ROLE_NOT_SUPPORTED'
out={'schema':'research.p461_fallen_angel_credit_role_r1.v1','workload_id':'P461_FALLEN_ANGEL_CREDIT_ROLE_R1','claim':'Fixed equal-capital diagnostic of P460 ANGL/FALN versus the frozen P249+P373 core and matched HYG credit control; no weight/product/date/cost search.','coverage':{'months':n,'block_sizes':sizes},'full_sample':full,'chronology':blocks,'positive_blocks':pos,'implementation_support':support,'decision':d,'decision_rule':'Support an implementation only if full-sample matched excess is positive, at least 2/3 chronology blocks are positive, and at least two of CAGR/Sharpe/max-drawdown improve versus frozen P249+P373 core. Correlations are descriptive redundancy evidence, not a tuned threshold.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p461_fallen_angel_credit_role_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':d,'support':support,'positive_blocks':pos,'corr':full['credit_return_corr'],'ANGL_vs_core':full['angl25']['vs_core'],'FALN_vs_core':full['faln25']['vs_core']},sort_keys=True))