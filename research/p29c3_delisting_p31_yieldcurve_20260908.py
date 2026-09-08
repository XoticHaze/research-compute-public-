#!/usr/bin/env python3
import argparse,datetime as dt,hashlib,json,math,time
from io import StringIO
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request,urlopen
import numpy as np,pandas as pd
START=int(dt.datetime(2006,1,1,tzinfo=dt.timezone.utc).timestamp()); END=int(dt.datetime(2026,9,8,tzinfo=dt.timezone.utc).timestamp())
UA='Mozilla/5.0 research-only 20260908-p29c3-p31'; COSTS=(10,25,50)
LAWCAL_COMMIT='ed4cf46e5ec5bb02e709aa08ee8a3a218d1b7d19'
HIST_URL=f'https://raw.githubusercontent.com/lawcal/sp500-components-history/{LAWCAL_COMMIT}/data/components_history.csv'
# Frozen historical semiconductor/security taxonomy. Membership/delist dates come independently from lawcal.
SEMI=set('AMD ADI AMAT AVGO BRCM CREE CY FSL INTC KLAC LLTC LRCX LSI MCHP MPWR MRVL MU MXIM NSM NVDA NVLS NXPI ON PMCS QCOM QRVO SNDK SWKS TER TXN VTSS XLNX ALTR ATML'.split())

def get(url,tries=5):
    last=None
    for a in range(1,tries+1):
        try:return urlopen(Request(url,headers={'User-Agent':UA,'Accept':'*/*'}),timeout=35).read(),a
        except Exception as e:
            last=e
            if a<tries: time.sleep(a*2)
    raise RuntimeError(f'{type(last).__name__}:{last}')

