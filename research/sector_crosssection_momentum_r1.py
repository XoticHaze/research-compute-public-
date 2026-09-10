from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; CONTROLS=['SPY','QQQ']; START='2006-01-01'; END='2026-09-11'; LOOKBACK=12; TOPK=3; COST=10/10000; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for pos in np.array_split(np.arange(len(z)),5):
  c=z.iloc[pos]
  if len(c)>=12: out.append(metric(c.a)['cagr']-metric(c.b)['cagr'])
 return out
raw=yf.download(SECTORS+CONTROLS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SECTORS+CONTROLS].dropna().resample('ME').last(); r=px.pct_change(); trailing=px[SECTORS].pct_change(LOOKBACK).shift(1); weights=pd.DataFrame(0.,index=px.index,columns=SECTORS)
for dt,row in trailing.iterrows():
 valid=row.dropna()
 if len(valid)==len(SECTORS): weights.loc[dt,valid.nlargest(TOPK).index]=1/TOPK
turnover=weights.diff().abs().sum(axis=1)/2; turnover.iloc[0]=weights.iloc[0].abs().sum()/2; gross=(weights*r[SECTORS]).sum(axis=1); net=gross-turnover*COST; ew=r[SECTORS].mean(axis=1); results={}
for name,start in WINDOWS.items():
 ix=px.index>=pd.Timestamp(start); cand=net.loc[ix].dropna(); matched=ew.loc[ix].reindex(cand.index); spy=r.SPY.loc[ix].reindex(cand.index); qqq=r.QQQ.loc[ix].reindex(cand.index); f=folds(cand,matched); cm=metric(cand); bm=metric(matched); sm=metric(spy); qm=metric(qqq); results[name]={'candidate':cm,'matched_equal_sector':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'vs_SPY_cagr':cm['cagr']-sm['cagr'],'vs_QQQ_cagr':cm['cagr']-qm['cagr'],'average_monthly_turnover':float(turnover.loc[ix].mean()),'total_cost_fraction_sum':float((turnover.loc[ix]*COST).sum())}
p=results['2010']; q=results['2015']; s=results['2020']; ok=p['matched_excess_cagr']>0 and p['positive_matched_folds']>=3 and q['matched_excess_cagr']>0 and q['positive_matched_folds']>=3 and s['matched_excess_cagr']>0 and s['positive_matched_folds']>=3
out={'schema':'research.sector_crosssection_momentum_r1','workload_id':'SECTOR_CROSSSECTION_MOMENTUM_R1','claim':'Test whether a frozen cross-sectional sector-selection model using prior 12-month return to hold the top three of a fixed nine-sector universe monthly earns durable after-cost excess versus equal-weight exposure to the same opportunity set, with SPY/QQQ opportunity context.','parameters':{'sectors':SECTORS,'lookback_months':LOOKBACK,'top_k':TOPK,'one_way_turnover_cost_bps':10,'signal_shift_months':1,'windows':WINDOWS,'no_parameter_or_universe_search':True},'results':results,'decision_rule':'SUPPORTED only if matched excess is positive with >=3/5 positive chronological folds in each 2010+, 2015+, and 2020+ window after realized turnover costs. SPY and QQQ are opportunity-cost context, not substitutes for the matched same-universe control.','decision':'SECTOR_CROSSSECTION_MOMENTUM_SUPPORTED' if ok else 'SECTOR_CROSSSECTION_MOMENTUM_NOT_SUPPORTED','limitations':['fixed legacy nine-sector SPDR universe avoids later-inception XLC/XLRE and is not historical constituent-level selection','Yahoo adjusted ETF prices are research-only','scientific discriminator only; no portfolio-ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/sector_crosssection_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
