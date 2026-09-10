from __future__ import annotations
import csv, io, json, re, urllib.request, zipfile
from pathlib import Path
import numpy as np, pandas as pd

URL='https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/6_Portfolios_ME_Prior_12_2_CSV.zip'
raw=urllib.request.urlopen(URL, timeout=30).read()
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=z.namelist()
    if not names: raise SystemExit('SOURCE_FAILURE_EMPTY_ZIP')
    text=z.read(names[0]).decode('latin1')
lines=text.splitlines()
start=None
for i,line in enumerate(lines):
    if 'Average Value Weighted Returns -- Monthly' in line:
        start=i
        break
if start is None: raise SystemExit('SOURCE_FAILURE_MONTHLY_SECTION_MISSING')
rows=[]; header=None
for line in lines[start+1:]:
    if header is None:
        if 'SMALL' in line.upper() and 'PRIOR' in line.upper():
            header=[x.strip() for x in next(csv.reader([line]))]
        continue
    parts=[x.strip() for x in next(csv.reader([line]))]
    if not parts or not re.fullmatch(r'\d{6}', parts[0]):
        if rows: break
        continue
    if len(parts)<7: continue
    try: vals=[float(x)/100.0 for x in parts[1:7]]
    except ValueError: continue
    rows.append([parts[0],*vals])
if len(rows)<900: raise SystemExit(f'SOURCE_FAILURE_SHORT_MONTHLY_HISTORY:{len(rows)}')
df=pd.DataFrame(rows,columns=['yyyymm','small_low','small_neutral','small_high','big_low','big_neutral','big_high'])
df['date']=pd.to_datetime(df.yyyymm+'01',format='%Y%m%d')+pd.offsets.MonthEnd(0)
df=df.set_index('date').drop(columns='yyyymm').sort_index()
# Small-high is the academic small-cap winner sleeve. The matched control is the
# equal-weight average of all three small-cap momentum buckets from the same sort.
df['small_broad']=(df.small_low+df.small_neutral+df.small_high)/3.0
df['excess']=df.small_high-df.small_broad

def cagr(s):
    return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def stats(a,b=None):
    x=df.loc[a:b]
    return {'start':a,'end':b,'months':int(len(x)),'small_high_cagr':cagr(x.small_high),'small_broad_cagr':cagr(x.small_broad),'matched_excess_pp':100*(cagr(x.small_high)-cagr(x.small_broad)),'mean_monthly_excess_pp':100*float(x.excess.mean()),'positive_excess_month_fraction':float((x.excess>0).mean())}
windows={k:stats(v) for k,v in {'1963+':'1963-01-01','1990+':'1990-01-01','2010+':'2010-01-01'}.items()}
blocks=[]
for a,b in [('1963-01-01','1989-12-31'),('1990-01-01','2009-12-31'),('2010-01-01',None)]:
    z=stats(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); blocks.append(z)
positive_blocks=sum(x['positive_matched_excess'] for x in blocks)
pass_gate=all(x['matched_excess_pp']>0 for x in windows.values()) and positive_blocks==3
out={'schema':'research.p399_academic_smallcap_momentum.v1','workload_id':'P399_ACADEMIC_SMALLCAP_MOMENTUM_R1','parent':'US_SMALL_CAP_MOMENTUM_TRANSPORT','source_url':URL,'source_authority':'Kenneth French Data Library, 6 Portfolios Formed on Size and Momentum (2x3), monthly value-weight returns','claim':'The small-cap high-prior-return portfolio has persistent return advantage over an equal-weight broad-small proxy formed from the same academic 2x3 sort. This is source-level mechanism evidence only and does not infer fund implementability or after-cost alpha.','windows':windows,'blocks':blocks,'positive_blocks':positive_blocks,'decision_rule':'SOURCE_MECHANISM_SUPPORTED only if matched CAGR excess is positive in fixed 1963+/1990+/2010+ windows and each non-overlapping 1963-1989/1990-2009/2010+ block is positive. No source/window/control adjustment after observation.','decision':'SOURCE_MECHANISM_SUPPORTED' if pass_gate else 'SOURCE_MECHANISM_NOT_SUPPORTED','scientific_consequence':('Academic source-level evidence independently supports persistence of the small-cap momentum mechanism. Preserve P395 ETF evidence while keeping fund implementability and after-cost claims separate.' if pass_gate else 'Academic source-level evidence does not independently support persistent small-cap momentum. Preserve P395 passing ETF evidence but narrow confidence; do not parameter-rescue or infer broad mechanism robustness.'),'limitations':['Academic portfolio returns do not provide implementable fund turnover/cost evidence for P395.','The matched broad-small proxy is the equal-weight average of the three small-cap momentum buckets from the same 2x3 sort.'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p399_academic_smallcap_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_blocks':positive_blocks,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()},'rows':len(df)},sort_keys=True))
