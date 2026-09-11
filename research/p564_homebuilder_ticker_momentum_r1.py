from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
END='2026-09-11'; COST_BPS=10.0
NAMES=['DHI','LEN','PHM','NVR','TOL','KBH','MTH','MHO','TMHC','LGIH','BLD','OC']
FOLDS=[('2014-01-01','2017-12-31'),('2018-01-01','2021-12-31'),('2022-01-01',END)]
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod());return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):
    e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def ev(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'equal_universe':stats(z.equal_universe),'XHB':stats(z.XHB),'matched_excess_cagr':cagr(z.strategy)-cagr(z.equal_universe),'xhb_excess_cagr':cagr(z.strategy)-cagr(z.XHB),'turnover_units':float(z.turnover.sum()),'mean_names':float(z.names.mean())}
def main():
    tickers=NAMES+['XHB'];raw=yf.download(tickers,start='2012-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;c=c[tickers].dropna(how='all').ffill();r=c.pct_change();m=c[NAMES].resample('ME').last();score=m.shift(1)/m.shift(12)-1;picks=score.rank(axis=1,ascending=False,method='first')<=3;w=picks.astype(float).div(picks.sum(axis=1),axis=0).fillna(0);dw=w.reindex(r.index,method='ffill').shift(1).fillna(0);name_r=r[NAMES];prev=dw.shift(1).fillna(0);turn=(dw-prev).abs().sum(axis=1)/2;strat=(dw*name_r.fillna(0)).sum(axis=1)-turn*(COST_BPS/10000);available=name_r.notna().sum(axis=1).replace(0,pd.NA);eq=name_r.sum(axis=1,skipna=True)/available;d=pd.DataFrame({'strategy':strat,'equal_universe':eq,'XHB':r.XHB,'turnover':turn,'names':(dw>0).sum(axis=1)});d=d.loc[(dw.sum(axis=1)>0)&d.equal_universe.notna()&d.XHB.notna()].dropna();overall=ev(d,'2014-01-01',END);folds=[ev(d,*f) for f in FOLDS];ep=sum(x['matched_excess_cagr']>0 for x in folds);xp=sum(x['xhb_excess_cagr']>0 for x in folds);decision='P564_SUPPORTED' if overall['matched_excess_cagr']>0 and overall['xhb_excess_cagr']>0 and ep>=2 and xp>=2 else 'P564_NOT_SUPPORTED_NO_RESCUE';out={'schema':'research.p564_homebuilder_ticker_momentum_r1','parent':'P564','tests_architecture_from':'P562','claim':'The exact P562 monthly 12-1 top-3 ticker momentum rule transports to a fixed liquid homebuilder/building-products cohort with durable after-cost excess over both its equal-weight same-name universe and XHB.','frozen_contract':{'universe':NAMES,'universe_note':'fixed present-day liquid homebuilder/building-products cohort; same fixed-universe control handles survivorship comparison','selection':'top 3 by trailing 12-month return excluding latest month','rebalance':'monthly, applied following session','cost_bps_per_one_way_turnover':COST_BPS,'controls':['equal-weight available names from same fixed universe','XHB'],'folds':FOLDS,'gate':'positive aggregate excess vs both controls and >=2/3 positive folds vs each','parameter_changes_from_p562':0,'no_parameter_rescue':True},'overall':overall,'folds':folds,'positive_fold_count_vs_equal_universe':ep,'positive_fold_count_vs_xhb':xp,'decision':decision,'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}};Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p564_homebuilder_ticker_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
