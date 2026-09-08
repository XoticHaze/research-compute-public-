import csv, io, json, math, urllib.request, time, hashlib
from datetime import datetime

SYMS=['smh.us','qqq.us','spy.us']
COSTS=[10,25,50]
LOOKBACK=20

def fetch(sym):
    url=f'https://stooq.com/q/d/l/?s={sym}&d1=20000101&d2=20260908&i=d'
    last=None
    for attempt in range(1,6):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            raw=urllib.request.urlopen(req,timeout=45).read()
            rows=[]
            for r in csv.DictReader(io.StringIO(raw.decode())):
                try: rows.append((r['Date'],float(r['Open']),float(r['Close'])))
                except (KeyError,ValueError): pass
            if len(rows)<LOOKBACK+2:
                raise RuntimeError(f'{sym} parsed only {len(rows)} rows from {len(raw)} bytes')
            return url,raw,rows,attempt
        except Exception as e:
            last=e
            print(f'SOURCE_ATTEMPT_FAILURE symbol={sym} attempt={attempt} class={type(e).__name__} detail={e}',flush=True)
            if attempt<5: time.sleep(attempt*2)
    raise RuntimeError(f'SOURCE_EXHAUSTED symbol={sym} attempts=5 last={type(last).__name__}:{last}')

def cagr(vals, years): return vals[-1]**(1/years)-1 if years>0 else 0

def mdd(vals):
    peak=vals[0]; dd=0
    for v in vals:
        peak=max(peak,v); dd=min(dd,v/peak-1)
    return dd

def run(cost_bps, dates, smh, qqq):
    eq=1.0; curve=[1.0]; prev=None; folds=[1.0]*5; fctrl=[1.0]*5; switches=0
    n=len(dates); fold_len=max(1,n//5)
    for i,d in enumerate(dates):
        if i<LOOKBACK+1: continue
        overnight=0.0; intraday=0.0
        for j in range(i-LOOKBACK,i):
            overnight += math.log(smh[j][1]/smh[j-1][2])
            intraday += math.log(smh[j][2]/smh[j][1])
        asset='SMH' if overnight>intraday else 'QQQ'
        ret=(smh[i][2]/smh[i-1][2]-1) if asset=='SMH' else (qqq[i][2]/qqq[i-1][2]-1)
        if prev is not None and asset!=prev:
            ret -= cost_bps/10000.0; switches+=1
        eq*=1+ret; curve.append(eq); prev=asset
        k=min(4,i//fold_len); folds[k]*=1+ret
        ctrl=.5*(smh[i][2]/smh[i-1][2]-1)+.5*(qqq[i][2]/qqq[i-1][2]-1)
        fctrl[k]*=1+ctrl
    years=(datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[LOOKBACK+1])).days/365.25
    fc=[folds[k]-fctrl[k] for k in range(5)]
    return {'cagr':cagr(curve,years),'max_drawdown':mdd(curve),'switches':switches,'positive_fold_terminal_excess':sum(x>0 for x in fc),'fold_terminal_excess':fc}

def bh(series,dates):
    a=LOOKBACK+1; years=(datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[a])).days/365.25
    return (series[-1][2]/series[a-1][2])**(1/years)-1

data={}; sources={}
for s in SYMS:
    u,b,r,attempt=fetch(s)
    sources[s]={'url':u,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'parsed_rows':len(r),'successful_attempt':attempt}
    data[s]=r
maps={s:{r[0]:r for r in data[s]} for s in SYMS}
dates=sorted(set(maps['smh.us'])&set(maps['qqq.us'])&set(maps['spy.us']))
if len(dates)<LOOKBACK+22: raise RuntimeError(f'insufficient matched rows: {len(dates)}')
smh=[maps['smh.us'][d] for d in dates]; qqq=[maps['qqq.us'][d] for d in dates]; spy=[maps['spy.us'][d] for d in dates]
res={str(c):run(c,dates,smh,qqq) for c in COSTS}
base={'SMH':bh(smh,dates),'QQQ':bh(qqq,dates),'SPY':bh(spy,dates)}
a=LOOKBACK+1; years=(datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[a])).days/365.25
eq=1.0
for i in range(a,len(dates)): eq*=1+.5*(smh[i][2]/smh[i-1][2]-1)+.5*(qqq[i][2]/qqq[i-1][2]-1)
base['STATIC_50_50']=eq**(1/years)-1
primary=res['25']; primary['excess_cagr_vs_static_50_50']=primary['cagr']-base['STATIC_50_50']
decision='P24_OVERNIGHT_INTRADAY_STATE_SUPPORTED' if primary['excess_cagr_vs_static_50_50']>0 and primary['positive_fold_terminal_excess']>=3 and res['50']['cagr']>base['STATIC_50_50'] else 'P24_OVERNIGHT_INTRADAY_STATE_NOT_SUPPORTED'
out={'schema':'p24.smh_overnight_intraday_state.v1','contract':{'lookback_sessions':20,'state':'SMH if cumulative prior-only overnight log return > cumulative prior-only intraday log return else QQQ','decision_at':'prior close using only completed sessions','cost_bps_per_switch':COSTS,'no_parameter_search':True},'matched_window':{'start':dates[a],'end':dates[-1],'sessions':len(dates)-a},'sources':sources,'baselines':base,'cost_results':res,'decision':decision,'authority_boundary':'research-only; no StrategySpec/runtime/broker/live mutation'}
print(json.dumps(out,indent=2,sort_keys=True))
open('p24_result.json','w').write(json.dumps(out,indent=2,sort_keys=True))
