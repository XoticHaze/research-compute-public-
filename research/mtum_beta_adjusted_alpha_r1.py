from __future__ import annotations
import json,math,statistics,urllib.request
from datetime import date
from pathlib import Path

EXPERIMENT_ID='MTUM_BETA_ADJUSTED_ALPHA_R1'
INHERITED_LEARNING=['SLP-20260911-MTUM-MOMENTUM-R1']
SYMS=['MTUM','IWB','SPY']

def get_json(url):
 r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}); return json.loads(urllib.request.urlopen(r,timeout=45).read())
def daily(sym):
 x=get_json(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1356998400&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true')['chart']['result'][0]
 return [(date.fromtimestamp(ts).isoformat(),float(p)) for ts,p in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']) if p is not None]
def monthly(px):
 last={}
 for d,p in px: last[d[:7]]=(d,p)
 xs=[last[k] for k in sorted(last)]
 return [(xs[i][0],xs[i][1]/xs[i-1][1]-1) for i in range(1,len(xs))]
def align(a,b):
 da=dict(a); db=dict(b); ds=sorted(set(da)&set(db)); return [(d,da[d],db[d]) for d in ds]
def ols(rows):
 if len(rows)<12: return None
 y=[r[1] for r in rows]; x=[r[2] for r in rows]; mx=statistics.fmean(x); my=statistics.fmean(y)
 den=sum((z-mx)**2 for z in x); beta=sum((xx-mx)*(yy-my) for xx,yy in zip(x,y))/den if den else 0.0
 alpha=my-beta*mx
 resid=[yy-(alpha+beta*xx) for xx,yy in zip(x,y)]
 s2=sum(e*e for e in resid)/max(1,len(rows)-2); se_alpha=math.sqrt(s2*(1/len(rows)+mx*mx/den)) if den else None
 t_alpha=alpha/se_alpha if se_alpha else None
 return {'months':len(rows),'monthly_alpha':alpha,'annualized_alpha_linear':12*alpha,'beta':beta,'alpha_tstat':t_alpha,'positive_residual_share':statistics.fmean([e>0 for e in resid])}
def slice_rows(rows,start=None,end=None): return [r for r in rows if (start is None or r[0]>=start) and (end is None or r[0]<end)]
def rolling(rows,n=36):
 vals=[]
 for i in range(n,len(rows)+1):
  r=ols(rows[i-n:i]); vals.append(r['annualized_alpha_linear'])
 return vals

def main():
 m={s:monthly(daily(s)) for s in SYMS}
 rows_iwb=align(m['MTUM'],m['IWB']); rows_spy=align(m['MTUM'],m['SPY'])
 full=ols(rows_iwb); pre=ols(slice_rows(rows_iwb,end='2020-01')); post=ols(slice_rows(rows_iwb,start='2020-01')); spy_full=ols(rows_spy)
 roll=rolling(rows_iwb,36)
 gates={'full_alpha_positive':full['annualized_alpha_linear']>0,'pre2020_alpha_positive':pre['annualized_alpha_linear']>0,'post2020_alpha_positive':post['annualized_alpha_linear']>0,'rolling_36m_positive_share_55pct':statistics.fmean([x>0 for x in roll])>=.55,'full_alpha_tstat_positive':full['alpha_tstat']>0}
 result={'full_vs_iwb':full,'pre2020_vs_iwb':pre,'post2020_vs_iwb':post,'full_vs_spy':spy_full,'rolling_36m_windows':len(roll),'rolling_36m_positive_alpha_share':statistics.fmean([x>0 for x in roll]),'rolling_36m_median_annualized_alpha':statistics.median(roll),'gates':gates,'decision':'BETA_ADJUSTED_MOMENTUM_SURVIVES' if all(gates.values()) else 'BETA_ADJUSTED_MOMENTUM_REJECTED'}
 out={'schema':'research.mtum_beta_adjusted_alpha_r1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':INHERITED_LEARNING,'uncertainty_resolved':'Whether MTUM raw excess over IWB is merely beta exposure or retains positive monthly beta-adjusted alpha across full, pre-2020, post-2020 and rolling chronology.','claim_tested':'MTUM retains positive beta-adjusted monthly alpha versus IWB through full history and both pre/post-2020 chronology, with majority-positive rolling 36-month alpha.','frozen_specification':{'asset':'MTUM','primary_control':'IWB','secondary_control':'SPY','returns':'Yahoo adjusted-close month-end returns','regression':'OLS MTUM monthly return = alpha + beta * control monthly return','chronology_splits':['full','pre-2020','post-2020'],'rolling_window_months':36,'rolling_positive_gate':0.55,'no_parameter_rescue':True},'result':result,'limitations':['ETF live-history implementation test, not a constituent-level factor attribution.','No risk-free-rate subtraction; this is beta-adjusted return alpha versus investable equity controls, matching the inherited comparator question.','Failure forbids changing split date, control, rolling window, or excluding momentum-reversal years.'],'boundaries':{'portfolio_ranking':False,'allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('research/artifacts').mkdir(exist_ok=True); Path('research/artifacts/mtum_beta_adjusted_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
