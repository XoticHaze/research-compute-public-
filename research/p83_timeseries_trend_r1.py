from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SYMS=("SPY","QQQ","TLT","GLD","DBC")
START="2006-01-01"; COSTS=(25,50,100)
WINDOWS={"full":None,"2015_forward":"2015-01-01","2020_forward":"2020-01-01"}


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); ann=float(r.mean()*12); dd=float((e/e.cummax()-1).min())
    return {"cagr":cagr(r),"annualized_vol":v,"sharpe_rf0":ann/v if v else None,"max_drawdown":dd,"calmar":cagr(r)/abs(dd) if dd<0 else None}

def source_hash(x):
    return hashlib.sha256(x.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()

def folds(q,col,bench):
    out=[]
    for i,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
        z=q.iloc[ids]
        if len(z): out.append({"fold":i,"start":str(z.index.min().date()),"end":str(z.index.max().date()),"excess_cagr":cagr(z[col])-cagr(z[bench])})
    return out

def main():
    raw=yf.download(list(SYMS),start=START,auto_adjust=True,progress=False,threads=False)
    if raw.empty: raise RuntimeError('empty_download')
    close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw[["Close"]]
    if not isinstance(close,pd.DataFrame): close=close.to_frame()
    close=close.loc[:,list(SYMS)].dropna(how='any').astype(float)
    last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=close.resample('ME').last(); m=m.loc[m.index<=cutoff]
    sma=(close.rolling(200,min_periods=200).mean()).resample('ME').last().reindex(m.index)
    rows=[]; prev=np.zeros(len(SYMS))
    for i,dt in enumerate(m.index[:-1]):
        sig=(m.loc[dt,list(SYMS)]>sma.loc[dt,list(SYMS)]).astype(float)
        if sig.isna().any(): continue
        nxt=m.index[i+1]; r=(m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1).astype(float)
        if r.isna().any(): continue
        w=sig.to_numpy(float)/len(SYMS)
        turnover=.5*float(np.abs(w-prev).sum()); gross=float((w*r.to_numpy(float)).sum())
        ew=float(r.mean()); rows.append({"date":nxt,"gross":gross,"turnover":turnover,"matched_ew":ew,"spy":float(r['SPY']),"qqq":float(r['QQQ']),"active_fraction":float(sig.mean())}); prev=w
    f=pd.DataFrame(rows).set_index('date')
    out={"schema":"research.p83_timeseries_trend_r1","parent":"P83","hypothesis":"A fixed per-asset 200-day time-series trend filter across a diversified liquid ETF universe can create durable after-cost excess and drawdown efficiency without cross-sectional ranking.","scientific_contract":{"universe":list(SYMS),"signal":"asset month-end close above its own causal 200-trading-day SMA","allocation":"20% notional per asset when signal on; inactive notional held as zero-return cash","rebalance":"monthly","costs_bps":list(COSTS),"matched_control":"same-universe static equal weight","opportunity_controls":["SPY","QQQ"],"windows":WINDOWS,"chronological_folds":5,"no_parameter_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","panel_sha256":source_hash(close),"last_complete_month_end":str(cutoff.date())},"tests":{}}
    for name,start in WINDOWS.items():
        q=f if start is None else f.loc[pd.Timestamp(start):]
        z={"months":len(q),"start":str(q.index.min().date()),"end":str(q.index.max().date()),"mean_active_fraction":float(q.active_fraction.mean()),"controls":{"matched_ew":metrics(q.matched_ew),"spy":metrics(q.spy),"qqq":metrics(q.qqq)},"costs":{}}
        for bp in COSTS:
            col=f'net_{bp}'; q=q.copy(); q[col]=q.gross-q.turnover*bp/10000
            fm=folds(q,col,'matched_ew'); cm=metrics(q[col]); z['costs'][str(bp)]={"candidate":cm,"excess_cagr_vs_matched":cm['cagr']-z['controls']['matched_ew']['cagr'],"excess_cagr_vs_spy":cm['cagr']-z['controls']['spy']['cagr'],"excess_cagr_vs_qqq":cm['cagr']-z['controls']['qqq']['cagr'],"sharpe_delta_vs_matched":cm['sharpe_rf0']-z['controls']['matched_ew']['sharpe_rf0'],"max_drawdown_delta_vs_matched":cm['max_drawdown']-z['controls']['matched_ew']['max_drawdown'],"positive_matched_folds":sum(x['excess_cagr']>0 for x in fm),"folds":fm}
        out['tests'][name]=z
    p=out['tests']['2020_forward']['costs']['50']; out['decision']='P83_TIMESERIES_TREND_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 and p['sharpe_delta_vs_matched']>0 else 'P83_TIMESERIES_TREND_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p83_timeseries_trend_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
