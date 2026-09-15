from __future__ import annotations
import json,math,statistics,urllib.request
from datetime import date
from pathlib import Path
EXPERIMENT_ID='SPMO_PANIC_REBOUND_TRANSPORT_R1'
INHERITED_LEARNING=['SLP-20260912-MTUM-PANIC-REBOUND-REGIME-R1']
SYMS=['SPMO','SPY','MGK','IWB']
def j(u):
 r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}); return json.loads(urllib.request.urlopen(r,timeout=45).read())
def mon(s):
 x=j(f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=1420070400&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true')['chart']['result'][0]; z={}
 for t,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']):
  if p is not None:z[date.fromtimestamp(t).isoformat()[:7]]=float(p)
 k=sorted(z);return {k[i]:z[k[i]]/z[k[i-1]]-1 for i in range(1,len(k))}
def fit(rs):
 y=[r[1] for r in rs];a=[r[2] for r in rs];b=[r[3] for r in rs];my,ma,mb=map(statistics.fmean,[y,a,b]);x=[v-ma for v in a];w=[v-mb for v in b];c=[v-my for v in y];s11=sum(v*v for v in x);s22=sum(v*v for v in w);s12=sum(u*v for u,v in zip(x,w));q1=sum(u*v for u,v in zip(x,c));q2=sum(u*v for u,v in zip(w,c));det=s11*s22-s12*s12;b1=(q1*s22-q2*s12)/det;b2=(q2*s11-q1*s12)/det;al=my-b1*ma-b2*mb;return al,b1,b2
def mean(x):return statistics.fmean(x) if x else None
def main():
 m={s:mon(s) for s in SYMS};ks=sorted(set.intersection(*(set(m[s]) for s in SYMS)));rs=[(k,m['SPMO'][k],m['SPY'][k],m['MGK'][k]-m['SPY'][k],m['IWB'][k]) for k in ks];al,b1,b2=fit(rs);vols=[];p=[];o=[];detail=[]
 for i,r in enumerate(rs):
  if i<12:continue
  k,y,spy,mg,iwb=r;prior=[z[4] for z in rs[i-12:i]];pret=math.prod(1+x for x in prior)-1;pv=statistics.pstdev(prior)*math.sqrt(12);high=bool(vols) and pv>statistics.median(vols);panic=pret<0 and high and iwb>0;res=y-(al+b1*spy+b2*mg);detail.append({'month':k,'panic_rebound':panic,'residual':res});(p if panic else o).append(res);vols.append(pv)
 diff=None if not p or not o else mean(p)-mean(o);result={'months_classified':len(detail),'panic_rebound_months':len(p),'panic_mean_monthly_residual':mean(p),'nonpanic_mean_monthly_residual':mean(o),'panic_minus_nonpanic_residual':diff,'panic_negative_residual_share':mean([x<0 for x in p]) if p else None,'decision':'REGIME_FRAGILITY_TRANSPORTS' if p and mean(p)<0 and diff<0 else 'REGIME_FRAGILITY_DOES_NOT_TRANSPORT'}
 out={'schema':'research.spmo_panic_rebound_transport_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether the frozen MTUM panic-rebound failure mode transports to an independent momentum ETF implementation.','claim_tested':'SPMO market- and mega-cap-growth-adjusted residual is also worse in the exact frozen IWB panic-rebound state inherited from MTUM.','frozen_specification':{'test_asset':'SPMO','market_control':'SPY','concentration_factor':'MGK minus SPY','panic_state':'prior 12m IWB return <0 AND prior 12m IWB annualized monthly volatility > expanding median AND current IWB return >0','no_parameter_rescue':True},'result':result,'classified_months':detail,'limitations':['Independent momentum ETF implementation but overlapping US large-cap opportunity set.','Transport result validates a failure mode, not a timing or allocation rule.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True);Path('research/artifacts/spmo_panic_rebound_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
