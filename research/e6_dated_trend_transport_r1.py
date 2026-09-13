#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math,statistics
from pathlib import Path
ROOT="6E"; LOOKBACK=20; HOLD=5; COST_BPS=10.0; RECENT_YEAR=2015; SOURCE_ARTIFACT_ID=10294324888
EXPERIMENT_ID="6E-DATED-TREND-TRANSPORT-R1"
PARENTS=["SLP-20260913-NQ-DATED-TREND-TRANSPORT-R1","SLP-20260913-ES-DATED-TREND-TRANSPORT-R1","F1B-CROSSROOT-DATED-CORPUS-RELEASE"]
def mean(x): return sum(x)/len(x) if x else float('nan')
def load(p):
 r=[]
 with p.open(newline='',encoding='utf-8') as f:
  for x in csv.DictReader(f):
   try: c=float(x['close']);v=float(x['volume']);o=float(x['open_interest'])
   except: continue
   if math.isfinite(c) and c>0 and v>0 and o>0:r.append((x['timestamp'],c))
 r.sort();return r
def month(p):return p.parent.name.split('-',1)[1]
def events(p):
 m=month(p); y=int(m[:4]); r=load(p); out=[]; i=LOOKBACK
 while i+HOLD<len(r):
  past=r[i][1]/r[i-LOOKBACK][1]-1; fwd=r[i+HOLD][1]/r[i][1]-1; pos=1 if past>0 else(-1 if past<0 else 0); cost=COST_BPS/10000 if pos else 0
  s=pos*fwd-cost; b=fwd-COST_BPS/10000; out.append({'contract_month':m,'contract_year':y,'strategy_return_after_cost':s,'matched_long_return_after_cost':b,'excess_return':s-b});i+=HOLD
 return out
def summ(e):
 if not e:return {}
 ex=[x['excess_return'] for x in e]; sr=[x['strategy_return_after_cost'] for x in e]; br=[x['matched_long_return_after_cost'] for x in e]
 return {'n':len(e),'mean_strategy_return_pct':100*mean(sr),'mean_matched_long_return_pct':100*mean(br),'mean_excess_return_pct':100*mean(ex),'median_excess_return_pct':100*statistics.median(ex),'positive_excess_fraction':sum(x>0 for x in ex)/len(ex)}
def main():
 files=sorted(Path('input/staging').glob('**/6E-*/1Day.csv'))
 if not files:raise RuntimeError('no released 6E dated-contract files found')
 all_events=[]; pc={}
 for p in files:
  e=events(p)
  if e:pc[month(p)]=summ(e);all_events+=e
 recent=[e for e in all_events if e['contract_year']>=RECENT_YEAR]; pos=sum(v['mean_excess_return_pct']>0 for v in pc.values())/len(pc)
 loo={}; years=sorted(set(e['contract_year'] for e in all_events))
 for y in years:loo[str(y)]=summ([e for e in all_events if e['contract_year']!=y]).get('mean_excess_return_pct')
 full=summ(all_events); rec=summ(recent); vals=list(loo.values()); gates={'full_mean_excess_positive':full.get('mean_excess_return_pct',-999)>0,'recent_mean_excess_positive':rec.get('mean_excess_return_pct',-999)>0,'majority_contracts_positive':pos>0.5,'all_leave_one_year_out_positive':bool(vals) and min(vals)>0,'minimum_event_count':len(all_events)>=250}; survives=all(gates.values())
 result={'schema':'public.e6_dated_trend_transport_r1.v1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':PARENTS,'uncertainty_resolved':'whether the simple dated-contract trend rejection in NQ and ES extends to a liquid non-equity futures root','claim_tested':'The identical frozen 20-active-session trend sign predicts the next 5 active sessions across released 6E dated contracts and beats an always-long matched opportunity after a 10 bp normalized round-trip cost without constructing a continuous series.','source_artifact_id':SOURCE_ARTIFACT_ID,'root':ROOT,'design':{'lookback_active_sessions':LOOKBACK,'hold_active_sessions':HOLD,'normalized_round_trip_cost_bps':COST_BPS,'active_row_filter':'volume>0 and open_interest>0','sampling':'non-overlapping within each dated contract','continuous_series_constructed':False,'roll_cutoff_selected':False,'back_adjustment':False,'matched_control':'always-long same contract/same decision windows/same normalized cost','recent_contract_year_gte':RECENT_YEAR},'contract_files_seen':len(files),'contracts_with_events':len(pc),'full':full,'recent':rec,'positive_contract_fraction':pos,'leave_one_contract_year_out_mean_excess_pct':loo,'gates':gates,'survives_transport':survives,'decision':'SURVIVES_TRANSPORT' if survives else 'REJECT_NO_PARAMETER_RESCUE','forbidden_parameter_rescue':['lookback change','holding-period change','cost reduction','exclude bad contract years','volume/open-interest threshold tuning','select only favorable contract months'],'authority':'SCIENTIFIC_EVIDENCE_ONLY','portfolio_allocation_authority':False,'strategy_spec_mutation':False,'runtime_authority_change':False,'broker_submission':False,'live_trading_change':False}
 Path('6e-dated-trend-transport-r1-result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__':main()
