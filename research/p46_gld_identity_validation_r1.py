from __future__ import annotations
import io,json,urllib.request
from pathlib import Path
import openpyxl,pandas as pd

URL='https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld'
TARGET_2020=23.68
TOLERANCE_PP=0.10

def fetch():
 req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0'})
 with urllib.request.urlopen(req,timeout=60) as r:return r.read()

def load_nav(b):
 w=openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=True)['US GLD Historical Archive']
 rows=[list(r) for r in w.iter_rows(values_only=True)]; h=list(rows[0]); di=h.index('Date'); ni=h.index('NAV/Share at 10:30am NYT')
 x=pd.DataFrame({'d':[r[di] for r in rows[1:]],'n':[r[ni] for r in rows[1:]]})
 x['d']=pd.to_datetime(x.d,errors='coerce');x['n']=pd.to_numeric(x.n,errors='coerce');x=x.dropna().drop_duplicates('d').sort_values('d')
 return dict(zip(x.d.dt.date,x.n.astype(float)))

def last_on_or_before(nav,d):
 k=max(x for x in nav if x<=d);return k,nav[k]

def main():
 from datetime import date
 b=fetch(); nav=load_nav(b); sd,s=last_on_or_before(nav,date(2019,12,31)); ed,e=last_on_or_before(nav,date(2020,12,31)); ret=100*(e/s-1); err=abs(ret-TARGET_2020)
 decision='P46_GLD_NAV_IDENTITY_VALIDATED' if err<=TOLERANCE_PP else 'P46_GLD_NAV_IDENTITY_NOT_VALIDATED'
 out={'schema':'research.p46_gld_identity_validation_r1','parent':'P46','contract':{'checkpoint':'calendar_2020','sec_filed_nav_total_return_pct':TARGET_2020,'predeclared_tolerance_pp':TOLERANCE_PP,'no_model_parameter_or_cost_changes':True},'issuer_rows':len(nav),'first_date':str(min(nav)),'last_date':str(max(nav)),'start_date_used':str(sd),'end_date_used':str(ed),'start_nav':s,'end_nav':e,'issuer_nav_compounded_return_pct':ret,'abs_error_pp':err,'decision':decision}
 Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p46_gld_identity_validation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
