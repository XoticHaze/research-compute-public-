#!/usr/bin/env python3
import json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

FOUNDRY_SRC = os.environ.get('FOUNDRY_SRC', '/tmp/research-foundry/src')
sys.path.insert(0, FOUNDRY_SRC)
from foundry_mm_ml.external_mnq_training import inventory_sessions, build_roll_schedule

SOURCE_REPO='mbytes21/MNQ_DATA'
SOURCE_COMMIT='fc5508e2c152938d6d9eb70a36b888ae26107176'
FOUNDRY_COMMIT='eafe3cb8f62855b4321cb16f96b3887b85710cbd'
SOURCE_TZ='America/New_York'
COSTS=(2.5,5.0,10.0)


def metrics(r):
    r=pd.Series(r,dtype=float).dropna()
    eq=(1+r).cumprod()
    if len(r)<2 or eq.iloc[-1] <= 0:
        return {'months':len(r),'cagr':None,'sharpe_rf0':None,'max_dd':None}
    years=len(r)/12
    vol=float(r.std(ddof=1)*math.sqrt(12))
    return {'months':len(r),'cagr':float(eq.iloc[-1]**(1/years)-1),'sharpe_rf0':float(r.mean()*12/vol) if vol>0 else None,'max_dd':float((eq/eq.cummax()-1).min())}


def cagr(r): return metrics(r)['cagr']


def folds(c,b,n=5):
    z=pd.concat([c.rename('c'),b.rename('b')],axis=1).dropna(); out=[]
    for i,idx in enumerate(np.array_split(np.arange(len(z)),n),1):
        q=z.iloc[idx]
        if len(q)<2: continue
        out.append({'fold':i,'start':q.index.min().date().isoformat(),'end':q.index.max().date().isoformat(),'excess_cagr':cagr(q.c)-cagr(q.b)})
    return out


def build_return_chain(frames,schedule):
    # Daily close for every available contract/session. Return on a roll day is measured
    # within the newly selected contract versus that same contract's prior available session,
    # avoiding a synthetic cross-contract price jump without modifying source-native prices.
    daily={}
    for (session,contract),frame in frames.items():
        if frame.empty: continue
        daily[(session,contract)]={'close':float(frame['close'].iloc[-1]),'volume':float(frame['volume'].sum())}
    by_contract={}
    for (session,contract),v in daily.items(): by_contract.setdefault(contract,[]).append((session,v['close']))
    prev_close={}
    for contract,rows in by_contract.items():
        rows=sorted(rows)
        prior=None
        for session,close in rows:
            prev_close[(session,contract)]=prior
            prior=close
    rows=[]; prior_selected=None; rolls=0
    for row in schedule.itertuples():
        key=(str(row.session),str(row.selected_contract)); v=daily.get(key); pc=prev_close.get(key)
        if not v or pc is None or pc<=0: continue
        if prior_selected is not None and prior_selected!=row.selected_contract: rolls+=1
        ret=v['close']/pc-1.0
        rows.append({'session':str(row.session),'contract':str(row.selected_contract),'return':ret,'close_native':v['close'],'selected_volume':float(row.selected_volume),'roll_reason':str(row.roll_reason)})
        prior_selected=row.selected_contract
    d=pd.DataFrame(rows)
    d['date']=pd.to_datetime(d.session,format='%Y%m%d',errors='raise')
    d=d.set_index('date').sort_index()
    d['chain_index']=(1+d['return']).cumprod()
    return d,rolls


def evaluate(chain,cost,start=None):
    idx=chain.chain_index
    m_idx=idx.resample('ME').last().dropna()
    mret=(1+chain['return']).resample('ME').prod()-1
    # Signal uses the prior 252 completed session returns. It is sampled at month end
    # and shifted one month before taking exposure.
    mom252=idx/idx.shift(252)-1
    msig=mom252.resample('ME').last().reindex(m_idx.index)
    w=(msig.shift(1)>0).astype(float)
    turnover=w.diff().abs().fillna(w.abs())
    cand=w*mret-turnover*cost/10000
    baseline=float(w.mean())*mret
    z=pd.concat([cand.rename('candidate'),baseline.rename('baseline'),w.rename('weight')],axis=1).dropna()
    if start: z=z.loc[z.index>=pd.Timestamp(start)]
    fs=folds(z.candidate,z.baseline)
    cm,bm=metrics(z.candidate),metrics(z.baseline)
    return {'start':z.index.min().date().isoformat(),'end':z.index.max().date().isoformat(),'candidate':cm,'matched_static':bm,'excess_cagr':cm['cagr']-bm['cagr'],'mean_exposure':float(z.weight.mean()),'positive_folds':sum(x['excess_cagr']>0 for x in fs),'folds':fs}


def main():
    source=Path(os.environ.get('MNQ_SOURCE_ROOT','/tmp/mnq-source/plaintext_csv'))
    frames,inventory=inventory_sessions(source,source_timezone=SOURCE_TZ)
    schedule=build_roll_schedule(inventory,confirmation_sessions=2)
    chain,rolls=build_return_chain(frames,schedule)
    out={'schema':'research.mnq_foundry_individual_contract_trend_r9','classification':'FOUNDRY_ADMITTED_PROVISIONAL_INDIVIDUAL_CONTRACT_RESEARCH_EVIDENCE','source':{'repo':SOURCE_REPO,'commit':SOURCE_COMMIT,'timezone':SOURCE_TZ,'timezone_evidence':'foundry jobs/evidence/mnq_external_timezone_calibration_v1.json','foundry_repo':'XoticHaze/research-foundry','foundry_commit':FOUNDRY_COMMIT,'roll_builder':'foundry_mm_ml.external_mnq_training.build_roll_schedule','confirmation_sessions':2,'price_adjustment':'none','return_chain_rule':'on each selected session, return uses selected contract close divided by same contract prior available-session close; no cross-contract raw price return'},'chain':{'sessions':int(len(chain)),'start':chain.index.min().date().isoformat(),'end':chain.index.max().date().isoformat(),'contracts':sorted(chain.contract.unique()),'roll_count':int(rolls)},'scientific_contract':{'mechanism':'prior 252 completed-session return-chain sign sampled monthly; next month long/cash','costs_bps':list(COSTS),'matched_control':'static exposure to same admitted MNQ return chain at candidate mean exposure','windows':['full','2022-forward'],'no_parameter_search':True,'no_mini_substitution':True,'research_only':True},'tests':{}}
    for bp in COSTS:
        out['tests'][str(bp)]={'full':evaluate(chain,bp),'2022_forward':evaluate(chain,bp,'2022-01-01')}
    p=out['tests']['5.0']; full=p['full']; recent=p['2022_forward']
    supported=full['excess_cagr']>0 and full['positive_folds']>=3 and full['candidate']['sharpe_rf0']>=full['matched_static']['sharpe_rf0'] and recent['excess_cagr']>0 and recent['positive_folds']>=3
    out['decision']='MNQ_INDIVIDUAL_CONTRACT_TREND_SUPPORTED' if supported else 'MNQ_INDIVIDUAL_CONTRACT_TREND_NOT_SUPPORTED'
    out['next_step']='If supported, compare NQ E-mini on independent dated-contract history and require family-level consistency; if not supported, do not reject MNQ broadly, only this frozen trend mechanism.'
    Path('mnq_foundry_trend_r9.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'decision':out['decision'],'chain':out['chain'],'primary':p},sort_keys=True))

if __name__=='__main__': main()
