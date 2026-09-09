from __future__ import annotations
import hashlib, json, re, urllib.request
from pathlib import Path

API={
 'QQQ_rolling_1M':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/performance/rolling?idType=ticker&variationType=1M&productType=ETF',
 'DBC_rolling_1M':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/performance/rolling?idType=ticker&variationType=1M&productType=ETF',
 'QQQ_navs':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF',
 'DBC_navs':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/navs?idType=ticker&productType=ETF',
 'QQQ_standard':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF',
 'DBC_standard':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF',
}
PAGES={
 'QQQ':'https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=QQQ',
 'DBC':'https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=DBC',
}
TERMS=('return','distribution','dividend','reinvest','total','nav','market','growth','baseline','benchmark','performance','effective','inception','date','period')
DATE_RE=re.compile(r'(?:19|20)\d\d[-/]\d\d[-/]\d\d')

def fetch(url, accept='application/json,text/plain,*/*'):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':accept})
 with urllib.request.urlopen(req,timeout=45) as r:
  b=r.read(); return r.status, r.headers.get('Content-Type'), b

def walk(x,path='',scalars=None,lists=None):
 scalars=[] if scalars is None else scalars; lists=[] if lists is None else lists
 if isinstance(x,dict):
  for k,v in x.items():
   p=f'{path}/{k}'
   if isinstance(v,(str,int,float,bool)) or v is None:
    if any(t in k.lower() or (isinstance(v,str) and t in v.lower()) for t in TERMS): scalars.append({'path':p,'value':v})
   else: walk(v,p,scalars,lists)
 elif isinstance(x,list):
  lists.append({'path':path,'length':len(x),'sample_type':type(x[0]).__name__ if x else None,'sample_keys':sorted(x[0].keys()) if x and isinstance(x[0],dict) else None})
  for i,v in enumerate(x[:1000]): walk(v,f'{path}/{i}',scalars,lists)
 return scalars,lists

def profile_api(name,url):
 status,ctype,b=fetch(url); txt=b.decode('utf-8','ignore'); obj=json.loads(txt)
 scalars,lists=walk(obj)
 dates=sorted(set(DATE_RE.findall(txt)))
 return {'url':url,'status':status,'content_type':ctype,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),
         'top_level_keys':sorted(obj.keys()) if isinstance(obj,dict) else [],'date_count':len(dates),'first_date':dates[0] if dates else None,'last_date':dates[-1] if dates else None,
         'semantic_scalars':scalars[:400],'list_profiles':sorted(lists,key=lambda z:z['length'],reverse=True)[:100]}

def profile_page(t,url):
 status,ctype,b=fetch(url,'text/html,*/*'); txt=b.decode('utf-8','ignore'); low=re.sub(r'\s+',' ',txt).lower()
 phrases={p:(p in low) for p in ('total return','dividends reinvested','reinvested dividends','distribution','growth of $10,000','growth of 10,000')}
 snippets={}
 for p,hit in phrases.items():
  if hit:
   i=low.find(p); snippets[p]=re.sub(r'\s+',' ',txt[max(0,i-220):i+len(p)+260])
 return {'ticker':t,'url':url,'status':status,'content_type':ctype,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'phrase_hits':phrases,'snippets':snippets}

def main():
 out={'schema':'research.p46_invesco_semantic_adjudicator_r1','parent':'P46','purpose':'adjudicate explicit issuer semantics and locate distinct DBC historical route without assuming 1M means monthly total return','api':{},'pages':{}}
 for k,u in API.items():
  try: out['api'][k]=profile_api(k,u)
  except Exception as e: out['api'][k]={'url':u,'error':repr(e)}
 for t,u in PAGES.items():
  try: out['pages'][t]=profile_page(t,u)
  except Exception as e: out['pages'][t]={'url':u,'error':repr(e)}
 q=out['api'].get('QQQ_rolling_1M',{}); d=out['api'].get('DBC_rolling_1M',{})
 q_lists=max([x.get('length',0) for x in q.get('list_profiles',[])],default=0); d_lists=max([x.get('length',0) for x in d.get('list_profiles',[])],default=0)
 out['adjudication']={'qqq_max_series_length':q_lists,'dbc_max_series_length':d_lists,
  'shared_endpoint_semantics_uniform': q_lists==d_lists and q_lists>1,
  'issuer_phrase_evidence':{t:v.get('phrase_hits',{}) for t,v in out['pages'].items()},
  'decision':'REQUIRE_FIELD_LEVEL_ADMISSION_NO_GENERIC_1M_EQUIVALENCE'}
 Path('artifacts').mkdir(exist_ok=True)
 Path('artifacts/p46_invesco_semantic_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
 print(json.dumps(out['adjudication'],sort_keys=True))
 print(json.dumps({k:{'status':v.get('status'),'bytes':v.get('bytes'),'date_count':v.get('date_count'),'first_date':v.get('first_date'),'last_date':v.get('last_date'),'largest_lists':v.get('list_profiles',[])[:3]} for k,v in out['api'].items()},sort_keys=True))
if __name__=='__main__': main()
