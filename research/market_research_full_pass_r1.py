#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, math, time, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

CONFIGS = {
  "p38_biotech_relmom": {"a":"XBI","b":"QQQ","kind":"relmom126","name":"Biotech 6m relative momentum"},
  "p39_homebuilder_trend": {"a":"ITB","b":"QQQ","kind":"sma200","name":"Homebuilder absolute trend"},
  "p40_energy_reversal": {"a":"XLE","b":"SPY","kind":"reversal21","name":"Energy 1m relative reversal"},
  "p41_gold_miners_relmom": {"a":"GDX","b":"GLD","kind":"relmom126","name":"Gold-miner vs bullion relative momentum"},
  "p42_regional_banks_recovery": {"a":"KRE","b":"SPY","kind":"recovery63","name":"Regional-bank recovery state"},
  "p43_defense_lowvol": {"a":"ITA","b":"SPY","kind":"lowvol63","name":"Defense relative low-vol state"},
  "p44_software_dual_mom": {"a":"IGV","b":"QQQ","kind":"dual126","name":"Software dual momentum"},
  "p45_smallcap_relmom": {"a":"IWM","b":"QQQ","kind":"relmom252","name":"Small-cap 12m relative momentum"},
}
START = "2000-01-01"
END = "2026-09-08"
COSTS = (10,25,50)

