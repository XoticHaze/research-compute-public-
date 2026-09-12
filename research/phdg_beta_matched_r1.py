import datetime as dt,json,urllib.request
from pathlib import Path
C=json.loads(Path('research/phdg-beta-matched-r1.json').read_text());START=dt.datetime.fromisoformat(C['start']+'T00:00:00+00:00');END=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)
def fetch(s):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={int(START.timestamp())}&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true';req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=30) as r:o=json.load(r)['chart']['result'][0]
 a=o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close'];return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}
px={s:fetch(s) for s in C['symbols']};common=sorted(set.intersection(*(set(px[s]) for s in C['symbols'])));months={}
for d in common:months.setdefault(d[:7],[]).append(d)
rows=[]
for m,ds in sorted(months.items()):
 if len(ds)<10:continue
 f,l=ds[0],ds[-1];rows.append({'month':m,**{s:px[s][l]/px[s][f]-1 for s in C['symbols']}})
def beta(h):
 x=[r['SPY']-r['BIL'] for r in h];y=[r['PHDG']-r['BIL'] for r in h];mx=sum(x)/len(x);my=sum(y)/len(y);den=sum((v-mx)**2 for v in x);b=0 if den<1e-12 else sum((a-mx)*(c-my) for a,c in zip(x,y))/den;lo,hi=C['beta_clip'];return max(lo,min(hi,b))
lb=C['beta_lookback_months'];cost=C['incremental_cost_bps_per_year']/10000/12;obs=[]
for i in range(lb,len(rows)):
 r=rows[i]
 if r['month']+'-01'<C['evaluation_start']:continue
 b=beta(rows[i-lb:i]);ctrl=b*r['SPY']+(1-b)*r['BIL'];obs.append({'month':r['month'],'beta':b,'ex':r['PHDG']-ctrl-cost})
def ann(v):return sum(v)/len(v)*12 if v else None
annual=[]
for y in sorted({o['month'][:4] for o in obs}):
 z=[o['ex'] for o in obs if o['month'].startswith(y+'-')]
 if len(z)>=11:annual.append({'year':int(y),'annualized_excess':ann(z),'positive':ann(z)>0})
full=ann([o['ex'] for o in obs]);recent=ann([o['ex'] for o in obs if o['month']+'-01'>=C['recent_start']]);w=C['rolling_months'];roll=[ann([x['ex'] for x in obs[i-w+1:i+1]]) for i in range(w-1,len(obs))];py=sum(a['positive'] for a in annual)/len(annual);pr=sum(x>0 for x in roll)/len(roll);worst=min(a['annualized_excess'] for a in annual);avg=sum(o['beta'] for o in obs)/len(obs);g=C['gates'];checks={'full':full>=g['min_full_excess'],'recent':recent>=g['min_recent_excess'],'years':py>=g['min_positive_year_fraction'],'rolling':pr>=g['min_rolling_positive_fraction'],'worst':worst>=g['min_worst_year']};out={'schema':'phdg_beta_matched_result.v1','experiment_id':C['experiment_id'],'months':len(obs),'average_causal_beta':avg,'full_after_cost_annualized_excess':full,'recent_after_cost_annualized_excess':recent,'positive_year_fraction':py,'rolling_36m_positive_fraction':pr,'worst_year_after_cost_excess':worst,'annual':annual,'checks':checks,'decision':'PASS_IMPLEMENTATION_DISCRIMINATOR' if all(checks.values()) else 'REJECT_IMPLEMENTATION_CLAIM','research_only':True};Path('phdg-beta-matched-r1-result.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
