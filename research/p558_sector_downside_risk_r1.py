from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
END='2026-09-11'; COST_BPS=10.0
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
FOLDS=[('2001-01-01','2007-12-31'),('2008-01-01','2013-12-31'),('2014-01-01','2019-12-31'),('2020-01-01',END)]
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod());return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):
    e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def evaluate(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'equal_sector':stats(z.equal_sector),'SPY':stats(z.SPY),'matched_excess_cagr':cagr(z.strategy)-cagr(z.equal_sector),'spy_excess_cagr':cagr(z.strategy)-cagr(z.SPY),'turnover_units':float(z.turnover.sum()),'mean_names':float(z.names.mean())}
def main():
    tickers=SECTORS+['SPY'];raw=yf.download(tickers,start='1999-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;close=close[tickers].dropna(how='all').ffill();daily=close.pct_change().dropna(how='all');neg=daily[SECTORS].clip(upper=0);downside=neg.pow(2).rolling(126,min_periods=100).mean().pow(0.5)*math.sqrt(252)
    month_score=downside.resample('ME').last();picks=month_score.rank(axis=1,ascending=True,method='first')<=3;weights=picks.astype(float).div(picks.sum(axis=1),axis=0).fillna(0.0);daily_w=weights.reindex(daily.index,method='ffill').shift(1).fillna(0.0);sector_r=daily[SECTORS].fillna(0.0);prev=daily_w.shift(1).fillna(0.0);turnover=(daily_w-prev).abs().sum(axis=1)/2.0;strat=(daily_w*sector_r).sum(axis=1)-turnover*(COST_BPS/10000);eq=sector_r.mean(axis=1)
    d=pd.DataFrame({'strategy':strat,'equal_sector':eq,'SPY':daily['SPY'],'turnover':turnover,'names':(daily_w>0).sum(axis=1)});d=d.loc[daily_w.sum(axis=1)>0].dropna();overall=evaluate(d,'2001-01-01',END);folds=[evaluate(d,*f) for f in FOLDS];eqpos=sum(f['matched_excess_cagr']>0 for f in folds);spypos=sum(f['spy_excess_cagr']>0 for f in folds);decision='P558_SUPPORTED' if overall['matched_excess_cagr']>0 and overall['spy_excess_cagr']>0 and eqpos>=3 and spypos>=3 else 'P558_NOT_SUPPORTED_NO_RESCUE'
    out={'schema':'research.p558_sector_downside_risk_r1','parent':'P558','claim':'A frozen monthly selector holding the three classic SPDR sectors with the lowest trailing six-month downside volatility can produce durable after-cost excess over equal-sector and SPY controls.','frozen_contract':{'universe':SECTORS,'feature':'annualized downside volatility from negative daily returns over trailing 126 sessions, min 100','selection':'lowest 3 at month end','rebalance':'monthly, applied following session','cost_bps_per_one_way_turnover':COST_BPS,'controls':['equal-weight sector universe','SPY'],'folds':FOLDS,'gate':'positive aggregate excess vs both controls and >=3/4 positive folds vs each','no_parameter_rescue':True},'overall':overall,'folds':folds,'positive_fold_count_vs_equal_sector':eqpos,'positive_fold_count_vs_spy':spypos,'decision':decision,'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p558_sector_downside_risk_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
