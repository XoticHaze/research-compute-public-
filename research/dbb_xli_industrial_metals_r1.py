import json, math, time, urllib.request
from datetime import datetime, timezone

TICKERS=['DBB','XLI','SPY']
START='2012-01-01'; END='2026-09-01'; COST=0.001; THRESH=0.03

def epoch(s): return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
def fetch(t):
    u=f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1={epoch(START)}&period2={epoch(END)}&interval=1d&events=div%2Csplits&includeAdjustedClose=true'
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    for k in range(4):
        try:
            with urllib.request.urlopen(req,timeout=30) as r: j=json.load(r)
            x=j['chart']['result'][0]; a=x['indicators']['adjclose'][0]['adjclose']; ts=x['timestamp']
            return {datetime.fromtimestamp(z,timezone.utc).date():p for z,p in zip(ts,a) if p is not None}
        except Exception:
            if k==3: raise
            time.sleep(2**k)
def month_end(d):
    out={}
    for dt,p in d.items():
        key=(dt.year,dt.month)
        if key not in out or dt>out[key][0]: out[key]=(dt,p)
    return {k:v[1] for k,v in out.items()}
def nextm(k): return (k[0]+(k[1]==12),1 if k[1]==12 else k[1]+1)
def cagr(rs):
    if not rs:return 0.0
    v=1
    for r in rs:v*=1+r
    return v**(12/len(rs))-1
def mdd(rs):
    v=pk=1; dd=0
    for r in rs:
        v*=1+r; pk=max(pk,v); dd=min(dd,v/pk-1)
    return dd

m={t:month_end(fetch(t)) for t in TICKERS}; keys=sorted(set.intersection(*(set(x) for x in m.values())))
rows=[]; prev=None
for i,k in enumerate(keys):
    if i<1: continue
    p=keys[i-1]
    if nextm(p)!=k: continue
    dbb=m['DBB'][p]/m['DBB'][keys[i-2]]-1 if i>=2 and nextm(keys[i-2])==p else None
    if dbb is None: continue
    xli=m['XLI'][k]/m['XLI'][p]-1; spy=m['SPY'][k]/m['SPY'][p]-1
    state=1 if dbb>=THRESH else 0
    cand=(xli if state else spy) - (COST if prev is not None and state!=prev else 0)
    rows.append({'k':k,'cand':cand,'xli':xli,'spy':spy,'state':state}); prev=state

def metrics(start):
    z=[r for r in rows if r['k']>=(start,1)]; f=sum(r['state'] for r in z)/len(z)
    control=[f*r['xli']+(1-f)*r['spy'] for r in z]
    cr=cagr([r['cand'] for r in z]); br=cagr(control)
    return {'candidate_cagr':cr,'matched_control_cagr':br,'excess_pp':100*(cr-br),'candidate_mdd':mdd([r['cand'] for r in z]),'control_mdd':mdd(control),'xli_fraction':f,'months':len(z)}
windows={str(y):metrics(y) for y in (2012,2018,2022)}
folds=[]
for a,b in [(2012,2015),(2016,2019),(2020,2022),(2023,2026)]:
    z=[r for r in rows if a<=r['k'][0]<=b]; f=sum(r['state'] for r in z)/len(z); ctl=[f*r['xli']+(1-f)*r['spy'] for r in z]
    folds.append({'period':f'{a}-{b}','excess_pp':100*(cagr([r['cand'] for r in z])-cagr(ctl))})
pos=sum(x['excess_pp']>0 for x in folds); w=windows['2012']; dd_det=100*(abs(w['candidate_mdd'])-abs(w['control_mdd']))
support=all(windows[str(y)]['excess_pp']>0 for y in (2012,2018,2022)) and pos>=3 and dd_det<=5
o={'decision':'DBB_XLI_INDUSTRIAL_METALS_SUPPORTED' if support else 'DBB_XLI_INDUSTRIAL_METALS_REJECTED','frozen':{'signal':'prior completed-month DBB total return >= +3%','candidate':'next month XLI else SPY','cost_one_way':COST,'control':'static XLI/SPY mixture matched to realized XLI participation','no_rescue':True},'windows':windows,'folds':folds,'positive_folds':pos,'drawdown_deterioration_pp':dd_det}
print('RESULT_JSON='+json.dumps(o,sort_keys=True))
