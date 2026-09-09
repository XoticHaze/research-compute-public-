#!/usr/bin/env python3
import json, math, os, re
from pathlib import Path
import numpy as np
import pandas as pd

SOURCE_REPO='mbytes21/MNQ_DATA'
SOURCE_COMMIT='fc5508e2c152938d6d9eb70a36b888ae26107176'
FOUNDRY_COMMIT='eafe3cb8f62855b4321cb16f96b3887b85710cbd'
SOURCE_TZ='America/New_York'
COSTS=(2.5,5.0,10.0)
CONTRACT_RE=re.compile(r'^MNQ (?P<month>03|06|09|12)-(?P<year>\d{2})$')
LAST_RE=re.compile(r'^(?P<date>\d{8})\.Last\.csv$')
REQUIRED=('datetime','open','high','low','close','volume')


def contract_key(name):
    m=CONTRACT_RE.fullmatch(name)
    if not m: raise ValueError(f'unsupported contract {name}')
    return 2000+int(m.group('year')),int(m.group('month'))


def load_minutes(path):
    f=pd.read_csv(path)
    if tuple(f.columns)!=REQUIRED: raise ValueError(f'{path}: schema={tuple(f.columns)}')
    ts=pd.to_datetime(f['datetime'],errors='raise')
    if ts.dt.tz is not None: raise ValueError('source timestamp unexpectedly tz-aware')
    f=f.copy(); f['timestamp']=ts.dt.tz_localize(SOURCE_TZ,ambiguous='infer',nonexistent='raise').dt.tz_convert('UTC')-pd.Timedelta(minutes=1)
    for c in REQUIRED[1:]: f[c]=pd.to_numeric(f[c],errors='raise')
    if f.timestamp.duplicated().any() or not f.timestamp.is_monotonic_increasing: raise ValueError(f'{path}: timestamp integrity')
    return f[['timestamp','open','high','low','close','volume']]


def inventory_sessions(root):
    frames={}; rows=[]
    dirs=sorted([p for p in root.glob('MNQ ??-??') if p.is_dir() and CONTRACT_RE.fullmatch(p.name)],key=lambda p:contract_key(p.name))
    for d in dirs:
        for p in sorted(d.glob('*.Last.csv')):
            m=LAST_RE.fullmatch(p.name)
            if not m: continue
            frame=load_minutes(p)
            if frame.empty: continue
            session=m.group('date'); frame=frame.copy(); frame['source_contract']=d.name; frame['source_session']=session
            frames[(session,d.name)]=frame
            rows.append({'session':session,'contract':d.name,'volume':float(frame.volume.sum()),'rows':int(len(frame))})
    if not rows: raise ValueError('no MNQ Last.csv sessions')
    return frames,pd.DataFrame(rows).sort_values(['session','contract']).reset_index(drop=True)


def build_roll_schedule(inv,confirmation_sessions=2):
    contracts=sorted(inv.contract.unique(),key=contract_key); sessions=sorted(inv.session.unique()); vol={(r.session,r.contract):float(r.volume) for r in inv.itertuples()}
    active=0; streak=0; pending=False; out=[]
    for session in sessions:
        reason='hold'
        if pending and active+1<len(contracts): active+=1; streak=0; pending=False; reason='volume_crossover_confirmed_prior_session'
        while active+1<len(contracts) and vol.get((session,contracts[active]),0)<=0 and vol.get((session,contracts[active+1]),0)>0:
            active+=1; streak=0; reason='current_contract_unavailable'
        current=contracts[active]; cv=vol.get((session,current),0); nxt=contracts[active+1] if active+1<len(contracts) else None; nv=vol.get((session,nxt),0) if nxt else 0
        if cv<=0:
            later=[c for c in contracts[active+1:] if vol.get((session,c),0)>0]
            if later:
                active=contracts.index(later[0]); current=contracts[active]; cv=vol.get((session,current),0); nxt=contracts[active+1] if active+1<len(contracts) else None; nv=vol.get((session,nxt),0) if nxt else 0; streak=0; reason='later_contract_availability_fallback'
        if cv>0 and nv>cv:
            streak+=1
            if streak>=confirmation_sessions: pending=True
        elif cv>0: streak=0
        out.append({'session':session,'selected_contract':current,'selected_volume':cv,'next_contract':nxt,'next_volume':nv,'next_dominance_streak':streak,'roll_reason':reason})
    s=pd.DataFrame(out)
    keys=[contract_key(c) for c in s.selected_contract]
    if keys!=sorted(keys): raise ValueError('roll schedule moved backward')
    return s


