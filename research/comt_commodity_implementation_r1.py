import datetime as dt, json, urllib.request
from pathlib import Path
C=json.loads(Path('research/comt-commodity-implementation-r1.json').read_text())
START=dt.datetime.fromisoformat(C['start']+'T00:00:00+00:00'); END=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)
def fetch(s):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={int(START.timestamp())}&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true'
 req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=30) as r:o=json.load(r)['chart']['result'][0]
 a=o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close']
 return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}
def ann(v):
 w=1.0
 for x in v:w*=1+x
 return w**(12/len(v))-1 if v else None
def comp(v):
 w=1.0
 for x in v:w*=1+x
 return w-1
px={s:fetch(s) for s in C['symbols']}; common=sorted(set.intersection(*(set(px[s]) for s in C['symbols'])))
months={}
for d in common:months.setdefault(d[:7],[]).append(d)
rows=[]
for m,ds in sorted(months.items()):
 if len(ds)<10 or m+'-01'<C['evaluation_start']:continue
 f,l=ds[0],ds[-1]; rows.append({'month':m,**{s:px[s][l]/px[s][f]-1 for s in C['symbols']}})
cost=C['incremental_comt_cost_bps_per_year']/10000/12
for r in rows:r['COMT_NET']=r['COMT']-cost;r['EX_DBC']=r['COMT_NET']-r['DBC'];r['EX_BCI']=r['COMT_NET']-r['BCI']
recent=[r for r in rows if r['month']+'-01'>=C['recent_start']]
years={}
for r in rows:years.setdefault(r['month'][:4],[]).append(r)
year_both={y:(comp([r['EX_DBC'] for r in rs]),comp([r['EX_BCI'] for r in rs])) for y,rs in years.items()}
pos=sum(a>0 and b>0 for a,b in year_both.values())/len(year_both)
trimn=max(1,int(len(rows)*C['trim_top_relative_month_fraction']))
keep_dbc=sorted(rows,key=lambda r:r['EX_DBC'])[:-trimn]; keep_bci=sorted(rows,key=lambda r:r['EX_BCI'])[:-trimn]
metrics={'months':len(rows),'full_comt_net_cagr':ann([r['COMT_NET'] for r in rows]),'full_dbc_cagr':ann([r['DBC'] for r in rows]),'full_bci_cagr':ann([r['BCI'] for r in rows]),'full_excess_vs_dbc':ann([r['COMT_NET'] for r in rows])-ann([r['DBC'] for r in rows]),'full_excess_vs_bci':ann([r['COMT_NET'] for r in rows])-ann([r['BCI'] for r in rows]),'recent_excess_vs_dbc':ann([r['COMT_NET'] for r in recent])-ann([r['DBC'] for r in recent]),'recent_excess_vs_bci':ann([r['COMT_NET'] for r in recent])-ann([r['BCI'] for r in recent]),'positive_year_fraction_vs_both':pos,'trimmed_excess_vs_dbc':ann([r['COMT_NET'] for r in keep_dbc])-ann([r['DBC'] for r in keep_dbc]),'trimmed_excess_vs_bci':ann([r['COMT_NET'] for r in keep_bci])-ann([r['BCI'] for r in keep_bci]),'year_excess_vs_controls':year_both}
g=C['gates']; checks={'full_dbc':metrics['full_excess_vs_dbc']>=g['min_full_excess_vs_dbc'],'full_bci':metrics['full_excess_vs_bci']>=g['min_full_excess_vs_bci'],'recent_dbc':metrics['recent_excess_vs_dbc']>=g['min_recent_excess_vs_dbc'],'recent_bci':metrics['recent_excess_vs_bci']>=g['min_recent_excess_vs_bci'],'years':metrics['positive_year_fraction_vs_both']>=g['min_positive_year_fraction_vs_both'],'trimmed':metrics['trimmed_excess_vs_dbc']>=g['min_trimmed_excess_vs_both'] and metrics['trimmed_excess_vs_bci']>=g['min_trimmed_excess_vs_both']}
out={'schema':'comt_commodity_implementation_result.v1','experiment_id':C['experiment_id'],'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Yahoo Finance chart adjusted-close public endpoint','contract':C,'metrics':metrics,'checks':checks,'decision':'PASS_IMPLEMENTATION_DISCRIMINATOR' if all(checks.values()) else 'REJECT_IMPLEMENTATION_CLAIM','research_only':True}
Path('comt-commodity-implementation-r1-result.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,indent=2,sort_keys=True))
