#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math
from pathlib import Path
ROOT='6E';LOOKBACK=20;HOLD=5;COST_BPS=10.0;RECENT_YEAR=2015;SOURCE_ARTIFACT_ID=10294324888
EXPERIMENT_ID='6E-DATED-TREND-CASH-SUFFICIENCY-R1';PARENT='SLP-20260913-6E-DATED-TREND-RELATIVE-TRANSPORT-R1'
def avg(x):return sum(x)/len(x) if x else float('nan')
def month(p):return p.parent.name.split('-',1)[1]
def load(p):
 out=[]
 with p.open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   try:c=float(r['close']);v=float(r['volume']);oi=float(r['open_interest'])
   except:continue
   if math.isfinite(c) and c>0 and v>0 and oi>0:out.append((r['timestamp'],c))
 out.sort();return out
def events(p):
 m=month(p);y=int(m[:4]);r=load(p);out=[];i=LOOKBACK
 while i+HOLD<len(r):
  past=r[i][1]/r[i-LOOKBACK][1]-1;fwd=r[i+HOLD][1]/r[i][1]-1;pos=1 if past>0 else(-1 if past<0 else 0);cost=COST_BPS/10000 if pos else 0
  out.append({'year':y,'contract':m,'ret':pos*fwd-cost});i+=HOLD
 return out
def stats(e):
 vals=[x['ret'] for x in e]
 return {'n':len(vals),'mean_strategy_return_pct':100*avg(vals),'positive_event_fraction':sum(v>0 for v in vals)/len(vals) if vals else 0}
def main():
 files=sorted(Path('input/staging').glob('**/6E-*/1Day.csv')); all_events=[]
 for p in files:all_events+=events(p)
 recent=[x for x in all_events if x['year']>=RECENT_YEAR];years=sorted(set(x['year'] for x in all_events));contracts=sorted(set(x['contract'] for x in all_events))
 year_means={str(y):100*avg([x['ret'] for x in all_events if x['year']==y]) for y in years};contract_means={c:100*avg([x['ret'] for x in all_events if x['contract']==c]) for c in contracts};loo={str(y):100*avg([x['ret'] for x in all_events if x['year']!=y]) for y in years}
 full=stats(all_events);rec=stats(recent);gates={'full_mean_strategy_positive_vs_cash':full['mean_strategy_return_pct']>0,'recent_mean_strategy_positive_vs_cash':rec['mean_strategy_return_pct']>0,'majority_contract_years_positive':sum(v>0 for v in year_means.values())/len(year_means)>0.5,'all_leave_one_year_out_positive':min(loo.values())>0,'minimum_event_count':len(all_events)>=250};survives=all(gates.values())
 result={'schema':'public.e6_trend_cash_sufficiency_r1.v1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':[PARENT],'claim_tested':'With the 6E 20x5 trend rule, active-row filter, sampling and 10 bp normalized cost frozen unchanged, after-cost strategy returns beat cash/zero return with positive full, recent and chronological breadth.','source_artifact_id':SOURCE_ARTIFACT_ID,'design':{'root':ROOT,'lookback_active_sessions':LOOKBACK,'hold_active_sessions':HOLD,'normalized_round_trip_cost_bps':COST_BPS,'active_row_filter':'volume>0 and open_interest>0','sampling':'non-overlapping within each dated contract','cash_baseline_return':0.0,'continuous_series_constructed':False,'roll_cutoff_selected':False,'back_adjustment':False},'full':full,'recent':rec,'positive_contract_year_fraction':sum(v>0 for v in year_means.values())/len(year_means),'positive_contract_fraction':sum(v>0 for v in contract_means.values())/len(contract_means),'leave_one_contract_year_out_mean_strategy_pct':loo,'gates':gates,'survives_economic_sufficiency':survives,'decision':'SURVIVES_CASH_SUFFICIENCY' if survives else 'REJECT_STANDALONE_ALPHA_NO_PARAMETER_RESCUE','risk_note':'Portfolio drawdown/capital utilization are intentionally not inferred because no continuous series or roll allocation is constructed.','authority':'SCIENTIFIC_EVIDENCE_ONLY','portfolio_allocation_authority':False,'live_trading_change':False}
 Path('6e-trend-cash-sufficiency-r1-result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__':main()
