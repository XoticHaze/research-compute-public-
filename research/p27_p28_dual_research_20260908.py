#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, math, time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

START = int(dt.datetime(1998,1,1,tzinfo=dt.timezone.utc).timestamp())
END = int(dt.datetime(2026,9,8,tzinfo=dt.timezone.utc).timestamp())
UA = 'Mozilla/5.0 research-only fixed-discriminator/20260908'
COSTS = (10,25,50)


def fetch(symbol):
    url=(f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?'
         f'period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true')
    last=None
    for attempt in range(1,6):
        try:
            req=Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
            raw=urlopen(req,timeout=30).read()
            obj=json.loads(raw)
            r=obj['chart']['result'][0]
            ts=r['timestamp']
            adj=(r.get('indicators',{}).get('adjclose') or [{}])[0].get('adjclose')
            if adj is None:
                adj=r['indicators']['quote'][0]['close']
            s=pd.Series(adj,index=pd.to_datetime(ts,unit='s',utc=True).tz_convert(None),dtype='float64').dropna()
            s=s[~s.index.duplicated(keep='last')].sort_index()
            if len(s)<1200: raise RuntimeError(f'insufficient rows={len(s)}')
            return s, {'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'rows':len(s),'start':s.index[0].date().isoformat(),'end':s.index[-1].date().isoformat(),'attempt':attempt}
        except Exception as exc:
            last=exc
            if attempt<5: time.sleep(2*attempt)
    raise RuntimeError(f'{symbol} source failure after retries: {type(last).__name__}: {last}')


def common_monthly(symbols):
    series={}; prov={}
    for s in symbols:
        series[s],prov[s]=fetch(s)
    daily=pd.concat(series,axis=1).sort_index().ffill(limit=3).dropna()
    monthly=daily.resample('ME').last().dropna()
    return daily,monthly,prov


def perf_from_monthly(r):
    r=pd.Series(r).dropna()
    if len(r)<2: return {'months':len(r),'cagr':None,'max_dd':None,'vol':None,'sharpe':None}
    wealth=(1+r).cumprod()
    years=len(r)/12.0
    cagr=float(wealth.iloc[-1]**(1/years)-1)
    dd=wealth/wealth.cummax()-1
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else 0.0
    ann=float(r.mean()*12)
    return {'months':len(r),'cagr':cagr,'max_dd':float(dd.min()),'vol':vol,'sharpe':ann/vol if vol>0 else None}


def fold_excess(strategy,control,n=5):
    d=pd.concat({'s':strategy,'c':control},axis=1).dropna()
    chunks=np.array_split(np.arange(len(d)),n)
    vals=[]
    for i,ix in enumerate(chunks,1):
        q=d.iloc[ix]
        ps=perf_from_monthly(q.s); pc=perf_from_monthly(q.c)
        vals.append({'fold':i,'start':q.index[0].date().isoformat(),'end':q.index[-1].date().isoformat(),'strategy_cagr':ps['cagr'],'control_cagr':pc['cagr'],'excess_cagr':ps['cagr']-pc['cagr']})
    return vals


def yearly_excess(strategy,control):
    d=pd.concat({'s':strategy,'c':control},axis=1).dropna()
    out=[]
    for y,g in d.groupby(d.index.year):
        sr=float((1+g.s).prod()-1); cr=float((1+g.c).prod()-1)
        out.append({'year':int(y),'strategy':sr,'control':cr,'excess':sr-cr})
    return out


def cost_adjust(gross,weights,bps):
    w=weights.copy().fillna(0.0)
    prev=w.shift(1).fillna(0.0)
    turnover=(w-prev).abs().sum(axis=1)/2.0
    return gross-(bps/10000.0)*turnover, turnover


def run_p27():
    sectors=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
    all_syms=sectors+['SPY','QQQ']
    daily,m,prov=common_monthly(all_syms)
    mr=m.pct_change()
    feats=[]
    for sym in sectors:
        x=pd.DataFrame(index=m.index)
        x['symbol']=sym
        x['mom1']=m[sym].pct_change(1)
        x['mom3']=m[sym].pct_change(3)
        x['mom6']=m[sym].pct_change(6)
        x['mom12']=m[sym].pct_change(12)
        x['vol6']=mr[sym].rolling(6).std()
        x['drawdown12']=m[sym]/m[sym].rolling(12).max()-1
        x['target']=mr[sym].shift(-1)-mr[sectors].mean(axis=1).shift(-1)
        feats.append(x)
    panel=pd.concat(feats).reset_index(names='date').sort_values(['date','symbol'])
    cols=['mom1','mom3','mom6','mom12','vol6','drawdown12']
    dates=sorted(panel.dropna(subset=cols).date.unique())
    weights=pd.DataFrame(0.0,index=m.index,columns=sectors)
    predictions=[]
    min_date=pd.Timestamp('2003-01-31')
    for date in dates:
        date=pd.Timestamp(date)
        if date<min_date: continue
        train=panel[(panel.date<date)&panel.target.notna()].dropna(subset=cols)
        test=panel[panel.date==date].dropna(subset=cols)
        if len(train)<500 or len(test)!=len(sectors): continue
        model=make_pipeline(StandardScaler(),Ridge(alpha=10.0))
        model.fit(train[cols],train.target)
        pred=model.predict(test[cols])
        ranked=sorted(zip(test.symbol,pred),key=lambda z:z[1],reverse=True)
        chosen=[x[0] for x in ranked[:2]]
        weights.loc[date,chosen]=0.5
        predictions.append({'date':date.date().isoformat(),'chosen':chosen,'score_gap_top2_vs_median':float(np.mean([x[1] for x in ranked[:2]])-np.median([x[1] for x in ranked]))})
    weights=weights.loc[weights.sum(axis=1)>0]
    next_ret=mr[sectors].shift(-1).reindex(weights.index)
    gross=(weights*next_ret).sum(axis=1)
    control=mr[sectors].mean(axis=1).shift(-1).reindex(weights.index)
    spy=mr['SPY'].shift(-1).reindex(weights.index); qqq=mr['QQQ'].shift(-1).reindex(weights.index)
    costs={}; turnovers=None
    for bps in COSTS:
        net,turn=cost_adjust(gross,weights,bps); turnovers=turn
        costs[str(bps)]={'strategy':perf_from_monthly(net),'static_sector_ew':perf_from_monthly(control),'spy':perf_from_monthly(spy),'qqq':perf_from_monthly(qqq),'excess_vs_sector_ew_cagr':perf_from_monthly(net)['cagr']-perf_from_monthly(control)['cagr'],'excess_vs_spy_cagr':perf_from_monthly(net)['cagr']-perf_from_monthly(spy)['cagr']}
    net25,_=cost_adjust(gross,weights,25)
    folds=fold_excess(net25,control); years=yearly_excess(net25,control)
    gate=(costs['25']['excess_vs_sector_ew_cagr']>0 and costs['25']['excess_vs_spy_cagr']>0 and sum(f['excess_cagr']>0 for f in folds)>=3 and costs['50']['excess_vs_sector_ew_cagr']>0)
    return {'schema':'p27-sector-cross-sectional-ridge.v1','child':'P27-C1','mechanism':'fixed expanding pooled Ridge cross-sectional sector excess-return ranker; top-2 next-month allocation','feature_contract':cols,'ridge_alpha':10.0,'universe':sectors,'matched_window':{'start':gross.dropna().index.min().date().isoformat(),'end':gross.dropna().index.max().date().isoformat(),'months':int(gross.dropna().shape[0])},'source':{'provider':'Yahoo Finance Chart v8 public endpoint','research_only':True,'canonical_mm_claim':False,'symbols':prov},'costs':costs,'turnover':{'mean_monthly':float(turnovers.mean()),'total':float(turnovers.sum())},'chronological_folds_25bps':folds,'yearly_excess_25bps':years,'positive_folds_25bps':sum(f['excess_cagr']>0 for f in folds),'positive_years_25bps':sum(y['excess']>0 for y in years),'represented_years':len(years),'decision':'P27_SECTOR_CROSS_SECTIONAL_ML_SUPPORTED_CANDIDATE' if gate else 'P27_SECTOR_CROSS_SECTIONAL_ML_NOT_SUPPORTED','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}


def run_p28():
    assets=['SPY','TLT','GLD','DBC']; all_syms=assets+['QQQ']
    daily,m,prov=common_monthly(all_syms)
    mr=m.pct_change()
    mom12=m[assets].pct_change(12)
    sma10=m[assets].rolling(10).mean()
    positive=(mom12>0)&(m[assets]>sma10)
    weights=positive.astype(float)
    counts=weights.sum(axis=1).replace(0,np.nan)
    weights=weights.div(counts,axis=0).fillna(0.0)
    valid=m.index[(mom12.notna().all(axis=1))]
    weights=weights.reindex(valid)
    next_ret=mr[assets].shift(-1).reindex(valid)
    gross=(weights*next_ret).sum(axis=1).dropna()
    weights=weights.reindex(gross.index)
    control=mr[assets].mean(axis=1).shift(-1).reindex(gross.index)
    spy=mr['SPY'].shift(-1).reindex(gross.index); qqq=mr['QQQ'].shift(-1).reindex(gross.index)
    balanced=(0.6*mr['SPY']+0.4*mr['TLT']).shift(-1).reindex(gross.index)
    costs={}; turnovers=None
    for bps in COSTS:
        net,turn=cost_adjust(gross,weights,bps); turnovers=turn
        ps=perf_from_monthly(net); pc=perf_from_monthly(control)
        costs[str(bps)]={'strategy':ps,'static_cross_asset_ew':pc,'spy':perf_from_monthly(spy),'qqq':perf_from_monthly(qqq),'static_60_40':perf_from_monthly(balanced),'excess_vs_cross_asset_ew_cagr':ps['cagr']-pc['cagr'],'excess_vs_spy_cagr':ps['cagr']-perf_from_monthly(spy)['cagr']}
    net25,_=cost_adjust(gross,weights,25)
    folds=fold_excess(net25,control); years=yearly_excess(net25,control)
    gate=(costs['25']['excess_vs_cross_asset_ew_cagr']>0 and sum(f['excess_cagr']>0 for f in folds)>=3 and costs['50']['excess_vs_cross_asset_ew_cagr']>0 and costs['25']['strategy']['max_dd']>=costs['25']['static_cross_asset_ew']['max_dd'])
    return {'schema':'p28-cross-asset-dual-trend.v1','child':'P28-C1','mechanism':'fixed monthly 12-month absolute momentum AND price-above-10-month-SMA; equal-weight qualifying SPY/TLT/GLD/DBC, otherwise cash','universe':assets,'matched_window':{'start':gross.index.min().date().isoformat(),'end':gross.index.max().date().isoformat(),'months':int(len(gross))},'source':{'provider':'Yahoo Finance Chart v8 public endpoint','research_only':True,'canonical_mm_claim':False,'symbols':prov},'costs':costs,'turnover':{'mean_monthly':float(turnovers.mean()),'total':float(turnovers.sum())},'chronological_folds_25bps':folds,'yearly_excess_25bps':years,'positive_folds_25bps':sum(f['excess_cagr']>0 for f in folds),'positive_years_25bps':sum(y['excess']>0 for y in years),'represented_years':len(years),'decision':'P28_CROSS_ASSET_DUAL_TREND_SUPPORTED_CANDIDATE' if gate else 'P28_CROSS_ASSET_DUAL_TREND_NOT_SUPPORTED','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--child',choices=['p27','p28'],required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    out=run_p27() if a.child=='p27' else run_p28()
    Path(a.out).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
    print(('P27_RECEIPT=' if a.child=='p27' else 'P28_RECEIPT=')+json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
