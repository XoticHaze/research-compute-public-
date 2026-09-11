from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P499 research@example.invalid'; Y=2021; N=20
OUT=Path('research/artifacts/p499_pit_roe_2021_coverage_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def hist():
 target=f'{Y}-06-30';p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'};j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0];h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy();z.columns=['ticker','cik'];z.ticker=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);z.cik=pd.to_numeric(z.cik,errors='coerce').astype('Int64');return int(rev['revid']),z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_TABLE')
def facts(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=30).read().decode()).get('facts',{}).get('us-gaap',{})
def has_roe(g,asof):
 nis=[]
 for tag in ['NetIncomeLoss','ProfitLoss']:
  for v in g.get(tag,{}).get('units',{}).get('USD',[]):
   if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:
    try:d=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
    except:continue
    if 300<=d<=430:nis.append((v['filed'],v['end']))
 if not nis:return False
 _,end=max(nis);eq=[]
 for tag in ['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']:
  for v in g.get(tag,{}).get('units',{}).get('USD',[]):
   if v.get('form')=='10-K' and not v.get('start') and v.get('end')==end and v.get('filed') and v['filed']<=asof and v.get('val') is not None and float(v['val'])>0:eq.append(v)
 return bool(eq)
def endpoint_ok(t):
 try:
  x=yf.download(t,start='2021-07-01',end='2022-07-10',auto_adjust=True,progress=False,threads=False)
  if x.empty:return False
  c=x['Close'];s=c.iloc[:,0] if isinstance(c,pd.DataFrame) else c
  return len(s.dropna())>=2
 except Exception:return False
rev,z=hist();idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');rows=[]
for _,r in s.iterrows():
 try:g=facts(int(r.cik));time.sleep(.05);hf=has_roe(g,'2021-06-30')
 except Exception:hf=False
 po=endpoint_ok(r.ticker)
 rows.append({'ticker':r.ticker,'cik':str(int(r.cik)),'roe_feature_ready':hf,'forward_endpoint_ready':po})
feature=[x for x in rows if x['roe_feature_ready']];usable=[x for x in feature if x['forward_endpoint_ready']];price_all=[x for x in rows if x['forward_endpoint_ready']]
out={'schema':'research.p499_pit_roe_2021_coverage_r1.v1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','workload_id':'P499_PIT_ROE_2021_COVERAGE_R1','claim':'Source-only decomposition of the exact 2021 P496 sample. Identify ROE-feature-ready members and forward-endpoint availability without computing returns, ranks, selected portfolios, or alpha.','revision_id':rev,'sample_n':len(rows),'feature_ready_n':len(feature),'feature_coverage':len(feature)/len(rows),'all_sample_price_ready_n':len(price_all),'all_sample_price_coverage':len(price_all)/len(rows),'feature_and_price_ready_n':len(usable),'intersection_coverage':len(usable)/len(rows),'feature_ready_but_price_missing':[x['ticker'] for x in feature if not x['forward_endpoint_ready']],'price_missing_all':[x['ticker'] for x in rows if not x['forward_endpoint_ready']],'decision':'PIT_ROE_2021_COVERAGE_DECOMPOSED','scientific_consequence':'Use this source-only identity to decide whether P496 is blocked by a narrow historical-symbol price seam or by broader causal-feature readiness. Do not use this diagnostic to relax the 80% gate or infer alpha.','boundaries':{'returns_computed':False,'ranks_computed':False,'alpha_inference':False,'coverage_gate_relaxation':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps({k:out[k] for k in ['decision','sample_n','feature_ready_n','feature_coverage','all_sample_price_ready_n','all_sample_price_coverage','feature_and_price_ready_n','intersection_coverage','feature_ready_but_price_missing','price_missing_all']},sort_keys=True))
