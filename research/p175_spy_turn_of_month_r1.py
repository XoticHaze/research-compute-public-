import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=[5,10,25]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; PC=10

def cagr(r):
 r=pd.Series(r).dropna(); return float((1+r).prod()**(252/len(r))-1)
def maxdd(r):
 e=(1+pd.Series(r).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def sharpe(r):
 r=pd.Series(r).dropna(); s=r.std(ddof=1); return float(np.sqrt(252)*r.mean()/s) if s>0 else float('nan')
def metrics(r): return {'cagr':cagr(r),'maxdd':maxdd(r),'sharpe':sharpe(r)}
def evaluate(z,c):
 p=z.pos; gross=p*z.SPY_ret+(1-p)*z.BIL_ret; turn=p.diff().abs().fillna(0); cand=gross-turn*c/10000
 e=float(p.mean()); matched=e*z.SPY_ret+(1-e)*z.BIL_ret; spy=z.SPY_ret
 return {'candidate':metrics(cand),'matched':metrics(matched),'spy':metrics(spy),'excess_matched':cagr(cand)-cagr(matched),'excess_spy':cagr(cand)-cagr(spy),'mean_spy_exposure':e,'days':int(len(z))}
def folds(z,c):
 months=pd.Index(z.index.to_period('M').unique()); out=[]
 for i,mset in enumerate(np.array_split(months,5),1):
  q=z[z.index.to_period('M').isin(mset)]; x=evaluate(q,c); out.append({'fold':i,'matched_excess':x['excess_matched'],'spy_excess':x['excess_spy']})
 return out
raw=yf.download(['SPY','BIL'],start='2007-01-01',end='2026-09-01',auto_adjust=True,progress=False,group_by='column')
close=raw['Close'][['SPY','BIL']] if isinstance(raw.columns,pd.MultiIndex) else raw[['SPY','BIL']]; close=close.dropna(how='all').ffill().dropna(); ret=close.pct_change().dropna()
meta=pd.DataFrame(index=ret.index); meta['month']=meta.index.to_period('M'); meta['rank']=meta.groupby('month').cumcount()+1; meta['n']=meta.groupby('month')['rank'].transform('max'); meta['pos']=((meta['rank']<=3)|(meta['rank']==meta['n'])).astype(float)
z=pd.DataFrame({'SPY_ret':ret.SPY,'BIL_ret':ret.BIL,'pos':meta.pos}).dropna(); sha=hashlib.sha256(close.to_csv().encode()).hexdigest()
r={'schema':'research.p175_spy_turn_of_month_r1','parent':'P175','hypothesis':'The turn-of-month calendar effect creates durable after-cost SPY excess beyond static exposure-matched equity exposure.','contract':{'position':'SPY on first three and last trading day of each month, otherwise BIL; calendar known ex ante','cost_bps':COSTS,'primary_cost_bps':PC,'windows':WINDOWS,'folds':5,'matched':'static SPY/BIL at evaluated mean SPY exposure','opportunity_control':'SPY','predeclared_gate':'2015+ at 10 bps positive matched excess, >=3/5 positive matched folds, candidate max drawdown no worse than matched','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(close.index[-1].date()),'panel_sha256':sha},'tests':{}}
for c in COSTS:
 r['tests'][str(c)]={}
 for k,s in WINDOWS.items():
  q=z.loc[pd.Timestamp(s):]; x=evaluate(q,c); fs=folds(q,c); x['folds']=fs; x['positive_matched_folds']=sum(a['matched_excess']>0 for a in fs); x['positive_spy_folds']=sum(a['spy_excess']>0 for a in fs); r['tests'][str(c)][k]=x
p=r['tests'][str(PC)]['2015']; r['decision']='P175_TURN_OF_MONTH_SURVIVOR' if p['excess_matched']>0 and p['positive_matched_folds']>=3 and p['candidate']['maxdd']>=p['matched']['maxdd'] else 'P175_TURN_OF_MONTH_REJECT'
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p175_spy_turn_of_month_r1.json').write_text(json.dumps(r,sort_keys=True,indent=2)); print(json.dumps(r,sort_keys=True))
