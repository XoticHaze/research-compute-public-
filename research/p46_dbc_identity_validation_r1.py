from __future__ import annotations
import json
from pathlib import Path
from datetime import date
from research import p46_invesco_semantic_adjudicator_r1 as base

CAL={2017:5.05,2020:-8.03,2021:41.34}
HELD={
 2018:{'dist':0.18853,'pay':'2018-12-31','target':-12.02},
 2019:{'dist':0.25383,'pay':'2019-12-31','target':12.16},
 2022:{'dist':0.14467,'pay':'2022-12-23','target':19.69},
 2023:{'dist':1.08926,'pay':'2023-12-22','target':-6.18},
 2024:{'dist':1.11582,'pay':'2024-12-27','target':2.00},
 2025:{'dist':0.74424,'pay':'2025-12-26','target':8.41},
}

def load():
 st,ct,b=base.fetch(base.API['DBC_navs'])
 assert st==200
 rows=json.loads(b.decode())
 out=[]
 for r in rows:
  try:
   d=date.fromisoformat(r['effectiveDate']); nav=float(r['netAssetValue'])
  except (KeyError,TypeError,ValueError):
   continue
  out.append((d,nav))
 # collapse duplicate dates deterministically to final issuer record
 return dict(out)

def last_on_or_before(nav,d):
 ds=[x for x in nav if x<=d]
 if not ds: raise KeyError(d)
 k=max(ds); return k,nav[k]

def annual_nav_return(nav,y):
 _,s=last_on_or_before(nav,date(y-1,12,31)); _,e=last_on_or_before(nav,date(y,12,31))
 return e/s-1

def annual_reinvested(nav,y,dist,pay):
 _,s=last_on_or_before(nav,date(y-1,12,31)); _,e=last_on_or_before(nav,date(y,12,31)); _,pn=last_on_or_before(nav,date.fromisoformat(pay))
 shares=1.0+dist/pn
 return shares*e/s-1

def main():
 nav=load(); cal={}
 for y,t in CAL.items():
  r=annual_nav_return(nav,y); cal[str(y)]={'issuer_nav_return_pct':100*r,'sec_nav_total_return_pct':t,'abs_error_pp':abs(100*r-t)}
 tol=max(v['abs_error_pp'] for v in cal.values())+1e-8
 held={}
 for y,x in HELD.items():
  r=annual_reinvested(nav,y,x['dist'],x['pay']); err=abs(100*r-x['target'])
  held[str(y)]={'distribution_per_share':x['dist'],'reinvestment_date':x['pay'],'reconstructed_nav_total_return_pct':100*r,'sec_nav_total_return_pct':x['target'],'abs_error_pp':err,'within_frozen_calibration_tolerance':err<=tol}
 decision='P46_DBC_IDENTITY_VALIDATED' if all(x['within_frozen_calibration_tolerance'] for x in held.values()) else 'P46_DBC_RECONSTRUCTION_NOT_YET_VALIDATED'
 out={'schema':'research.p46_dbc_identity_validation_r1','parent':'P46','contract':{'calibration_years':list(CAL),'heldout_distribution_years':list(HELD),'tolerance_rule':'max zero-distribution calibration error plus 1e-8 percentage-point numeric epsilon','no_model_parameter_or_cost_changes':True},'issuer_daily_rows':len(nav),'first_date':str(min(nav)),'last_date':str(max(nav)),'calibration':cal,'frozen_tolerance_pp':tol,'heldout':held,'decision':decision}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_dbc_identity_validation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
 print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
