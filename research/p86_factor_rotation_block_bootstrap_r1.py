from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SYMS=("MTUM","QUAL","USMV","VLUE","SIZE"); BP=50; SEED=8601; REPS=2000; BLOCK=6

def cagr(r):
 r=np.asarray(r,float); return float(np.prod(1+r)**(12/len(r))-1)
def sharpe(r):
 r=np.asarray(r,float); s=np.std(r,ddof=1); return float(np.mean(r)/s*np.sqrt(12)) if s else None
def series():
 raw=yf.download(list(SYMS)+["SPY"],start="2013-01-01",auto_adjust=True,progress=False,threads=False); c=raw['Close'].dropna(how='any').astype(float); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=c.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]; prev=np.zeros(len(SYMS))
 for i in range(6,len(m)-1):
  dt=m.index[i]; nxt=m.index[i+1]; mom=(m.loc[dt,list(SYMS)]/m.iloc[i-6][list(SYMS)]-1).sort_values(ascending=False); chosen=set(mom.index[:2]); w=np.array([.5 if s in chosen else 0 for s in SYMS]); r=(m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1).to_numpy(float); turn=.5*float(abs(w-prev).sum()); rows.append((nxt,float(w@r-turn*BP/10000),float(np.mean(r)),float(m.loc[nxt,'SPY']/m.loc[dt,'SPY']-1))); prev=w
 return pd.DataFrame(rows,columns=['date','candidate','matched','spy']).set_index('date')
def boot(q):
 n=len(q); rng=np.random.default_rng(SEED); starts=np.arange(n); dc=[]; ds=[]
 for _ in range(REPS):
  idx=[]
  while len(idx)<n:
   s=int(rng.choice(starts)); idx.extend([(s+j)%n for j in range(BLOCK)])
  x=q.iloc[idx[:n]]; dc.append(cagr(x.candidate)-cagr(x.matched)); ds.append(sharpe(x.candidate)-sharpe(x.matched))
 point_c=cagr(q.candidate)-cagr(q.matched); point_s=sharpe(q.candidate)-sharpe(q.matched)
 return {'months':n,'point_excess_cagr_vs_matched':point_c,'point_sharpe_delta_vs_matched':point_s,'p_nonpositive_excess_cagr':float(np.mean(np.array(dc)<=0)),'p_nonpositive_sharpe_delta':float(np.mean(np.array(ds)<=0)),'excess_cagr_q05_q95':[float(np.quantile(dc,.05)),float(np.quantile(dc,.95))],'sharpe_delta_q05_q95':[float(np.quantile(ds,.05)),float(np.quantile(ds,.95))]}
def main():
 f=series(); out={'schema':'research.p86_factor_rotation_block_bootstrap_r1','parent':'P86','contract':{'model':'unchanged P86 top-two six-month factor momentum','cost_bps':BP,'block_months':BLOCK,'replications':REPS,'seed':SEED,'windows':['2020_forward','2022_forward'],'no_parameter_search':True},'tests':{'2020_forward':boot(f.loc['2020-01-01':]),'2022_forward':boot(f.loc['2022-01-01':])}}
 a=out['tests']['2020_forward']; out['decision']='P86_LATER_WINDOW_STATISTICALLY_SUPPORTED' if a['point_excess_cagr_vs_matched']>0 and a['p_nonpositive_excess_cagr']<.20 else 'P86_LATER_WINDOW_BOOTSTRAP_FRAGILE'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p86_factor_rotation_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
