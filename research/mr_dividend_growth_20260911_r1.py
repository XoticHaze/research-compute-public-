from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['VIG','NOBL','SPY']; START='2013-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_dividend_growth_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T]
windows={'2014+':('2014-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2014_2016':('2014-01-01','2016-12-31'),'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    net=float(s.iloc[-1]/s.iloc[0])*(1-EP)*(1-EP); cagr=net**(1/years)-1
    w=(s/s.iloc[0])*(1-EP); dd=float((w/w.cummax()-1).min())
    d=s.pct_change().dropna(); vol=float(d.std(ddof=1)*math.sqrt(252)); sr=float(d.mean()*252/vol) if vol>0 else None
    return {'days':int(len(s)),'years':float(years),'cagr':float(cagr),'max_drawdown':dd,'ann_vol':vol,'simple_sharpe':sr}

def pack(periods):
    out={}
    for k,(a,b) in periods.items():
        row={s:stats(s,a,b) for s in T}
        for s in ['VIG','NOBL']:
            if 'cagr' in row[s] and 'cagr' in row['SPY']:
                row[s]['spy_excess_pp']=100*(row[s]['cagr']-row['SPY']['cagr'])
                row[s]['drawdown_delta_pp']=100*(row[s]['max_drawdown']-row['SPY']['max_drawdown'])
                row[s]['sharpe_delta']=row[s]['simple_sharpe']-row['SPY']['simple_sharpe']
        out[k]=row
    return out
W=pack(windows); B=pack(blocks)
posw={s:sum(W[k][s].get('spy_excess_pp',-999)>0 for k in W) for s in ['VIG','NOBL']}
posb={s:sum(B[k][s].get('spy_excess_pp',-999)>0 for k in B) for s in ['VIG','NOBL']}
coverage=all(B[k][s].get('days',0)>=500 for k in B for s in T)
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('spy_excess_pp',-999)>0 for s in ['VIG','NOBL'])
out={'schema':'research.mr_dividend_growth_20260911_r1.v1','workload_id':'MR_DIVIDEND_GROWTH_20260911_R1','parent':'DIVIDEND_GROWTH_EQUITY_SELECTION','claim':'If dividend-growth selection creates durable total-return alpha rather than only defensive/risk-shaping exposure, both VIG and NOBL should beat SPY after equal endpoint friction across fixed long windows and disjoint chronology.','contract':{'candidates':['VIG','NOBL'],'matched_control':'SPY','endpoint_cost_bps_each_side_each_series':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_spy_excess_windows':posw,'positive_spy_excess_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates beat SPY in >=3/4 windows and >=3/4 blocks and both are positive from 2022+. Drawdown/Sharpe are diagnostic only; no product/control/date/cost rescue.','decision':('DIVIDEND_GROWTH_ALPHA_SUPPORTED' if passed else ('DIVIDEND_GROWTH_COVERAGE_NOT_READY' if not coverage else 'DIVIDEND_GROWTH_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'VIG_SPY_pp':{k:round(W[k]['VIG'].get('spy_excess_pp',-999),3) for k in W},'NOBL_SPY_pp':{k:round(W[k]['NOBL'].get('spy_excess_pp',-999),3) for k in W},'counts':{'VIG_positive_windows':posw['VIG'],'VIG_positive_blocks':posb['VIG'],'NOBL_positive_windows':posw['NOBL'],'NOBL_positive_blocks':posb['NOBL']},'risk_2022plus':{'VIG_sharpe_delta':round(W['2022+']['VIG'].get('sharpe_delta',-999),3),'VIG_dd_delta_pp':round(W['2022+']['VIG'].get('drawdown_delta_pp',-999),3),'NOBL_sharpe_delta':round(W['2022+']['NOBL'].get('sharpe_delta',-999),3),'NOBL_dd_delta_pp':round(W['2022+']['NOBL'].get('drawdown_delta_pp',-999),3)}},sort_keys=True))
