import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

C=json.loads(Path('research/semiconductor-p13-semantics-correction-r2.json').read_text())
START=dt.datetime.fromisoformat(C['start']+'T00:00:00+00:00')
END=dt.datetime.fromisoformat(C['end_exclusive']+'T00:00:00+00:00')
SYMS=C['universe']+[C['benchmark'],C['broad_market']]


def fetch(sym):
    u=(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={int(START.timestamp())}'
       f'&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true')
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=30) as r:o=json.load(r)['chart']['result'][0]
    a=o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close']
    return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}


def beta(xs,ys):
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys); den=sum((x-mx)**2 for x in xs)
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den if den>1e-18 else 1.0


def compounded(rs):
    e=1.0
    for r in rs:e*=1+r
    return e-1


def cagr(rs,years):
    e=1.0
    for r in rs:e*=1+r
    return e**(1/years)-1 if e>0 else -1.0


def maxdd(rs):
    e=p=1.0; w=0.0
    for r in rs:
        e*=1+r; p=max(p,e); w=min(w,e/p-1)
    return w

px={s:fetch(s) for s in SYMS}
dates=sorted(set.intersection(*(set(px[s]) for s in SYMS)))
month_last=[i for i,d in enumerate(dates[:-1]) if dates[i+1][:7]!=d[:7]]
L=C['lookback_sessions']; periods=[]
for j,p in enumerate(month_last[:-1]):
    q=month_last[j+1]; entry=p+1; exitp=q+1
    if p<L or exitp>=len(dates):continue
    if dates[entry] < C['first_entry_not_before']:continue
    smh_daily=[math.log(px[C['benchmark']][dates[k]]/px[C['benchmark']][dates[k-1]]) for k in range(p-L+1,p+1)]
    smh_cum=math.log(px[C['benchmark']][dates[p]]/px[C['benchmark']][dates[p-L]])
    score={}
    for s in C['universe']:
        sd=[math.log(px[s][dates[k]]/px[s][dates[k-1]]) for k in range(p-L+1,p+1)]
        b=beta(smh_daily,sd)
        raw=px[s][dates[p]]/px[s][dates[p-L]]-1
        lograw=math.log(px[s][dates[p]]/px[s][dates[p-L]])
        score[s]={'raw':raw,'resid':lograw-b*smh_cum,'beta':b}
    def basket(sel):return sum(px[s][dates[exitp]]/px[s][dates[entry]]-1 for s in sel)/len(sel)
    rawsel=sorted(C['universe'],key=lambda s:score[s]['raw'],reverse=True)[:C['top_n']]
    ressel=sorted(C['universe'],key=lambda s:score[s]['resid'],reverse=True)[:C['top_n']]
    loo={}
    for omit in C['universe']:
        u=[s for s in C['universe'] if s!=omit]
        sel=sorted(u,key=lambda s:score[s]['raw'],reverse=True)[:C['top_n']]
        loo[omit]=basket(sel)
    periods.append({'signal':dates[p],'entry':dates[entry],'exit':dates[exitp],'year':int(dates[entry][:4]),
                    'raw_gross':basket(rawsel),'resid_gross':basket(ressel),'smh':px[C['benchmark']][dates[exitp]]/px[C['benchmark']][dates[entry]]-1,
                    'qqq':px[C['broad_market']][dates[exitp]]/px[C['broad_market']][dates[entry]]-1,'loo':loo})

years=(dt.date.fromisoformat(periods[-1]['exit'])-dt.date.fromisoformat(periods[0]['entry'])).days/365.25
smh=[p['smh'] for p in periods]; qqq=[p['qqq'] for p in periods]

cost_results={}
for bps in C['cost_scenarios_bps']:
    drag=bps/10000
    resid=[p['resid_gross']-drag for p in periods]; raw=[p['raw_gross']-drag for p in periods]
    cost_results[str(bps)]={'residual_cagr':cagr(resid,years),'raw_cagr':cagr(raw,years),'smh_cagr':cagr(smh,years),'qqq_cagr':cagr(qqq,years),
        'residual_compounded':compounded(resid),'raw_compounded':compounded(raw),'smh_compounded':compounded(smh),
        'residual_minus_raw_cagr_pp':100*(cagr(resid,years)-cagr(raw,years)),'residual_minus_smh_cagr_pp':100*(cagr(resid,years)-cagr(smh,years)),
        'residual_minus_raw_compounded_pp':100*(compounded(resid)-compounded(raw)),'residual_minus_smh_compounded_pp':100*(compounded(resid)-compounded(smh)),
        'residual_max_drawdown':maxdd(resid),'raw_max_drawdown':maxdd(raw)}