def fetch(symbol):
    p1=int(dt.datetime.fromisoformat(START).replace(tzinfo=dt.timezone.utc).timestamp())
    p2=int((dt.datetime.fromisoformat(END)+dt.timedelta(days=1)).replace(tzinfo=dt.timezone.utc).timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits&includeAdjustedClose=true"
    last=None
    for attempt in range(1,6):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 research-only"})
            with urllib.request.urlopen(req,timeout=30) as r: raw=r.read()
            doc=json.loads(raw)
            result=doc["chart"]["result"][0]
            ts=result["timestamp"]
            adj=result.get("indicators",{}).get("adjclose",[{}])[0].get("adjclose")
            if adj is None: adj=result["indicators"]["quote"][0]["close"]
            s=pd.Series(adj,index=pd.to_datetime(ts,unit="s",utc=True).tz_convert(None).normalize(),dtype=float,name=symbol).dropna()
            s=s[~s.index.duplicated(keep="last")].sort_index()
            if len(s)<500: raise RuntimeError(f"too_few_rows:{len(s)}")
            return s,{"symbol":symbol,"url":url,"sha256":hashlib.sha256(raw).hexdigest(),"rows":int(len(s)),"attempt":attempt,"first":str(s.index.min().date()),"last":str(s.index.max().date())}
        except Exception as e:
            last=repr(e)
            if attempt<5: time.sleep(attempt*1.5)
    raise RuntimeError(f"source_failure:{symbol}:{last}")

def month_ends(index):
    p=pd.Series(index,index=index)
    return p.groupby(index.to_period("M")).last().values

def make_weights(px,kind):
    a,b=px.columns[:2]
    idx=px.index
    me=pd.DatetimeIndex(month_ends(idx))
    sig=pd.Series(np.nan,index=idx)
    ra21=px[a].pct_change(21); rb21=px[b].pct_change(21)
    ra63=px[a].pct_change(63); rb63=px[b].pct_change(63)
    ra126=px[a].pct_change(126); rb126=px[b].pct_change(126)
    ra252=px[a].pct_change(252); rb252=px[b].pct_change(252)
    rv_a=px[a].pct_change().rolling(63).std(); rv_b=px[b].pct_change().rolling(63).std()
    sma200=px[a].rolling(200).mean()
    draw=px[a]/px[a].rolling(252).max()-1
    if kind=="relmom126": raw=ra126-rb126
    elif kind=="relmom252": raw=ra252-rb252
    elif kind=="sma200": raw=px[a]/sma200-1
    elif kind=="reversal21": raw=-(ra21-rb21)
    elif kind=="recovery63": raw=np.where((ra63>0)&(draw<-0.05),1.0,-1.0); raw=pd.Series(raw,index=idx)
    elif kind=="lowvol63": raw=rv_b-rv_a
    elif kind=="dual126": raw=np.minimum(ra126-rb126,ra126)
    else: raise ValueError(kind)
    sig.loc[me]=np.where(raw.loc[me]>0,1.0,0.0)
    # Decision at month-end is applied from next session onward.
    sig=sig.shift(1).ffill().fillna(0.0)
    return pd.DataFrame({a:sig,b:1.0-sig},index=idx)

def static_weights(px):
    return pd.DataFrame(0.5,index=px.index,columns=px.columns[:2])

def portfolio(px,w,bps):
    rets=px.pct_change().fillna(0.0)
    w=w.reindex(px.index).ffill().fillna(0.5)
    gross=(w*rets).sum(axis=1)
    turnover=w.diff().abs().sum(axis=1).fillna(0.0)/2.0
    net=gross-turnover*(bps/10000.0)
    return net,turnover

def cagr(r):
    if len(r)<2:return float('nan')
    years=(r.index[-1]-r.index[0]).days/365.25
    total=float((1+r).prod())
    return float(total**(1/years)-1) if years>0 and total>0 else float('nan')

def maxdd(r):
    eq=(1+r).cumprod(); return float((eq/eq.cummax()-1).min())

def annvol(r): return float(r.std(ddof=1)*math.sqrt(252))
def sharpe(r):
    s=r.std(ddof=1); return float(r.mean()/s*math.sqrt(252)) if s>0 else float('nan')

def fold_excess(r,br,n=5):
    ids=np.array_split(np.arange(len(r)),n); vals=[]
    for z in ids:
        rr=r.iloc[z]; bb=br.iloc[z]
        vals.append(float((1+rr).prod()-(1+bb).prod()))
    return vals

def yearly_excess(r,br):
    out=[]
    for y,g in r.groupby(r.index.year):
        b=br[br.index.year==y]
        if len(g)<100 or len(b)!=len(g): continue
        out.append(float((1+g).prod()-(1+b).prod()))
    return out

def run(child):
    c=CONFIGS[child]
    symbols=[]
    for s in (c['a'],c['b'],'SPY','QQQ'):
        if s not in symbols: symbols.append(s)
    series={}; prov=[]
    for s in symbols:
        series[s],p=fetch(s); prov.append(p)
    px=pd.concat(series.values(),axis=1,join='inner').dropna()
    px.columns=symbols
    # Require enough warmup and use exact common observed window.
    warm={'relmom126':126,'relmom252':252,'sma200':200,'reversal21':21,'recovery63':252,'lowvol63':63,'dual126':126}[c['kind']]
    px=px.iloc[warm:].copy()
    w=make_weights(px[[c['a'],c['b']]],c['kind'])
    sw=static_weights(px[[c['a'],c['b']]])
    metrics={}
    primary=None
    for bps in COSTS:
        r,t=portfolio(px[[c['a'],c['b']]],w,bps)
        br,bt=portfolio(px[[c['a'],c['b']]],sw,0)
        folds=fold_excess(r,br); years=yearly_excess(r,br)
        m={"strategy_cagr":cagr(r),"matched_static_cagr":cagr(br),"excess_cagr_pp":100*(cagr(r)-cagr(br)),"positive_folds":sum(x>0 for x in folds),"folds":folds,"positive_years":sum(x>0 for x in years),"year_count":len(years),"max_drawdown":maxdd(r),"static_max_drawdown":maxdd(br),"ann_vol":annvol(r),"static_ann_vol":annvol(br),"sharpe":sharpe(r),"static_sharpe":sharpe(br),"switches":int((t>0).sum())}
        metrics[str(bps)]=m
        if bps==25: primary=(r,br,m)
    # pure benchmark CAGRs on same window, no strategy costs
    benchmarks={s:cagr(px[s].pct_change().fillna(0.0)) for s in symbols}
    gate=metrics['25']['excess_cagr_pp']>0 and metrics['25']['positive_folds']>=3 and metrics['50']['excess_cagr_pp']>0
    return {"schema":"market_research_full_pass_r1_result","child":child,"hypothesis":c['name'],"kind":c['kind'],"pair":[c['a'],c['b']],"window":{"start":str(px.index.min().date()),"end":str(px.index.max().date()),"sessions":len(px)},"source_provenance":prov,"cost_bps_per_switch_notional":list(COSTS),"metrics":metrics,"benchmarks":benchmarks,"support_gate":gate,"decision":"SUPPORTED_REQUIRES_INDEPENDENT_VALIDATION" if gate else "NOT_SUPPORTED_ROTATE","scientific_notes":"Prospectively fixed single-pass mechanism; no parameter search. External Yahoo Chart inputs are research-only and identified by exact response SHA256; no MM canonical-data claim.","protected_boundaries":{"strategy_spec_mutation":False,"runtime_authority_change":False,"broker_submission":False,"live_trading_change":False}}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--child',choices=sorted(CONFIGS),required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    result=run(a.child); Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"child":a.child,"decision":result['decision'],"window":result['window'],"primary":result['metrics']['25'],"stress50_excess_pp":result['metrics']['50']['excess_cagr_pp']},indent=2))
if __name__=='__main__': main()
