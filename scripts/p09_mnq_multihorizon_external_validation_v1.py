from __future__ import annotations
import json, math
import numpy as np
import pandas as pd
import yfinance as yf

START='2019-05-06'; END='2026-09-06'

def dl(t):
    x=yf.download(t,start=START,end=END,auto_adjust=False,progress=False,threads=False)
    if isinstance(x.columns,pd.MultiIndex): x.columns=x.columns.get_level_values(0)
    x=x.rename(columns=str.lower).dropna(subset=['open','high','low','close'])
    x.index=pd.to_datetime(x.index,utc=True)
    return x

def pct_rank(s,w=252):
    def f(a):
        if len(a)<40 or not np.isfinite(a[-1]): return np.nan
        b=a[np.isfinite(a)]
        return np.mean(b<=a[-1]) if len(b) else np.nan
    return s.rolling(w,min_periods=40).apply(f,raw=True)

def main():
    m=dl('MNQ=F'); q=dl('QQQ')
    r=m['close'].pct_change()
    vol5=r.rolling(5).std(); vol20=r.rolling(20).std()
    mom20=m['close'].pct_change(20)
    dd20=m['close']/m['close'].rolling(20).max()-1
    simple=pct_rank(vol20)
    multi=(pct_rank(vol5)+pct_rank(vol20)+pct_rank(-mom20)+pct_rank(-dd20))/4.0
    fut=[]
    for k in range(1,6): fut.append(m['low'].shift(-k)/m['close']-1)
    mae=-pd.concat(fut,axis=1).min(axis=1)
    fwd5=m['close'].shift(-5)/m['close']-1
    d=pd.DataFrame({'simple':simple,'multi':multi,'mae5':mae,'fwd5':fwd5,'mom20':mom20}).dropna()
    years=sorted(y for y in d.index.year.unique() if y>=2021)
    folds=[]
    for y in years:
        g=d[d.index.year==y]
        if len(g)<80: continue
        s_cut=d[d.index<g.index.min()]['simple'].quantile(.8)
        m_cut=d[d.index<g.index.min()]['multi'].quantile(.8)
        if not np.isfinite(s_cut) or not np.isfinite(m_cut): continue
        hi_s=g[g.simple>=s_cut]; lo_s=g[g.simple<s_cut]
        hi_m=g[g.multi>=m_cut]; lo_m=g[g.multi<m_cut]
        folds.append({'year':int(y),'n':int(len(g)),
          'simple_mae_spread':float(hi_s.mae5.mean()-lo_s.mae5.mean()),
          'multi_mae_spread':float(hi_m.mae5.mean()-lo_m.mae5.mean()),
          'multi_better':bool((hi_m.mae5.mean()-lo_m.mae5.mean())>(hi_s.mae5.mean()-lo_s.mae5.mean()))})
    # fixed risk-filter economic consumer: long only when 20d momentum > 0, exclude prior-only top-risk quintile
    rows=[]
    for y in years:
        g=d[d.index.year==y].copy()
        if len(g)<80: continue
        hist=d[d.index<g.index.min()]
        sc=hist.simple.quantile(.8); mc=hist.multi.quantile(.8)
        if not np.isfinite(sc) or not np.isfinite(mc): continue
        base=g[g.mom20>0]
        ss=g[(g.mom20>0)&(g.simple<sc)]
        mm=g[(g.mom20>0)&(g.multi<mc)]
        rows.append({'year':int(y),'base_n':int(len(base)),'simple_n':int(len(ss)),'multi_n':int(len(mm)),
          'base_mean_bps':float(base.fwd5.mean()*1e4),'simple_mean_bps':float(ss.fwd5.mean()*1e4),'multi_mean_bps':float(mm.fwd5.mean()*1e4)})
    econ={}
    for c in (0,5,10):
        a=[]
        for z in rows:
            a.append({'year':z['year'],'multi_minus_simple_net_bps':z['multi_mean_bps']-z['simple_mean_bps'],
                      'multi_minus_base_net_bps':z['multi_mean_bps']-z['base_mean_bps']})
        econ[str(c)]={'folds':a,'multi_vs_simple_positive_folds':sum(x['multi_minus_simple_net_bps']>0 for x in a),'fold_count':len(a)}
    idx=d.index
    mnq_bh=float(m.loc[idx[-1],'close']/m.loc[idx[0],'close']-1)
    q2=q.reindex(idx,method='ffill').dropna()
    common=idx.intersection(q2.index)
    qqq_bh=float(q2.loc[common[-1],'close']/q2.loc[common[0],'close']-1) if len(common)>1 else None
    better=sum(x['multi_better'] for x in folds); n=len(folds)
    decision='P09_MULTIHORIZON_EXTERNAL_TRANSFER_PROMISING' if n>=4 and better>=math.ceil(.67*n) else ('P09_MULTIHORIZON_EXTERNAL_TRANSFER_NOT_SUPPORTED' if n>=4 else 'INSUFFICIENT_FOLDS')
    receipt={'schema':'p09-mnq-multihorizon-external-v1','source':'Yahoo Finance public MNQ=F and QQQ','window':[str(idx[0]),str(idx[-1])],
      'folds':folds,'economic_filter_rows':rows,'cost_scenarios_bps':econ,'matched_buy_hold':{'mnq':mnq_bh,'qqq':qqq_bh},'decision':decision,
      'strategy_spec_write':False,'runtime_activation':False,'broker_submit':False,'promotion_authority':False,'live_trading_change':False}
    print('P09_MULTIHORIZON_RECEIPT='+json.dumps(receipt,sort_keys=True))
if __name__=='__main__': main()
