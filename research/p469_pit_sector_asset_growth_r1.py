from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P469R2 research@example.invalid'; YEARS=list(range(2018,2025)); N=100; COST=.0025; MIN_SECTOR_N=3; MIN_ELIGIBLE_SECTORS=6
SECTOR_ETF={'Communication Services':'XLC','Consumer Discretionary':'XLY','Consumer Staples':'XLP','Energy':'XLE','Financials':'XLF','Health Care':'XLV','Industrials':'XLI','Information Technology':'XLK','Materials':'XLB','Real Estate':'XLRE','Utilities':'XLU'}
OUT=Path('research/artifacts/p469_pit_sector_asset_growth_r2.json');OUT.parent.mkdir(parents=True,exist_ok=True)
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
 if not vals:return None
 by={}
 for e,f,a in vals:
  if e not in by or f>by[e][0]:by[e]=(f,a)
 o=sorted(by.items())
 if len(o)<2:return None
 e0,(f0,a0)=o[-2];e1,(f1,a1)=o[-1];d=(pd.Timestamp(e1)-pd.Timestamp(e0)).days
 if not(300<=d<=430) or a0<=0:return None
 return float(a1/a0-1)
def annual_return(t,start,end):
 raw=yf.download(t,start=start,end=end,auto_adjust=True,progress=False,threads=False)
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.DataFrame):c=c[t] if t in c.columns else c.iloc[:,0]
 s=c.dropna();return float(s.iloc[-1]/s.iloc[0]-1)-COST if len(s)>=2 else None
cache={};cohorts=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker')
 feats=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.035)
   x=ag(cache[cik],asof)
   if x is not None and row.sector in SECTOR_ETF:feats.append({'ticker':row.ticker,'sector':row.sector,'asset_growth':x})
  except Exception:pass
 feature_rate=len(feats)/len(s);sec={}
 for x in feats:sec.setdefault(x['sector'],[]).append(x)
 eligible={k:v for k,v in sec.items() if len(v)>=MIN_SECTOR_N and k in SECTOR_ETF};chosen=min(eligible,key=lambda k:np.median([x['asset_growth'] for x in eligible[k]])) if eligible else None
 start=f'{y}-07-01';end=f'{y+1}-07-10';returns={k:annual_return(SECTOR_ETF[k],start,end) for k in eligible};spy=annual_return('SPY',start,end)
 available={k:v for k,v in returns.items() if v is not None};candidate=available.get(chosen);basket=float(np.mean(list(available.values()))) if available else None
 ready=feature_rate>=.85 and len(eligible)>=MIN_ELIGIBLE_SECTORS and chosen in available and len(available)==len(eligible) and spy is not None
 cohorts.append({'year':y,'revision_id':int(rev['revid']),'sample_n':len(s),'feature_n':len(feats),'feature_rate':feature_rate,'eligible_sector_n':len(eligible),'eligible_sector_counts':{k:len(v) for k,v in eligible.items()},'chosen_sector':chosen,'chosen_etf':SECTOR_ETF.get(chosen),'chosen_median_asset_growth':float(np.median([x['asset_growth'] for x in eligible[chosen]])) if chosen else None,'ready':ready,'candidate_return':candidate if ready else None,'equal_sector_basket_return':basket if ready else None,'spy_return':spy if ready else None,'excess_vs_sector_basket':candidate-basket if ready else None,'excess_vs_spy':candidate-spy if ready else None})
valid=[x for x in cohorts if x['ready']];all_ready=len(valid)==len(YEARS);posbasket=sum(x['excess_vs_sector_basket']>0 for x in valid);posspy=sum(x['excess_vs_spy']>0 for x in valid)
if all_ready:
 cg=float(np.prod([1+x['candidate_return'] for x in valid])**(1/len(valid))-1);bg=float(np.prod([1+x['equal_sector_basket_return'] for x in valid])**(1/len(valid))-1);sg=float(np.prod([1+x['spy_return'] for x in valid])**(1/len(valid))-1)
else:cg=bg=sg=None
support=all_ready and posbasket>=5 and posspy>=5 and cg>bg and cg>sg
decision='PIT_SECTOR_ASSET_GROWTH_ALPHA_SUPPORTED' if support else ('PIT_SECTOR_ASSET_GROWTH_ALPHA_NOT_SUPPORTED' if all_ready else 'PIT_SECTOR_ASSET_GROWTH_DATA_NOT_READY')
out={'schema':'research.p469_pit_sector_asset_growth_r2.v1','workload_id':'P469_PIT_SECTOR_ASSET_GROWTH_R2','parent':'P07_INDUSTRY_OPPORTUNITY_ENGINE_SUPPORT','claim':'Causal sector-state repair after R1 return-consumer sparsity: derive historical GICS-sector median annual asset growth from deterministic historical S&P members and filed-at SEC 10-K Assets, but evaluate selected sector through stable sector ETFs. This preserves causal state while removing delisted-constituent price availability from the economic consumer.','r1_failure_class':'RETURN_CONSUMER_HISTORICAL_CONSTITUENT_PRICE_COVERAGE_NOT_READY','contract':{'years':YEARS,'sample_n':N,'sample_rule':'100 evenly spaced historical S&P members after ticker sort, used only to estimate causal sector state','feature':'two consecutive annual 10-K Assets values filed by June 30','sector_state':'median asset growth among sampled historical members','eligible_sector_min_names':MIN_SECTOR_N,'eligible_sector_min_count':MIN_ELIGIBLE_SECTORS,'selection':'lowest median asset-growth eligible historical GICS sector','return_consumer':'fixed SPDR sector ETF map','controls':['equal-weight eligible sector ETF basket','SPY'],'endpoint_cost_bps':25,'feature_coverage_min':.85,'all_years_required':True,'support':'candidate beats both controls after costs in >=5/7 years and compound CAGR exceeds both'},'cohorts':cohorts,'summary':{'ready_years':len(valid),'positive_vs_sector_basket_years':posbasket,'positive_vs_spy_years':posspy,'candidate_compound_cagr':cg,'sector_basket_compound_cagr':bg,'spy_compound_cagr':sg,'compound_excess_vs_sector_basket':cg-bg if all_ready else None,'compound_excess_vs_spy':cg-sg if all_ready else None},'decision':decision,'no_rescue':{'sector_count_gate_changed':False,'min_names_gate_changed':False,'return_threshold_changed':False,'date_changed':False,'signal_direction_changed':False},'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':out['summary'],'cohorts':[{k:x[k] for k in ['year','ready','chosen_sector','chosen_etf','excess_vs_sector_basket','excess_vs_spy']} for x in cohorts]},sort_keys=True))