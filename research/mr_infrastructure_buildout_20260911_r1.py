from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['PAVE','IFRA','XLI','SPY']; START='2018-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_infrastructure_buildout_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2)
    cagr=gross**(1/years)-1
    r=s.pct_change().dropna(); w=(1+r).cumprod(); dd=w/w.cummax()-1
    sh=(r.mean()/r.std(ddof=1))*math.sqrt(252) if r.std(ddof=1)>0 else float('nan')
    return {'days':int(len(s)),'cagr':float(cagr),'maxdd':float(dd.min()),'sharpe':float(sh)}

def frame(start,end=None):
    out={s:stats(s,start,end) for s in T}
    if all(out[s].get('days',0)>=252 for s in T):
        for s in ['PAVE','IFRA']:
            out[s+'_minus_XLI_pp']=100*(out[s]['cagr']-out['XLI']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2019+':frame('2019-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2019_2020':frame('2019-01-01','2020-12-31'),'2021_2022':frame('2021-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_XLI_pp',-999)>0 for v in src.values())
pw,pb=count('PAVE',windows),count('PAVE',blocks); iw,ib=count('IFRA',windows),count('IFRA',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('PAVE_minus_XLI_pp',-999)>0 and windows['2022+'].get('IFRA_minus_XLI_pp',-999)>0
passed=coverage and pw>=2 and pb>=2 and iw>=2 and ib>=2 and recent
out={'schema':'research.mr_infrastructure_buildout_20260911_r1.v1','workload_id':'MR_INFRASTRUCTURE_BUILDOUT_20260911_R1','parent':'INFRASTRUCTURE_BUILDOUT_EQUITY_PREMIUM','claim':'If infrastructure-buildout selection creates durable excess return beyond broad industrial beta, both PAVE and IFRA should beat XLI after fixed endpoint costs across post-inception long windows and disjoint chronology; SPY is opportunity-cost context.','contract':{'implementations':['PAVE','IFRA'],'matched_control':'XLI','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'PAVE_positive_windows':pw,'PAVE_positive_blocks':pb,'IFRA_positive_windows':iw,'IFRA_positive_blocks':ib},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat XLI in >=2/3 windows and >=2/3 blocks, both beat XLI from 2022+, and every block has >=252 observations. No wrapper/control/date/cost rescue.','decision':('INFRASTRUCTURE_BUILDOUT_PREMIUM_SUPPORTED' if passed else ('INFRASTRUCTURE_BUILDOUT_SOURCE_COVERAGE_NOT_READY' if not coverage else 'INFRASTRUCTURE_BUILDOUT_PREMIUM_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'PAVE_XLI_pp':{k:round(v.get('PAVE_minus_XLI_pp',-999),3) for k,v in windows.items()},'IFRA_XLI_pp':{k:round(v.get('IFRA_minus_XLI_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
