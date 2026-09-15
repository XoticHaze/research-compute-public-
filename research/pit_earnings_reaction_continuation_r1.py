from __future__ import annotations
import bisect,json,statistics,urllib.request
from datetime import date
from pathlib import Path

EXPERIMENT_ID='PIT_EARNINGS_REACTION_CONTINUATION_R1'
INHERITED_LEARNING=['PIT_QUARTERLY_EARNINGS_ACCELERATION_R1_REJECT_20260912']
TICKER_TO_SECTOR={'AAPL':'XLK','MSFT':'XLK','NVDA':'XLK','AMAT':'SMH','CAT':'XLI','DE':'XLI','JPM':'XLF','BAC':'XLF','XOM':'XLE','CVX':'XLE','JNJ':'XLV','PFE':'XLV','PG':'XLP','KO':'XLP','HD':'XLY','LOW':'XLY','NEE':'XLU','DUK':'XLU','AMZN':'XLY','META':'XLC'}
SPY='SPY'; HOLD=21; COST=.005
UA='XoticHaze market-research earnings reaction study research@example.com'

def req(url):
 r=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json,*/*'}); return urllib.request.urlopen(r,timeout=45).read()
def get_json(url): return json.loads(req(url))
def prices(symbol):
 x=get_json(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=946684800&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true')['chart']['result'][0]
 return [(date.fromtimestamp(ts).isoformat(),float(p)) for ts,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']) if p is not None]
def idx_after(px,d): return bisect.bisect_right([x[0] for x in px],d)
def ret_between(px,a,b): return px[b][1]/px[a][1]-1
def mean(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None

def earnings_dates(cik):
 s=get_json(f'https://data.sec.gov/submissions/CIK{cik}.json')['filings']['recent']; out=[]
 items=s.get('items',['']*len(s['form']))
 for form,filed,item in zip(s['form'],s['filingDate'],items):
  if form=='8-K' and filed>='2010-01-01' and '2.02' in (item or ''): out.append(filed)
 return sorted(set(out))

def main():
 mp=get_json('https://www.sec.gov/files/company_tickers.json'); ciks={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()}
 syms=sorted(set(TICKER_TO_SECTOR)|set(TICKER_TO_SECTOR.values())|{SPY}); px={s:prices(s) for s in syms}
 pos=[]; nonpos=[]
 for t,sector in TICKER_TO_SECTOR.items():
  for filed in earnings_dates(ciks[t]):
   i=idx_after(px[t],filed)
   if i<=0 or i+1+HOLD>=len(px[t]): continue
   reaction_day=i; entry=i+1; exit_i=entry+HOLD
   r0=px[t][reaction_day][0]; entry_d=px[t][entry][0]; exit_d=px[t][exit_i][0]
   si=bisect.bisect_left([x[0] for x in px[sector]],r0); sj=bisect.bisect_left([x[0] for x in px[sector]],entry_d); sk=bisect.bisect_left([x[0] for x in px[sector]],exit_d)
   bi=bisect.bisect_left([x[0] for x in px[SPY]],entry_d); bk=bisect.bisect_left([x[0] for x in px[SPY]],exit_d)
   if min(si,sj,sk,bi,bk)<0 or sk>=len(px[sector]) or bk>=len(px[SPY]) or si==0: continue
   stock_reaction=ret_between(px[t],reaction_day-1,reaction_day)
   sector_reaction=ret_between(px[sector],si-1,si)
   reaction_excess=stock_reaction-sector_reaction
   fwd=ret_between(px[t],entry,exit_i)-COST
   sec=ret_between(px[sector],sj,sk); spy=ret_between(px[SPY],bi,bk)
   e={'ticker':t,'sector':sector,'filed':filed,'reaction_day':r0,'entry':entry_d,'exit':exit_d,'reaction_excess':reaction_excess,'sector_excess':fwd-sec,'spy_excess':fwd-spy}
   (pos if reaction_excess>0 else nonpos).append(e)
 sec=[e['sector_excess'] for e in pos]; spy=[e['spy_excess'] for e in pos]
 years=[]
 for y in sorted({e['filed'][:4] for e in pos}):
  xs=[e['sector_excess'] for e in pos if e['filed'].startswith(y)]
  if len(xs)>=2: years.append({'year':int(y),'n':len(xs),'mean_sector_excess':mean(xs),'positive':mean(xs)>0})
 recent=[e['sector_excess'] for e in pos if e['filed']>='2022-01-01']; neg=[e['sector_excess'] for e in nonpos]
 contrast=None if not sec or not neg else mean(sec)-mean(neg)
 gates={'n_at_least_75':len(pos)>=75,'mean_sector_positive':bool(sec and mean(sec)>0),'median_sector_positive':bool(sec and med(sec)>0),'mean_spy_positive':bool(spy and mean(spy)>0),'event_hit_rate_55pct':bool(sec and mean([x>0 for x in sec])>=.55),'positive_year_share_60pct':bool(years and mean([x['positive'] for x in years])>=.60),'recent_positive':bool(recent and mean(recent)>0),'positive_reaction_beats_nonpositive':bool(contrast is not None and contrast>0)}
 result={'positive_reaction_events':len(pos),'nonpositive_reaction_events':len(nonpos),'mean_after_cost_sector_excess':mean(sec),'median_after_cost_sector_excess':med(sec),'mean_after_cost_spy_excess':mean(spy),'positive_sector_excess_share':mean([x>0 for x in sec]) if sec else None,'positive_year_share':mean([x['positive'] for x in years]) if years else None,'recent_since_2022_sector_excess':mean(recent),'positive_minus_nonpositive_sector_excess':contrast,'year_holdouts':years,'gates':gates,'decision':'ADMIT_FOR_DISJOINT_PIT_UNIVERSE_TEST' if all(gates.values()) else 'REJECT_NO_PARAMETER_RESCUE'}
 out={'schema':'research.pit_earnings_reaction_continuation_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether expectation-relative information is better captured by the market response to an earnings filing than by realized EPS acceleration.','claim_tested':'Positive first-full-session sector-relative reaction after SEC 8-K Item 2.02 filing predicts positive next-21-session after-cost excess versus matched sector ETF and SPY.','frozen_specification':{'event':'SEC 8-K Item 2.02','reaction_measure':'first full trading session after filing, stock return minus matched-sector return','signal':'reaction_excess > 0','information_time':'after reaction session close; enter following session','holding_sessions':HOLD,'round_trip_cost':COST,'ticker_to_sector':TICKER_TO_SECTOR,'broad_market':SPY},'result':result,'positive_events':pos,'nonpositive_events':nonpos,'limitations':['Current-ticker panel is a mechanism screen, not historical membership authority.','SEC submissions recent arrays can omit older filings moved to oldfiles.','Sign-only reaction gate is prospectively frozen; failure forbids magnitude threshold, horizon, cost, ticker, sector, or year rescue.','Pass only admits a disjoint point-in-time universe child.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True); Path('research/artifacts/pit_earnings_reaction_continuation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
