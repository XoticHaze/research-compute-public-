from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, yfinance as yf

SYMS=['SPMO','SPY','IJS','IJR','IMTM','IEFA','PIE','EEM']
START='2015-01-01'; END='2026-09-10'
BLOCKS={'2016_2019':('2016-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_present':('2023-01-01','2026-09-10')}
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last()
r=px.pct_change().dropna()
x=pd.DataFrame({
    'us_combo_excess':0.5*(r.SPMO-r.SPY)+0.5*(r.IJS-r.IJR),
    'developed_momentum_excess':r.IMTM-r.IEFA,
    'emerging_momentum_excess':r.PIE-r.EEM,
}).dropna()

def relationship(series: str):
    out={}
    for name,(a,b) in BLOCKS.items():
        z=x.loc[(x.index>=pd.Timestamp(a))&(x.index<=pd.Timestamp(b)),['us_combo_excess',series]].dropna()
        out[name]={
            'months':int(len(z)),
            'excess_corr':float(z.us_combo_excess.corr(z[series])),
            'opposite_sign_fraction':float(((z.us_combo_excess*z[series])<0).mean()),
            'both_negative_fraction':float(((z.us_combo_excess<0)&(z[series]<0)).mean()),
        }
    z=x.loc[x.index>=pd.Timestamp('2016-01-01'),['us_combo_excess',series]].dropna()
    overall=float(z.us_combo_excess.corr(z[series]))
    low=sum(v['excess_corr']<0.6 for v in out.values())
    return {'overall_excess_corr':overall,'blocks_below_0_6':low,'blocks':out}

dev=relationship('developed_momentum_excess')
em=relationship('emerging_momentum_excess')
passed=dev['overall_excess_corr']<0.6 and dev['blocks_below_0_6']>=2 and em['overall_excess_corr']<0.6 and em['blocks_below_0_6']>=2
decision='P318_GLOBAL_MOMENTUM_COMPLEMENTARITY_SUPPORTED' if passed else 'P318_GLOBAL_MOMENTUM_COMPLEMENTARITY_NOT_ESTABLISHED'
out={
 'schema':'research.p318_global_momentum_redundancy_r1','parent':'P318',
 'claim':'Test whether supported developed/emerging momentum transport supplies a genuinely distinct return source relative to the already-supported fixed US 50/50 SPMO+IJS sleeve, using matched-relative monthly excess rather than raw market beta. No geography/product/weight/lookback/window search.',
 'representations':{'us_supported_combo_excess':'0.5*(SPMO-SPY)+0.5*(IJS-IJR)','developed_momentum_excess':'IMTM-IEFA','emerging_momentum_excess':'PIE-EEM'},
 'blocks':BLOCKS,'developed':dev,'emerging':em,
 'decision_rule':'Advance a global-momentum combination hypothesis only if BOTH geography representations have 2016+ matched-relative excess correlation below 0.6 versus the fixed US momentum+small-value sleeve and at least 2/3 fixed blocks below 0.6. Otherwise treat geographic momentum as scientifically supported but insufficiently distinct for a new combination claim.',
 'decision':decision,
 'limitations':['scientific redundancy discriminator, not allocation or portfolio ranking','uses fixed ETF representations already adjudicated elsewhere','correlation claim only; underlying survivor alpha evidence retains its own after-cost gates','same adjusted-price provider','no parameter, weight, product, runtime, broker, or live authority'],
 'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p318_global_momentum_redundancy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(out,sort_keys=True))
