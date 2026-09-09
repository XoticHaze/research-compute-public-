#!/usr/bin/env python3
import hashlib,io,json,time
from pathlib import Path
from urllib.request import Request,urlopen
import numpy as np
import pandas as pd
from huggingface_hub import HfApi,hf_hub_download

HF_REPO='lynx1231/historical-futures-data-sample'
AXB='axb0306/cme-futures-ohlc'
UA='Mozilla/5.0 research-only hf-es-continuous-adjudication-r16'

def get(url):
    last=None
    for a in range(1,6):
        try:return urlopen(Request(url,headers={'User-Agent':UA}),timeout=30).read()
        except Exception as e:last=e; time.sleep(a*2)
    raise RuntimeError(f'{type(last).__name__}:{last}')

def axb_daily(root):
    raw=get(f'https://api.github.com/repos/{AXB}/contents/{root}?ref=main'); items=json.loads(raw); fs=sorted([x for x in items if x['name'].startswith(root+'_daily_') and x['name'].endswith('.csv')],key=lambda x:x['name']); item=fs[-1]; b=get(item['download_url']); f=pd.read_csv(io.BytesIO(b)); lc={str(c).lower():c for c in f.columns}; dc=next(lc[k] for k in ('date','datetime','timestamp') if k in lc); idx=pd.to_datetime(f[dc],utc=True).dt.tz_convert(None); s=pd.Series(pd.to_numeric(f[lc['close']],errors='raise').values,index=idx,name=root).dropna().sort_index(); return s,{'path':item['path'],'blob_sha':item['sha'],'sha256':hashlib.sha256(b).hexdigest()}

def main():
    api=HfApi(); info=api.dataset_info(HF_REPO); rev=info.sha; files=hf_hub_download(HF_REPO,'files.csv',repo_type='dataset',revision=rev); mf=pd.read_csv(files); lc={str(c).lower():c for c in mf.columns}; rootc=lc['root']; freqc=next(lc[k] for k in ('frequency','freq','interval') if k in lc); pathc=next(lc[k] for k in ('path','file','filename') if k in lc); es=mf[(mf[rootc].astype(str).str.upper()=='ES') & (mf[freqc].astype(str).str.lower().str.contains('daily'))]
    rows=[]; prov=[]
    for _,m in es.iterrows():
        rel=str(m[pathc]); p=hf_hub_download(HF_REPO,rel,repo_type='dataset',revision=rev); raw=Path(p).read_bytes(); f=pd.read_parquet(p); c={str(x).lower():x for x in f.columns}; date=pd.to_datetime(f[c['date']],errors='raise'); valid=(pd.to_numeric(f[c['volume']],errors='coerce').fillna(0)>0)&pd.concat([pd.to_numeric(f[c[k]],errors='coerce') for k in ('open','high','low','close')],axis=1).notna().all(axis=1); q=f.loc[valid].copy(); q['date_norm']=date.loc[valid]; q['contract']=q[c['contract_symbol']].astype(str); q['close_norm']=pd.to_numeric(q[c['close']],errors='raise'); q['volume_norm']=pd.to_numeric(q[c['volume']],errors='raise'); rows.append(q[['date_norm','contract','close_norm','volume_norm']]); prov.append({'path':rel,'sha256':hashlib.sha256(raw).hexdigest(),'rows_valid':int(valid.sum()),'rows_rejected':int((~valid).sum())})
    x=pd.concat(rows,ignore_index=True).sort_values(['date_norm','contract']); dates=sorted(x.date_norm.unique()); daily=[]
    # causal active-contract choice: today's held contract is the highest-volume eligible contract on previous date.
    prev_choice=None
    bydate={d:g for d,g in x.groupby('date_norm')}
    for i in range(1,len(dates)):
        pdte=dates[i-1]; dte=dates[i]; prev=bydate[pdte]; cur=bydate[dte]; choice=str(prev.sort_values('volume_norm',ascending=False).iloc[0].contract); pprev=prev[prev.contract==choice]; pcur=cur[cur.contract==choice]
        if pprev.empty or pcur.empty: continue
        ret=float(pcur.iloc[-1].close_norm/pprev.iloc[-1].close_norm-1); daily.append({'date':pd.Timestamp(dte),'contract':choice,'return':ret,'rolled':prev_choice is not None and choice!=prev_choice}); prev_choice=choice
    chain=pd.DataFrame(daily).set_index('date').sort_index(); esref,esp=axb_daily('ES'); mesref,mesp=axb_daily('MES'); refs=pd.concat([chain['return'].rename('dated'),esref.pct_change().rename('ES'),mesref.pct_change().rename('MES')],axis=1).dropna()
    def stats(col):
        d=(refs['dated']-refs[col])*10000; return {'sessions':len(refs),'correlation':float(refs[['dated',col]].corr().iloc[0,1]),'median_abs_difference_bps':float(d.abs().median()),'p95_abs_difference_bps':float(d.abs().quantile(.95)),'same_sign_fraction':float((np.sign(refs.dated)==np.sign(refs[col])).mean())}
    top=[]
    refs['es_diff_bps']=(refs.dated-refs.ES)*10000; refs['mes_diff_bps']=(refs.dated-refs.MES)*10000
    for dt,r in refs.assign(maxabs=np.maximum(refs.es_diff_bps.abs(),refs.mes_diff_bps.abs())).nlargest(15,'maxabs').iterrows(): top.append({'date':dt.date().isoformat(),'dated_return':float(r.dated),'es_return':float(r.ES),'mes_return':float(r.MES),'es_difference_bps':float(r.es_diff_bps),'mes_difference_bps':float(r.mes_diff_bps)})
    out={'schema':'research.hf_es_continuous_adjudication_r16','classification':'DATED_CONTRACT_SOURCE_ADJUDICATION_NOT_ALPHA_EVIDENCE','source':{'dataset':HF_REPO,'revision':rev,'contracts':prov,'license_metadata':None},'chain':{'rule':'finite positive-volume dated ES rows only; select next session contract by previous session volume; same-contract close-to-close return; no back-adjustment','sessions':len(chain),'rolls':int(chain.rolled.sum()),'start':chain.index.min().date().isoformat(),'end':chain.index.max().date().isoformat()},'reference':{'ES':esp,'MES':mesp},'comparison':{'ES':stats('ES'),'MES':stats('MES'),'top_discrepancies':top},'decision':None}
    esstat=out['comparison']['ES']; messtat=out['comparison']['MES']
    if esstat['correlation']>messtat['correlation'] and esstat['median_abs_difference_bps']<=messtat['median_abs_difference_bps']:
        out['decision']='DATED_ES_TRACKS_ES_CONTINUOUS_MORE_CLOSELY'
    elif messtat['correlation']>esstat['correlation'] and messtat['median_abs_difference_bps']<=esstat['median_abs_difference_bps']:
        out['decision']='DATED_ES_TRACKS_MES_CONTINUOUS_MORE_CLOSELY'
    else: out['decision']='CONTINUOUS_REPRESENTATION_MIXED'
    out['consequence']='Use this only to localize continuous-series artifacts and choose the next dated-contract validation. License remains unresolved, so no canonical redistribution or promotion is authorized.'
    Path('hf_es_continuous_adjudication_r16.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
