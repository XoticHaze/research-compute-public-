from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
SYMBOLS=('SPY','QQQ','TLT','GLD','DBC'); COSTS=(25,50,100); LOOKBACK=10

def cagr(x):
 x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1) if len(x) else float('nan')
def mdd(x):
 w=(1+pd.Series(x,dtype=float).dropna()).cumprod(); return float((w/w.cummax()-1).min())
def sharpe(x):
 x=pd.Series(x,dtype=float).dropna(); s=x.std(ddof=0); return float(x.mean()/s*math.sqrt(12)) if s>0 else float('nan')
def build(m):
 rec=[]; prev={s:0.0 for s in SYMBOLS}
 for i in range(LOOKBACK,len(m)-1):
  sig=m.index[i]; out=m.index[i+1]; sma=m.iloc[i-LOOKBACK+1:i+1].mean(); elig=[s for s in SYMBOLS if float(m.loc[sig,s])>float(sma[s])]
  w={s:(1/len(elig) if s in elig else 0.0) for s in SYMBOLS} if elig else {s:0.0 for s in SYMBOLS}
  r=m.loc[out]/m.loc[sig]-1; turn=.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS)
  rec.append({'date':out,'gross':sum(w[s]*float(r[s]) for s in SYMBOLS),'matched':float(r.mean()),'qqq':float(r['QQQ']),'turnover':turn,'invested':sum(w.values())}); prev=w
 return pd.DataFrame(rec).set_index('date')
def score(f,bp):
 cand=f.gross-f.turnover*bp/10000.; folds=[]
 for n,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
  q=f.iloc[ids]; c=q.gross-q.turnover*bp/10000.; folds.append({'fold':n,'ew':cagr(c)-cagr(q.matched),'qqq':cagr(c)-cagr(q.qqq)})
 return {'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'candidate_cagr':cagr(cand),'matched_cagr':cagr(f.matched),'qqq_cagr':cagr(f.qqq),'excess_vs_matched':cagr(cand)-cagr(f.matched),'excess_vs_qqq':cagr(cand)-cagr(f.qqq),'candidate_max_drawdown':mdd(cand),'matched_max_drawdown':mdd(f.matched),'candidate_sharpe':sharpe(cand),'matched_sharpe':sharpe(f.matched),'positive_folds_vs_matched':sum(x['ew']>0 for x in folds),'positive_folds_vs_qqq':sum(x['qqq']>0 for x in folds),'annual_turnover':float(f.turnover.mean()*12),'mean_invested':float(f.invested.mean()),'folds':folds}
def main():
 px=yf.download(list(SYMBOLS),start='2005-01-01',auto_adjust=True,progress=False)['Close'][list(SYMBOLS)].dropna(); cutoff=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); m=px.loc[px.index<cutoff].resample('ME').last(); f=build(m); tests={}
 for bp in COSTS:
  tests[str(bp)]={'full':score(f,bp),'2019_forward':score(f.loc[f.index>=pd.Timestamp('2019-01-01')],bp),'2022_forward':score(f.loc[f.index>=pd.Timestamp('2022-01-01')],bp)}
 p=tests['50']; ok=p['full']['excess_vs_matched']>0 and p['full']['positive_folds_vs_matched']>=3 and p['2022_forward']['excess_vs_matched']>0
 out={'schema':'research.p84_crossasset_trend_breadth_r1','parent':'P84','hypothesis':'A fixed multi-asset trend-breadth allocator can improve after-cost return/risk over exact same-universe equal weight without cross-sectional ranking.','contract':{'universe':list(SYMBOLS),'rule':'month-end close above trailing 10-month average; equal weight among eligible assets; unallocated capital cash','lookback_months':LOOKBACK,'costs_bps':list(COSTS),'matched_control':'same-universe equal weight exact months','opportunity_control':'QQQ exact months','no_parameter_search':True},'tests':tests,'decision':'P84_TREND_BREADTH_SUPPORTED_FOR_DEPTH' if ok else 'P84_TREND_BREADTH_NOT_SUPPORTED','next_rule':'If unsupported, kill exact family without lookback rescue. If supported, next discriminator must use an independent representation and causal entry delay.'}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p84_crossasset_trend_breadth_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'tests':tests},sort_keys=True))
if __name__=='__main__': main()
