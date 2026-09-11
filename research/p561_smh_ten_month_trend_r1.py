from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
END='2026-09-11'; COST_BPS=10.0
FOLDS=[('2007-01-01','2013-12-31'),('2014-01-01','2019-12-31'),('2020-01-01',END)]
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod());return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):
    e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def ev(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'matched_exposure_control':stats(z.control),'SMH':stats(z.SMH),'SPY':stats(z.SPY),'matched_excess_cagr':cagr(z.strategy)-cagr(z.control),'smh_excess_cagr':cagr(z.strategy)-cagr(z.SMH),'spy_excess_cagr':cagr(z.strategy)-cagr(z.SPY),'turnover_units':float(z.turnover.sum()),'exposure_mean':float(z.exposure.mean())}
def main():
    raw=yf.download(['SMH','SPY'],start='2006-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;c=c[['SMH','SPY']].dropna().ffill();r=c.pct_change().dropna();m=c.SMH.resample('ME').last();ma=m.rolling(10,min_periods=10).mean();sig=(m>ma).astype(float).rename('exposure');exp=sig.reindex(r.index,method='ffill').shift(1).dropna();d=r.join(exp).dropna();d['turnover']=d.exposure.diff().abs().fillna(0);d['strategy']=d.exposure*d.SMH-d.turnover*(COST_BPS/10000);mean_exp=float(d.exposure.mean());d['control']=mean_exp*d.SMH
    overall=ev(d,'2007-01-01',END);folds=[ev(d,*f) for f in FOLDS];mp=sum(x['matched_excess_cagr']>0 for x in folds);sp=sum(x['spy_excess_cagr']>0 for x in folds);decision='P561_SUPPORTED' if overall['matched_excess_cagr']>0 and overall['spy_excess_cagr']>0 and mp>=2 and sp>=2 and overall['strategy']['max_drawdown']>overall['SMH']['max_drawdown'] else 'P561_NOT_SUPPORTED_NO_RESCUE'
    out={'schema':'research.p561_smh_ten_month_trend_r1','parent':'P561','claim':'A frozen 10-month moving-average trend filter on SMH can preserve its industry premium while creating after-cost excess over an exposure-matched SMH control and SPY, with lower drawdown than buy-and-hold SMH.','frozen_contract':{'asset':'SMH','feature':'month-end close versus trailing 10-month simple moving average','signal':'100% SMH when close > 10-month MA; otherwise cash','availability':'decision applied following session','transition_cost_bps':COST_BPS,'matched_control':'constant SMH weight equal to strategy mean exposure, remainder cash','secondary_control':'SPY buy-and-hold','folds':FOLDS,'gate':'positive aggregate excess vs matched and SPY, >=2/3 positive folds vs each, and lower max drawdown than SMH','no_parameter_rescue':True},'overall':overall,'folds':folds,'positive_fold_count_vs_matched':mp,'positive_fold_count_vs_spy':sp,'decision':decision,'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p561_smh_ten_month_trend_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
