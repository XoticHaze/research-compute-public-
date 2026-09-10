import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['XMMO','XMHQ','MDY','IJH','SPY']; W={'2007':'2007-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; COSTS=[10,25,50]

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def passive_cost(r,bps):
 q=pd.Series(r).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def blend_returns(d,bps):
 f=bps/10000; out=[]; w=np.array([.5,.5],dtype=float)
 for i,(_,row) in enumerate(d[['XMMO','XMHQ']].iterrows()):
  target=np.array([.5,.5]); turnover=float(np.abs(target-w).sum()) if i else 1.0
  rr=target*np.array([row['XMMO'],row['XMHQ']],dtype=float)
  port=float(rr.sum()-turnover*f)
  gross=target*(1+np.array([row['XMMO'],row['XMHQ']],dtype=float))
  w=gross/gross.sum()
  out.append(port)
 s=pd.Series(out,index=d.index)
 if len(s): s.iloc[-1]-=f
 return s
def ev(d,bps):
 br=blend_returns(d,bps); m={'BLEND':met(br)}
 for a in ['XMMO','XMHQ','MDY','IJH','SPY']: m[a]=met(passive_cost(d[a],bps))
 fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; bm=met(blend_returns(q,bps)); mm={a:met(passive_cost(q[a],bps)) for a in ['XMMO','MDY','IJH','SPY']}
  fs.append({'fold':i,'blend_minus_mdy':bm['cagr']-mm['MDY']['cagr'],'blend_minus_ijh':bm['cagr']-mm['IJH']['cagr'],'blend_minus_spy':bm['cagr']-mm['SPY']['cagr'],'blend_minus_xmmo':bm['cagr']-mm['XMMO']['cagr']})
 return {'metrics':m,'blend_minus_mdy':m['BLEND']['cagr']-m['MDY']['cagr'],'blend_minus_ijh':m['BLEND']['cagr']-m['IJH']['cagr'],'blend_minus_spy':m['BLEND']['cagr']-m['SPY']['cagr'],'blend_minus_xmmo':m['BLEND']['cagr']-m['XMMO']['cagr'],'positive_mdy_folds':sum(x['blend_minus_mdy']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2006-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={str(b):{k:ev(r.loc[pd.Timestamp(v):],b) for k,v in W.items()} for b in COSTS}; p=tests['25']; support=all(p[k]['blend_minus_mdy']>0 for k in W) and p['2010']['positive_mdy_folds']>=4 and tests['50']['2010']['blend_minus_mdy']>0; decision='P222_FIXED_FACTOR_BLEND_SUPPORT' if support else 'P222_FIXED_FACTOR_BLEND_NOT_SUPPORTED'; out={'schema':'research.p222_midcap_factor_blend_r1','parent':'P222','hypothesis':'A frozen 50/50 monthly XMMO/XMHQ blend can repair XMMO chronology persistence while preserving after-cost matched-size excess.','contract':{'components':['XMMO','XMHQ'],'weights':[.5,.5],'rebalance':'monthly','primary_matched_control':'MDY','secondary_matched_control':'IJH','opportunity_context':'SPY','windows':W,'chronological_folds':5,'cost_bps':COSTS,'primary_cost_bps':25,'gate':'positive blend-MDY CAGR every window at 25 bps, >=4/5 positive MDY folds from 2010, and positive 2010 blend-MDY at 50 bps','no_weight_window_fund_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p222_midcap_factor_blend_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))