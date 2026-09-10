from __future__ import annotations
import json,re
from io import StringIO
from pathlib import Path
import pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P479 research@example.invalid'; YEARS=list(range(2018,2025)); N=20
OUT=Path('research/artifacts/p479_pit_forward_price_coverage_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy(); z.columns=['ticker','cik']; z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False); z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64'); return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
rows=[]
for y in YEARS:
 rev,z=hist(f'{y}-06-30'); idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)]; s=z.iloc[idx].drop_duplicates('ticker'); tickers=s.ticker.tolist()
 raw=yf.download(tickers,start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=False)
 close=raw.get('Close',pd.DataFrame()) if not raw.empty else pd.DataFrame()
 if isinstance(close,pd.Series): close=close.to_frame(tickers[0])
 status=[]
 for t in tickers:
  q=close[t].dropna() if hasattr(close,'columns') and t in close.columns else pd.Series(dtype=float)
  status.append({'ticker':t,'observations':int(len(q)),'first_date':str(q.index.min().date()) if len(q) else None,'last_date':str(q.index.max().date()) if len(q) else None,'has_start_and_end':bool(len(q)>=2 and q.index.min()<=pd.Timestamp(f'{y}-07-15') and q.index.max()>=pd.Timestamp(f'{y+1}-06-15'))})
 ok=sum(x['has_start_and_end'] for x in status); rate=ok/len(tickers)
 rows.append({'year':y,'revision_id':int(rev['revid']),'sample_n':len(tickers),'endpoint_ready_n':ok,'endpoint_ready_rate':rate,'ready':rate>=.80,'symbols':status})
ready=all(x['ready'] for x in rows)
out={'schema':'research.p479_pit_forward_price_coverage_r1.v1','workload_id':'P479_PIT_FORWARD_PRICE_COVERAGE_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Coverage-only test of the frozen historical-symbol forward-price source. Confirm both beginning and end availability for each one-year window without computing returns or inspecting fundamental ranks.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'identical 20 evenly spaced historical S&P members after ticker sort','price_source':'Yahoo adjusted close via yfinance, same source family as P471','endpoint_coverage_min':.80,'returns_computed':False,'fundamental_ranks_inspected':False,'no_symbol_substitution':True},'cohorts':rows,'decision':'PIT_FORWARD_PRICE_COVERAGE_READY' if ready else 'PIT_FORWARD_PRICE_COVERAGE_NOT_READY','scientific_consequence':'Price-side coverage independently clears the frozen gate; combine only after feature-side coverage clears.' if ready else 'Price-side coverage is independently deficient; isolate missing historical-symbol identities before any economic rerun and do not drop names post hoc.','boundaries':{'performance_inspection':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'coverage':{str(x['year']):x['endpoint_ready_rate'] for x in rows},'missing':{str(x['year']):[z['ticker'] for z in x['symbols'] if not z['has_start_and_end']] for x in rows}},sort_keys=True))
