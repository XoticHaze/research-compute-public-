from __future__ import annotations
import json,math
from pathlib import Path
import pandas as pd,yfinance as yf
END='2026-09-11';COST_BPS=10.0
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
FOLDS=[('2001-01-01','2007-12-31'),('2008-01-01','2013-12-31'),('2014-01-01','2019-12-31'),('2020-01-01',END)]
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod());return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def ev(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'equal_sector':stats(z.equal_sector),'SPY':stats(z.SPY),'matched_excess_cagr':cagr(z.strategy)-cagr(z.equal_sector),'spy_excess_cagr':cagr(z.strategy)-cagr(z.SPY),'turnover_units':float(z.turnover.sum())}
def main():
    ts=SECTORS+['SPY'];raw=yf.download(ts,start='1999-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;c=c[ts].dropna(how='all').ffill();r=c.pct_change().dropna(how='all');neg=r[SECTORS].clip(upper=0);dv=neg.pow(2).rolling(126,min_periods=100).mean().pow(.5)*math.sqrt(252);ms=dv.resample('ME').last();inv=1/ms.replace(0,pd.NA);w=inv.div(inv.sum(axis=1),axis=0).fillna(0);dw=w.reindex(r.index,method='ffill').shift(1).fillna(0);prev=dw.shift(1).fillna(0);turn=(dw-prev).abs().sum(axis=1)/2;strat=(dw*r[SECTORS].fillna(0)).sum(axis=1)-turn*(COST_BPS/10000);eq=r[SECTORS].mean(axis=1);d=pd.DataFrame({'strategy':strat,'equal_sector':eq,'SPY':r.SPY,'turnover':turn});d=d.loc[dw.sum(axis=1)>0].dropna();overall=ev(d,'2001-01-01',END);folds=[ev(d,*f) for f in FOLDS];ep=sum(x['matched_excess_cagr']>0 for x in folds);sp=sum(x['spy_excess_cagr']>0 for x in folds);decision='P559_SUPPORTED' if overall['matched_excess_cagr']>0 and overall['spy_excess_cagr']>0 and ep>=3 and sp>=3 else 'P559_NOT_SUPPORTED_NO_RESCUE';out={'schema':'research.p559_sector_downside_risk_parity_r1','parent':'P559','claim':'Monthly inverse-downside-volatility weighting across all nine classic SPDR sectors can produce durable after-cost excess over equal-sector and SPY controls.','frozen_contract':{'feature':'trailing 126-session downside volatility','weighting':'inverse downside volatility across all sectors, normalized to 100%','rebalance':'monthly, applied following session','cost_bps_per_one_way_turnover':COST_BPS,'controls':['equal-weight sector universe','SPY'],'folds':FOLDS,'gate':'positive aggregate excess vs both and >=3/4 positive folds vs each','no_parameter_rescue':True},'overall':overall,'folds':folds,'positive_fold_count_vs_equal_sector':ep,'positive_fold_count_vs_spy':sp,'decision':decision,'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}};Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p559_sector_downside_risk_parity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
