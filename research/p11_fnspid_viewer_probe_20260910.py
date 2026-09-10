from __future__ import annotations
import json, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DATASET='sabareesh88/FNSPID_nasdaq'
BASE='https://datasets-server.huggingface.co'
SYMBOLS=['AMAT','NVDA','AMD','AVGO','KLAC','LRCX','DHI','LEN','PHM','TOL']

def get(path, params):
    url=BASE+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'market-research-p11-fnspid-probe/1.1','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            return {'ok':True,'status':r.status,'url':url,'json':json.loads(r.read().decode())}
    except Exception as e:
        return {'ok':False,'url':url,'error':repr(e)}

def symbol_probe(s,cfg,split,sf,df):
    where=f'"{sf}" = \'{s}\''
    with ThreadPoolExecutor(max_workers=2) as ex:
        fa=ex.submit(get,'/filter',{'dataset':DATASET,'config':cfg,'split':split,'where':where,'orderby':f'"{df}" ASC','offset':0,'length':1})
        fd=ex.submit(get,'/filter',{'dataset':DATASET,'config':cfg,'split':split,'where':where,'orderby':f'"{df}" DESC','offset':0,'length':1})
        asc,desc=fa.result(),fd.result()
    row={'symbol':s,'asc_ok':asc['ok'],'desc_ok':desc['ok'],'asc_error':asc.get('error'),'desc_error':desc.get('error')}
    if asc['ok'] and desc['ok']:
        ar=(asc['json'].get('rows') or []); dr=(desc['json'].get('rows') or [])
        row['missing']=not bool(ar)
        row['earliest_raw']=ar[0].get('row',{}).get(df) if ar else None
        row['latest_raw']=dr[0].get('row',{}).get(df) if dr else None
    return row

spl=get('/splits',{'dataset':DATASET})
res={'schema':'research.p11_fnspid_viewer_probe_20260910','dataset':DATASET,'splits_probe':{'ok':spl['ok'],'error':spl.get('error')},'rows':[]}
if not spl['ok']:
    res['decision']='VIEWER_ROUTE_FAILURE_NOT_SOURCE_FAILURE'
else:
    items=spl['json'].get('splits') or []
    if not items:
        res['decision']='VIEWER_ROUTE_FAILURE_NOT_SOURCE_FAILURE'
    else:
        cfg=items[0]['config']; split=items[0]['split']; res['config']=cfg; res['split']=split
        first=get('/first-rows',{'dataset':DATASET,'config':cfg,'split':split})
        features=(first.get('json') or {}).get('features') or []
        names=[f.get('name') for f in features if isinstance(f,dict)]
        res['feature_names']=names
        lower={str(n).lower():n for n in names}
        sf=next((lower[x] for x in ['stock_symbol','stock','ticker','symbol'] if x in lower),None)
        df=next((lower[x] for x in ['date','datetime','timestamp','published_at','published'] if x in lower),None)
        res['symbol_field']=sf; res['date_field']=df
        if not sf or not df:
            res['decision']='VIEWER_SCHEMA_FAILURE_NOT_MODEL_FAILURE'
        else:
            rows=[]
            with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as ex:
                fut={ex.submit(symbol_probe,s,cfg,split,sf,df):s for s in SYMBOLS}
                for f in as_completed(fut): rows.append(f.result())
            rows.sort(key=lambda r:SYMBOLS.index(r['symbol'])); res['rows']=rows
            all_ok=all(r['asc_ok'] and r['desc_ok'] for r in rows)
            missing=[r['symbol'] for r in rows if r.get('missing')]; res['missing_symbols']=missing
            explicit=naive=date_only=0
            for r in rows:
                for v in [r.get('earliest_raw'),r.get('latest_raw')]:
                    t=str(v or '')
                    if len(t)==10: date_only+=1
                    elif t.endswith('Z') or 'UTC' in t or ('+' in t[10:] if len(t)>10 else False): explicit+=1
                    elif ':' in t: naive+=1
            res['timestamp_shape_endpoint_samples']={'explicit_offset':explicit,'datetime_no_offset':naive,'date_only':date_only}
            if not all_ok:
                res['decision']='VIEWER_FILTER_ROUTE_FAILURE_NOT_SOURCE_FAILURE'
            elif missing:
                res['decision']='FNSPID_MIRROR_SYMBOL_COVERAGE_FAILURE'
            else:
                res['decision']='FNSPID_MIRROR_BOUNDED_ROWS_AVAILABLE_TIMESTAMP_SEMANTICS_STILL_UNVERIFIED'
res['causal_admission']=False
res['note']='This probe is a cheap server-side bounded mirror check only. It does not establish upstream object identity, license permission, timezone semantics, or causal admission.'
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p11_fnspid_viewer_probe_20260910.json').write_text(json.dumps(res,indent=2,sort_keys=True)); print(json.dumps(res,sort_keys=True))
