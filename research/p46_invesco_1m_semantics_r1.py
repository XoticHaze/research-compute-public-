import json,urllib.request
from pathlib import Path
U='https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/{t}/performance/rolling?idType=ticker&variationType=1M&productType=ETF'
def get(t):return json.loads(urllib.request.urlopen(urllib.request.Request(U.format(t=t),headers={'User-Agent':'Mozilla/5.0'}),timeout=45).read())
def walk(x,path='',out=None):
 out=[] if out is None else out
 if isinstance(x,dict):
  if any(k in x for k in ('date','effectiveDate','returnPercentage','value')):out.append({'path':path,'keys':sorted(x.keys()),'record':x})
  for k,v in x.items():walk(v,f'{path}/{k}',out)
 elif isinstance(x,list):
  for i,v in enumerate(x):walk(v,f'{path}/{i}',out)
 return out
def main():
 o={'schema':'research.p46_invesco_1m_semantics_r1','parent':'P46','assets':{}}
 for t in ('QQQ','DBC'):
  x=get(t);r=walk(x);dated=[a for a in r if isinstance(a['record'],dict) and ('date' in a['record'] or 'effectiveDate' in a['record'])];dates=sorted({str(a['record'].get('date') or a['record'].get('effectiveDate')) for a in dated});ret=[a for a in r if 'returnPercentage' in a['record']];o['assets'][t]={'top_level_keys':sorted(x.keys()) if isinstance(x,dict) else [],'candidate_records':len(r),'dated_records':len(dated),'return_percentage_records':len(ret),'unique_dates':len(dates),'first_date':dates[0] if dates else None,'last_date':dates[-1] if dates else None,'sample_return_records':ret[:10],'sample_dated_records':dated[:10]}
 o['decision']='INVESCO_1M_SEMANTICS_PROFILED';Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p46_invesco_1m_semantics_r1.json').write_text(json.dumps(o,indent=2,sort_keys=True));print(json.dumps({t:{k:v for k,v in a.items() if k not in ('sample_return_records','sample_dated_records')} for t,a in o['assets'].items()},sort_keys=True))
if __name__=='__main__':main()
