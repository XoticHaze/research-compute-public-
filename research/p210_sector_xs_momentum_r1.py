import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
ALL=SECTORS+['SPY']
WINDOWS={'2006':'2006-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}
LOOKBACK=12; TOPK=2; COST_BPS=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r)
 c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**0.5)
 return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def cost_series(gross,w):
 dw=w.diff().abs().sum(axis=1); dw.iloc[0]=w.iloc[0].abs().sum();
 return gross-(COST_BPS/10000)*dw

def evaluate(px,start):
 q=px.loc[pd.Timestamp(start):].copy(); r=q.pct_change(); score=q[SECTORS].pct_change(LOOKBACK).shift(1)
 w=pd.DataFrame(0.0,index=q.index,columns=SECTORS)
 for dt,row in score.iterrows():
  v=row.dropna()
  if len(v)>=TOPK:
   w.loc[dt,v.nlargest(TOPK).index]=1/TOPK
 gross=(w*r[SECTORS]).sum(axis=1)
 strat=cost_series(gross,w)
 bw=pd.DataFrame(1/len(SECTORS),index=q.index,columns=SECTORS)
 base=cost_series((bw*r[SECTORS]).sum(axis=1),bw)
 spy=r['SPY'].copy(); spy.iloc[0]-=COST_BPS/10000; spy.iloc[-1]-=COST_BPS/10000
 valid=(w.sum(axis=1)>0) & gross.notna(); strat=strat[valid]; base=base.loc[strat.index]; spy=spy.loc[strat.index]
 sm,bm,pm=met(strat),met(base),met(spy)
 folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(strat)),5),1):
  s=strat.iloc[ix]; b=base.iloc[ix]; p=spy.iloc[ix]; folds.append({'fold':i,'strategy_minus_equalweight':met(s)['cagr']-met(b)['cagr'],'strategy_minus_spy':met(s)['cagr']-met(p)['cagr']})
 return {'strategy':sm,'equalweight':bm,'spy':pm,'strategy_minus_equalweight':sm['cagr']-bm['cagr'],'strategy_minus_spy':sm['cagr']-pm['cagr'],'positive_equalweight_folds':sum(x['strategy_minus_equalweight']>0 for x in folds),'positive_spy_folds':sum(x['strategy_minus_spy']>0 for x in folds),'folds':folds,'avg_monthly_turnover':float(w.loc[strat.index].diff().abs().sum(axis=1).mean()),'months':len(strat)}

raw=yf.download(ALL,start='2004-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False)
cl=raw['Close'][ALL] if isinstance(raw.columns,pd.MultiIndex) else raw[ALL]
cl=cl.dropna(how='any').resample('ME').last()
tests={k:evaluate(cl,v) for k,v in WINDOWS.items()}
a,b,c,d=(tests[k] for k in ['2006','2010','2015','2020'])
pass_windows=all(x['strategy_minus_equalweight']>0 and x['strategy_minus_spy']>0 for x in (a,b,c,d))
decision='P210_SECTOR_XS_MOMENTUM_SURVIVOR' if pass_windows and b['positive_equalweight_folds']>=4 and b['positive_spy_folds']>=4 else 'P210_SECTOR_XS_MOMENTUM_REJECT'
out={'schema':'research.p210_sector_xs_momentum_r1','parent':'P210','hypothesis':'A frozen monthly top-2 cross-sectional 12-month momentum selector across the nine long-history US sector ETFs creates durable after-cost excess versus an equal-weight same-universe control and SPY.','contract':{'universe':SECTORS,'lookback_months':LOOKBACK,'top_k':TOPK,'rebalance':'monthly','signal_lag_months':1,'matched_control':'monthly equal-weight same sector universe','opportunity_cost':'SPY','external_cost_bps_per_dollar_traded':COST_BPS,'windows':WINDOWS,'chronological_folds':5,'gate':'positive excess versus both controls in every window plus >=4/5 positive 2010+ folds versus each','no_parameter_window_universe_topk_or_threshold_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p210_sector_xs_momentum_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
