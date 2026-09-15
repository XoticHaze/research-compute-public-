from __future__ import annotations
import json,math,statistics,urllib.request
from datetime import date
from pathlib import Path

EXPERIMENT_ID='MTUM_PANIC_REBOUND_REGIME_R1'
INHERITED_LEARNING=['SLP-20260912-MTUM-BETA-ADJUSTED-ALPHA-R1','SLP-20260912-MTUM-MEGACAP-CONCENTRATION-ALPHA-R1']
SYMS=['MTUM','IWB','MGK']

def j(url):
 r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}); return json.loads(urllib.request.urlopen(r,timeout=45).read())
def monthly(sym):
 x=j(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1356998400&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true')['chart']['result'][0]; last={}
 for ts,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']):
  if p is not None: last[date.fromtimestamp(ts).isoformat()[:7]]=float(p)
 ks=sorted(last); return {ks[i]:last[ks[i]]/last[ks[i-1]]-1 for i in range(1,len(ks))}
def rows(ms):
 ks=sorted(set.intersection(*(set(v) for v in ms.values()))); return [(k,ms['MTUM'][k],ms['IWB'][k],ms['MGK'][k]-ms['IWB'][k]) for k in ks]
def fit(rs):
 y=[r[1] for r in rs]; x1=[r[2] for r in rs]; x2=[r[3] for r in rs]; my,m1,m2=map(statistics.fmean,[y,x1,x2]); a=[x-m1 for x in x1]; b=[x-m2 for x in x2]; c=[x-my for x in y]
 s11=sum(x*x for x in a); s22=sum(x*x for x in b); s12=sum(x*z for x,z in zip(a,b)); sy1=sum(x*z for x,z in zip(a,c)); sy2=sum(x*z for x,z in zip(b,c)); det=s11*s22-s12*s12
 b1=(sy1*s22-sy2*s12)/det; b2=(sy2*s11-sy1*s12)/det; alpha=my-b1*m1-b2*m2
 return alpha,b1,b2
def mean(xs): return statistics.fmean(xs) if xs else None

def main():
 rs=rows({s:monthly(s) for s in SYMS}); alpha,b1,b2=fit(rs)
 enriched=[]; vols=[]
 for i,r in enumerate(rs):
  d,y,mkt,mg=r; resid=y-(alpha+b1*mkt+b2*mg)
  if i>=12:
   prior=[z[2] for z in rs[i-12:i]]; prior_ret=math.prod(1+x for x in prior)-1; prior_vol=statistics.pstdev(prior)*math.sqrt(12)
   hist_vols=vols[:] ; high_vol=bool(hist_vols) and prior_vol>statistics.median(hist_vols); rebound=mkt>0; panic=prior_ret<0 and high_vol and rebound
   enriched.append({'month':d,'residual':resid,'prior_12m_iwb_return':prior_ret,'prior_12m_iwb_ann_vol':prior_vol,'high_vol_vs_expanding_median':high_vol,'iwb_rebound_month':rebound,'panic_rebound':panic})
   vols.append(prior_vol)
  elif i>0:
   prior=[z[2] for z in rs[max(0,i-12):i]]; vols.append(statistics.pstdev(prior)*math.sqrt(12) if len(prior)>1 else 0.0)
 panic=[x['residual'] for x in enriched if x['panic_rebound']]; other=[x['residual'] for x in enriched if not x['panic_rebound']]
 diff=None if not panic or not other else mean(panic)-mean(other)
 result={'months_classified':len(enriched),'panic_rebound_months':len(panic),'panic_mean_monthly_residual':mean(panic),'nonpanic_mean_monthly_residual':mean(other),'panic_minus_nonpanic_residual':diff,'panic_negative_residual_share':mean([x<0 for x in panic]) if panic else None,'decision':'REVERSAL_REGIME_EXPOSURE_DETECTED' if panic and mean(panic)<0 and diff<0 else 'REVERSAL_REGIME_EXPOSURE_NOT_DETECTED'}
 out={'schema':'research.mtum_panic_rebound_regime_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether the surviving MTUM concentration-adjusted residual is materially worse in a prospectively defined panic-rebound state motivated by momentum-crash literature.','claim_tested':'MTUM concentration-adjusted residual is not dependent on avoiding panic-rebound months defined without MTUM outcomes: prior 12-month IWB return < 0, prior 12-month IWB volatility above its expanding historical median, and current IWB month > 0.','frozen_specification':{'residual_model':'MTUM = alpha + beta1*IWB + beta2*(MGK-IWB), fit full live history','panic_rebound_definition':['prior 12m IWB compounded return < 0','prior 12m annualized IWB monthly volatility > expanding historical median','current IWB monthly return > 0'],'no_MTUМ_outcome_used_in_regime_definition':True,'source_reference':'Daniel and Moskowitz Momentum Crashes: panic states follow market declines/high volatility and coincide with rebounds','no_parameter_rescue':True},'result':result,'classified_months':enriched,'limitations':['This is a regime-dependence falsifier, not a timing strategy or allocation rule.','Expanding-median volatility makes the state chronology-safe but is a simplified investable proxy for the literature panic state.','Do not tune lookback, volatility quantile, or rebound threshold after result.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True); Path('research/artifacts/mtum_panic_rebound_regime_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
