from __future__ import annotations
import io,json,math,urllib.request,zipfile
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p506_rwj_ff5_independent_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
URL='https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip'
WINDOWS={'2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}
BLOCKS={'2010_2014':('2010-01-01','2014-12-31'),'2015_2019':('2015-01-01','2019-12-31'),'2020_plus':('2020-01-01',None)}
HURDLE=.0025

def load_ff5():
    data=urllib.request.urlopen(URL,timeout=30).read()
    z=zipfile.ZipFile(io.BytesIO(data)); name=z.namelist()[0]
    lines=z.read(name).decode('utf-8','replace').splitlines()
    start=next(i for i,s in enumerate(lines) if s.strip().startswith(',Mkt-RF'))
    end=next(i for i in range(start+1,len(lines)) if not lines[i].strip())
    f=pd.read_csv(io.StringIO('\n'.join(lines[start:end])))
    first=f.columns[0]; f=f.rename(columns={first:'ym'}); f=f[f.ym.astype(str).str.fullmatch(r'\d{6}')]
    f.index=pd.to_datetime(f.ym.astype(str),format='%Y%m').dt.to_period('M').dt.to_timestamp('M')
    for k in ['Mkt-RF','SMB','HML','RMW','CMA','RF']: f[k]=pd.to_numeric(f[k],errors='coerce')/100
    return f[['Mkt-RF','SMB','HML','RMW','CMA','RF']].dropna(),data

ff,ffbytes=load_ff5()
raw=yf.download(['RWJ','IWN','IJR','SPY'],start='2009-12-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
ret=c[['RWJ','IWN','IJR','SPY']].resample('ME').last().pct_change(fill_method=None)
z=ret.join(ff,how='inner').dropna()

def fit(asset,start,end=None):
    q=z.loc[z.index>=pd.Timestamp(start)].copy()
    if end: q=q.loc[q.index<=pd.Timestamp(end)]
    y=(q[asset]-q.RF).to_numpy(); X=np.column_stack([np.ones(len(q)),q[['Mkt-RF','SMB','HML','RMW','CMA']].to_numpy()])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b; n=len(y); k=X.shape[1]
    s2=float(resid@resid/max(1,n-k)); cov=s2*np.linalg.inv(X.T@X); se=float(np.sqrt(cov[0,0])); ann=float(b[0]*12); after=ann-HURDLE
    return {'months':int(n),'annualized_alpha':ann,'annualized_alpha_after_25bp_hurdle':after,'alpha_t':float(b[0]/se) if se>0 else None,'betas':{name:float(v) for name,v in zip(['Mkt-RF','SMB','HML','RMW','CMA'],b[1:])},'residual_vol_ann':float(np.std(resid,ddof=1)*math.sqrt(12))}

def paired(start,end=None):
    rwj=fit('RWJ',start,end); iwn=fit('IWN',start,end); ijr=fit('IJR',start,end)
    return {'RWJ':rwj,'IWN':iwn,'IJR':ijr,'RWJ_minus_IWN_after_hurdle_alpha':rwj['annualized_alpha_after_25bp_hurdle']-iwn['annualized_alpha_after_25bp_hurdle'],'RWJ_minus_IJR_after_hurdle_alpha':rwj['annualized_alpha_after_25bp_hurdle']-ijr['annualized_alpha_after_25bp_hurdle']}

wins={k:paired(v) for k,v in WINDOWS.items()}; blocks={k:paired(a,b) for k,(a,b) in BLOCKS.items()}
positive_windows=sum(v['RWJ']['annualized_alpha_after_25bp_hurdle']>0 for v in wins.values())
positive_blocks=sum(v['RWJ']['annualized_alpha_after_25bp_hurdle']>0 for v in blocks.values())
beats_iwn_windows=sum(v['RWJ_minus_IWN_after_hurdle_alpha']>0 for v in wins.values())
beats_iwn_blocks=sum(v['RWJ_minus_IWN_after_hurdle_alpha']>0 for v in blocks.values())
supported=positive_windows==3 and positive_blocks>=2 and beats_iwn_windows>=2 and beats_iwn_blocks>=2
decision='RWJ_INDEPENDENT_FF5_RESIDUAL_SUPPORTED' if supported else 'RWJ_INDEPENDENT_FF5_RESIDUAL_NOT_SUPPORTED'
import hashlib
out={'schema':'research.p506_rwj_ff5_independent_r1.v1','workload_id':'P506_RWJ_FF5_INDEPENDENT_R1','parent':'REVENUE_WEIGHTING_FUND_FAMILY','claim':'Independent-source attribution test of RWJ using Ken French monthly five-factor data rather than ETF-spread factor construction. Require positive after-25bp FF5 alpha across all fixed windows and >=2/3 chronology blocks, plus RWJ alpha above IWN in >=2/3 windows and blocks. No factor/window/product/hurdle search.','sources':{'ff5_url':URL,'ff5_zip_sha256':hashlib.sha256(ffbytes).hexdigest(),'price_source':'Yahoo adjusted ETF prices via yfinance'},'contract':{'factors':['Mkt-RF','SMB','HML','RMW','CMA'],'candidate':'RWJ','value_comparator':'IWN','smallcap_comparator':'IJR','annual_hurdle_bps':25,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'RWJ after-hurdle FF5 alpha positive 3/3 windows and >=2/3 blocks; RWJ after-hurdle FF5 alpha exceeds IWN in >=2/3 windows and >=2/3 blocks','no_factor_window_product_hurdle_or_threshold_search':True},'windows':wins,'blocks':blocks,'summary':{'positive_rwj_windows':positive_windows,'positive_rwj_blocks':positive_blocks,'rwj_beats_iwn_windows':beats_iwn_windows,'rwj_beats_iwn_blocks':beats_iwn_blocks},'decision':decision,'scientific_consequence':'Support revenue-weighting residual only if it survives this independent academic-factor implementation; otherwise downgrade the distinct-alpha interpretation while preserving previously observed matched-return evidence.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'summary':out['summary'],'windows':{k:{'rwj_alpha_pp':round(v['RWJ']['annualized_alpha_after_25bp_hurdle']*100,3),'iwn_alpha_pp':round(v['IWN']['annualized_alpha_after_25bp_hurdle']*100,3),'delta_pp':round(v['RWJ_minus_IWN_after_hurdle_alpha']*100,3),'rwj_t':round(v['RWJ']['alpha_t'],2)} for k,v in wins.items()},'blocks':{k:{'rwj_alpha_pp':round(v['RWJ']['annualized_alpha_after_25bp_hurdle']*100,3),'delta_iwn_pp':round(v['RWJ_minus_IWN_after_hurdle_alpha']*100,3)} for k,v in blocks.items()}},sort_keys=True))
