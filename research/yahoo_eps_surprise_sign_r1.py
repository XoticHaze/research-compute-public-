from __future__ import annotations
import bisect,json,statistics,urllib.request
from datetime import date
from pathlib import Path
import yfinance as yf

EXPERIMENT_ID='YAHOO_EPS_SURPRISE_SIGN_R1'
INHERITED_LEARNING=['PIT_QUARTERLY_EARNINGS_ACCELERATION_R1_REJECT_20260912','SLP-20260912-PIT-EARNINGS-REACTION-CONTINUATION-R1']
TICKER_TO_SECTOR={'AAPL':'XLK','MSFT':'XLK','NVDA':'XLK','AMAT':'SMH','CAT':'XLI','DE':'XLI','JPM':'XLF','BAC':'XLF','XOM':'XLE','CVX':'XLE','JNJ':'XLV','PFE':'XLV','PG':'XLP','KO':'XLP','HD':'XLY','LOW':'XLY','NEE':'XLU','DUK':'XLU','AMZN':'XLY','META':'XLC'}
SPY='SPY'; HOLD=21; COST=.005

def get_json(url):
 r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}); return json.loads(urllib.request.urlopen(r,timeout=45).read())
def prices(symbol):
 x=get_json(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=946684800&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true')['chart']['result'][0]
 return [(date.fromtimestamp(ts).isoformat(),float(p)) for ts,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']) if p is not None]
def mean(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None
def fwd(px,known,hold=HOLD):
 ds=[x[0] for x in px]; i=bisect.bisect_right(ds,known); j=i+hold
 return None if i>=len(px) or j>=len(px) else (px[i][0],px[i][1],px[j][0],px[j][1])
def range_ret(px,a,b):
 ds=[x[0] for x in px]; i=bisect.bisect_left(ds,a); j=bisect.bisect_left(ds,b)
 return None if i>=len(px) or j>=len(px) else px[j][1]/px[i][1]-1

def earnings(ticker):
 df=yf.Ticker(ticker).get_earnings_dates(limit=60)
 if df is None or df.empty: return []
 out=[]
 for idx,row in df.iterrows():
  try: est=float(row['EPS Estimate']); rep=float(row['Reported EPS'])
  except Exception: continue
  if est!=est or rep!=rep: continue
  d=idx.date().isoformat() if hasattr(idx,'date') else str(idx)[:10]
  out.append({'event_date':d,'eps_estimate':est,'reported_eps':rep,'surprise_raw':rep-est,'positive_surprise':rep>est})
 return out

def main():
 syms=sorted(set(TICKER_TO_SECTOR)|set(TICKER_TO_SECTOR.values())|{SPY}); px={s:prices(s) for s in syms}
 pos=[]; nonpos=[]
 for t,sector in TICKER_TO_SECTOR.items():
  for e in earnings(t):
   w=fwd(px[t],e['event_date'])
   if not w: continue
   a,p0,b,p1=w; sr=range_ret(px[sector],a,b); br=range_ret(px[SPY],a,b)
   if sr is None or br is None: continue
   after=p1/p0-1-COST
   row={'ticker':t,'sector':sector,**e,'entry':a,'exit':b,'sector_excess':after-sr,'spy_excess':after-br}
   (pos if e['positive_surprise'] else nonpos).append(row)
 sec=[e['sector_excess'] for e in pos]; spy=[e['spy_excess'] for e in pos]; neg=[e['sector_excess'] for e in nonpos]
 years=[]
 for y in sorted({e['event_date'][:4] for e in pos}):
  xs=[e['sector_excess'] for e in pos if e['event_date'].startswith(y)]
  if len(xs)>=2: years.append({'year':int(y),'n':len(xs),'mean_sector_excess':mean(xs),'positive':mean(xs)>0})
 recent=[e['sector_excess'] for e in pos if e['event_date']>='2022-01-01']; contrast=None if not sec or not neg else mean(sec)-mean(neg)
 gates={'n_at_least_75':len(pos)>=75,'mean_sector_positive':bool(sec and mean(sec)>0),'median_sector_positive':bool(sec and med(sec)>0),'mean_spy_positive':bool(spy and mean(spy)>0),'event_hit_rate_55pct':bool(sec and mean([x>0 for x in sec])>=.55),'positive_year_share_60pct':bool(years and mean([x['positive'] for x in years])>=.60),'recent_positive':bool(recent and mean(recent)>0),'positive_surprise_beats_nonpositive':bool(contrast is not None and contrast>0)}
 result={'positive_surprise_events':len(pos),'nonpositive_surprise_events':len(nonpos),'mean_after_cost_sector_excess':mean(sec),'median_after_cost_sector_excess':med(sec),'mean_after_cost_spy_excess':mean(spy),'positive_sector_excess_share':mean([x>0 for x in sec]) if sec else None,'positive_year_share':mean([x['positive'] for x in years]) if years else None,'recent_since_2022_sector_excess':mean(recent),'positive_minus_nonpositive_sector_excess':contrast,'year_holdouts':years,'gates':gates,'decision':'SURVIVES_SCREEN_REQUIRES_SOURCE_PARITY_AND_DISJOINT_PIT_TEST' if all(gates.values()) else 'REJECT_NO_PARAMETER_RESCUE'}
 out={'schema':'research.yahoo_eps_surprise_sign_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether true reported-EPS versus historical consensus estimate sign contains forward information after realized-EPS acceleration and price-reaction proxies failed.','claim_tested':'Positive reported EPS minus historical analyst EPS estimate predicts positive next-21-session after-cost excess versus matched sector ETF and SPY.','frozen_specification':{'signal':'Reported EPS > EPS Estimate from Yahoo/yfinance historical earnings_dates','information_time':'earnings event calendar date; enter first trading session strictly after event date','holding_sessions':HOLD,'round_trip_cost':COST,'ticker_to_sector':TICKER_TO_SECTOR,'broad_market':SPY,'source_role':'public screening source only; survivor requires independent chronology/source parity validation'},'result':result,'positive_events':pos,'nonpositive_events':nonpos,'limitations':['Yahoo/yfinance historical estimate provenance is not canonical point-in-time authority; a survivor must pass independent source-parity validation before scientific promotion.','Fixed current-ticker panel is a mechanism screen, not historical membership authority.','Failure forbids surprise-magnitude threshold, horizon, cost, ticker, sector, or year rescue.','Pass only permits source-parity and disjoint point-in-time validation.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True); Path('research/artifacts/yahoo_eps_surprise_sign_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
