import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['DBMF','SPY','IEF']; W={'2020':'2020-01-01','2022':'2022-01-01','2023':'2023-01-01'}; B=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def edge_cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def ev(d):
 cand=edge_cost(.8*d['SPY']+.2*d['DBMF']); matched=edge_cost(.8*d['SPY']+.2*d['IEF']); spy=edge_cost(d['SPY'])
 cm,mm,sm=met(cand),met(matched),met(spy); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(cand)),5),1):
  c=cand.iloc[ix]; m=matched.iloc[ix]; s=spy.iloc[ix]; fs.append({'fold':i,'candidate_minus_matched':met(c)['cagr']-met(m)['cagr'],'candidate_minus_spy':met(c)['cagr']-met(s)['cagr']})
 return {'candidate':cm,'matched':mm,'spy':sm,'candidate_minus_matched':cm['cagr']-mm['cagr'],'candidate_minus_spy':cm['cagr']-sm['cagr'],'positive_matched_folds':sum(x['candidate_minus_matched']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2019-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c=(tests[k] for k in ['2020','2022','2023']); decision='P216_MANAGED_FUTURES_COMBINATION_SURVIVOR' if all(x['candidate_minus_matched']>0 for x in (a,b,c)) and a['positive_matched_folds']>=4 and a['candidate']['sharpe']>=a['matched']['sharpe'] and a['candidate']['maxdd']>=a['matched']['maxdd'] else 'P216_MANAGED_FUTURES_COMBINATION_REJECT'; out={'schema':'research.p216_managed_futures_combination_r1','parent':'P216','hypothesis':'Replacing a fixed 20% IEF sleeve with DBMF in an 80/20 SPY diversifier allocation creates durable after-cost incremental value and improves risk without weight optimization.','contract':{'candidate':'80% SPY + 20% DBMF','matched_control':'80% SPY + 20% IEF','opportunity_context':'SPY','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit':B,'fund_internal_costs':'embedded in adjusted ETF returns','gate':'positive candidate-matched CAGR every window; >=4/5 positive matched folds from 2020; 2020 Sharpe no lower and max drawdown no worse than matched','no_weight_window_timing_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p216_managed_futures_combination_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
