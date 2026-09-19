from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SYMS=['SPMO','SPY','XMMO','IJH','IJS','IJR']
START='2015-01-01'
END='2026-09-10'
COST_BPS=25
WINDOWS={'2017_plus':'2017-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}

raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna()
monthly=px.resample('ME').last().pct_change().dropna()

def fixed_combo(momentum: str) -> pd.Series:
    gross=.5*monthly[momentum]+.5*monthly.IJS
    drift=.5*(1+monthly[momentum])/(1+gross)
    turnover=2*(drift-.5).abs()
    return gross-turnover*(COST_BPS/10000)

spmo=fixed_combo('SPMO')
xmmo=fixed_combo('XMMO')
spmo_matched=.5*monthly.SPY+.5*monthly.IJR
xmmo_matched=.5*monthly.IJH+.5*monthly.IJR

def stats(s: pd.Series) -> dict:
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12
    sd=s.std()
    return {
        'months':int(len(s)),
        'cagr':float(w.iloc[-1]**(1/yrs)-1),
        'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,
        'max_drawdown':float((w/w.cummax()-1).min())
    }

def window(a: str) -> dict:
    idx=spmo.index[spmo.index>=pd.Timestamp(a)]
    s=spmo.loc[idx]; x=xmmo.loc[idx]; sb=spmo_matched.loc[idx]; xb=xmmo_matched.loc[idx]
    ss,xx,sbs,xbs=stats(s),stats(x),stats(sb),stats(xb)
    return {
        'spmo_combo':ss,
        'xmmo_combo':xx,
        'spmo_matched':sbs,
        'xmmo_matched':xbs,
        'spmo_matched_excess_cagr':ss['cagr']-sbs['cagr'],
        'xmmo_matched_excess_cagr':xx['cagr']-xbs['cagr'],
        'direct_spmo_minus_xmmo_cagr':ss['cagr']-xx['cagr'],
        'matched_excess_advantage_spmo_minus_xmmo':(ss['cagr']-sbs['cagr'])-(xx['cagr']-xbs['cagr']),
        'sharpe_advantage_spmo_minus_xmmo':ss['sharpe']-xx['sharpe'],
        'max_drawdown_advantage_spmo_minus_xmmo':ss['max_drawdown']-xx['max_drawdown']
    }

results={k:window(v) for k,v in WINDOWS.items()}
z=pd.DataFrame({'spmo':spmo,'xmmo':xmmo}).loc['2017-01-01':].dropna()
fold_direct=[]
for part in np.array_split(z,5):
    fold_direct.append(stats(part.spmo)['cagr']-stats(part.xmmo)['cagr'])

spmo_direct=sum(results[k]['direct_spmo_minus_xmmo_cagr']>0.005 for k in results)
spmo_alpha=sum(results[k]['matched_excess_advantage_spmo_minus_xmmo']>0 for k in results)
xmmo_direct=sum(results[k]['direct_spmo_minus_xmmo_cagr']<-0.005 for k in results)
xmmo_alpha=sum(results[k]['matched_excess_advantage_spmo_minus_xmmo']<0 for k in results)
pos_folds=sum(x>0 for x in fold_direct)
neg_folds=sum(x<0 for x in fold_direct)
if spmo_direct>=2 and spmo_alpha>=2 and pos_folds>=3:
    decision='P308_SPMO_SMALLVALUE_CLEAR_REPRESENTATIVE'
elif xmmo_direct>=2 and xmmo_alpha>=2 and neg_folds>=3:
    decision='P308_XMMO_SMALLVALUE_CLEAR_REPRESENTATIVE'
else:
    decision='P308_NO_CLEAR_REPRESENTATIVE_PRESERVE_BOTH'

out={
    'schema':'research.p308_momentum_smallvalue_headtohead_r1',
    'parent':'P308',
    'claim':'Frozen common-sample fixed equal-weight after-cost head-to-head between SPMO+IJS and XMMO+IJS using each momentum sleeve exact matched control. No weight, product, window, regime, or threshold search.',
    'cost_bps':COST_BPS,
    'weights':{'momentum':0.5,'IJS':0.5},
    'matched_controls':{'SPMO_pair':{'SPY':0.5,'IJR':0.5},'XMMO_pair':{'IJH':0.5,'IJR':0.5}},
    'results':results,
    'chronology_fold_direct_spmo_minus_xmmo_cagr':fold_direct,
    'positive_spmo_folds':pos_folds,
    'positive_xmmo_folds':neg_folds,
    'decision_rule':'Select SPMO only if its direct CAGR exceeds XMMO by >0.50pp in at least 2/3 fixed windows, its matched-excess advantage is positive in at least 2/3 windows, and >=3/5 chronology folds favor SPMO. Apply the symmetric rule for XMMO. Otherwise preserve both as scientifically supported representations and make no representative-selection claim.',
    'decision':decision,
    'limitations':['same adjusted-price provider','ETF proxy evidence rather than constituent-level point-in-time selection','selection test is scientific representation adjudication, not portfolio allocation authority','no parameter/weight/window/product search','no product/runtime/broker/live authority'],
    'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}
}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p308_momentum_smallvalue_headtohead_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(out,sort_keys=True))
