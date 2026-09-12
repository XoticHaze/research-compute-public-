from __future__ import annotations
import bisect,json,statistics,time,urllib.request,xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

EXPERIMENT_ID='PIT_INSIDER_OPEN_MARKET_SALE_CONTROL_R1'
INHERITED_LEARNING=['PIT_QUARTERLY_EARNINGS_ACCELERATION_R1_REJECT_20260912']
TICKER_TO_SECTOR={'AAPL':'XLK','MSFT':'XLK','NVDA':'XLK','AMAT':'SMH','CAT':'XLI','DE':'XLI','JPM':'XLF','BAC':'XLF','XOM':'XLE','CVX':'XLE','JNJ':'XLV','PFE':'XLV','PG':'XLP','KO':'XLP','HD':'XLY','LOW':'XLY','NEE':'XLU','DUK':'XLU','AMZN':'XLY','META':'XLC'}
SPY='SPY'; HOLD=63; COST=.005
UA='XoticHaze market-research insider event study research@example.com'

def req(url):
 r=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json,text/xml,*/*'}); return urllib.request.urlopen(r,timeout=45).read()
def get_json(url): return json.loads(req(url))
def prices(symbol):
 x=get_json(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=946684800&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true')['chart']['result'][0]
 return [(date.fromtimestamp(ts).isoformat(),float(p)) for ts,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']) if p is not None]
def event_window(px,known):
 ds=[x[0] for x in px]; i=bisect.bisect_right(ds,known); j=i+HOLD
 return None if j>=len(px) else (px[i][0],px[i][1],px[j][0],px[j][1])
def ret(px,a,b):
 ds=[x[0] for x in px]; i=bisect.bisect_left(ds,a); j=bisect.bisect_left(ds,b)
 return None if i>=len(px) or j>=len(px) else px[j][1]/px[i][1]-1
def text(node,path):
 x=node.find(path); return None if x is None else x.text
def sales(cik):
 s=get_json(f'https://data.sec.gov/submissions/CIK{cik}.json')['filings']['recent']; out=[]
 for form,acc,filed,doc in zip(s['form'],s['accessionNumber'],s['filingDate'],s['primaryDocument']):
  if form!='4' or filed<'2010-01-01': continue
  try: root=ET.fromstring(req(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{doc}"))
  except Exception: continue
  for tr in root.findall('.//nonDerivativeTransaction'):
   if text(tr,'transactionCoding/transactionCode')!='S': continue
   if text(tr,'transactionAmounts/transactionAcquiredDisposedCode/value')!='D': continue
   try:
    shares=float(text(tr,'transactionAmounts/transactionShares/value')); price=float(text(tr,'transactionAmounts/transactionPricePerShare/value'))
   except (TypeError,ValueError): continue
   if shares<=0 or price<=0: continue
   out.append({'filed':filed,'transaction_date':text(tr,'transactionDate/value'),'shares':shares,'price':price,'value':shares*price})
  time.sleep(.03)
 return out
def mean(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None

def main():
 mp=get_json('https://www.sec.gov/files/company_tickers.json'); ciks={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()}
 syms=sorted(set(TICKER_TO_SECTOR)|set(TICKER_TO_SECTOR.values())|{SPY}); px={s:prices(s) for s in syms}
 events=[]
 for t,sector in TICKER_TO_SECTOR.items():
  for p in sales(ciks[t]):
   w=event_window(px[t],p['filed'])
   if not w: continue
   a,p0,b,p1=w; sr=ret(px[sector],a,b); br=ret(px[SPY],a,b)
   if sr is None or br is None: continue
   after=p1/p0-1-COST
   events.append({'ticker':t,'sector':sector,**p,'entry':a,'exit':b,'sector_excess':after-sr,'spy_excess':after-br})
 sec=[e['sector_excess'] for e in events]; spy=[e['spy_excess'] for e in events]
 years=[]
 for y in sorted({e['filed'][:4] for e in events}):
  xs=[e['sector_excess'] for e in events if e['filed'].startswith(y)]
  if len(xs)>=2: years.append({'year':int(y),'n':len(xs),'mean_sector_excess':mean(xs),'negative':mean(xs)<0})
 recent=[e['sector_excess'] for e in events if e['filed']>='2022-01-01']
 gates={'n_at_least_50':len(events)>=50,'mean_sector_negative':bool(sec and mean(sec)<0),'median_sector_negative':bool(sec and med(sec)<0),'mean_spy_negative':bool(spy and mean(spy)<0),'event_underperform_rate_55pct':bool(sec and mean([x<0 for x in sec])>=.55),'negative_year_share_60pct':bool(years and mean([x['negative'] for x in years])>=.60),'recent_negative':bool(recent and mean(recent)<0)}
 result={'events':len(events),'mean_after_cost_sector_excess':mean(sec),'median_after_cost_sector_excess':med(sec),'mean_after_cost_spy_excess':mean(spy),'negative_sector_excess_share':mean([x<0 for x in sec]) if sec else None,'negative_year_share':mean([x['negative'] for x in years]) if years else None,'recent_since_2022_sector_excess':mean(recent),'year_holdouts':years,'gates':gates,'decision':'SUPPORTS_DIRECTIONAL_SALES_SIGNAL' if all(gates.values()) else 'REJECT_DIRECTIONAL_SALES_SIGNAL'}
 out={'schema':'research.pit_insider_open_market_sale_control_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether insider transaction direction contains information or generic Form 4 activity/issuer selection could explain any purchase result.','claim_tested':'SEC Form 4 open-market sale code S known at filing time predicts negative 63-session after-cost stock excess versus matched-sector ETF and SPY.','frozen_specification':{'signal':'Form 4 non-derivative transactionCode=S and disposed=D with positive shares and price','information_time':'SEC Form 4 filing date; next trading session','holding_sessions':HOLD,'round_trip_cost':COST,'ticker_to_sector':TICKER_TO_SECTOR,'broad_market':SPY,'sources':['SEC submissions + Form 4 ownership XML','Yahoo adjusted daily history']},'result':result,'events_detail':events,'limitations':['Fixed current-ticker panel is a mechanism screen, not historical membership authority.','Form 4 issuer submissions recent arrays can omit older filings moved to oldfiles; this screen uses filings exposed in current SEC submissions recent history.','Failure forbids value threshold, role/title filter, horizon, cost, ticker, sector, or year rescue.','This is a signed-control sibling; final purchase-vs-sale interpretation requires consuming the purchase experiment separately.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True); Path('research/artifacts/pit_insider_open_market_sale_control_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
