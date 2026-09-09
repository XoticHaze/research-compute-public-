import hashlib,json,urllib.request
from pathlib import Path
BASE='https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/{ticker}/performance/rolling?idType=ticker&variationType={variation}&productType=ETF'
V=('monthly','month','m1','1M','monthlyPerformance','rollingMonthly','y1')
def get(u):
 r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'application/json,*/*'});return urllib.request.urlopen(r,timeout=45).read()
def main():
 out={'schema':'research.p46_invesco_totalreturn_probe_r1','parent':'P46','purpose':'discover whether official Invesco rolling-performance API exposes a machine-readable monthly total-return history for QQQ/DBC','probes':{}}
 for t in ('QQQ','DBC'):
  out['probes'][t]={}
  for v in V:
   u=BASE.format(ticker=t,variation=v)
   try:
    b=get(u);txt=b.decode('utf-8','ignore');
    try:o=json.loads(txt)
    except Exception:o=None
    out['probes'][t][v]={'url':u,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'json_type':type(o).__name__ if o is not None else None,'preview':txt[:1200]}
   except Exception as e:out['probes'][t][v]={'url':u,'error':repr(e)}
 out['decision']='ROLLING_PERFORMANCE_API_PROFILED';Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p46_invesco_totalreturn_probe_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps({t:{v:{'bytes':x.get('bytes'),'error':x.get('error')} for v,x in d.items()} for t,d in out['probes'].items()},sort_keys=True))
if __name__=='__main__':main()
