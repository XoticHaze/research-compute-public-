#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, math, time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

START=int(dt.datetime(1998,1,1,tzinfo=dt.timezone.utc).timestamp())
END=int(dt.datetime(2026,9,8,tzinfo=dt.timezone.utc).timestamp())
UA='Mozilla/5.0 research-only fixed-discriminator/20260908-p29p30'
COSTS=(10,25,50)


def fetch(symbol):
    url=(f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true')
    last=None
    for attempt in range(1,6):
        try:
            raw=urlopen(Request(url,headers={'User-Agent':UA,'Accept':'application/json'}),timeout=30).read()
            obj=json.loads(raw); r=obj['chart']['result'][0]; ts=r['timestamp']
            adj=(r.get('indicators',{}).get('adjclose') or [{}])[0].get('adjclose') or r['indicators']['quote'][0]['close']
            s=pd.Series(adj,index=pd.to_datetime(ts,unit='s',utc=True).tz_convert(None),dtype='float64').dropna()
            s=s[~s.index.duplicated(keep='last')].sort_index()
            if len(s)<1000: raise RuntimeError(f'insufficient rows={len(s)}')
            return s,{'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'rows':len(s),'start':s.index[0].date().isoformat(),'end':s.index[-1].date().isoformat(),'attempt':attempt}
        except Exception as exc:
            last=exc
            if attempt<5: time.sleep(2*attempt)
    raise RuntimeError(f'{symbol} source failure: {type(last).__name__}: {last}')


def perf(r,annual=12):
    r=pd.Series(r).dropna()
    w=(1+r).cumprod(); years=len(r)/annual
    cagr=float(w.iloc[-1]**(1/years)-1); dd=w/w.cummax()-1
    vol=float(r.std(ddof=1)*math.sqrt(annual)); ann=float(r.mean()*annual)
    return {'periods':len(r),'cagr':cagr,'max_dd':float(dd.min()),'vol':vol,'sharpe':ann/vol if vol>0 else None}


def folds(strategy,control,n=5):
    d=pd.concat({'s':strategy,'c':control},axis=1).dropna(); out=[]
    for i,ix in enumerate(np.array_split(np.arange(len(d)),n),1):
        q=d.iloc[ix]; ps=perf(q.s); pc=perf(q.c)
        out.append({'fold':i,'start':q.index[0].date().isoformat(),'end':q.index[-1].date().isoformat(),'excess_cagr':ps['cagr']-pc['cagr']})
    return out


def run_p29():
    stocks=['NVDA','AMD','AVGO','QCOM','TXN','AMAT','LRCX','KLAC','MU','ADI','MRVL','MCHP']
    syms=stocks+['SMH','QQQ','SPY']; series={}; prov={}
    for s in syms: series[s],prov[s]=fetch(s)
    daily=pd.concat(series,axis=1).sort_index().ffill(limit=3).dropna(); m=daily.resample('ME').last().dropna(); mr=m.pct_change()
    rel6=m[stocks].pct_change(6).sub(m['SMH'].pct_change(6),axis=0)
    weights=pd.DataFrame(0.0,index=m.index,columns=stocks)
    for date,row in rel6.iterrows():
        if row.notna().all():
            chosen=list(row.nlargest(3).index); weights.loc[date,chosen]=1/3
    weights=weights.loc[weights.sum(axis=1)>0]
    nr=mr[stocks].shift(-1).reindex(weights.index); valid=nr.notna().all(axis=1)
    weights=weights.loc[valid]; nr=nr.loc[valid]
    gross=(weights*nr).sum(axis=1)
    control=mr[stocks].mean(axis=1).shift(-1).reindex(weights.index)
    smh=mr['SMH'].shift(-1).reindex(weights.index); qqq=mr['QQQ'].shift(-1).reindex(weights.index); spy=mr['SPY'].shift(-1).reindex(weights.index)
    prev=weights.shift(1).fillna(0); turn=(weights-prev).abs().sum(axis=1)/2
    costs={}
    for bps in COSTS:
        net=gross-turn*bps/10000.0
        costs[str(bps)]={'strategy':perf(net),'semiconductor_ew':perf(control),'smh':perf(smh),'qqq':perf(qqq),'spy':perf(spy),'excess_vs_semiconductor_ew_cagr':perf(net)['cagr']-perf(control)['cagr'],'excess_vs_smh_cagr':perf(net)['cagr']-perf(smh)['cagr']}
    net25=gross-turn*.0025; fs=folds(net25,control)
    yearly=[]
    d=pd.concat({'s':net25,'c':control},axis=1).dropna()
    for y,g in d.groupby(d.index.year): yearly.append({'year':int(y),'excess':float((1+g.s).prod()-(1+g.c).prod())})
    gate=(costs['25']['excess_vs_semiconductor_ew_cagr']>0 and costs['25']['excess_vs_smh_cagr']>0 and sum(x['excess_cagr']>0 for x in fs)>=3 and costs['50']['excess_vs_semiconductor_ew_cagr']>0)
    return {'schema':'p29.semiconductor_cross_sectional_relative_momentum.v1','child':'P29-C1','mechanism':'monthly top-3 semiconductor stocks by prior-only 6-month total return minus SMH 6-month total return; equal weight next month','universe':stocks,'matched_window':{'start':gross.index.min().date().isoformat(),'end':gross.index.max().date().isoformat(),'months':len(gross)},'source':{'provider':'Yahoo Finance Chart v8','research_only':True,'canonical_mm_claim':False,'symbols':prov},'costs':costs,'mean_monthly_turnover':float(turn.mean()),'chronological_folds_25bps':fs,'positive_folds_25bps':sum(x['excess_cagr']>0 for x in fs),'positive_years_25bps':sum(x['excess']>0 for x in yearly),'represented_years':len(yearly),'decision':'P29_SEMICONDUCTOR_RELATIVE_MOMENTUM_SUPPORTED_CANDIDATE' if gate else 'P29_SEMICONDUCTOR_RELATIVE_MOMENTUM_NOT_SUPPORTED','promotion_authority':False,'live_trading_change':False}


def run_p30():
    syms=['SMH','QQQ','SPY']; s={}; prov={}
    for x in syms: s[x],prov[x]=fetch(x)
    d=pd.concat(s,axis=1).dropna(); r5=d['SMH']/d['SMH'].shift(5)-1
    events=[]; last=-999
    for i in range(5,len(d)-5):
        if i-last<20: continue
        if r5.iloc[i] <= -0.08:
            date=d.index[i]; end=d.index[i+5]
            vals={x:float(d[x].iloc[i+5]/d[x].iloc[i]-1) for x in syms}
            events.append({'date':date,'end':end,**vals}); last=i
    if len(events)<20: raise RuntimeError(f'insufficient events={len(events)}')
    ev=pd.DataFrame(events).set_index('date'); results={}
    for bps in COSTS:
        net=ev.SMH-2*bps/10000.0; exq=net-ev.QQQ; exs=net-ev.SPY
        chunks=np.array_split(np.arange(len(ev)),5); fold=[]
        for k,ix in enumerate(chunks,1): fold.append({'fold':k,'start':ev.index[ix[0]].date().isoformat(),'end':ev.index[ix[-1]].date().isoformat(),'mean_excess_vs_qqq':float(exq.iloc[ix].mean())})
        results[str(bps)]={'events':len(ev),'smh_mean_net':float(net.mean()),'smh_median_net':float(net.median()),'qqq_mean':float(ev.QQQ.mean()),'spy_mean':float(ev.SPY.mean()),'mean_excess_vs_qqq':float(exq.mean()),'median_excess_vs_qqq':float(exq.median()),'mean_excess_vs_spy':float(exs.mean()),'win_rate_vs_qqq':float((exq>0).mean()),'positive_folds_vs_qqq':sum(x['mean_excess_vs_qqq']>0 for x in fold),'folds':fold}
    years=[]
    ex25=ev.SMH-.005-ev.QQQ
    for y,g in ex25.groupby(ex25.index.year): years.append({'year':int(y),'mean_excess_vs_qqq':float(g.mean()),'events':len(g)})
    p=results['25']; gate=(p['mean_excess_vs_qqq']>0 and p['mean_excess_vs_spy']>0 and p['median_excess_vs_qqq']>0 and p['positive_folds_vs_qqq']>=3 and results['50']['mean_excess_vs_qqq']>0)
    return {'schema':'p30.smh_capitulation_mean_reversion.v1','child':'P30-C1','mechanism':'non-overlapping event study: when completed-session SMH 5-session return <= -8%, buy SMH at close and hold 5 sessions; minimum 20 sessions between events','matched_window':{'start':ev.index.min().date().isoformat(),'end':ev.index.max().date().isoformat(),'events':len(ev)},'source':{'provider':'Yahoo Finance Chart v8','research_only':True,'canonical_mm_claim':False,'symbols':prov},'cost_model':'round trip subtracts 2x stated bps from SMH event return','results':results,'positive_years_25bps':sum(x['mean_excess_vs_qqq']>0 for x in years),'represented_years':len(years),'decision':'P30_SMH_CAPITULATION_MEAN_REVERSION_SUPPORTED_CANDIDATE' if gate else 'P30_SMH_CAPITULATION_MEAN_REVERSION_NOT_SUPPORTED','promotion_authority':False,'live_trading_change':False}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--child',choices=['p29','p30'],required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    out=run_p29() if a.child=='p29' else run_p30(); Path(a.out).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
    print(('P29_RECEIPT=' if a.child=='p29' else 'P30_RECEIPT=')+json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