def fetch_price(sym,min_rows=250):
    ys=sym.replace('.','-'); u=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ys)}?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true'
    try:
        raw,a=get(u); r=json.loads(raw)['chart']['result'][0]; ts=r['timestamp']; adj=(r.get('indicators',{}).get('adjclose') or [{}])[0].get('adjclose') or r['indicators']['quote'][0]['close']
        s=pd.Series(adj,index=pd.to_datetime(ts,unit='s',utc=True).tz_convert(None),dtype='float64').dropna().sort_index(); s=s[~s.index.duplicated(keep='last')]
        if len(s)<min_rows: raise RuntimeError('insufficient rows')
        return s,{'provider':'Yahoo Chart v8','url':u,'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(s),'attempt':a}
    except Exception as e:return None,{'provider':'Yahoo Chart v8','url':u,'error':str(e)}

def perf(r,periods=12):
    r=pd.Series(r).dropna(); w=(1+r).cumprod(); y=len(r)/periods
    if len(r)<2:return {'periods':len(r),'cagr':None,'max_dd':None,'vol':None}
    return {'periods':len(r),'cagr':float(w.iloc[-1]**(1/y)-1),'max_dd':float((w/w.cummax()-1).min()),'vol':float(r.std(ddof=1)*math.sqrt(periods))}

def folds(s,c,n=5):
    d=pd.concat({'s':s,'c':c},axis=1).dropna(); out=[]
    for i,ix in enumerate(np.array_split(np.arange(len(d)),n),1):
        q=d.iloc[ix]; out.append({'fold':i,'start':q.index[0].date().isoformat(),'end':q.index[-1].date().isoformat(),'excess_cagr':perf(q.s)['cagr']-perf(q.c)['cagr']})
    return out

def years(s,c):
    d=pd.concat({'s':s,'c':c},axis=1).dropna(); return [{'year':int(y),'excess':float((1+g.s).prod()-(1+g.c).prod())} for y,g in d.groupby(d.index.year)]

def run_p29():
    raw,a=get(HIST_URL); h=pd.read_csv(StringIO(raw.decode()));
    for col in ['date_added','date_removed']:
        h[col]=pd.to_datetime(h[col].astype(str).str.replace('*','',regex=False),errors='coerce')
    h=h[h.symbol.isin(SEMI)].copy(); syms=sorted(set(h.symbol)|{'SMH','QQQ','SPY'}); ser={}; prov={}; failed={}
    for x in syms:
        s,p=fetch_price(x)
        if s is None: failed[x]=p
        else: ser[x]=s; prov[x]=p
    m={k:v.resample('ME').last() for k,v in ser.items()}; months=pd.date_range('2007-03-31','2026-08-31',freq='ME'); rows=[]
    for date in months:
        members=sorted(set(h.loc[(h.date_added<=date)&(h.date_removed.isna()| (h.date_removed>date)),'symbol']))
        avail=[]; mom={}; nxt={}; nd=date+pd.offsets.MonthEnd(1); pd6=date-pd.offsets.MonthEnd(6)
        for x in members:
            s=m.get(x)
            if s is None or any(z not in s.index for z in [pd6,date,nd]): continue
            if pd.isna(s.loc[pd6]) or pd.isna(s.loc[date]) or pd.isna(s.loc[nd]): continue
            avail.append(x); mom[x]=float(s.loc[date]/s.loc[pd6]-1); nxt[x]=float(s.loc[nd]/s.loc[date]-1)
        if len(avail)<4: continue
        pick=sorted(avail,key=lambda x:mom[x],reverse=True)[:3]; rows.append({'date':date,'members':len(members),'available':len(avail),'coverage':len(avail)/len(members),'chosen':pick,'gross':float(np.mean([nxt[x] for x in pick])),'ew':float(np.mean([nxt[x] for x in avail]))})
    d=pd.DataFrame(rows).set_index('date')
    for x in ['SMH','QQQ','SPY']:
        s=m[x]; d[x.lower()]=[float(s.loc[z+pd.offsets.MonthEnd(1)]/s.loc[z]-1) if z in s.index and z+pd.offsets.MonthEnd(1) in s.index else np.nan for z in d.index]
    turns=[1.0]+[1-len(set(a)&set(b))/3 for a,b in zip(d.chosen[:-1],d.chosen[1:])]; turn=pd.Series(turns,index=d.index); costs={}
    for b in COSTS:
        net=d.gross-turn*b/10000; costs[str(b)]={'strategy':perf(net),'independent_semi_ew':perf(d.ew),'smh':perf(d.smh),'qqq':perf(d.qqq),'spy':perf(d.spy),'excess_vs_ew_cagr':perf(net)['cagr']-perf(d.ew)['cagr'],'excess_vs_smh_cagr':perf(net)['cagr']-perf(d.smh)['cagr']}
    net25=d.gross-turn*.0025; fs=folds(net25,d.ew); ys=years(net25,d.ew); cov={'median':float(d.coverage.median()),'p10':float(d.coverage.quantile(.1)),'months':len(d),'months_ge_80pct':int((d.coverage>=.8).sum())}
    source_ok=len(d)>=180 and cov['median']>=.8 and cov['months_ge_80pct']/max(1,len(d))>=.8
    gate=source_ok and costs['25']['excess_vs_ew_cagr']>0 and costs['25']['excess_vs_smh_cagr']>0 and sum(x['excess_cagr']>0 for x in fs)>=3 and costs['50']['excess_vs_ew_cagr']>0
    return {'schema':'p29.external_delisting_confirmation.v1','child':'P29-C3','frozen_rule':'prior 6-month momentum; top-3 equal weight next month','membership_source':{'repo':'lawcal/sp500-components-history','commit':LAWCAL_COMMIT,'file':'data/components_history.csv','sha256':hashlib.sha256(raw).hexdigest(),'delisting_fields':['date_added','date_removed'],'taxonomy':'frozen historical semiconductor symbol taxonomy in workload'},'matched_window':{'start':d.index.min().date().isoformat(),'end':d.index.max().date().isoformat(),'months':len(d)},'coverage':cov,'costs':costs,'positive_folds_25bps':sum(x['excess_cagr']>0 for x in fs),'folds_25bps':fs,'positive_years_25bps':sum(x['excess']>0 for x in ys),'represented_years':len(ys),'price_provenance':prov,'price_failures':failed,'decision':'P29_EXTERNAL_DELISTING_CONFIRMATION_SUPPORTED' if gate else ('P29_EXTERNAL_DELISTING_CONFIRMATION_INCONCLUSIVE_COVERAGE' if not source_ok else 'P29_EXTERNAL_DELISTING_CONFIRMATION_NOT_SUPPORTED'),'promotion_authority':False,'live_trading_change':False}

def fred(series):
    url=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}'; raw,a=get(url); d=pd.read_csv(StringIO(raw.decode())); d.columns=['date',series]; d['date']=pd.to_datetime(d.date); d[series]=pd.to_numeric(d[series],errors='coerce'); return d.set_index('date')[series],{'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'attempt':a}

