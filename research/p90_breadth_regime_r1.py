from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

COSTS=(25,50,100)
TICKERS=['QQQ','RSP','SPY']

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod()
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan')
    ann=float(r.mean()*12) if len(r) else float('nan')
    dd=float((eq/eq.cummax()-1).min()) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'max_drawdown':dd}

def main():
    raw=yf.download(TICKERS,start='2003-01-01',auto_adjust=True,progress=False,threads=False)
    close=raw['Close'].dropna().astype(float)
    last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=close.resample('ME').last(); m=m[m.index<=cutoff]
    rows=[]; prev=np.array([0.5,0.5])
    for i in range(6,len(m)-1):
        dt=m.index[i]; nxt=m.index[i+1]
        rel_now=float(m.loc[dt,'QQQ']/m.loc[dt,'RSP'])
        rel_lag=float(m.iloc[i-6]['QQQ']/m.iloc[i-6]['RSP'])
        concentration=rel_now>rel_lag
        w=np.array([1.0,0.0]) if concentration else np.array([0.0,1.0])
        r=(m.loc[nxt,['QQQ','RSP']]/m.loc[dt,['QQQ','RSP']]-1).to_numpy(float)
        turn=0.5*float(abs(w-prev).sum())
        rows.append({'date':nxt,'gross':float(w@r),'turnover':turn,'matched':float(0.5*r.sum()),'qqq':float(r[0]),'rsp':float(r[1]),'spy':float(m.loc[nxt,'SPY']/m.loc[dt,'SPY']-1),'concentration':bool(concentration)})
        prev=w
    f=pd.DataFrame(rows).set_index('date')
    out={'schema':'research.p90_breadth_regime_r1','parent':'P90','hypothesis':'A fixed six-month QQQ/RSP relative-strength state identifies concentration versus breadth regimes strongly enough to create durable after-cost excess by selecting QQQ or RSP.','contract':{'signal':'QQQ/RSP ratio higher than six months earlier = QQQ, otherwise RSP','allocation':'100% QQQ or 100% RSP monthly','costs_bps':list(COSTS),'matched_control':'static 50/50 QQQ-RSP','opportunity_control':'SPY','windows':['full','2015_forward','2020_forward'],'folds':5,'no_parameter_search':True},'tests':{}}
    for name,start in [('full',None),('2015_forward','2015-01-01'),('2020_forward','2020-01-01')]:
        q=f if start is None else f.loc[start:]
        z={'months':len(q),'concentration_fraction':float(q.concentration.mean()),'controls':{'matched':metrics(q.matched),'qqq':metrics(q.qqq),'rsp':metrics(q.rsp),'spy':metrics(q.spy)},'costs':{}}
        ids=np.array_split(np.arange(len(q)),5)
        for bp in COSTS:
            net=q.gross-q.turnover*bp/10000; cm=metrics(net); folds=[]
            for j,x in enumerate(ids,1):
                a=q.iloc[x]; candidate=a.gross-a.turnover*bp/10000
                folds.append({'fold':j,'excess_cagr_vs_matched':cagr(candidate)-cagr(a.matched),'excess_cagr_vs_spy':cagr(candidate)-cagr(a.spy)})
            z['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_matched':cm['cagr']-z['controls']['matched']['cagr'],'excess_cagr_vs_spy':cm['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-z['controls']['matched']['sharpe_rf0'],'max_drawdown_delta_vs_matched':cm['max_drawdown']-z['controls']['matched']['max_drawdown'],'positive_matched_folds':sum(x['excess_cagr_vs_matched']>0 for x in folds),'folds':folds}
        out['tests'][name]=z
    p=out['tests']['2020_forward']['costs']['50']
    out['decision']='P90_BREADTH_REGIME_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 and p['sharpe_delta_vs_matched']>0 else 'P90_BREADTH_REGIME_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p90_breadth_regime_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
