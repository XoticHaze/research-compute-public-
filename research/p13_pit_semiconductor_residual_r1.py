from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import pitindex
import yfinance as yf

START=pd.Timestamp('2018-01-01')
END=pd.Timestamp('2026-09-01')
LOOKBACK=126
TOPK=3
BP=50
PIT_COMMIT='2df030e5c9be7c83cf4b28c3d8597d74d274757e'


def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else None


def maxdd(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); return float((eq/eq.cummax()-1).min()) if len(eq) else None


def stats(f):
    folds=[]
    for i,ix in enumerate(np.array_split(np.arange(len(f)),5),1):
        q=f.iloc[ix]
        folds.append({'fold':i,'residual_vs_raw':cagr(q.net)-cagr(q.raw_net),'residual_vs_pit_ew':cagr(q.net)-cagr(q.pit_ew),'residual_vs_smh':cagr(q.net)-cagr(q.smh),'residual_vs_qqq':cagr(q.net)-cagr(q.qqq)})
    return {'months':int(len(f)),'residual_cagr':cagr(f.net),'raw_cagr':cagr(f.raw_net),'pit_ew_cagr':cagr(f.pit_ew),'smh_cagr':cagr(f.smh),'qqq_cagr':cagr(f.qqq),'excess_vs_raw_cagr':cagr(f.net)-cagr(f.raw_net),'excess_vs_pit_ew_cagr':cagr(f.net)-cagr(f.pit_ew),'excess_vs_smh_cagr':cagr(f.net)-cagr(f.smh),'excess_vs_qqq_cagr':cagr(f.net)-cagr(f.qqq),'max_drawdown':maxdd(f.net),'positive_folds_vs_raw':sum(x['residual_vs_raw']>0 for x in folds),'positive_folds_vs_pit_ew':sum(x['residual_vs_pit_ew']>0 for x in folds),'positive_folds_vs_smh':sum(x['residual_vs_smh']>0 for x in folds),'positive_folds_vs_qqq':sum(x['residual_vs_qqq']>0 for x in folds),'folds':folds}


