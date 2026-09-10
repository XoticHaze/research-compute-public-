import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['QUAL','MTUM','SPY','QQQ']; W={'2015':'2015-01-01','2018':'2018-01-01','2020':'2020-01-01'}; B=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def edge_cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def ev(d):
 blend=edge_cost(.5*d['QUAL']+.5*d['MTUM']); spy=edge_cost(d['SPY']); qqq=edge_cost(d['QQQ'])
 bm,sm,qm=met(blend),met(spy),met(qqq); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(blend)),5),1):
  b=blend.iloc[ix]; s=spy.iloc[ix]; q=qqq.iloc[ix]; fs.append({'fold':i,'blend_minus_spy':met(b)['cagr']-met(s)['cagr'],'blend_minus_qqq':met(b)['cagr']-met(q)['cagr']})
 return {'blend':bm,'spy':sm,'qqq':qm,'blend_minus_spy':bm['cagr']-sm['cagr'],'blend_minus_qqq':bm['cagr']-qm['cagr'],'positive_spy_folds':sum(x['blend_minus_spy']>0 for x in fs),'positive_qqq_folds':sum(x['blend_minus_qqq']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2014-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c=(tests[k] for k in ['2015','2018','2020']); decision='P211_QUALITY_MOMENTUM_BLEND_SURVIVOR' if all(x['blend_minus_spy']>0 and x['blend_minus_qqq']>=0 for x in (a,b,c)) and a['positive_spy_folds']>=4 and a['positive_qqq_folds']>=4 else 'P211_QUALITY_MOMENTUM_BLEND_REJECT'; out={'schema':'research.p211_quality_momentum_blend_r1','parent':'P211','hypothesis':'A fixed 50/50 QUAL+MTUM blend creates durable after-cost excess over SPY and clears QQQ opportunity cost without tactical timing.','contract':{'weights':{'QUAL':0.5,'MTUM':0.5},'matched_control':'SPY','opportunity_cost':'QQQ','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit':B,'gate':'positive blend-SPY and nonnegative blend-QQQ in every window; >=4/5 positive folds versus each from 2015+','no_weight_window_timing_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p211_quality_momentum_blend_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
