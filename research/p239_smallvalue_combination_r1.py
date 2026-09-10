import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['AVUV','AVDV','IJR','VSS','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10
def metrics(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}
def cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 cand=.5*d.AVUV+.5*d.AVDV; ctrl=.5*d.IJR+.5*d.VSS; zc=metrics(cost(cand)); zm=metrics(cost(ctrl)); zs=metrics(cost(d.SPY)); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; a=metrics(cost(.5*q.AVUV+.5*q.AVDV)); b=metrics(cost(.5*q.IJR+.5*q.VSS)); s=metrics(cost(q.SPY)); fs.append({'fold':i,'vs_matched':a['cagr']-b['cagr'],'vs_spy':a['cagr']-s['cagr']})
 return {'candidate':zc,'matched_control':zm,'spy':zs,'vs_matched':zc['cagr']-zm['cagr'],'vs_spy':zc['cagr']-zs['cagr'],'positive_matched_folds':sum(x['vs_matched']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['vs_matched']>0 for k in W) and t['2020']['positive_matched_folds']>=4; out={'schema':'research.p239_smallvalue_combination_r1','parent':'P239','claim':'fixed equal combination of supported US and developed-ex-US small-value sleeves preserves after-cost matched excess without selecting among sleeves','contract':{'candidate_weights':{'AVUV':0.5,'AVDV':0.5},'matched_control_weights':{'IJR':0.5,'VSS':0.5},'opportunity_context':'SPY','windows':W,'folds':5,'cost_bps':B,'fixed_test':True,'no_weight_or_parameter_search':True},'tests':t,'decision':'P239_SUPPORT' if ok else 'P239_NOT_SUPPORTED','limitations':['fixed research combination is not portfolio-ranking or allocation authority','shared post-2020 history is short'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p239_smallvalue_combination_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))