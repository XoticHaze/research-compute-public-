import json, urllib.request, urllib.parse, time, hashlib
from datetime import datetime, timezone

SYMS=['SMH','QQQ','SPY']
COSTS=[10,25,50]
LOOKBACK=20
START=int(datetime(2000,1,1,tzinfo=timezone.utc).timestamp())
END=int(datetime(2026,9,8,12,0,tzinfo=timezone.utc).timestamp())

def fetch(sym):
    url=(f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym,safe="")}'
         f'?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true')
    last=None
    for attempt in range(1,6):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            raw=urllib.request.urlopen(req,timeout=45).read(); p=json.loads(raw); r=p['chart']['result'][0]
            q=r['indicators']['quote'][0]; adj=((r.get('indicators',{}).get('adjclose') or [{}])[0].get('adjclose') or q.get('close'))
            rows=[]
            for ts,o,h,l,c,a in zip(r['timestamp'],q['open'],q['high'],q['low'],q['close'],adj):
                if None in (o,h,l,c,a) or float(c)<=0: continue
                factor=float(a)/float(c); ao=float(o)*factor; ah=float(h)*factor; al=float(l)*factor; ac=float(a)
                if min(ao,ah,al,ac)<=0: continue
                rows.append((datetime.fromtimestamp(ts,timezone.utc).date().isoformat(),ao,ah,al,ac))
            if len(rows)<LOOKBACK+22: raise RuntimeError(f'{sym} parsed only {len(rows)} rows')
            return url,raw,rows,attempt
        except Exception as e:
            last=e; print(f'SOURCE_ATTEMPT_FAILURE symbol={sym} attempt={attempt} class={type(e).__name__} detail={e}',flush=True)
            if attempt<5: time.sleep(attempt*2)
    raise RuntimeError(f'SOURCE_EXHAUSTED symbol={sym} last={type(last).__name__}:{last}')

def mdd(curve):
    peak=curve[0]; out=0.0
    for v in curve:
        peak=max(peak,v); out=min(out,v/peak-1)
    return out

def run(cost,dates,smh,qqq):
    eq=1.0; curve=[1.0]; prev=None; switches=0; n=len(dates); fl=max(1,n//5); fs=[1.0]*5; fc=[1.0]*5
    for i in range(LOOKBACK+1,n):
        vals=[]
        for j in range(i-LOOKBACK,i):
            _,_,h,l,c=smh[j]
            if h>l: vals.append((2*c-h-l)/(h-l))
        pressure=sum(vals)/len(vals) if vals else 0.0
        asset='SMH' if pressure>0 else 'QQQ'
        ret=(smh[i][4]/smh[i-1][4]-1) if asset=='SMH' else (qqq[i][4]/qqq[i-1][4]-1)
        if prev is not None and asset!=prev: ret-=cost/10000.0; switches+=1
        eq*=1+ret; curve.append(eq); prev=asset
        k=min(4,i//fl); fs[k]*=1+ret; fc[k]*=1+(.5*(smh[i][4]/smh[i-1][4]-1)+.5*(qqq[i][4]/qqq[i-1][4]-1))
    years=(datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[LOOKBACK+1])).days/365.25
    cagr=eq**(1/years)-1; fold_ex=[fs[k]-fc[k] for k in range(5)]
    return {'cagr':cagr,'max_drawdown':mdd(curve),'switches':switches,'positive_fold_terminal_excess':sum(x>0 for x in fold_ex),'fold_terminal_excess':fold_ex}

data={}; sources={}
for s in SYMS:
    u,b,r,a=fetch(s); data[s]=r; sources[s]={'provider':'Yahoo Finance chart API v8','url':u,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'parsed_rows':len(r),'successful_attempt':a,'price_basis':'adjusted OHLC reconstructed with adjusted_close/raw_close factor'}
maps={s:{r[0]:r for r in data[s]} for s in SYMS}; dates=sorted(set(maps['SMH'])&set(maps['QQQ'])&set(maps['SPY']))
smh=[maps['SMH'][d] for d in dates]; qqq=[maps['QQQ'][d] for d in dates]; spy=[maps['SPY'][d] for d in dates]; a=LOOKBACK+1
years=(datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[a])).days/365.25
base={}
for name,series in [('SMH',smh),('QQQ',qqq),('SPY',spy)]: base[name]=(series[-1][4]/series[a-1][4])**(1/years)-1
eq=1.0
for i in range(a,len(dates)): eq*=1+.5*(smh[i][4]/smh[i-1][4]-1)+.5*(qqq[i][4]/qqq[i-1][4]-1)
base['STATIC_50_50']=eq**(1/years)-1
res={str(c):run(c,dates,smh,qqq) for c in COSTS}; p=res['25']; p['excess_cagr_vs_static_50_50']=p['cagr']-base['STATIC_50_50']
decision='P26_SMH_CLOSING_PRESSURE_SUPPORTED' if p['excess_cagr_vs_static_50_50']>0 and p['positive_fold_terminal_excess']>=3 and res['50']['cagr']>base['STATIC_50_50'] else 'P26_SMH_CLOSING_PRESSURE_NOT_SUPPORTED'
out={'schema':'p26.smh_closing_pressure.v1','contract':{'lookback_sessions':20,'state':'hold SMH next session iff prior-only mean adjusted daily close-location value > 0 else QQQ','close_location_value':'(2*close-high-low)/(high-low)','cost_bps_per_switch':COSTS,'no_parameter_search':True},'matched_window':{'start':dates[a],'end':dates[-1],'sessions':len(dates)-a},'sources':sources,'baselines':base,'cost_results':res,'decision':decision,'authority_boundary':'research-only; no StrategySpec/runtime/broker/live mutation'}
print(json.dumps(out,indent=2,sort_keys=True)); open('p26_result.json','w').write(json.dumps(out,indent=2,sort_keys=True))
