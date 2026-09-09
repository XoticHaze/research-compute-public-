from __future__ import annotations
import json,urllib.request
from pathlib import Path

BASE='https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/'
STANDARD=BASE+'performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF'
ROLLING=BASE+'performance/rolling?idType=ticker&variationType=1M&productType=ETF'

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'application/json,text/plain,*/*'})
    with urllib.request.urlopen(req,timeout=45) as r: return json.loads(r.read().decode('utf-8'))

def walk(x,path='',out=None):
    out=[] if out is None else out
    if isinstance(x,dict):
        for k,v in x.items():
            p=f'{path}/{k}'
            if isinstance(v,(str,int,float,bool)) or v is None:
                text=(p+' '+str(v)).lower()
                if any(t in text for t in ('nav','return','year','effective','asof','1y','5y','10y','one','five','ten')): out.append({'path':p,'value':v})
            else: walk(v,p,out)
    elif isinstance(x,list):
        for i,v in enumerate(x): walk(v,f'{path}/{i}',out)
    return out

def shareclass_endpoint(obj,key):
    arr=obj.get(key,[]) if isinstance(obj,dict) else []
    for s in arr:
        if isinstance(s,dict) and str(s.get('type','')).lower()=='shareclass':
            data=s.get('data') or []
            if data:
                return {'label':s.get('label'),'start':data[0],'end':data[-1],'points':len(data)}
    return None

def main():
    standard=fetch(STANDARD); rolling=fetch(ROLLING)
    endpoints={k:shareclass_endpoint(rolling,k) for k in ('lineChart1YData','lineChart3YData','lineChart5YData','lineChart10YData')}
    out={'schema':'research.p46_qqq_identity_checkpoint_r1','parent':'P46','standard_candidate_scalars':walk(standard)[:1000],'rolling_shareclass_endpoints':endpoints,'effective_date':rolling.get('effectiveDate') if isinstance(rolling,dict) else None,'decision':'QQQ_ISSUER_IDENTITY_CHECKPOINTS_EXTRACTED'}
    Path('results').mkdir(exist_ok=True); Path('results/p46_qqq_identity_checkpoint_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps({'decision':out['decision'],'effective_date':out['effective_date'],'endpoints':endpoints,'standard_candidate_count':len(out['standard_candidate_scalars'])},sort_keys=True))
if __name__=='__main__': main()
