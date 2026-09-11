from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, requests, yfinance as yf
API='https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query'
START='2004-01-01'; END='2026-09-11'; COST_BPS=10.0
FOLDS=[('2004-01-01','2009-12-31'),('2010-01-01','2015-12-31'),('2016-01-01','2021-12-31'),('2022-01-01',END)]
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod())
    return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):
    e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def fetch():
    p={'format':'json','fields':'auction_date,security_type,security_term,bid_to_cover_ratio','filter':'security_type:eq:Note,security_term:eq:10-Year','sort':'auction_date','page[size]':'5000'}
    x=requests.get(API,params=p,headers={'User-Agent':'XoticHaze-Research/1.0'},timeout=(15,60));x.raise_for_status();j=x.json();d=pd.DataFrame(j['data'])
    d['auction_date']=pd.to_datetime(d['auction_date']);d['btc']=pd.to_numeric(d['bid_to_cover_ratio'],errors='coerce');d=d.dropna(subset=['auction_date','btc']).sort_values('auction_date')
    d['median']=d['btc'].expanding(min_periods=12).median();d['long_w']=(d['btc']>=d['median']).astype(float)
    # Auction result is public on auction date; use only the final completed auction of each month and apply next month.
    m=d.set_index('auction_date')['long_w'].resample('ME').last().dropna().shift(1).dropna();return m,j.get('meta',{}),d
def evaluate(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'control':stats(z.control),'TLT':stats(z.TLT),'SHY':stats(z.SHY),'SPY':stats(z.SPY),'matched_excess_cagr':cagr(z.strategy)-cagr(z.control),'spy_excess_cagr':cagr(z.strategy)-cagr(z.SPY),'switches':int(z.switch.sum()),'long_weight_mean':float(z.long_w.mean())}
def main():
    sig,meta,au=fetch();raw=yf.download(['TLT','SHY','SPY'],start='2003-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;r=close[['TLT','SHY','SPY']].dropna().pct_change().dropna();d=r.join(sig.reindex(r.index,method='ffill').rename('long_w')).dropna();d['short_w']=1-d.long_w;d['switch']=d.long_w.diff().abs().fillna(0);d['strategy']=d.long_w*d.TLT+d.short_w*d.SHY-d.switch*(COST_BPS/10000);d['control']=0.5*d.TLT+0.5*d.SHY
    overall=evaluate(d,START,END);folds=[evaluate(d,*f) for f in FOLDS];positive=sum(f['matched_excess_cagr']>0 for f in folds);decision='P551_SUPPORTED' if overall['matched_excess_cagr']>0 and positive>=3 else 'P551_NOT_SUPPORTED_NO_RESCUE'
    out={'schema':'research.p551_treasury_auction_demand_duration_r1','parent':'P551','claim':'Primary-market 10Y Treasury auction demand can causally rotate long versus short Treasury funds with durable after-cost excess over a static duration mix.','frozen_contract':{'source':API,'feature':'10-Year Note bid_to_cover_ratio','signal':'last completed auction each month; bid-to-cover at/above expanding median after 12 auctions => TLT, else SHY; applied following month','control':'static 50/50 TLT/SHY','opportunity_controls':['TLT','SHY','SPY'],'cost_bps_per_full_switch':COST_BPS,'folds':FOLDS,'no_parameter_rescue':True},'overall':overall,'folds':folds,'positive_fold_count':positive,'decision':decision,'source_diagnostics':{'usable_auctions':int(len(au)),'first_auction':str(au.auction_date.min().date()),'last_auction':str(au.auction_date.max().date()),'meta':meta},'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p551_treasury_auction_demand_duration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