yearly=[]; drag25=.0025
for y in sorted(set(p['year'] for p in periods)):
    idx=[i for i,p in enumerate(periods) if p['year']==y]
    if len(idx)<10 or y>2025:continue
    rr=[periods[i]['resid_gross']-drag25 for i in idx]; rw=[periods[i]['raw_gross']-drag25 for i in idx]; sb=[smh[i] for i in idx]
    yearly.append({'year':y,'n':len(idx),'residual_net':compounded(rr),'raw_net':compounded(rw),'smh':compounded(sb),'residual_minus_smh_pp':100*(compounded(rr)-compounded(sb)),'raw_minus_smh_pp':100*(compounded(rw)-compounded(sb))})
resid_pos=sum(x['residual_minus_smh_pp']>0 for x in yearly)/len(yearly)
raw_pos=sum(x['raw_minus_smh_pp']>0 for x in yearly)/len(yearly)
r25=cost_results['25']; rg=C['residual_gates']
resid_pass=(r25['residual_minus_raw_cagr_pp']>=rg['min_residual_minus_raw_cagr_pp'] and r25['residual_minus_smh_cagr_pp']>=rg['min_residual_minus_smh_cagr_pp'] and resid_pos>=rg['min_positive_smh_excess_year_fraction'] and cost_results['50']['residual_minus_smh_cagr_pp']>=rg['min_50bps_residual_minus_smh_cagr_pp'] and 100*(r25['residual_max_drawdown']-r25['raw_max_drawdown'])>=-rg['max_drawdown_worsening_vs_raw_pp'])

loo_rows=[]
for omit in C['universe']:
    r25s=[p['loo'][omit]-.0025 for p in periods]; r50s=[p['loo'][omit]-.005 for p in periods]
    loo_rows.append({'omitted':omit,'primary_cagr':cagr(r25s,years),'primary_excess_vs_smh_cagr_pp':100*(cagr(r25s,years)-cagr(smh,years)),
                     'primary_excess_vs_smh_compounded_pp':100*(compounded(r25s)-compounded(smh)),'stress_cagr':cagr(r50s,years),'stress_excess_vs_smh_cagr_pp':100*(cagr(r50s,years)-cagr(smh,years))})
vals=sorted(x['primary_excess_vs_smh_cagr_pp'] for x in loo_rows); med=(vals[4]+vals[5])/2; pos=sum(x['primary_excess_vs_smh_cagr_pp']>0 for x in loo_rows)/len(loo_rows); spos=sum(x['stress_excess_vs_smh_cagr_pp']>0 for x in loo_rows)/len(loo_rows); worst=min(vals); lg=C['loo_gates']
loo_pass=pos>=lg['min_positive_loo_fraction'] and med>=lg['min_median_excess_cagr_pp'] and worst>=lg['min_worst_excess_cagr_pp'] and spos>=lg['min_stress_positive_loo_fraction']
out={'schema':'semiconductor_p13_semantics_correction_result.v1','experiment_id':C['experiment_id'],'periods':len(periods),'first_entry':periods[0]['entry'],'last_exit':periods[-1]['exit'],'years':years,'cost_semantics':C['cost_semantics'],
     'stock_specific_residual':{'cost_results':cost_results,'calendar_years':yearly,'residual_positive_smh_year_fraction':resid_pos,'raw_positive_smh_year_fraction':raw_pos,'passes_corrected_gate':resid_pass,'gates':rg},
     'raw_momentum_leave_one_out':{'rows':loo_rows,'primary_positive_loo_fraction':pos,'stress_positive_loo_fraction':spos,'median_primary_excess_cagr_pp':med,'worst_primary_excess_cagr_pp':worst,'passes_corrected_gate':loo_pass,'gates':lg},
     'promotion_blocked_by_static_universe':True,'research_only':True}
Path('semiconductor-p13-semantics-correction-r2-result.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