def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod()
    if len(r)<2 or eq.iloc[-1]<=0: return {'months':len(r),'cagr':None,'sharpe_rf0':None,'max_dd':None}
    years=len(r)/12; vol=float(r.std(ddof=1)*math.sqrt(12))
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
    daily={}
    for (session,contract),frame in frames.items():
        if not frame.empty: daily[(session,contract)]={'close':float(frame.close.iloc[-1]),'volume':float(frame.volume.sum())}
    by_contract={}
    for (session,contract),v in daily.items(): by_contract.setdefault(contract,[]).append((session,v['close']))
    prev={}
    for contract,rows in by_contract.items():
        prior=None
        for session,close in sorted(rows): prev[(session,contract)]=prior; prior=close
    rows=[]; prior_sel=None; rolls=0
    for row in schedule.itertuples():
        key=(str(row.session),str(row.selected_contract)); v=daily.get(key); pc=prev.get(key)
        if not v or pc is None or pc<=0: continue
        if prior_sel is not None and prior_sel!=row.selected_contract: rolls+=1
        rows.append({'session':str(row.session),'contract':str(row.selected_contract),'return':v['close']/pc-1.0,'close_native':v['close'],'selected_volume':float(row.selected_volume),'roll_reason':str(row.roll_reason)})
        prior_sel=row.selected_contract
    d=pd.DataFrame(rows); d['date']=pd.to_datetime(d.session,format='%Y%m%d',errors='raise'); d=d.set_index('date').sort_index(); d['chain_index']=(1+d['return']).cumprod()
    return d,rolls


def evaluate(chain,cost,start=None):
    idx=chain.chain_index; mret=(1+chain['return']).resample('ME').prod()-1; mom252=idx/idx.shift(252)-1; msig=mom252.resample('ME').last(); w=(msig.shift(1)>0).astype(float); turnover=w.diff().abs().fillna(w.abs()); cand=w*mret-turnover*cost/10000; baseline=float(w.mean())*mret; z=pd.concat([cand.rename('candidate'),baseline.rename('baseline'),w.rename('weight')],axis=1).dropna()
    if start: z=z.loc[z.index>=pd.Timestamp(start)]
    fs=folds(z.candidate,z.baseline); cm,bm=metrics(z.candidate),metrics(z.baseline)
    return {'start':z.index.min().date().isoformat(),'end':z.index.max().date().isoformat(),'candidate':cm,'matched_static':bm,'excess_cagr':cm['cagr']-bm['cagr'],'mean_exposure':float(z.weight.mean()),'positive_folds':sum(x['excess_cagr']>0 for x in fs),'folds':fs}


def main():
    source=Path(os.environ.get('MNQ_SOURCE_ROOT','/tmp/mnq-source/plaintext_csv')); frames,inventory=inventory_sessions(source); schedule=build_roll_schedule(inventory,2); chain,rolls=build_return_chain(frames,schedule)
    out={'schema':'research.mnq_foundry_individual_contract_trend_r9','classification':'FOUNDRY_ADMITTED_PROVISIONAL_INDIVIDUAL_CONTRACT_RESEARCH_EVIDENCE','source':{'repo':SOURCE_REPO,'commit':SOURCE_COMMIT,'timezone':SOURCE_TZ,'timezone_evidence':'research-foundry jobs/evidence/mnq_external_timezone_calibration_v1.json','foundry_repo':'XoticHaze/research-foundry','foundry_commit':FOUNDRY_COMMIT,'roll_logic_origin':'external_mnq_training.build_roll_schedule semantics copied exactly into public harness because public Actions token cannot clone private Foundry','confirmation_sessions':2,'price_adjustment':'none','return_chain_rule':'selected-contract daily close / same-contract prior available-session close; no cross-contract raw price return'},'chain':{'sessions':int(len(chain)),'start':chain.index.min().date().isoformat(),'end':chain.index.max().date().isoformat(),'contracts':sorted(chain.contract.unique()),'roll_count':int(rolls)},'scientific_contract':{'mechanism':'prior 252 completed-session return-chain sign sampled monthly; next month long/cash','costs_bps':list(COSTS),'matched_control':'static exposure to same admitted MNQ return chain at candidate mean exposure','windows':['full','2022-forward'],'no_parameter_search':True,'no_mini_substitution':True,'research_only':True},'tests':{}}
    for bp in COSTS: out['tests'][str(bp)]={'full':evaluate(chain,bp),'2022_forward':evaluate(chain,bp,'2022-01-01')}
    p=out['tests']['5.0']; full=p['full']; recent=p['2022_forward']; supported=full['excess_cagr']>0 and full['positive_folds']>=3 and full['candidate']['sharpe_rf0']>=full['matched_static']['sharpe_rf0'] and recent['excess_cagr']>0 and recent['positive_folds']>=3
    out['decision']='MNQ_INDIVIDUAL_CONTRACT_TREND_SUPPORTED' if supported else 'MNQ_INDIVIDUAL_CONTRACT_TREND_NOT_SUPPORTED'; out['next_step']='If supported, compare NQ E-mini on independent dated-contract history and require family-level consistency; if not supported, reject only this frozen trend mechanism.'
    Path('mnq_foundry_trend_r9.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps({'decision':out['decision'],'chain':out['chain'],'primary':p},sort_keys=True))
if __name__=='__main__': main()
