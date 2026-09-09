#!/usr/bin/env python3
import io,json,time,hashlib
from pathlib import Path
from urllib.request import Request,urlopen
import numpy as np
import pandas as pd
import mnq_foundry_trend_r9 as r9

UA='Mozilla/5.0 research-only mnq-chain-fidelity-r11'
AXB_API='https://api.github.com/repos/axb0306/cme-futures-ohlc/contents/MNQ?ref=main'

def get(url):
    last=None
    for a in range(1,6):
        try:return urlopen(Request(url,headers={'User-Agent':UA}),timeout=30).read(),a
        except Exception as e:last=e; time.sleep(a*2)
    raise RuntimeError(f'{type(last).__name__}: {last}')

def axb_daily():
    raw,a=get(AXB_API); items=json.loads(raw); files=sorted([x for x in items if x['name'].startswith('MNQ_daily_') and x['name'].endswith('.csv')],key=lambda x:x['name'])
    if not files: raise RuntimeError('no MNQ daily file')
    item=files[-1]; b,batt=get(item['download_url']); f=pd.read_csv(io.BytesIO(b)); lower={str(c).lower():c for c in f.columns}; dc=next((lower[x] for x in ('date','datetime','timestamp') if x in lower),None); cc=lower.get('close')
    if dc is None or cc is None: raise RuntimeError(f'schema {list(f.columns)}')
    idx=pd.to_datetime(f[dc],errors='raise',utc=True).dt.tz_convert(None); s=pd.Series(pd.to_numeric(f[cc],errors='raise').values,index=idx,name='axb_close').dropna(); s=s[~s.index.duplicated(keep='last')].sort_index()
    return s,{'path':item['path'],'github_blob_sha':item['sha'],'sha256':hashlib.sha256(b).hexdigest(),'rows':len(s),'listing_sha256':hashlib.sha256(raw).hexdigest(),'attempts':{'listing':a,'file':batt}}

def main():
    source=Path('/tmp/mnq-source/plaintext_csv'); frames,inv=r9.inventory_sessions(source); sched=r9.build_roll_schedule(inv,2); chain,rolls=r9.build_return_chain(frames,sched); axb,prov=axb_daily()
    a=chain['return'].rename('admitted_chain'); b=axb.pct_change().rename('external_continuous'); z=pd.concat([a,b],axis=1).dropna(); z['diff_bps']=(z.admitted_chain-z.external_continuous)*10000; z['abs_bps']=z.diff_bps.abs()
    corr=float(z[['admitted_chain','external_continuous']].corr().iloc[0,1]); same=float((np.sign(z.admitted_chain)==np.sign(z.external_continuous)).mean()); top=[]
    for dt,row in z.nlargest(12,'abs_bps').iterrows(): top.append({'date':dt.date().isoformat(),'admitted_return':float(row.admitted_chain),'external_return':float(row.external_continuous),'difference_bps':float(row.diff_bps)})
    out={'schema':'research.mnq_chain_fidelity_r11','classification':'IMPLEMENTATION_AND_SOURCE_FIDELITY_DIAGNOSTIC_NOT_ALPHA_RESULT','source_chain':{'repo':r9.SOURCE_REPO,'commit':r9.SOURCE_COMMIT,'sessions':len(chain),'rolls':rolls},'reference':{'repo':'axb0306/cme-futures-ohlc','role':'independent recent continuous overlap only','provenance':prov},'overlap':{'start':z.index.min().date().isoformat(),'end':z.index.max().date().isoformat(),'sessions':len(z),'daily_return_correlation':corr,'same_sign_fraction':same,'median_abs_difference_bps':float(z.abs_bps.median()),'p95_abs_difference_bps':float(z.abs_bps.quantile(.95)),'top_discrepancies':top},'decision':None}
    out['decision']='MNQ_CHAIN_FIDELITY_SUPPORTED' if corr>=.995 and same>=.98 and out['overlap']['median_abs_difference_bps']<=3 else 'MNQ_CHAIN_FIDELITY_REQUIRES_DIAGNOSIS'
    out['consequence']='If supported, R9 negative trend result is not dismissed as a simple chain-construction bug. If diagnosis required, R9 remains scientifically inconclusive until exact seam/session mismatch is resolved.'
    Path('mnq_chain_fidelity_r11.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps({'decision':out['decision'],'overlap':out['overlap']},sort_keys=True))
if __name__=='__main__':main()
