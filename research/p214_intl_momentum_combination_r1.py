import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['IMTM','EFA','SPY']; W={'2016':'2016-01-01','2018':'2018-01-01','2020':'2020-01-01'}; B=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def edge_cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def ev(d):
 cand=edge_cost(.5*d['SPY']+.5*d['IMTM']); matched=edge_cost(.5*d['SPY']+.5*d['EFA']); spy=edge_cost(d['SPY'])
 cm,mm,sm=met(cand),met(matched),met(spy); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(cand)),5),1):
  c=cand.iloc[ix]; m=matched.iloc[ix]; s=spy.iloc[ix]; fs.append({'fold':i,'candidate_minus_matched':met(c)['cagr']-met(m)['cagr'],'candidate_minus_spy':met(c)['cagr']-met(s)['cagr']})
 return {'candidate':cm,'matched':mm,'spy':sm,'candidate_minus_matched':cm['cagr']-mm['cagr'],'candidate_minus_spy':cm['cagr']-sm['cagr'],'positive_matched_folds':sum(x['candidate_minus_matched']>0 for x in fs),'positive_spy_folds':sum(x['candidate_minus_spy']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2015-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c=(tests[k] for k in ['2016','2018','2020']); decision='P214_INTL_MOMENTUM_COMBINATION_SURVIVOR' if all(x['candidate_minus_matched']>0 for x in (a,b,c)) and a['positive_matched_folds']>=4 and a['candidate']['sharpe']>=a['matched']['sharpe'] and a['candidate']['maxdd']>=a['matched']['maxdd'] else 'P214_INTL_MOMENTUM_COMBINATION_REJECT'; out={'schema':'research.p214_intl_momentum_combination_r1','parent':'P214','hypothesis':'Replacing EFA with IMTM inside a fixed 50/50 SPY/developed-markets allocation adds durable incremental after-cost alpha without worsening risk, even if IMTM does not beat SPY standalone.','contract':{'candidate':'50% SPY + 50% IMTM','matched_control':'50% SPY + 50% EFA','opportunity_context':'SPY','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit':B,'gate':'positive candidate-matched CAGR every window; >=4/5 positive matched folds from 2016; 2016 Sharpe no lower and max drawdown no worse than matched','no_weight_window_timing_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p214_intl_momentum_combination_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