def main():
    months=pd.date_range('2018-07-31','2026-08-31',freq='ME')
    snaps={}; universe=set()
    for dt in months:
        x=pitindex.get_constituents(dt.date().isoformat(),index='sp500')
        mask=x['gics_sub_industry'].fillna('').str.contains('Semiconductor',case=False,regex=False)
        names=sorted(set(x.loc[mask,'ticker'].astype(str).str.replace('.','-',regex=False)))
        snaps[dt]=names; universe.update(names)
    tickers=sorted(universe|{'SMH','QQQ'})
    raw=yf.download(tickers,start=(START-pd.Timedelta(days=220)).date().isoformat(),end=(END+pd.Timedelta(days=10)).date().isoformat(),auto_adjust=True,progress=False,threads=False,group_by='column')
    close=raw['Close'].sort_index(); volume=raw['Volume'].sort_index()
    ok=[s for s in tickers if s in close.columns and int(close[s].notna().sum())>=LOOKBACK+40]
    daily_ret=close.pct_change(fill_method=None)
    rows=[]; prev_res=set(); prev_raw=set()
    for dt in months[:-1]:
        nxt=dt+pd.offsets.MonthEnd(1); members=[s for s in snaps[dt] if s in ok and s not in {'SMH','QQQ'}]
        end_ix=close.index.get_indexer([dt],method='pad')[0]; next_ix=close.index.get_indexer([nxt],method='pad')[0]
        if end_ix<LOOKBACK or next_ix<=end_ix or end_ix<0 or next_ix<0: continue
        smh_window=daily_ret['SMH'].iloc[end_ix-LOOKBACK+1:end_ix+1]
        scored=[]
        for s in members:
            w=daily_ret[s].iloc[end_ix-LOOKBACK+1:end_ix+1]
            z=pd.concat([w,smh_window],axis=1).dropna()
            if len(z)<100: continue
            y=z.iloc[:,0].to_numpy(float); x=z.iloc[:,1].to_numpy(float); X=np.column_stack([np.ones(len(x)),x]); beta=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@beta
            residual_score=float(resid.sum())
            p0=close[s].iloc[end_ix-LOOKBACK]; p1=close[s].iloc[end_ix]; p2=close[s].iloc[next_ix]
            if pd.isna(p0) or pd.isna(p1) or pd.isna(p2) or p0<=0 or p1<=0: continue
            scored.append((s,residual_score,float(p1/p0-1),float(p2/p1-1)))
        if len(scored)<TOPK+1: continue
        res_names=[x[0] for x in sorted(scored,key=lambda x:(-x[1],x[0]))[:TOPK]]
        raw_names=[x[0] for x in sorted(scored,key=lambda x:(-x[2],x[0]))[:TOPK]]
        rr={x[0]:x[3] for x in scored}; gross=float(np.mean([rr[s] for s in res_names])); raw_gross=float(np.mean([rr[s] for s in raw_names])); ew=float(np.mean(list(rr.values())))
        res_turn=1.0 if not prev_res else 1-len(prev_res&set(res_names))/TOPK; raw_turn=1.0 if not prev_raw else 1-len(prev_raw&set(raw_names))/TOPK; prev_res=set(res_names); prev_raw=set(raw_names)
        smh=float(close['SMH'].iloc[next_ix]/close['SMH'].iloc[end_ix]-1); qqq=float(close['QQQ'].iloc[next_ix]/close['QQQ'].iloc[end_ix]-1)
        rows.append({'date':dt,'net':gross-res_turn*BP/10000,'raw_net':raw_gross-raw_turn*BP/10000,'pit_ew':ew,'smh':smh,'qqq':qqq,'members':len(snaps[dt]),'eligible':len(scored),'coverage':len(scored)/len(snaps[dt]) if snaps[dt] else 0,'residual_names':res_names,'raw_names':raw_names})
    f=pd.DataFrame(rows).set_index('date')
    result={'schema':'research.p13_pit_semiconductor_residual_r1','parent':'P13','hypothesis':'The frozen 126-session stock-specific residual top-3 signal retains after-cost incremental selection value when the universe is replaced by point-in-time S&P 500 semiconductor membership.','contract':{'point_in_time_provider':'pitindex','pitindex_commit':PIT_COMMIT,'signal':'126-session OLS stock return residual to SMH; sum residuals; monthly top3 equal weight','raw_control':'same PIT eligible universe prior-126-session raw momentum top3','matched_control':'same PIT eligible universe equal weight','opportunity_controls':['SMH','QQQ'],'cost_bps':BP,'windows':['full','2022_forward'],'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','requested_tickers':len(tickers),'usable_tickers':len(ok),'usable_names':ok},'coverage':{'months':int(len(f)),'median':float(f.coverage.median()),'p10':float(f.coverage.quantile(.1)),'months_ge_80pct':int((f.coverage>=.8).sum())},'tests':{'full':stats(f),'2022_forward':stats(f.loc[f.index>=pd.Timestamp('2022-01-01')])}}
    t=result['tests']['2022_forward']; cov=result['coverage']; supported=t['excess_vs_raw_cagr']>0 and t['excess_vs_pit_ew_cagr']>0 and t['positive_folds_vs_raw']>=3 and cov['median']>=.8
    result['decision']='P13_PIT_RESIDUAL_SUPPORTED' if supported else ('P13_PIT_DATA_COVERAGE_INADEQUATE' if cov['median']<.8 else 'P13_PIT_RESIDUAL_NOT_SUPPORTED')
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_pit_semiconductor_residual_r1.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':result['decision'],'coverage':result['coverage'],'full':result['tests']['full'],'recent':result['tests']['2022_forward']},sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
