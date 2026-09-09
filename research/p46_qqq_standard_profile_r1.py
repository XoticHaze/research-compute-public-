from __future__ import annotations
import json, hashlib, urllib.request
from pathlib import Path

URLS={
  'navs':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF',
  'standard':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF',
  'rolling_1m':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/performance/rolling?idType=ticker&variationType=1M&productType=ETF',
}

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'application/json,text/plain,*/*'})
    with urllib.request.urlopen(req,timeout=45) as r:
        b=r.read()
        return r.status,r.headers.get('Content-Type'),b

def summarize(x,path='',out=None):
    out=[] if out is None else out
    if isinstance(x,dict):
        for k,v in x.items():
            p=f'{path}/{k}'
            if isinstance(v,(str,int,float,bool)) or v is None:
                out.append({'path':p,'value':v})
            else:
                summarize(v,p,out)
    elif isinstance(x,list):
        out.append({'path':path,'list_length':len(x),'sample_keys':sorted(x[0].keys()) if x and isinstance(x[0],dict) else None})
        for i,v in enumerate(x[:200]): summarize(v,f'{path}/{i}',out)
    return out

def main():
    result={'schema':'research.p46_qqq_standard_profile_r1','parent':'P46','hypothesis':'Issuer performance endpoint contains explicit QQQ NAV return checkpoints suitable for independent daily-NAV identity validation.','surfaces':{}}
    for name,url in URLS.items():
        status,ctype,b=fetch(url)
        obj=json.loads(b.decode('utf-8'))
        result['surfaces'][name]={
            'url':url,'status':status,'content_type':ctype,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),
            'top_level_type':type(obj).__name__,
            'top_level_keys':sorted(obj.keys()) if isinstance(obj,dict) else None,
            'profile':summarize(obj)[:1200],
        }
    Path('results').mkdir(exist_ok=True)
    Path('results/p46_qqq_standard_profile_r1.json').write_text(json.dumps(result,indent=2,sort_keys=True))
    print(json.dumps({'decision':'PROFILE_MATERIALIZED','standard_profile_items':len(result['surfaces']['standard']['profile']),'nav_profile_items':len(result['surfaces']['navs']['profile'])},sort_keys=True))

if __name__=='__main__': main()
