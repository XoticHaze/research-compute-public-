from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

START='2019-01-01'
END='2026-09-13'
SYMS=('DHI','LEN','PHM','NVR','TOL','MTH','KBH','LGIH','TMHC','GRBK','CVCO','SKY','TPH','DFH','UHG','MDC','LEGH','SDHC','NOBH','ITB','QQQ')

def epoch(s): return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
def fetch(symbol):
    q=urlencode({'period1':epoch(START),'period2':epoch(END),'interval':'1d','events':'history','includeAdjustedClose':'true'})
    req=Request(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}',headers={'User-Agent':'Mozilla/5.0 research-compute/1.0'})
    with urlopen(req,timeout=30) as r: payload=json.loads(r.read().decode())
    result=(payload.get('chart',{}).get('result') or [None])[0]
    if not result: raise RuntimeError(f'{symbol}: no result')
    tz=result.get('meta',{}).get('exchangeTimezoneName') or 'America/New_York'
    dates=[datetime.fromtimestamp(ts,timezone.utc).astimezone(ZoneInfo(tz)).date().isoformat() for ts in (result.get('timestamp') or [])]
    return tz, dates

rows={}; sets={}
for s in SYMS:
    try:
        tz,dates=fetch(s); ds=set(dates); sets[s]=ds
        rows[s]={'status':'ok','timezone':tz,'rows':len(dates),'unique_dates':len(ds),'first':min(ds) if ds else None,'last':max(ds) if ds else None,'head':sorted(ds)[:3],'tail':sorted(ds)[-3:]}
    except Exception as exc:
        rows[s]={'status':'error','error':f'{type(exc).__name__}: {exc}'}
base=sets.get('DHI',set())
for s in SYMS:
    if s in sets: rows[s]['overlap_dhi']=len(base & sets[s])
valid_sets=[sets[s] for s in SYMS if s in sets]
common=set.intersection(*valid_sets) if valid_sets else set()
fresh=('DFH','LEGH','SDHC','NOBH','TPH','UHG','MDC')
print('SOURCE_CALENDAR_PROBE='+json.dumps({'rows':rows,'fresh_candidates':{s:rows[s] for s in fresh},'common_dates_all_source_valid':len(common),'common_head':sorted(common)[:5],'common_tail':sorted(common)[-5:]},sort_keys=True))
