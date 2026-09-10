import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['NTSX','SPY','IEF']; W={'2019':'2019-01-01','2020':'2020-01-01','2022':'2022-01-01'}; B=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def edge_cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def balanced(d):
 return .6*d['SPY']+.4*d['IEF']

def ev(d):
 n=edge_cost(d['NTSX']); b=edge_cost(balanced(d)); s=edge_cost(d['SPY']); nm,bm,sm=met(n),met(b),met(s); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(n)),5),1):
  qn=n.iloc[ix]; qb=b.iloc[ix]; qs=s.iloc[ix]; fs.append({'fold':i,'ntsx_minus_6040':met(qn)['cagr']-met(qb)['cagr'],'ntsx_minus_spy':met(qn)['cagr']-met(qs)['cagr']})
 return {'ntsx':nm,'balanced_60_40':bm,'spy':sm,'ntsx_minus_6040':nm['cagr']-bm['cagr'],'ntsx_minus_spy':nm['cagr']-sm['cagr'],'positive_6040_folds':sum(x['ntsx_minus_6040']>0 for x in fs),'positive_spy_folds':sum(x['ntsx_minus_spy']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2018-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c=(tests[k] for k in ['2019','2020','2022']); decision='P213_NTSX_CAPITAL_EFFICIENCY_SURVIVOR' if all(x['ntsx_minus_6040']>0 and x['ntsx_minus_spy']>=0 for x in (a,b,c)) and a['positive_6040_folds']>=4 and a['positive_spy_folds']>=4 and a['ntsx']['maxdd']>=a['spy']['maxdd'] else 'P213_NTSX_CAPITAL_EFFICIENCY_REJECT'; out={'schema':'research.p213_ntsx_capital_efficiency_r1','parent':'P213','hypothesis':'NTSX capital-efficient 90/60 exposure creates durable net fund excess over a simple 60/40 SPY/IEF matched balanced control while clearing SPY opportunity cost without worse drawdown.','contract':{'candidate':'NTSX','matched_control':'60% SPY + 40% IEF monthly-return blend','opportunity_cost':'SPY','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit':B,'fund_internal_costs_and_financing':'embedded in adjusted NTSX returns','gate':'positive NTSX-60/40 and nonnegative NTSX-SPY in every window; >=4/5 positive 2019 folds versus each; 2019 max drawdown no worse than SPY','no_window_leverage_weight_or_timing_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p213_ntsx_capital_efficiency_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
