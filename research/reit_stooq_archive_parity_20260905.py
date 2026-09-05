from __future__ import annotations

"""Source-only archival/parity diagnostic for frozen Equity REIT holdout.

Stooq is tested only as an independent archive candidate. No REIT model or target economics
are computed. A candidate source is useful only if AVB/EQR have long history AND its daily
return semantics closely reproduce Yahoo on unaffected ESS/DLR controls plus available
recent AVB/EQR overlap. This diagnostic does not authorize a source switch by itself.
"""

import csv,json,io
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import math,statistics

SYMBOLS=('AVB','EQR','ESS','DLR'); START='20140101'; END='20260902'; OUT=Path('reit_stooq_archive_parity_20260905.json')

def stooq(sym):
    url=f'https://stooq.com/q/d/l/?s={sym.lower()}.us&d1={START}&d2={END}&i=d'; req=Request(url,headers={'User-Agent':'Mozilla/5.0 research-compute-public/1.0'})
    with urlopen(req,timeout=30) as r:text=r.read().decode()
    rows=list(csv.DictReader(io.StringIO(text))); out={}
    for row in rows:
        try: out[row['Date']]=float(row['Close'])
        except Exception: pass
    return out

def yahoo(sym):
    p1=int(datetime(2014,1,1,tzinfo=timezone.utc).timestamp()); p2=int(datetime(2026,9,3,tzinfo=timezone.utc).timestamp()); q=urlencode({'period1':p1,'period2':p2,'interval':'1d','events':'history','includeAdjustedClose':'true'}); req=Request(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}',headers={'User-Agent':'Mozilla/5.0 research-compute-public/1.0'})
    with urlopen(req,timeout=30) as r:p=json.loads(r.read().decode()); x=(p.get('chart',{}).get('result') or [None])[0]
    ts=x.get('timestamp') or []; ind=x.get('indicators',{}); vals=((ind.get('adjclose') or [{}])[0].get('adjclose') or [])
    out={}
    for t,v in zip(ts,vals):
        if v is not None:out[datetime.fromtimestamp(t,tz=timezone.utc).strftime('%Y-%m-%d')]=float(v)
    return out

def returns(px,dates):
    r={}
    for a,b in zip(dates[:-1],dates[1:]):
        if px[a] and px[b]:r[b]=px[b]/px[a]-1.0
    return r

def corr(a,b):
    if len(a)<3:return None
    ma=sum(a)/len(a);mb=sum(b)/len(b);num=sum((x-ma)*(y-mb) for x,y in zip(a,b));da=math.sqrt(sum((x-ma)**2 for x in a));db=math.sqrt(sum((y-mb)**2 for y in b));return None if da==0 or db==0 else num/(da*db)

def main():
    result={}; long_ok=[]; parity_ok=[]
    for s in SYMBOLS:
        st=stooq(s); yh=yahoo(s); common=sorted(set(st)&set(yh)); sr=returns(st,common);yr=returns(yh,common); rd=sorted(set(sr)&set(yr)); a=[sr[d] for d in rd];b=[yr[d] for d in rd];diff=[abs(x-y)*10000.0 for x,y in zip(a,b)]
        item={'stooq_rows':len(st),'stooq_first':min(st) if st else None,'stooq_last':max(st) if st else None,'yahoo_rows':len(yh),'overlap_price_dates':len(common),'overlap_return_days':len(rd),'daily_return_corr':corr(a,b),'median_abs_return_diff_bps':None if not diff else float(statistics.median(diff)),'p95_abs_return_diff_bps':None if not diff else float(sorted(diff)[int(.95*(len(diff)-1))])}
        result[s]=item
        if len(st)>=3000:long_ok.append(s)
        if item['overlap_return_days']>=10 and (item['daily_return_corr'] or -1)>=0.995 and (item['median_abs_return_diff_bps'] or 999)<=2.0:parity_ok.append(s)
    candidate=bool('AVB' in long_ok and 'EQR' in long_ok and 'ESS' in parity_ok and 'DLR' in parity_ok and 'AVB' in parity_ok and 'EQR' in parity_ok)
    out={'schema':'public_compute.reit_stooq_archive_parity.v1','generated_at':datetime.now(timezone.utc).isoformat(),'symbols':result,'long_history_symbols':long_ok,'return_parity_symbols':parity_ok,'candidate_source_mechanics_supported':candidate,'source_switch_authorized':False,'authorization_boundary':'even candidate=true only supports a separately frozen source-adapter parity consumer before any holdout model economics','target_returns_computed':False,'model_executed':False,'research_only':True}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('REIT_STOOQ_ARCHIVE_PARITY='+json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
