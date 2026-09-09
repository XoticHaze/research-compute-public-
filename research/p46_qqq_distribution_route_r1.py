from __future__ import annotations
import json, hashlib, urllib.request, urllib.error
from pathlib import Path

BASE='https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/'
CANDIDATES=[
 'distributions?idType=ticker&productType=ETF',
 'distribution?idType=ticker&productType=ETF',
 'dividends?idType=ticker&productType=ETF',
 'distributionHistory?idType=ticker&productType=ETF',
 'income/distributions?idType=ticker&productType=ETF',
]

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'application/json,text/plain,*/*'})
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            b=r.read(); return r.status,r.headers.get('Content-Type'),b,None
    except urllib.error.HTTPError as e:
        b=e.read(); return e.code,e.headers.get('Content-Type'),b,repr(e)
    except Exception as e:
        return None,None,b'',repr(e)

def profile(obj):
    if isinstance(obj,list):
        return {'type':'list','length':len(obj),'sample_keys':sorted(obj[0].keys()) if obj and isinstance(obj[0],dict) else None,'sample':obj[:5]}
    if isinstance(obj,dict):
        return {'type':'dict','keys':sorted(obj.keys()),'sample':{k:obj[k] for k in list(obj)[:20]}}
    return {'type':type(obj).__name__,'repr':repr(obj)[:500]}

def main():
    out={'schema':'research.p46_qqq_distribution_route_r1','parent':'P46','purpose':'discover official Invesco QQQ dated distribution surface required to reconstruct issuer total return without changing P46','candidates':[]}
    for suffix in CANDIDATES:
        url=BASE+suffix; status,ctype,b,err=fetch(url); rec={'url':url,'status':status,'content_type':ctype,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest() if b else None,'error':err}
        if b:
            try: rec['json_profile']=profile(json.loads(b.decode('utf-8')))
            except Exception: rec['text_prefix']=b.decode('utf-8','ignore')[:800]
        out['candidates'].append(rec)
    hits=[x for x in out['candidates'] if x['status']==200 and x.get('json_profile')]
    out['decision']='OFFICIAL_DISTRIBUTION_ROUTE_FOUND' if hits else 'OFFICIAL_DISTRIBUTION_ROUTE_NOT_FOUND_IN_PREDECLARED_CANDIDATES'
    Path('results').mkdir(exist_ok=True); Path('results/p46_qqq_distribution_route_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps({'decision':out['decision'],'statuses':[(x['url'],x['status'],x.get('json_profile',{}).get('type')) for x in out['candidates']]},sort_keys=True))
if __name__=='__main__': main()
