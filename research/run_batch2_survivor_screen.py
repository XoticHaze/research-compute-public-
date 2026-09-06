#!/usr/bin/env python3
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

START='2014-01-01T00:00:00+00:00'
END='2026-09-02T00:00:00+00:00'

def epoch(text):
    from datetime import datetime
    return int(datetime.fromisoformat(text).timestamp())

def probe(symbol):
    q=urlencode({'period1':epoch(START),'period2':epoch(END),'interval':'1d','events':'history','includeAdjustedClose':'true'})
    req=Request(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}',headers={'User-Agent':'Mozilla/5.0 research-compute/1.0'})
    try:
        with urlopen(req,timeout=30) as r:
            payload=json.loads(r.read().decode())
        result=(payload.get('chart',{}).get('result') or [None])[0]
        ts=[] if not result else (result.get('timestamp') or [])
        return {'status':'available' if ts else 'no_data','rows':len(ts)}
    except HTTPError as e:
        return {'status':'http_error','code':e.code}
    except URLError as e:
        return {'status':'url_error','reason':str(e.reason)}

c=json.loads(Path('research/batch2-contract.json').read_text())
out={'schema':'research_compute_public.batch2_source_survivorship.v1','research_only':True,'external_holdouts_loaded':False,'families':{}}
for family,spec in c['families'].items():
    symbols=list(spec['development_universe'])+[spec['primary_industry_etf']]
    probes={s:probe(s) for s in symbols}
    out['families'][family]={'probes':probes,'runnable':all(v['status']=='available' for v in probes.values())}
print('BATCH2_SOURCE_SURVIVORSHIP='+json.dumps(out,sort_keys=True))
