import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['MTUM','IMTM','IWB','IEFA','SPY']; W={'2016':'2016-01-01','2020':'2020-01-01','2022':'2022-01-01'}; B=10
def m(r):
 q=pd.Series(r).dropna(); e=(1+q).cumprod(); n=len(q); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 cand=.5*d.MTUM+.5*d.IMTM; ctrl=.5*d.IWB+.5*d.IEFA; z={'candidate':m(c(cand)),'matched':m(c(ctrl)),'spy':m(c(d.SPY))}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; ca=.5*q.MTUM+.5*q.IMTM; co=.5*q.IWB+.5*q.IEFA; fs.append({'fold':i,'vs_matched':m(c(ca))['cagr']-m(c(co))['cagr'],'vs_spy':m(c(ca))['cagr']-m(c(q.SPY))['cagr']})
 return {'metrics':z,'vs_matched':z['candidate']['cagr']-z['matched']['cagr'],'vs_spy':z['candidate']['cagr']-z['spy']['cagr'],'positive_matched_folds':sum(x['vs_matched']>0 for x in fs),'positive_spy_folds':sum(x['vs_spy']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2015-09-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; r=cl.dropna(how='any').resample('ME').last().pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(s):]) for k,s in W.items()}; ok=all(t[k]['vs_matched']>0 for k in W) and t['2016']['positive_matched_folds']>=4 and t['2020']['positive_matched_folds']>=4 and t['2022']['positive_matched_folds']>=4
out={'schema':'research.p247_global_momentum_combo_r1','parent':'P238/P246/P247','claim':'fixed equal US/international momentum combination converts two positive-but-chronology-weak sleeves into persistent after-cost matched-control excess','contract':{'candidate_weights':{'MTUM':0.5,'IMTM':0.5},'matched_control_weights':{'IWB':0.5,'IEFA':0.5},'opportunity_context':'SPY','windows':W,'folds':5,'cost_bps':B,'fixed_test':True,'no_weight_window_fund_or_parameter_search':True},'tests':t,'decision':'P247_SUPPORT' if ok else 'P247_NOT_SUPPORTED','limitations':['shorter common history due to IMTM inception','equal-weight combination is a scientific candidate, not portfolio authority'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p247_global_momentum_combo_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
