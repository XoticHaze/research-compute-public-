import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['KMLM','SPY','IEF']; W={'2021':'2021-01-01','2022':'2022-01-01','2023':'2023-01-01'}; B=10; F=B/10000

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def rebalanced_net(d,assets,target):
 target=np.array(target,dtype=float); out=[]; turns=[]; prev_end=None
 for _,row in d[assets].iterrows():
  turn=1.0 if prev_end is None else float(.5*np.abs(target-prev_end).sum()); gross=float(np.dot(target,row.values)); out.append(gross-F*turn); prev_end=target*(1+row.values)/(1+gross) if 1+gross else target.copy(); turns.append(turn)
 s=pd.Series(out,index=d.index,dtype=float)
 if len(s): s.iloc[-1]-=F
 return s,float(np.mean(turns)),float(np.sum(turns)+1)

def single(r):
 q=pd.Series(r).dropna().copy()
 if len(q): q.iloc[0]-=F; q.iloc[-1]-=F
 return q

def ev(d):
 c,ct,_=rebalanced_net(d,['SPY','KMLM'],[.8,.2]); m,mt,_=rebalanced_net(d,['SPY','IEF'],[.8,.2]); s=single(d['SPY']); cm,mm,sm=met(c),met(m),met(s); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(c)),5),1):
  fs.append({'fold':i,'candidate_minus_matched':met(c.iloc[ix])['cagr']-met(m.iloc[ix])['cagr'],'candidate_minus_spy':met(c.iloc[ix])['cagr']-met(s.iloc[ix])['cagr']})
 return {'candidate':cm,'matched':mm,'spy':sm,'candidate_minus_matched':cm['cagr']-mm['cagr'],'candidate_minus_spy':cm['cagr']-sm['cagr'],'positive_matched_folds':sum(x['candidate_minus_matched']>0 for x in fs),'candidate_avg_monthly_turnover':ct,'matched_avg_monthly_turnover':mt,'folds':fs}
raw=yf.download(A,start='2020-12-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c=(tests[k] for k in ['2021','2022','2023']); decision='P218_KMLM_COMBINATION_SURVIVOR' if all(x['candidate_minus_matched']>0 for x in (a,b,c)) and a['positive_matched_folds']>=4 and a['candidate']['sharpe']>=a['matched']['sharpe'] and a['candidate']['maxdd']>=a['matched']['maxdd'] else 'P218_KMLM_COMBINATION_REJECT'; out={'schema':'research.p218_kmlm_combination_r1','parent':'P218','hypothesis':'A distinct managed-futures implementation, KMLM, independently transports P216-like value when replacing 20% IEF in a frozen 80/20 SPY diversifier allocation.','contract':{'candidate':'80% SPY + 20% KMLM monthly rebalanced','matched_control':'80% SPY + 20% IEF monthly rebalanced','opportunity_context':'SPY','windows':W,'chronological_folds':5,'external_cost_bps_per_one_sided_dollar_traded':B,'turnover_definition':'initial entry 1.0; monthly rebalance 0.5*sum(abs(target-postreturn_drift_weight)); final exit 1.0','fund_internal_costs':'embedded in adjusted ETF returns','gate':'positive candidate-matched CAGR every window; >=4/5 positive matched folds from 2021; 2021 Sharpe no lower and max drawdown no worse than matched','no_weight_window_timing_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p218_kmlm_combination_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
