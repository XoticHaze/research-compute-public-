from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T = ['SPMO','IJS','SPY','IJR','DBMF','BIL','SRLN','HYG','SHY']
START='2015-01-01'; END='2026-09-11'; LB=24; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True)
PLAN=ART/'p423_p305_dbmf_coverage_plan.json'; PRICES=ART/'p423_p305_dbmf_monthly_prices.csv'; OUT=ART/'p423_p305_dbmf_coverage_r2.json'


def download_monthly():
    raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
    if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
    c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
    return c[T].resample('ME').last()


def derived(monthly):
    r=monthly.pct_change(fill_method=None)
    p305=.5*(r.SPMO+r.IJS); p305ctl=.5*(r.SPY+r.IJR)
    bs=[]
    for i in range(len(r)):
        w=r[['HYG','SHY','SRLN']].iloc[max(0,i-LB):i].dropna()
        if len(w)<LB:
            bs.append((np.nan,np.nan)); continue
        b=np.linalg.lstsq(w[['HYG','SHY']].values,w.SRLN.values,rcond=None)[0]
        b=np.clip(b,0,1)
        if b.sum()>1: b=b/b.sum()
        bs.append(tuple(map(float,b)))
    b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1)
    loanctl=b.hyg*r.HYG+b.shy*r.SHY
    return pd.DataFrame({'p305':p305,'p305ctl':p305ctl,'dbmf':r.DBMF,'bil':r.BIL,'srln':r.SRLN,'loanctl':loanctl})


def preflight():
    m=download_monthly()
    m.to_csv(PRICES,index_label='date')
    availability={}
    for t in T:
        s=m[t].dropna()
        availability[t]={'first_month':s.index.min().strftime('%Y-%m-%d') if len(s) else None,'last_month':s.index.max().strftime('%Y-%m-%d') if len(s) else None,'price_months':int(len(s))}
    d=derived(m)
    common=d.dropna()
    idx=common.index
    n=len(idx)
    contiguous=False
    if n:
        periods=idx.to_period('M').astype(int)
        contiguous=bool(np.all(np.diff(periods)==1)) if n>1 else True
    min_total=60; min_block=18
    eligible=n>=min_total and contiguous
    blocks=[]
    if eligible:
        sizes=[n//3,n//3,n-2*(n//3)]
        if min(sizes)<min_block: eligible=False
        else:
            off=0
            for j,sz in enumerate(sizes,1):
                z=idx[off:off+sz]; off+=sz
                blocks.append({'block':j,'start':z[0].strftime('%Y-%m-%d'),'end':z[-1].strftime('%Y-%m-%d'),'observations':int(len(z))})
    plan={'schema':'research.p423_p305_dbmf_coverage_plan.v1','workload_id':'P423_P305_DBMF_COVERAGE_VALID_R2','coverage_only_preflight':True,'performance_metrics_computed':False,'source_window':{'start':START,'end_exclusive':END},'availability':availability,'derived_common':{'first_month':idx.min().strftime('%Y-%m-%d') if n else None,'last_month':idx.max().strftime('%Y-%m-%d') if n else None,'common_observations':int(n),'contiguous_months':contiguous},'predeclared_coverage_rule':{'minimum_total_common_observations':min_total,'three_contiguous_equal_count_blocks':True,'minimum_observations_per_block':min_block,'no_post_result_date_movement':True},'blocks':blocks,'coverage_eligible':bool(eligible),'decision_if_ineligible':'DATA_REPRESENTATION_LIMIT__PRESERVE_NEEDS_CONFIRMATION'}
    PLAN.write_text(json.dumps(plan,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({'coverage_eligible':eligible,'common_observations':n,'contiguous_months':contiguous,'blocks':[b['observations'] for b in blocks]},sort_keys=True))
    return eligible


def ep(s):
    y=pd.Series(s,dtype=float).dropna().copy()
    if len(y): y.iloc[0]-=EP; y.iloc[-1]-=EP
    return y

def stats(s):
    q=ep(s); n=len(q)
    if n<2:return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None,'vol':None}
    w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12); ann=q.mean()*12
    return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min()),'vol':float(vol)}
def corr(a,b):
    z=pd.concat([a,b],axis=1).dropna(); v=z.iloc[:,0].corr(z.iloc[:,1]) if len(z)>=3 else np.nan
    return float(v) if pd.notna(v) else None
def roll_excess(q,n=12):
    a=(1+q.challenger).rolling(n).apply(np.prod,raw=True)-1; b=(1+q.challenger_ctl).rolling(n).apply(np.prod,raw=True)-1; z=(a-b).dropna()
    return {'windows':len(z),'positive_fraction':float((z>0).mean()) if len(z) else None,'median_excess':float(z.median()) if len(z) else None,'worst_excess':float(z.min()) if len(z) else None}
