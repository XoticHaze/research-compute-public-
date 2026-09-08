#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, math, time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
import pitindex

START=int(dt.datetime(2004,1,1,tzinfo=dt.timezone.utc).timestamp())
END=int(dt.datetime(2026,9,8,tzinfo=dt.timezone.utc).timestamp())
UA='Mozilla/5.0 research-only fixed-validation/20260908-p29c2-p28c2'
COSTS=(10,25,50)
PIT_COMMIT='2df030e5c9be7c83cf4b28c3d8597d74d274757e'

def fetch(symbol,min_rows=250):
    ys=symbol.replace('.','-')
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ys)}?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true'
    last=None
    for attempt in range(1,6):
        try:
            raw=urlopen(Request(url,headers={'User-Agent':UA,'Accept':'application/json'}),timeout=30).read()
            r=json.loads(raw)['chart']['result'][0]; ts=r['timestamp']
            adj=(r.get('indicators',{}).get('adjclose') or [{}])[0].get('adjclose') or r['indicators']['quote'][0]['close']
            s=pd.Series(adj,index=pd.to_datetime(ts,unit='s',utc=True).tz_convert(None),dtype='float64').dropna().sort_index()
            s=s[~s.index.duplicated(keep='last')]
            if len(s)<min_rows: raise RuntimeError(f'insufficient rows={len(s)}')
            return s,{'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'rows':len(s),'start':s.index[0].date().isoformat(),'end':s.index[-1].date().isoformat(),'attempt':attempt}
        except Exception as exc:
            last=exc
            if attempt<5: time.sleep(2*attempt)
    return None,{'url':url,'error':f'{type(last).__name__}: {last}'}

def perf(r):
    r=pd.Series(r).dropna(); w=(1+r).cumprod(); years=len(r)/12
    if len(r)<2 or years<=0: return {'months':len(r),'cagr':None,'max_dd':None,'vol':None}
    dd=w/w.cummax()-1
    return {'months':len(r),'cagr':float(w.iloc[-1]**(1/years)-1),'max_dd':float(dd.min()),'vol':float(r.std(ddof=1)*math.sqrt(12))}

def fold_excess(s,c,n=5):
    d=pd.concat({'s':s,'c':c},axis=1).dropna(); out=[]
    for i,ix in enumerate(np.array_split(np.arange(len(d)),n),1):
        q=d.iloc[ix]; ps=perf(q.s); pc=perf(q.c)
        out.append({'fold':i,'start':q.index[0].date().isoformat(),'end':q.index[-1].date().isoformat(),'excess_cagr':ps['cagr']-pc['cagr']})
    return out

def yearly(s,c):
    d=pd.concat({'s':s,'c':c},axis=1).dropna(); out=[]
    for y,g in d.groupby(d.index.year): out.append({'year':int(y),'excess':float((1+g.s).prod()-(1+g.c).prod())})
    return out

def run_p29():
    months=pd.date_range('2005-01-31','2026-08-31',freq='ME')
    snapshots={}; universe=set(); pit_counts={}
    for date in months:
        df=pitindex.get_constituents(date.date().isoformat(),index='sp500')
        mask=df['gics_sub_industry'].fillna('').str.contains('Semiconductor',case=False,regex=False)
        tickers=sorted(set(df.loc[mask,'ticker'].astype(str)))
        snapshots[date]=tickers; pit_counts[str(date.date())]=len(tickers); universe.update(tickers)
    controls=['SMH','QQQ','SPY']; series={}; prov={}; failed={}
    for sym in sorted(universe|set(controls)):
        s,p=fetch(sym)
        if s is None: failed[sym]=p
        else: series[sym]=s; prov[sym]=p
    monthly={k:v.resample('ME').last() for k,v in series.items()}
    rows=[]
    for date in months:
        members=snapshots[date]; avail=[]; mom={}; nxt={}
        next_date=date+pd.offsets.MonthEnd(1)
        for sym in members:
            s=monthly.get(sym)
            if s is None or date not in s.index or next_date not in s.index: continue
            prior=date-pd.offsets.MonthEnd(6)
            if prior not in s.index or pd.isna(s.loc[prior]) or pd.isna(s.loc[date]) or pd.isna(s.loc[next_date]): continue
            avail.append(sym); mom[sym]=float(s.loc[date]/s.loc[prior]-1); nxt[sym]=float(s.loc[next_date]/s.loc[date]-1)
        if len(avail)<4: continue
        chosen=sorted(avail,key=lambda x:mom[x],reverse=True)[:3]
        gross=float(np.mean([nxt[x] for x in chosen])); ew=float(np.mean([nxt[x] for x in avail]))
        rows.append({'date':date,'members':len(members),'available':len(avail),'coverage':len(avail)/len(members) if members else 0,'chosen':chosen,'gross':gross,'ew':ew})
    d=pd.DataFrame(rows).set_index('date')
    for ctrl in controls:
        s=monthly[ctrl]; d[ctrl.lower()]=[float(s.loc[x+pd.offsets.MonthEnd(1)]/s.loc[x]-1) if x in s.index and x+pd.offsets.MonthEnd(1) in s.index else np.nan for x in d.index]
    chosen_sets=d.chosen.tolist(); turns=[1.0]
    for a,b in zip(chosen_sets[:-1],chosen_sets[1:]): turns.append(1-len(set(a)&set(b))/3)
    turn=pd.Series(turns,index=d.index)
    costs={}
    for bps in COSTS:
        net=d.gross-turn*bps/10000
        costs[str(bps)]={'strategy':perf(net),'pit_semiconductor_ew':perf(d.ew),'smh':perf(d.smh),'qqq':perf(d.qqq),'spy':perf(d.spy),'excess_vs_pit_ew_cagr':perf(net)['cagr']-perf(d.ew)['cagr'],'excess_vs_smh_cagr':perf(net)['cagr']-perf(d.smh)['cagr']}
    net25=d.gross-turn*.0025; folds=fold_excess(net25,d.ew); yrs=yearly(net25,d.ew)
    coverage={'median':float(d.coverage.median()),'p10':float(d.coverage.quantile(.1)),'months_ge_80pct':int((d.coverage>=.8).sum()),'months':len(d)}
    source_ok=coverage['median']>=.9 and coverage['months_ge_80pct']/coverage['months']>=.9
    gate=source_ok and costs['25']['excess_vs_pit_ew_cagr']>0 and costs['25']['excess_vs_smh_cagr']>0 and sum(x['excess_cagr']>0 for x in folds)>=3 and costs['50']['excess_vs_pit_ew_cagr']>0
    decision='P29_PIT_SURVIVORSHIP_VALIDATION_SUPPORTED' if gate else ('P29_PIT_VALIDATION_INCONCLUSIVE_SOURCE_COVERAGE' if not source_ok else 'P29_PIT_SURVIVORSHIP_VALIDATION_NOT_SUPPORTED')
    return {'schema':'p29.pit_semiconductor_momentum_validation.v1','child':'P29-C2','frozen_parent_rule':'prior 6-month momentum; top-3 equal weight next month; no parameter changes','point_in_time_membership':{'provider':'pitindex','repo':'arielNacamulli/pitindex','commit':PIT_COMMIT,'index':'S&P 500','filter':'gics_sub_industry contains Semiconductor'},'matched_window':{'start':d.index.min().date().isoformat(),'end':d.index.max().date().isoformat(),'months':len(d)},'source':{'prices':'Yahoo Finance Chart v8','research_only':True,'canonical_mm_claim':False,'successful':prov,'failed':failed},'coverage':coverage,'costs':costs,'mean_monthly_turnover':float(turn.mean()),'positive_folds_25bps':sum(x['excess_cagr']>0 for x in folds),'chronological_folds_25bps':folds,'positive_years_25bps':sum(x['excess']>0 for x in yrs),'represented_years':len(yrs),'decision':decision,'promotion_authority':False,'live_trading_change':False}

def run_p28():
    assets=['VTI','IEF','IAU','PDBC']; controls=['SPY','QQQ']; ser={}; prov={}
    for x in assets+controls:
        s,p=fetch(x,1000)
        if s is None: raise RuntimeError(f'{x} source failure {p}')
        ser[x]=s; prov[x]=p
    m=pd.concat(ser,axis=1).sort_index().ffill(limit=3).dropna().resample('ME').last().dropna(); mr=m.pct_change()
    mom12=m[assets].pct_change(12); sma10=m[assets].rolling(10).mean(); signal=(mom12>0)&(m[assets]>sma10)
    w=signal.astype(float); cnt=w.sum(axis=1).replace(0,np.nan); w=w.div(cnt,axis=0).fillna(0)
    valid=m.index[mom12.notna().all(axis=1)]; w=w.reindex(valid); nr=mr[assets].shift(-1).reindex(valid); ok=nr.notna().all(axis=1); w=w.loc[ok]; nr=nr.loc[ok]
    gross=(w*nr).sum(axis=1); ew=mr[assets].mean(axis=1).shift(-1).reindex(gross.index); spy=mr.SPY.shift(-1).reindex(gross.index); qqq=mr.QQQ.shift(-1).reindex(gross.index); bal=(.6*mr.VTI+.4*mr.IEF).shift(-1).reindex(gross.index)
    turn=(w-w.shift(1).fillna(0)).abs().sum(axis=1)/2; costs={}
    for bps in COSTS:
        net=gross-turn*bps/10000; costs[str(bps)]={'strategy':perf(net),'independent_proxy_ew':perf(ew),'static_60_40':perf(bal),'spy':perf(spy),'qqq':perf(qqq),'excess_vs_proxy_ew_cagr':perf(net)['cagr']-perf(ew)['cagr'],'excess_vs_spy_cagr':perf(net)['cagr']-perf(spy)['cagr']}
    net25=gross-turn*.0025; folds=fold_excess(net25,ew); yrs=yearly(net25,ew)
    gate=costs['25']['excess_vs_proxy_ew_cagr']>0 and sum(x['excess_cagr']>0 for x in folds)>=3 and costs['50']['excess_vs_proxy_ew_cagr']>0 and costs['25']['strategy']['max_dd']>=costs['25']['independent_proxy_ew']['max_dd']
    return {'schema':'p28.independent_proxy_dual_trend_validation.v1','child':'P28-C2','frozen_parent_rule':'12-month positive momentum AND price above 10-month SMA; equal weight qualifying assets; cash otherwise','independent_representation':{'equity':'VTI','treasury':'IEF','gold':'IAU','commodity':'PDBC'},'matched_window':{'start':gross.index.min().date().isoformat(),'end':gross.index.max().date().isoformat(),'months':len(gross)},'source':{'provider':'Yahoo Finance Chart v8','research_only':True,'canonical_mm_claim':False,'symbols':prov},'costs':costs,'mean_monthly_turnover':float(turn.mean()),'positive_folds_25bps':sum(x['excess_cagr']>0 for x in folds),'chronological_folds_25bps':folds,'positive_years_25bps':sum(x['excess']>0 for x in yrs),'represented_years':len(yrs),'decision':'P28_INDEPENDENT_PROXY_VALIDATION_SUPPORTED' if gate else 'P28_INDEPENDENT_PROXY_VALIDATION_NOT_SUPPORTED','promotion_authority':False,'live_trading_change':False}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--child',choices=['p29','p28'],required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    out=run_p29() if a.child=='p29' else run_p28(); Path(a.out).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n'); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