def run_p31():
    y10,p10=fred('DGS10'); y2,p2=fred('DGS2'); prices={}; pp={}
    for x in ['SMH','QQQ','SPY']:
        s,p=fetch_price(x,1000)
        if s is None: raise RuntimeError(f'{x}:{p}')
        prices[x]=s; pp[x]=p
    m=pd.concat(prices,axis=1).resample('ME').last().dropna(); curve=pd.concat({'y10':y10,'y2':y2},axis=1).ffill(limit=10).resample('ME').last(); d=m.join(curve).dropna(); ret=d[['SMH','QQQ','SPY']].pct_change().shift(-1); sig=(d.y10-d.y2)>0; gross=pd.Series(np.where(sig,ret.SMH,ret.QQQ),index=d.index); control=(ret.SMH+ret.QQQ)/2; ok=gross.notna()&control.notna()&ret.SPY.notna(); gross,control,spy=gross[ok],control[ok],ret.SPY[ok]; switches=sig.astype(int).diff().abs().fillna(1).reindex(gross.index); costs={}
    for b in COSTS:
        net=gross-switches*b/10000; costs[str(b)]={'strategy':perf(net),'smh_qqq_50_50':perf(control),'spy':perf(spy),'smh':perf(ret.SMH.reindex(net.index)),'qqq':perf(ret.QQQ.reindex(net.index)),'excess_vs_50_50_cagr':perf(net)['cagr']-perf(control)['cagr']}
    net25=gross-switches*.0025; fs=folds(net25,control); ys=years(net25,control); gate=costs['25']['excess_vs_50_50_cagr']>0 and sum(x['excess_cagr']>0 for x in fs)>=3 and costs['50']['excess_vs_50_50_cagr']>0
    return {'schema':'p31.yield_curve_semiconductor_allocator.v1','child':'P31-C1','frozen_rule':'month-end DGS10-DGS2 > 0 => SMH next month else QQQ','source':{'fred':{'DGS10':p10,'DGS2':p2},'prices':pp,'research_only':True,'canonical_mm_claim':False},'matched_window':{'start':gross.index.min().date().isoformat(),'end':gross.index.max().date().isoformat(),'months':len(gross)},'costs':costs,'switches':int(switches.sum()),'positive_folds_25bps':sum(x['excess_cagr']>0 for x in fs),'folds_25bps':fs,'positive_years_25bps':sum(x['excess']>0 for x in ys),'represented_years':len(ys),'decision':'P31_YIELD_CURVE_ALLOCATOR_SUPPORTED' if gate else 'P31_YIELD_CURVE_ALLOCATOR_NOT_SUPPORTED','promotion_authority':False,'live_trading_change':False}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--child',choices=['p29c3','p31'],required=True); ap.add_argument('--out',required=True); a=ap.parse_args(); out=run_p29() if a.child=='p29c3' else run_p31(); Path(a.out).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n'); print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
