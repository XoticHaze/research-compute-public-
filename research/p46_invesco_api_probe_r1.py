from __future__ import annotations
import hashlib, json, re, urllib.request
from pathlib import Path

URLS={
 "QQQ_navs":"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF",
 "DBC_navs":"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/navs?idType=ticker&productType=ETF",
 "QQQ_perf":"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF",
 "DBC_perf":"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF",
}
DATE_RE=re.compile(r'20\d\d[-/]\d\d[-/]\d\d')

def probe(url):
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 CC-Market-Research/1.0","Accept":"application/json,text/plain,*/*"})
 with urllib.request.urlopen(req,timeout=45) as r:
  b=r.read(); txt=b.decode('utf-8','ignore')
  try: obj=json.loads(txt); keys=sorted(obj.keys()) if isinstance(obj,dict) else []
  except Exception: obj=None; keys=[]
  dates=sorted(set(DATE_RE.findall(txt)))
  return {"status":r.status,"content_type":r.headers.get('Content-Type'),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest(),"top_level_keys":keys[:50],"date_count":len(dates),"first_date":dates[0] if dates else None,"last_date":dates[-1] if dates else None,"preview":txt[:500]}

def main():
 out={"schema":"research.p46_invesco_api_probe_r1","parent":"P46","purpose":"adjudicate whether discovered issuer APIs provide usable QQQ/DBC NAV/performance history","probes":{}}
 for k,u in URLS.items():
  try: out['probes'][k]={"url":u,**probe(u)}
  except Exception as e: out['probes'][k]={"url":u,"error":repr(e)}
 usable={k:v for k,v in out['probes'].items() if v.get('status')==200 and v.get('bytes',0)>100}
 out['decision']='INVESCO_API_RESPONSES_OBSERVED' if usable else 'INVESCO_API_PROBE_FAILED'
 Path('artifacts').mkdir(exist_ok=True)
 Path('artifacts/p46_invesco_api_probe_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
 print(json.dumps(out,sort_keys=True))
 if not usable: raise SystemExit(2)
if __name__=='__main__': main()
