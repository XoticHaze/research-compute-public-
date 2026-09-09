#!/usr/bin/env python3
import hashlib, json, math, time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

MARKETS={'ES':'ES=F','NQ':'NQ=F','RTY':'RTY=F','GC':'GC=F','ZN':'ZN=F'}
COSTS=(2.5,5.0,10.0); TOPK=2
START=int(pd.Timestamp('2010-01-01',tz='UTC').timestamp()); END=int(pd.Timestamp('2026-09-10',tz='UTC').timestamp())

def load_close(ticker):
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true'
    last=None
    for attempt in range(1,6):
        try:
            raw=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 research-compute'}),timeout=30).read(); payload=json.loads(raw)['chart']['result'][0]
            idx=pd.to_datetime(payload['timestamp'],unit='s',utc=True).tz_convert(None); vals=payload['indicators']['quote'][0]['close']; s=pd.Series(vals,index=idx,dtype=float).dropna().sort_index(); s=s[~s.index.duplicated(keep='last')]
            if len(s)<1500: raise RuntimeError(f'{ticker}: only {len(s)} rows')
            if (s<=0).any(): raise RuntimeError(f'{ticker}: nonpositive price not valid for price-ratio screen')
            return s,{'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(s),'attempt':attempt,'first':s.index.min().date().isoformat(),'last':s.index.max().date().isoformat()}
        except Exception as e:
            last=e
            if attempt<5: time.sleep(min(2**attempt,8))
    raise RuntimeError(f'{ticker}: source fetch failed after retries: {last}')

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else None

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); years=len(r)/12; vol=float(r.std(ddof=1)*math.sqrt(12)); dd=eq/eq.cummax()-1
    return {'months':len(r),'cagr':float(eq.iloc[-1]**(1/years)-1),'ann_vol':vol,'sharpe_rf0':float(r.mean()*12/vol) if vol>0 else None,'max_dd':float(dd.min()),'final_equity':float(eq.iloc[-1])}

def main():
    close={}; source={}
    for k,t in MARKETS.items(): close[k],source[k]=load_close(t)
    monthly=pd.concat({k:v.resample('ME').last() for k,v in close.items()},axis=1).dropna(); ret=monthly.pct_change(); mom=monthly.pct_change(12)
    rows=[]; prev={k:0.0 for k in MARKETS}
    for i in range(13,len(monthly)):
        dt=monthly.index[i-1]; nxt=monthly.index[i]; score=mom.loc[dt].dropna()
        if len(score)!=len(MARKETS): continue
        picks=list(score.sort_values(ascending=False).head(TOPK).index); w={k:(1/TOPK if k in picks else 0.0) for k in MARKETS}; r=ret.loc[nxt]
        if r.isna().any(): continue
        turn=.5*sum(abs(w[k]-prev[k]) for k in MARKETS); rows.append({'date':nxt,'gross':sum(w[k]*float(r[k]) for k in MARKETS),'ew':float(r.mean()),'turn':turn,'picks':picks}); prev=w
    fr=pd.DataFrame(rows).set_index('date')
    out={'schema':'research.futures_crossasset_portfolio_momentum_r5','classification':'EXTERNAL_PROXY_PORTFOLIO_SCREEN_ONLY','scientific_contract':{'markets':MARKETS,'mechanism':'rank prior 12-month returns cross-sectionally each month; equally weight top 2 next month','top_k':TOPK,'costs_bps':list(COSTS),'matched_control':'same five-market equal-weight portfolio on identical months','chronological_folds':5,'no_parameter_search':True,'no_canonical_roll_claim':True},'supersedes_run_interpretation':{'run_id':34330894110,'classification':'DATA_TRANSPORT_TRANSIENT','reason':'Yahoo yfinance request was rate-limited before science; direct chart fetch with bounded retries replaces transport only, scientific contract unchanged'},'source':source,'window':{'start':fr.index.min().date().isoformat(),'end':fr.index.max().date().isoformat(),'months':len(fr)},'tests':{}}
    for bp in COSTS:
        f=fr.copy(); f['net']=f.gross-f.turn*bp/10000.0; folds=[]
        for j,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
            q=f.iloc[ids]; folds.append({'fold':j,'start':q.index.min().date().isoformat(),'end':q.index.max().date().isoformat(),'excess_cagr':cagr(q.net)-cagr(q.ew)})
        out['tests'][str(bp)]={'candidate':metrics(f.net),'matched_equal_weight':metrics(f.ew),'excess_cagr':cagr(f.net)-cagr(f.ew),'positive_folds':sum(x['excess_cagr']>0 for x in folds),'folds':folds,'mean_monthly_turnover':float(f.turn.mean())}
    p=out['tests']['5.0']; out['decision']='FUTURES_CROSSASSET_MOMENTUM_SCREEN_SUPPORTED' if p['excess_cagr']>0 and p['positive_folds']>=3 and p['candidate']['sharpe_rf0']>=p['matched_equal_weight']['sharpe_rf0'] else 'FUTURES_CROSSASSET_MOMENTUM_SCREEN_NOT_SUPPORTED'
    Path('futures_crossasset_portfolio_momentum_r5.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'primary':p},sort_keys=True))
if __name__=='__main__': main()
