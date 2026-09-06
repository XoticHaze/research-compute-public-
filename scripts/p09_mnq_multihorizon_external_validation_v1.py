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

def stat(x):
    return None if len(x)==0 else float(x.mean())

def main():
    m=dl('MNQ=F'); q=dl('QQQ')
    r=m['close'].pct_change(); vol5=r.rolling(5).std(); vol20=r.rolling(20).std()
    mom20=m['close'].pct_change(20); dd20=m['close']/m['close'].rolling(20).max()-1
    simple=pct_rank(vol20)
    multi=(pct_rank(vol5)+pct_rank(vol20)+pct_rank(-mom20)+pct_rank(-dd20))/4.0
    fut=[m['low'].shift(-k)/m['close']-1 for k in range(1,6)]
    mae=-pd.concat(fut,axis=1).min(axis=1); fwd5=m['close'].shift(-5)/m['close']-1
    d=pd.DataFrame({'simple':simple,'multi':multi,'mae5':mae,'fwd5':fwd5,'mom20':mom20}).dropna()
    years=sorted(y for y in d.index.year.unique() if y>=2021)
    folds=[]
    for y in years:
        g=d[d.index.year==y]; hist=d[d.index<g.index.min()] if len(g) else d.iloc[0:0]
        if len(g)<80: continue
        sc=hist.simple.quantile(.8); mc=hist.multi.quantile(.8)
        if not np.isfinite(sc) or not np.isfinite(mc): continue
        hs,ls=g[g.simple>=sc],g[g.simple<sc]; hm,lm=g[g.multi>=mc],g[g.multi<mc]
        ss=stat(hs.mae5)-stat(ls.mae5) if len(hs) and len(ls) else None
        ms=stat(hm.mae5)-stat(lm.mae5) if len(hm) and len(lm) else None
        comparable=ss is not None and ms is not None and np.isfinite(ss) and np.isfinite(ms)
        folds.append({'year':int(y),'n':int(len(g)),'simple_mae_spread':ss,'multi_mae_spread':ms,
                      'comparable':bool(comparable),'multi_better':bool(comparable and ms>ss)})

    # Fixed economic consumer: rebalance every five sessions so 5-session outcomes do not overlap.
    # Long only when prior-known 20d momentum > 0; compare no risk gate, simple-vol gate, multi-horizon gate.
    rows=[]; selections={}
    for y in years:
        full=d[d.index.year==y]; hist=d[d.index<full.index.min()] if len(full) else d.iloc[0:0]
        if len(full)<80: continue
        sc=hist.simple.quantile(.8); mc=hist.multi.quantile(.8)
        if not np.isfinite(sc) or not np.isfinite(mc): continue
        g=full.iloc[::5].copy()
        base=g[g.mom20>0]; ss=g[(g.mom20>0)&(g.simple<sc)]; mm=g[(g.mom20>0)&(g.multi<mc)]
        rows.append({'year':int(y),'decision_rows':int(len(g)),'base_n':int(len(base)),'simple_n':int(len(ss)),'multi_n':int(len(mm)),
          'base_mean_bps':float(base.fwd5.mean()*1e4) if len(base) else None,
          'simple_mean_bps':float(ss.fwd5.mean()*1e4) if len(ss) else None,
          'multi_mean_bps':float(mm.fwd5.mean()*1e4) if len(mm) else None})
        selections[int(y)]={'base':base.fwd5*1e4,'simple':ss.fwd5*1e4,'multi':mm.fwd5*1e4}

    econ={}
    for c in (0,5,10):
        per=[]
        for y,s in selections.items():
            node={'year':y}
            for k,v in s.items():
                net=v-c
                node[k+'_n']=int(len(net)); node[k+'_net_mean_bps']=float(net.mean()) if len(net) else None
                node[k+'_net_total_bps']=float(net.sum()) if len(net) else 0.0
            node['multi_minus_simple_net_mean_bps']=(node['multi_net_mean_bps']-node['simple_net_mean_bps']) if node['multi_net_mean_bps'] is not None and node['simple_net_mean_bps'] is not None else None
            node['multi_minus_simple_net_total_bps']=node['multi_net_total_bps']-node['simple_net_total_bps']
            node['multi_minus_base_net_total_bps']=node['multi_net_total_bps']-node['base_net_total_bps']
            per.append(node)
        econ[str(c)]={'folds':per,
          'multi_vs_simple_mean_positive_folds':sum((x['multi_minus_simple_net_mean_bps'] or 0)>0 for x in per),
          'multi_vs_simple_total_positive_folds':sum(x['multi_minus_simple_net_total_bps']>0 for x in per),'fold_count':len(per),
          'pooled_multi_minus_simple_net_total_bps':float(sum(x['multi_minus_simple_net_total_bps'] for x in per)),
          'pooled_multi_minus_base_net_total_bps':float(sum(x['multi_minus_base_net_total_bps'] for x in per))}

    idx=d.index; mnq_bh=float(m.loc[idx[-1],'close']/m.loc[idx[0],'close']-1)
    q2=q.reindex(idx,method='ffill').dropna(); common=idx.intersection(q2.index)
    qqq_bh=float(q2.loc[common[-1],'close']/q2.loc[common[0],'close']-1) if len(common)>1 else None
    comp=[x for x in folds if x['comparable']]; better=sum(x['multi_better'] for x in comp); n=len(comp)
    # Representation must clear 67% comparable folds AND the economic consumer must beat simple on mean in >=67% folds at 5bp.
    e5=econ['5']; econ_ok=e5['fold_count']>=4 and e5['multi_vs_simple_mean_positive_folds']>=math.ceil(.67*e5['fold_count'])
    rep_ok=n>=4 and better>=math.ceil(.67*n)
    decision='P09_MULTIHORIZON_EXTERNAL_TRANSFER_PROMISING' if rep_ok and econ_ok else ('P09_MULTIHORIZON_EXTERNAL_TRANSFER_NOT_SUPPORTED' if n>=4 else 'INSUFFICIENT_FOLDS')
    receipt={'schema':'p09-mnq-multihorizon-external-v2','source':'Yahoo Finance public MNQ=F and QQQ','window':[str(idx[0]),str(idx[-1])],
      'folds':folds,'economic_filter_rows':rows,'cost_scenarios_bps':econ,'matched_buy_hold':{'mnq':mnq_bh,'qqq':qqq_bh},
      'representation_gate':{'comparable_folds':n,'multi_better_folds':better,'pass':rep_ok},
      'economic_gate_5bps':{'positive_mean_folds':e5['multi_vs_simple_mean_positive_folds'],'folds':e5['fold_count'],'pass':econ_ok},
      'decision':decision,'strategy_spec_write':False,'runtime_activation':False,'broker_submit':False,'promotion_authority':False,'live_trading_change':False}
    print('P09_MULTIHORIZON_RECEIPT='+json.dumps(receipt,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
