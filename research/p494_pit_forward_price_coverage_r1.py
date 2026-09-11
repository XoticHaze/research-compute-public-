import json,re
from io import StringIO
from pathlib import Path
import pandas as pd,requests,yfinance as yf
YEARS=list(range(2018,2025));N=40;UA={'User-Agent':'CommandCenter-MarketResearch-P494/1.0'}
OUT=Path('research/artifacts/p494_pit_forward_price_coverage_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(y):
 target=f'{y}-06-30';p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'};j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0];h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None)
  if sk:
   z=t[[sk]].copy();z.columns=['ticker'];z.ticker=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);return int(rev['revid']),z.sort_values('ticker')
 raise RuntimeError('NO_TABLE')
def ok(t,y):
 try:
  q=yf.download(t,start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=False)['Close'].dropna()
  if hasattr(q,'columns'):q=q.iloc[:,0]
  a=q[q.index<=pd.Timestamp(f'{y}-07-15')];b=q[q.index>=pd.Timestamp(f'{y+1}-06-15')]
  return len(a)>0 and len(b)>0
 except Exception:return False
rows=[]
for y in YEARS:
 rev,z=hist(y);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');bad=[]
 for t in s.ticker:
  if not ok(t,y):bad.append(t)
 rows.append({'year':y,'revision_id':rev,'sample_n':len(s),'price_ready_n':len(s)-len(bad),'price_coverage':(len(s)-len(bad))/len(s),'missing_tickers':bad})
all_ready=all(x['price_coverage']>=.80 for x in rows)
out={'schema':'research.p494_pit_forward_price_coverage_r1.v1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Decompose the P492/P493 common-coverage blocker by measuring forward-price availability alone on the exact 40-member historical sampling rule.','rows':rows,'decision':'FORWARD_PRICE_COVERAGE_SUFFICIENT' if all_ready else 'FORWARD_PRICE_COVERAGE_INSUFFICIENT','scientific_consequence':'If price coverage is sufficient, residual common-coverage deficit is primarily SEC feature representation; otherwise repair historical price identity/lineage before scoring PIT alpha.','boundaries':{'alpha_inference':False,'membership_change':False,'coverage_gate_relaxation':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out))