import json, urllib.request
from datetime import datetime, timezone
u='https://download.bls.gov/pub/time.series/cu/cu.data.1.AllItems'
req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 research-source-audit'})
with urllib.request.urlopen(req,timeout=45) as r: text=r.read().decode()
rows=[]
for line in text.splitlines()[1:]:
 p=line.split()
 if len(p)>=4 and p[0]=='CUSR0000SA0' and p[2].startswith('M') and p[2]!='M13':
  month=p[2][1:]; rows.append((f'{p[1]}-{month}-01',float(p[3])))
rows.sort(); post=[x for x in rows if x[0]>='2016-01-01']
out={'schema':'cpi_source_coverage_result.v1','generated_at':datetime.now(timezone.utc).isoformat(),'source':'BLS public time-series download','series':'CUSR0000SA0','row_count':len(rows),'post_2016_row_count':len(post),'first_date':rows[0][0] if rows else None,'last_date':rows[-1][0] if rows else None,'chronology_unique':len({d for d,_ in rows})==len(rows),'monthly_coverage_sufficient':len(post)>=120,'decision':'SOURCE_READY' if len(post)>=120 else 'SOURCE_NOT_READY','research_only':True}
open('fred-cpi-source-coverage-r1-result.json','w').write(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,indent=2,sort_keys=True))
