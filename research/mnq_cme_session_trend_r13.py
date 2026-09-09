#!/usr/bin/env python3
import io,json,time,hashlib
from datetime import timedelta
from pathlib import Path
from urllib.request import Request,urlopen
import numpy as np
import pandas as pd
import mnq_foundry_trend_r9 as r9

UA='Mozilla/5.0 research-only mnq-cme-session-trend-r13'
AXB_API='https://api.github.com/repos/axb0306/cme-futures-ohlc/contents/MNQ?ref=main'

def trading_date(ts):
    local=ts.dt.tz_convert('America/Chicago')
    base=local.dt.date
    return pd.Series([d+timedelta(days=1) if (h>17 or (h==17 and m>=0)) else d for d,h,m in zip(base,local.dt.hour,local.dt.minute)],index=ts.index)

def build_session_inventory(root):
    rows=[]
    for d in sorted([p for p in root.glob('MNQ ??-??') if p.is_dir() and r9.CONTRACT_RE.fullmatch(p.name)],key=lambda p:r9.contract_key(p.name)):
        pieces=[]
        for p in sorted(d.glob('*.Last.csv')):
            if not r9.LAST_RE.fullmatch(p.name): continue
            f=r9.load_minutes(p); f=f.copy(); f['trading_date']=trading_date(f.timestamp); pieces.append(f)
        if not pieces: continue
        allf=pd.concat(pieces,ignore_index=True).sort_values('timestamp')
        for td,g in allf.groupby('trading_date',sort=True):
            rows.append({'session':pd.Timestamp(td).strftime('%Y%m%d'),'contract':d.name,'volume':float(g.volume.sum()),'rows':int(len(g)),'close':float(g.close.iloc[-1]),'first_utc':g.timestamp.iloc[0].isoformat(),'last_utc':g.timestamp.iloc[-1].isoformat()})
    inv=pd.DataFrame(rows).sort_values(['session','contract']).reset_index(drop=True)
    if inv.empty: raise RuntimeError('empty CME session inventory')
    return inv

def build_chain(inv):
    sched=r9.build_roll_schedule(inv[['session','contract','volume','rows']],2); daily={(str(x.session),str(x.contract)):float(x.close) for x in inv.itertuples()}; by={}
    for (s,c),close in daily.items(): by.setdefault(c,[]).append((s,close))
    prev={}
    for c,vals in by.items():
        prior=None
        for s,close in sorted(vals): prev[(s,c)]=prior; prior=close
    rows=[]; lastc=None; rolls=0
    for x in sched.itertuples():
        k=(str(x.session),str(x.selected_contract)); close=daily.get(k); pc=prev.get(k)
        if close is None or pc is None or pc<=0: continue
        if lastc is not None and lastc!=x.selected_contract: rolls+=1
        rows.append({'date':pd.to_datetime(str(x.session),format='%Y%m%d'),'contract':str(x.selected_contract),'return':close/pc-1,'close_native':close,'roll_reason':str(x.roll_reason)})
        lastc=x.selected_contract
    d=pd.DataFrame(rows).set_index('date').sort_index(); d['chain_index']=(1+d['return']).cumprod(); return d,sched,rolls

def get(url):
    last=None
    for a in range(1,6):
        try:return urlopen(Request(url,headers={'User-Agent':UA}),timeout=30).read()
        except Exception as e:last=e; time.sleep(a*2)
    raise RuntimeError(f'{type(last).__name__}:{last}')

def axb():
    raw=get(AXB_API); items=json.loads(raw); fs=sorted([x for x in items if x['name'].startswith('MNQ_daily_') and x['name'].endswith('.csv')],key=lambda x:x['name']); item=fs[-1]; b=get(item['download_url']); f=pd.read_csv(io.BytesIO(b)); l={str(c).lower():c for c in f.columns}; dc=next(l[k] for k in ('date','datetime','timestamp') if k in l); idx=pd.to_datetime(f[dc],utc=True).dt.tz_convert(None); s=pd.Series(pd.to_numeric(f[l['close']]).values,index=idx).dropna(); return s,{'path':item['path'],'blob_sha':item['sha'],'sha256':hashlib.sha256(b).hexdigest()}
def main():
    root=Path('/tmp/mnq-source/plaintext_csv'); inv=build_session_inventory(root); chain,sched,rolls=build_chain(inv); ref,prov=axb(); z=pd.concat([chain['return'].rename('chain'),ref.pct_change().rename('ref')],axis=1).dropna(); diff=(z.chain-z.ref)*10000; corr=float(z.corr().iloc[0,1]); same=float((np.sign(z.chain)==np.sign(z.ref)).mean()); fidelity={'start':z.index.min().date().isoformat(),'end':z.index.max().date().isoformat(),'sessions':len(z),'correlation':corr,'same_sign_fraction':same,'median_abs_difference_bps':float(diff.abs().median()),'p95_abs_difference_bps':float(diff.abs().quantile(.95))}
    tests={}
    for bp in r9.COSTS: tests[str(bp)]={'full':r9.evaluate(chain,bp),'2022_forward':r9.evaluate(chain,bp,'2022-01-01')}
    fidelity_ok=corr>=.995 and same>=.98 and fidelity['median_abs_difference_bps']<=3
    p=tests['5.0']; science_ok=p['full']['excess_cagr']>0 and p['full']['positive_folds']>=3 and p['full']['candidate']['sharpe_rf0']>=p['full']['matched_static']['sharpe_rf0'] and p['2022_forward']['excess_cagr']>0 and p['2022_forward']['positive_folds']>=3
    decision='MNQ_CME_SESSION_TREND_SUPPORTED' if fidelity_ok and science_ok else ('MNQ_CME_SESSION_TREND_NOT_SUPPORTED' if fidelity_ok else 'MNQ_CME_SESSION_CHAIN_INCONCLUSIVE')
    out={'schema':'research.mnq_cme_session_trend_r13','classification':'FOUNDRY_SOURCE_CME_SESSION_NORMALIZED_RESEARCH_EVIDENCE','correction_reason':'R11 showed calendar-file daily returns were not faithful to independent MNQ overlap; R13 reconstructs actual CME Globex trading dates at 17:00 America/Chicago before roll scheduling and economic returns','source':{'repo':r9.SOURCE_REPO,'commit':r9.SOURCE_COMMIT,'timestamp_timezone':r9.SOURCE_TZ,'cme_session_boundary':'17:00 America/Chicago','reference':prov},'chain':{'sessions':len(chain),'start':chain.index.min().date().isoformat(),'end':chain.index.max().date().isoformat(),'roll_count':rolls,'contracts':sorted(chain.contract.unique())},'fidelity':fidelity,'tests':tests,'decision':decision,'scientific_result_valid':bool(fidelity_ok),'next_step':'Only interpret the trend economics if fidelity passes. If fidelity still fails, compare exact session closes around top mismatch dates against individual source bars before any model judgment.'}
    Path('mnq_cme_session_trend_r13.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps({'decision':decision,'fidelity':fidelity,'primary':p},sort_keys=True))
if __name__=='__main__':main()
