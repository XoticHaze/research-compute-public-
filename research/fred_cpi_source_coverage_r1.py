import csv, io, json, time, urllib.request
from datetime import datetime, timezone
u='https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL'
text=None; errors=[]
for attempt in range(3):
 try:
  req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=90) as r: text=r.read().decode()
  break
 except Exception as e:
  errors.append(type(e).__name__+': '+str(e))
  if attempt<2: time.sleep(2*(attempt+1))
if text is None: raise RuntimeError('FRED CPI fetch failed after retries: '+' | '.join(errors))
rows=[]
for row in csv.DictReader(io.StringIO(text)):
 try: rows.append((row['observation_date'],float(row['CPIAUCSL'])))
 except: pass
post=[x for x in rows if x[0]>='2016-01-01']
out={'schema':'fred_cpi_source_coverage_result.v1','generated_at':datetime.now(timezone.utc).isoformat(),'series':'CPIAUCSL','row_count':len(rows),'post_2016_row_count':len(post),'first_date':rows[0][0] if rows else None,'last_date':rows[-1][0] if rows else None,'chronology_unique':len({d for d,_ in rows})==len(rows),'monthly_coverage_sufficient':len(post)>=120,'fetch_attempts':len(errors)+1,'decision':'SOURCE_READY' if len(post)>=120 else 'SOURCE_NOT_READY','research_only':True}
open('fred-cpi-source-coverage-r1-result.json','w').write(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,indent=2,sort_keys=True))
