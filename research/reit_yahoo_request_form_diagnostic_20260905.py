from __future__ import annotations

"""Source-only Yahoo request-form diagnostic for frozen REIT holdout symbols.

No model, target return, admission, or holdout economics are computed. Compare multiple
request forms against the same provider for AVB/EQR, with ESS/DLR as long-history
controls, to determine whether prior 14/27-row truncation is endpoint/request pathology.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SYMBOLS=('AVB','EQR','ESS','DLR')
OUT=Path('reit_yahoo_request_form_diagnostic_20260905.json')
START=int(datetime(2014,1,1,tzinfo=timezone.utc).timestamp())
END=int(datetime(2026,9,3,tzinfo=timezone.utc).timestamp())
FORMS=(
    ('query1_period2014','query1.finance.yahoo.com',{'period1':START,'period2':END,'interval':'1d','events':'history','includeAdjustedClose':'true'}),
    ('query1_period0','query1.finance.yahoo.com',{'period1':0,'period2':END,'interval':'1d','events':'history','includeAdjustedClose':'true'}),
    ('query1_range_max','query1.finance.yahoo.com',{'range':'max','interval':'1d','events':'history','includeAdjustedClose':'true'}),
    ('query2_period2014','query2.finance.yahoo.com',{'period1':START,'period2':END,'interval':'1d','events':'history','includeAdjustedClose':'true'}),
    ('query2_range_max','query2.finance.yahoo.com',{'range':'max','interval':'1d','events':'history','includeAdjustedClose':'true'}),
)

def fetch(symbol,host,params):
    q=urlencode(params); req=Request(f'https://{host}/v8/finance/chart/{symbol}?{q}',headers={'User-Agent':'Mozilla/5.0 research-compute-public/1.0'})
    with urlopen(req,timeout=30) as r:p=json.loads(r.read().decode())
    x=(p.get('chart',{}).get('result') or [None])[0]
    if not x:return {'status':'NO_RESULT','error':p.get('chart',{}).get('error')}
    ts=x.get('timestamp') or []; ind=x.get('indicators',{}); qclose=((ind.get('quote') or [{}])[0].get('close') or []); adj=((ind.get('adjclose') or [{}])[0].get('adjclose') or [])
    def rows(values):
        out=[]
        for t,v in zip(ts,values):
            if v is not None:
                out.append(datetime.fromtimestamp(t,tz=timezone.utc).isoformat())
        return out
    qr=rows(qclose); ar=rows(adj)
    return {'status':'PASS','timestamp_count':len(ts),'quote_nonnull':len(qr),'adj_nonnull':len(ar),'quote_first':qr[0] if qr else None,'quote_last':qr[-1] if qr else None,'adj_first':ar[0] if ar else None,'adj_last':ar[-1] if ar else None}

def main():
    results={}
    for name,host,params in FORMS:
        results[name]={}
        for s in SYMBOLS:
            try:results[name][s]=fetch(s,host,params)
            except Exception as exc:results[name][s]={'status':'ERROR','error':f'{type(exc).__name__}: {exc}'}
    restored=[]
    for name in results:
        avb=results[name]['AVB']; eqr=results[name]['EQR']
        if avb.get('adj_nonnull',0)>=3000 and eqr.get('adj_nonnull',0)>=3000:restored.append(name)
    out={'schema':'public_compute.reit_yahoo_request_form_diagnostic.v1','generated_at':datetime.now(timezone.utc).isoformat(),'symbols':list(SYMBOLS),'forms':results,'forms_restoring_avb_eqr_long_history':restored,'target_returns_computed':False,'model_executed':False,'holdout_economics_computed':False,'research_only':True}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print('REIT_YAHOO_REQUEST_FORM_DIAGNOSTIC='+json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