def ev(q):
    ch,ctl,co,coctl=stats(q.challenger),stats(q.challenger_ctl),stats(q.core),stats(q.core_ctl); neg=q.loc[q.core<0]
    return {'challenger':ch,'matched_control':ctl,'core_stack':co,'core_stack_control':coctl,'challenger_matched_excess_cagr':ch['cagr']-ctl['cagr'],'core_matched_excess_cagr':co['cagr']-coctl['cagr'],'opportunity_cost_vs_core':{'cagr_delta':ch['cagr']-co['cagr'],'sharpe_delta':ch['sharpe']-co['sharpe'],'maxdd_delta':ch['max_drawdown']-co['max_drawdown']},'correlation':{'challenger_core':corr(q.challenger,q.core),'dbmf_p305':corr(q.dbmf,q.p305)},'downside_corr_when_core_negative':corr(neg.challenger,neg.core),'rolling_12m_matched_excess':roll_excess(q)}

def evaluate():
    plan=json.loads(PLAN.read_text())
    if not plan['coverage_eligible']:
        out={'schema':'research.p423_p305_dbmf_coverage_r2.v1','workload_id':'P423_P305_DBMF_COVERAGE_VALID_R2','decision':'DATA_REPRESENTATION_LIMIT','coverage_plan':plan,'scientific_consequence':'Coverage preflight failed before performance evaluation. Preserve prior P305+DBMF common-sample economics as NEEDS_CONFIRMATION; do not move dates, weights, products, costs, or thresholds to rescue.'}
        OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision']},sort_keys=True)); return
    m=pd.read_csv(PRICES,index_col='date',parse_dates=True)
    d=derived(m)
    q=pd.DataFrame(index=d.index)
    q['p305']=d.p305; q['dbmf']=d.dbmf; q['challenger']=.5*d.p305+.5*d.dbmf; q['challenger_ctl']=.5*d.p305ctl+.5*d.bil; q['core']=.5*d.p305+.5*d.srln; q['core_ctl']=.5*d.p305ctl+.5*d.loanctl
    q=q.dropna()
    full=ev(q)
    chronology={}
    for b in plan['blocks']:
        z=q.loc[b['start']:b['end']]; chronology[f"block_{b['block']}"]=ev(z)
    pos=sum(v['challenger_matched_excess_cagr']>0 for v in chronology.values()); opp=full['opportunity_cost_vs_core']; roll=full['rolling_12m_matched_excess']
    passed=full['challenger_matched_excess_cagr']>0 and pos>=2 and roll['positive_fraction'] is not None and roll['positive_fraction']>=.65 and (opp['cagr_delta']>0 or opp['sharpe_delta']>0 or opp['maxdd_delta']>0)
    decision='MARGINAL_PORTFOLIO_UTILITY_SUPPORTED_COVERAGE_VALID' if passed else 'MARGINAL_PORTFOLIO_UTILITY_NOT_SUPPORTED_COVERAGE_VALID'
    out={'schema':'research.p423_p305_dbmf_coverage_r2.v1','workload_id':'P423_P305_DBMF_COVERAGE_VALID_R2','claim':'Adjudicate the unchanged fixed 50% P305 + 50% DBMF challenger versus the frozen P249/P373 core only after a performance-blind causal-coverage preflight establishes three usable chronology blocks.','coverage_plan':plan,'contract':{'challenger':'50% P305 + 50% DBMF','p305':'50% SPMO + 50% IJS','p305_control':'50% SPY + 50% IJR','dbmf_control':'BIL','core_stack':'50% P305 + 50% SRLN','p373_control':'causal prior-24m HYG+SHY','endpoint_cost_bps_each':25,'weight_search':False,'post_result_window_movement':False},'full_sample':full,'chronology':chronology,'positive_challenger_blocks':pos,'decision_rule':'Support only if coverage preflight passes, full after-cost matched excess is positive, >=2/3 predeclared coverage-valid blocks are positive, >=65% rolling 12m matched excess windows are positive, and at least one CAGR/Sharpe/maxDD dimension improves versus fixed core.','decision':decision,'scientific_consequence':'Preserve P305 and DBMF standalone evidence regardless. This result changes only the scientific confidence in marginal combination utility; Coordinator retains ranking/allocation authority.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({'decision':decision,'coverage_blocks':[b['observations'] for b in plan['blocks']],'full_matched_excess_pp':round(100*full['challenger_matched_excess_cagr'],3),'chronology_excess_pp':[round(100*v['challenger_matched_excess_cagr'],3) for v in chronology.values()],'rolling_positive_fraction':roll['positive_fraction'],'opportunity_vs_core':{k:round(v,4) for k,v in opp.items()}},sort_keys=True))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=['preflight','evaluate'],required=True); a=ap.parse_args()
    preflight() if a.mode=='preflight' else evaluate()
