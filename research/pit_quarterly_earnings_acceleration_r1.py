from __future__ import annotations
import bisect, json, statistics, time, urllib.request
from datetime import date
from pathlib import Path

EXPERIMENT_ID='PIT_QUARTERLY_EARNINGS_ACCELERATION_R1'
INHERITED_LEARNING=['PIT_SIMPLE_10K_SCALAR_FAMILY_PARK_20260912']
TICKER_TO_SECTOR={'AAPL':'XLK','MSFT':'XLK','NVDA':'XLK','AMAT':'SMH','CAT':'XLI','JPM':'XLF','XOM':'XLE','JNJ':'XLV','PG':'XLP','HD':'XLY'}
SPY='SPY'; HOLD=63; COST=.005
UA='XoticHaze market-research PIT quarterly event study contact@example.com'

def get_json(url):
 r=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(r,timeout=45).read())

def prices(symbol):
 url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=946684800&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true'
 x=get_json(url)['chart']['result'][0]; out=[]
 for ts,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']):
  if p is not None: out.append((date.fromtimestamp(ts).isoformat(),float(p)))
 return out

def quarterly_eps(cik):
 d=get_json(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'); us=d.get('facts',{}).get('us-gaap',{})
 vals=[]
 for concept in ('EarningsPerShareDiluted','EarningsPerShareBasicAndDiluted'):
  vals += us.get(concept,{}).get('units',{}).get('USD/shares',[])
 rows=[]
 for v in vals:
  if v.get('form') not in ('10-Q','10-K') or not all(v.get(k) for k in ('filed','end','fy','fp','val','accn')): continue
  if v.get('fp') not in ('Q1','Q2','Q3','FY'): continue
  if v.get('start'):
   try: days=(date.fromisoformat(v['end'])-date.fromisoformat(v['start'])).days
   except: continue
   if not 60<=days<=120: continue
  rows.append({'filed':v['filed'],'end':v['end'],'fy':int(v['fy']),'fp':v['fp'],'eps':float(v['val']),'accn':v['accn']})
 # first accession per fiscal quarter, no amendment rewrite
 q={}
 for r in sorted(rows,key=lambda z:(z['fy'],z['fp'],z['filed'],z['accn'])): q.setdefault((r['fy'],r['fp']),r)
 return sorted(q.values(),key=lambda z:z['filed'])

def ret(px,a,b):
 ds=[x[0] for x in px]; i=bisect.bisect_left(ds,a); j=bisect.bisect_left(ds,b)
 return None if i>=len(px) or j>=len(px) else px[j][1]/px[i][1]-1

def event_window(px,filed):
 ds=[x[0] for x in px]; i=bisect.bisect_right(ds,filed); j=i+HOLD
 return None if j>=len(px) else (px[i][0],px[i][1],px[j][0],px[j][1])

def mean(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None

def main():
 mp=get_json('https://www.sec.gov/files/company_tickers.json'); ciks={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()}
 syms=sorted(set(TICKER_TO_SECTOR)|set(TICKER_TO_SECTOR.values())|{SPY}); px={s:prices(s) for s in syms}
 events=[]
 for t,sec in TICKER_TO_SECTOR.items():
  qs=quarterly_eps(ciks[t]); by={(r['fy'],r['fp']):r for r in qs}
  for r in qs:
   prev=by.get((r['fy']-1,r['fp'])); prev2=by.get((r['fy']-2,r['fp']))
   if not prev or not prev2: continue
   growth=r['eps']-prev['eps']; prior_growth=prev['eps']-prev2['eps']; accel=growth-prior_growth
   w=event_window(px[t],r['filed'])
   if not w: continue
   a,p0,b,p1=w; sr=ret(px[sec],a,b); br=ret(px[SPY],a,b)
   if sr is None or br is None: continue
   after=p1/p0-1-COST
   events.append({'ticker':t,'sector':sec,'filed':r['filed'],'fy':r['fy'],'fp':r['fp'],'eps':r['eps'],'yoy_eps_change':growth,'prior_yoy_eps_change':prior_growth,'acceleration':accel,'sector_excess':after-sr,'spy_excess':after-br})
  time.sleep(.12)
 pos=[e for e in events if e['acceleration']>0]; neg=[e for e in events if e['acceleration']<=0]
 sec=[e['sector_excess'] for e in pos]; spy=[e['spy_excess'] for e in pos]; other=[e['sector_excess'] for e in neg]
 years=[]
 for y in sorted({e['filed'][:4] for e in pos}):
  xs=[e['sector_excess'] for e in pos if e['filed'].startswith(y)]
  if len(xs)>=2: years.append({'year':int(y),'n':len(xs),'mean_sector_excess':mean(xs),'positive':mean(xs)>0})
 recent=[e['sector_excess'] for e in pos if e['filed']>='2022-01-01']; spread=mean(sec)-mean(other) if sec and other else None
 gates={'n_at_least_50':len(pos)>=50,'mean_sector_positive':bool(sec and mean(sec)>0),'median_sector_positive':bool(sec and med(sec)>0),'mean_spy_positive':bool(spy and mean(spy)>0),'event_hit_rate_55pct':bool(sec and mean([x>0 for x in sec])>=.55),'positive_year_share_60pct':bool(years and mean([x['positive'] for x in years])>=.60),'recent_positive':bool(recent and mean(recent)>0),'acceleration_beats_deceleration':bool(spread is not None and spread>0)}
 result={'positive_acceleration_events':len(pos),'nonpositive_events':len(neg),'mean_after_cost_sector_excess':mean(sec),'median_after_cost_sector_excess':med(sec),'mean_after_cost_spy_excess':mean(spy),'positive_sector_excess_share':mean([x>0 for x in sec]) if sec else None,'positive_year_share':mean([x['positive'] for x in years]) if years else None,'recent_since_2022_sector_excess':mean(recent),'acceleration_minus_other_sector_excess':spread,'year_holdouts':years,'gates':gates,'decision':'ADMIT_FOR_DISJOINT_PIT_UNIVERSE_TEST' if all(gates.values()) else 'REJECT_NO_PARAMETER_RESCUE'}
 out={'schema':'research.pit_quarterly_earnings_acceleration_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether higher-frequency quarterly earnings acceleration known at filing time contains excess information absent from annual 10-K scalar tests.','claim_tested':'Positive acceleration in year-over-year quarterly diluted EPS predicts positive 63-session after-cost stock excess versus matched-sector ETF and SPY.','frozen_specification':{'signal':'(EPS_t-EPS_t-4)-(EPS_t-4-EPS_t-8)>0','information_time':'SEC filing date; next trading session','holding_sessions':HOLD,'round_trip_cost':COST,'ticker_to_sector':TICKER_TO_SECTOR,'broad_market':SPY,'sources':['SEC companyfacts','Yahoo adjusted daily history']},'result':result,'events':events,'limitations':['Fixed current-ticker panel is a mechanism screen, not historical membership authority.','Failure forbids threshold, horizon, cost, ticker, sector, or EPS-concept rescue.','Pass only admits a disjoint point-in-time universe child.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True); Path('research/artifacts/pit_quarterly_earnings_acceleration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
