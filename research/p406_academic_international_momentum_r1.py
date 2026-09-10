from __future__ import annotations
import csv, io, json, re, urllib.request, zipfile
from pathlib import Path
import pandas as pd

URL='https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_ex_US_6_Portfolios_ME_Prior_12_2_CSV.zip'
raw=urllib.request.urlopen(URL,timeout=30).read()
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=z.namelist()
    if not names: raise SystemExit('SOURCE_FAILURE_EMPTY_ZIP')
    text=z.read(names[0]).decode('latin1')
lines=text.splitlines(); start=None
for i,line in enumerate(lines):
    if 'Average Value Weighted Returns -- Monthly' in line:
        start=i; break
if start is None: raise SystemExit('SOURCE_FAILURE_MONTHLY_SECTION_MISSING')
rows=[]; header=None
for line in lines[start+1:]:
    parts=[x.strip() for x in next(csv.reader([line]))]
    if header is None:
        if len(parts)>=7 and any('SMALL' in x.upper() for x in parts[1:]): header=parts
        continue
    if not parts or not re.fullmatch(r'\d{6}',parts[0]):
        if rows: break
        continue
    if len(parts)<7: continue
    try: vals=[float(x)/100.0 for x in parts[1:7]]
    except ValueError: continue
    rows.append([parts[0],*vals])
if len(rows)<350: raise SystemExit(f'SOURCE_FAILURE_SHORT_HISTORY:{len(rows)}')
df=pd.DataFrame(rows,columns=['yyyymm','small_low','small_neutral','small_high','big_low','big_neutral','big_high'])
df['date']=pd.to_datetime(df.yyyymm+'01',format='%Y%m%d')+pd.offsets.MonthEnd(0)
df=df.set_index('date').drop(columns='yyyymm').sort_index()
df['small_broad']=(df.small_low+df.small_neutral+df.small_high)/3.0

def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def stats(a,b=None):
    x=df.loc[a:b]
    return {'start':a,'end':b,'months':int(len(x)),'small_high_cagr':cagr(x.small_high),'small_broad_cagr':cagr(x.small_broad),'matched_excess_pp':100*(cagr(x.small_high)-cagr(x.small_broad)),'positive_month_fraction':float((x.small_high>x.small_broad).mean())}
windows={k:stats(v) for k,v in {'1991+':'1991-01-01','2005+':'2005-01-01','2015+':'2015-01-01'}.items()}
blocks=[]
for a,b in [('1991-01-01','2004-12-31'),('2005-01-01','2014-12-31'),('2015-01-01',None)]:
    z=stats(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); blocks.append(z)
pos=sum(z['positive_matched_excess'] for z in blocks)
passed=all(z['matched_excess_pp']>0 for z in windows.values()) and pos==3
out={'schema':'research.p406_academic_international_momentum.v1','workload_id':'P406_ACADEMIC_INTERNATIONAL_MOMENTUM_R1','parent':'INTERNATIONAL_MOMENTUM','source_authority':'Kenneth French Data Library, Developed ex US 6 Portfolios Formed on Size and Momentum, monthly value-weight returns','source_url':URL,'claim':'Developed-ex-US small-cap high-prior-return has a persistent source-level return advantage over an equal-weight broad-small proxy from the same 2x3 momentum sort. This adjudicates mechanism persistence only, not ETF implementation or after-cost fund alpha.','windows':windows,'blocks':blocks,'positive_blocks':pos,'decision_rule':'SOURCE_MECHANISM_SUPPORTED only if matched CAGR excess is positive in fixed 1991+/2005+/2015+ windows and all three non-overlapping chronology blocks. No source/window/control adjustment after observation.','decision':'SOURCE_MECHANISM_SUPPORTED' if passed else 'SOURCE_MECHANISM_NOT_SUPPORTED','scientific_consequence':('Academic developed-ex-US evidence supports a persistent international small-cap momentum mechanism. Preserve P391 ETF failure as implementation/representation evidence rather than broad mechanism falsification; a distinct investable representation would be needed before survivor status.' if passed else 'Academic developed-ex-US evidence also fails to support persistent international small-cap momentum. Together with P391 this establishes multiple independent weaknesses; close this exact family without parameter rescue.'),'limitations':['Academic portfolios do not establish ETF fees, turnover, capacity, liquidity, or implementation alpha.','This source-level test does not rescue P391 or authorize an ETF survivor.'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p406_academic_international_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_blocks':pos,'rows':len(df),'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))
