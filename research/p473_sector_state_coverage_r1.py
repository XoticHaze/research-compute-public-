from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P473 research@example.invalid';YEARS=list(range(2018,2025));N=100;MIN_NAMES=3;MIN_SECTORS=6
OUT=Path('research/artifacts/p473_sector_state_coverage_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((low[k] for k in low if 'cik' in k),None);gk=next((low[k] for k in low if k in ('gicssector','sector')),None)
  if sk and ck and gk:
   z=t[[sk,ck,gk]].copy();z.columns=['ticker','cik','sector'];z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64');z['sector']=z.sector.astype(str).str.strip();return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def ag(facts,asof):
 vals=[]
 for v in facts.get('facts',{}).get('us-gaap',{}).get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:vals.append((v['end'],v['filed'],float(v['val'])))
 by={}
 for e,f,a in vals:
  if e not in by or f>by[e][0]:by[e]=(f,a)
 o=sorted(by.items())
 if len(o)<2:return None
 e0,(f0,a0)=o[-2];e1,(f1,a1)=o[-1];d=(pd.Timestamp(e1)-pd.Timestamp(e0)).days
 return float(a1/a0-1) if 300<=d<=430 and a0>0 else None
def price_available(tickers,start,end):
 if not tickers:return set()
 raw=yf.download(tickers,start=start,end=end,auto_adjust=True,progress=False,threads=False)
 if raw.empty:return set()
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.Series):c=c.to_frame(tickers[0])
 return {t for t in tickers if t in c.columns and len(c[t].dropna())>=2}
cache={};coh=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');feats=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.035)
   x=ag(cache[cik],asof)
   if x is not None:feats.append({'ticker':row.ticker,'sector':row.sector})
  except Exception:pass
 sec={}
 for x in feats:sec[x['sector']]=sec.get(x['sector'],0)+1
 elig={k:v for k,v in sec.items() if v>=MIN_NAMES};avail=price_available([x['ticker'] for x in feats],f'{y}-07-01',f'{y+1}-07-10');fr=len(feats)/len(s);pr=len(avail)/len(feats) if feats else 0;ready=fr>=.80 and len(elig)>=MIN_SECTORS and pr>=.80
 coh.append({'year':y,'revision_id':int(rev['revid']),'historical_member_count':len(z),'sample_n':len(s),'feature_count':len(feats),'feature_rate':fr,'sector_causal_name_counts':sec,'eligible_sector_count':len(elig),'eligible_sectors':elig,'forward_price_available_count':len(avail),'forward_price_availability_rate':pr,'ready':ready})
all_ready=all(x['ready'] for x in coh);decision='ALL_YEARS_READY' if all_ready else 'DATA_NOT_READY'
out={'schema':'research.p473_sector_state_coverage_r1.v1','workload_id':'P473_PIT_SECTOR_STATE_COVERAGE_R1','parent':'P07_INDUSTRY_OPPORTUNITY_ENGINE_SUPPORT','claim':'Data-only preperformance readiness probe. No candidate selection and no forward performance values are calculated or reported. Uses deterministic breadth-preserving 100-name historical S&P representation solely to test the original causal asset-growth, >=6 sectors, >=3 names/sector and >=80% forward-price availability gates.','contract':{'years':YEARS,'sample_n':N,'feature_coverage_min':.80,'eligible_sector_min_names':MIN_NAMES,'eligible_sector_min_count':MIN_SECTORS,'forward_price_availability_min':.80,'all_years_required':True,'forward_return_values_prohibited':True},'cohorts':coh,'ready_years':sum(x['ready'] for x in coh),'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'ready_years':out['ready_years'],'cohorts':[{k:x[k] for k in ['year','feature_rate','eligible_sector_count','forward_price_availability_rate','ready']} for x in coh]},sort_keys=True))