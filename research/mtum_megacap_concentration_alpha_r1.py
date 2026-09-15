from __future__ import annotations
import json,statistics,urllib.request
from datetime import date
from pathlib import Path

EXPERIMENT_ID='MTUM_MEGACAP_CONCENTRATION_ALPHA_R1'
INHERITED_LEARNING=['SLP-20260911-MTUM-MOMENTUM-R1','SLP-20260912-MTUM-BETA-ADJUSTED-ALPHA-R1']
SYMS=['MTUM','IWB','MGK']

def j(url):
 r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}); return json.loads(urllib.request.urlopen(r,timeout=45).read())
def monthly(sym):
 x=j(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1356998400&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true')['chart']['result'][0]
 last={}
 for ts,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']):
  if p is not None: last[date.fromtimestamp(ts).isoformat()[:7]]=float(p)
 ks=sorted(last); return {ks[i]:last[ks[i]]/last[ks[i-1]]-1 for i in range(1,len(ks))}
def rows(ms):
 ks=sorted(set.intersection(*(set(v) for v in ms.values())))
 return [(k,ms['MTUM'][k],ms['IWB'][k],ms['MGK'][k]-ms['IWB'][k]) for k in ks]
def fit(rs):
 n=len(rs); y=[r[1] for r in rs]; x1=[r[2] for r in rs]; x2=[r[3] for r in rs]
 my,m1,m2=map(statistics.fmean,[y,x1,x2]); a=[z-m1 for z in x1]; b=[z-m2 for z in x2]; c=[z-my for z in y]
 s11=sum(z*z for z in a); s22=sum(z*z for z in b); s12=sum(u*v for u,v in zip(a,b)); sy1=sum(u*v for u,v in zip(a,c)); sy2=sum(u*v for u,v in zip(b,c)); det=s11*s22-s12*s12
 b1=(sy1*s22-sy2*s12)/det; b2=(sy2*s11-sy1*s12)/det; alpha=my-b1*m1-b2*m2
 return {'months':n,'monthly_alpha':alpha,'annualized_alpha_linear':12*alpha,'iwb_beta':b1,'megacap_growth_relative_beta':b2}
def sl(rs,start=None,end=None): return [r for r in rs if (start is None or r[0]>=start) and (end is None or r[0]<end)]
def main():
 rs=rows({s:monthly(s) for s in SYMS}); full=fit(rs); pre=fit(sl(rs,end='2020-01')); post=fit(sl(rs,start='2020-01'))
 roll=[fit(rs[i-36:i])['annualized_alpha_linear'] for i in range(36,len(rs)+1)]; share=statistics.fmean([x>0 for x in roll])
 gates={'full_alpha_positive':full['annualized_alpha_linear']>0,'pre2020_alpha_positive':pre['annualized_alpha_linear']>0,'post2020_alpha_positive':post['annualized_alpha_linear']>0,'rolling_36m_positive_share_55pct':share>=.55}
 result={'full':full,'pre2020':pre,'post2020':post,'rolling_36m_windows':len(roll),'rolling_36m_positive_alpha_share':share,'rolling_36m_median_annualized_alpha':statistics.median(roll),'gates':gates,'decision':'CONCENTRATION_ADJUSTED_MOMENTUM_SURVIVES' if all(gates.values()) else 'CONCENTRATION_EXPLAINS_OR_DESTABILIZES_SURVIVOR'}
 out={'schema':'research.mtum_megacap_concentration_alpha_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether the beta-adjusted MTUM survivor is explained by concentrated exposure to mega-cap growth winners.','claim_tested':'MTUM retains positive incremental monthly alpha after controlling simultaneously for IWB market return and the MGK-minus-IWB mega-cap-growth relative factor across full, pre/post-2020 and rolling chronology.','frozen_specification':{'asset':'MTUM','market_control':'IWB','concentration_factor':'MGK minus IWB monthly adjusted-close return','regression':'MTUM = alpha + beta1*IWB + beta2*(MGK-IWB)','chronology_splits':['full','pre-2020','post-2020'],'rolling_window_months':36,'rolling_positive_gate':0.55,'no_parameter_rescue':True},'result':result,'limitations':['MGK-minus-IWB is an investable mega-cap-growth concentration proxy, not holdings-level attribution.','Failure/survival should be followed by reversal-regime falsification only if economically warranted.','Do not replace MGK after observing the result.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True); Path('research/artifacts/mtum_megacap_concentration_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
