from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import pandas as pd,requests
UA='CommandCenter MarketResearch P495 research@example.invalid'; YEARS=list(range(2018,2025)); N=40
OUT=Path('research/artifacts/p495_pit_feature_coverage_decomposition_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(y):
 target=f'{y}-06-30'; p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}; j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]; h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy(); z.columns=['ticker','cik']; z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False); z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64'); return int(rev['revid']),z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_TABLE')
def facts(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=30).read().decode()).get('facts',{}).get('us-gaap',{})
def inst(g,tag,asof):
 vals=[]
 for v in g.get(tag,{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None: vals.append((v['end'],v['filed'],float(v['val'])))
 d={}
 for x in vals:
  if x[0] not in d or x[1]>d[x[0]][1]: d[x[0]]=x
 return [d[k] for k in sorted(d)]
def annual(g,tag,asof):
 vals=[]
 for unit,arr in g.get(tag,{}).get('units',{}).items():
  if unit!='USD':continue
  for v in arr:
   if v.get('form')!='10-K' or not v.get('start') or not v.get('end') or not v.get('filed') or v['filed']>asof or v['end']>asof or v.get('val') is None:continue
   try:days=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
   except Exception:continue
   if 250<=days<=450: vals.append((v['end'],v['filed'],float(v['val'])))
 d={}
 for x in vals:
  if x[0] not in d or x[1]>d[x[0]][1]:d[x[0]]=x
 return [d[k] for k in sorted(d)]
def has_del(g,asof):
 a=inst(g,'Assets',asof);l=inst(g,'Liabilities',asof); common=sorted(set(x[0] for x in a)&set(x[0] for x in l)); return len(common)>=2
def has_margin(g,asof):
 o=annual(g,'OperatingIncomeLoss',asof);rv=annual(g,'Revenues',asof) or annual(g,'SalesRevenueNet',asof); common=sorted(set(x[0] for x in o)&set(x[0] for x in rv)); return len(common)>=2
cache={};rows=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(y);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker'); dc=mc=0; missd=[];missm=[]
 for _,r in s.iterrows():
  try:
   cik=int(r.cik)
   if cik not in cache:cache[cik]=facts(cik);time.sleep(.04)
   d=has_del(cache[cik],asof);m=has_margin(cache[cik],asof)
  except Exception:d=m=False
  if d:dc+=1
  else:missd.append(r.ticker)
  if m:mc+=1
  else:missm.append(r.ticker)
 rows.append({'year':y,'revision_id':rev,'sample_n':len(s),'deleveraging_feature_n':dc,'deleveraging_feature_coverage':dc/len(s),'margin_feature_n':mc,'margin_feature_coverage':mc/len(s),'missing_deleveraging':missd,'missing_margin':missm})
out={'schema':'research.p495_pit_feature_coverage_decomposition_r1.v1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Measure filed-at SEC feature availability alone for the exact P492 deleveraging and P493 operating-margin definitions on the unchanged historical samples; no prices, returns, or ranks.','rows':rows,'decision':'PIT_FEATURE_COVERAGE_DECOMPOSED','scientific_consequence':'Use exact feature-only coverage to distinguish SEC taxonomy/representation debt from already-cleared forward-price coverage before further causal PIT alpha execution.','boundaries':{'alpha_inference':False,'feature_change':False,'membership_change':False,'coverage_gate_relaxation':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':out['decision'],'rows':[{k:v for k,v in x.items() if not k.startswith('missing_')} for x in rows]},sort_keys=True))