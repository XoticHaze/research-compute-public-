from __future__ import annotations
import io,json,math,urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

SYMS={'DBMF':'dbmf.us','BIL':'bil.us','SPY':'spy.us'}; EP=.0025
OUT=Path('research/artifacts/mr_dbmf_stooq_independent_20260911_r3.json'); OUT.parent.mkdir(parents=True,exist_ok=True)

def load(sym):
    url=f'https://stooq.com/q/d/l/?s={SYMS[sym]}&d1=20200101&d2=20260912&i=d'
    with urllib.request.urlopen(url,timeout=30) as r: raw=r.read()
    df=pd.read_csv(io.BytesIO(raw))
    if df.empty or 'Date' not in df or 'Close' not in df: raise RuntimeError(f'STOOQ_SOURCE_FAILURE_{sym}')
    df['Date']=pd.to_datetime(df['Date']); return df.set_index('Date')['Close'].astype(float).sort_index().rename(sym)
px=pd.concat([load(s) for s in SYMS],axis=1).dropna()
m=px.resample('ME').last().pct_change().dropna().loc['2021-01-01':]
if len(m)<60: raise RuntimeError(f'STOOQ_SOURCE_COVERAGE_NOT_READY:{len(m)}')

def stats(r,cost=0.0):
    r=r.dropna(); w=(1+r).cumprod()*(1-cost)**2; years=len(r)/12.0; dd=w/w.cummax()-1; sd=r.std(ddof=1)
    return {'months':int(len(r)),'cagr':float(w.iloc[-1]**(1/years)-1),'maxdd':float(dd.min()),'sharpe':float((r.mean()/sd)*math.sqrt(12)) if sd>0 else None}
def ev(a,b=None):
    z=m.loc[a:b]; c=stats(z.DBMF,EP); cash=stats(z.BIL); spy=stats(z.SPY)
    return {'candidate':c,'cash_control':cash,'spy_opportunity':spy,'cash_excess_cagr_pp':100*(c['cagr']-cash['cagr']),'spy_excess_cagr_pp':100*(c['cagr']-spy['cagr']),'spy_corr':float(z.DBMF.corr(z.SPY))}
windows={'2021+':ev('2021-01-01'),'2022+':ev('2022-01-01'),'2024+':ev('2024-01-01')}
blocks={'2021_2022':ev('2021-01-01','2022-12-31'),'2023_2024':ev('2023-01-01','2024-12-31'),'2025_plus':ev('2025-01-01')}
# Same orthogonal rolling/downside checks, now on independent source bytes.
cand=(1+m.DBMF).rolling(12).apply(np.prod,raw=True)*(1-EP)**2-1
cash=(1+m.BIL).rolling(12).apply(np.prod,raw=True)-1
rex=(cand-cash).dropna(); down=m[m.SPY<0]; severe=m[m.SPY<=-0.05]
rolling={'windows':int(len(rex)),'positive_fraction':float((rex>0).mean()),'median_excess_pp':float(100*rex.median())}
conditional={'down_months':int(len(down)),'down_cash_excess_mean_pp':float(100*(down.DBMF-down.BIL).mean()),'severe_months':int(len(severe)),'severe_cash_excess_mean_pp':float(100*(severe.DBMF-severe.BIL).mean())}
positive_windows=sum(v['cash_excess_cagr_pp']>0 for v in windows.values()); positive_blocks=sum(v['cash_excess_cagr_pp']>0 for v in blocks.values())
passed=(positive_windows>=3 and positive_blocks>=2 and windows['2024+']['cash_excess_cagr_pp']>0 and rolling['windows']>=48 and rolling['positive_fraction']>=0.60 and rolling['median_excess_pp']>0 and conditional['down_cash_excess_mean_pp']>0 and conditional['severe_months']>=5 and conditional['severe_cash_excess_mean_pp']>0)
decision='DBMF_INDEPENDENT_SOURCE_VALIDATION_SUPPORTED' if passed else 'DBMF_INDEPENDENT_SOURCE_VALIDATION_NOT_SUPPORTED'
out={'schema':'research.mr_dbmf_stooq_independent_20260911_r3.v1','workload_id':'MR_DBMF_STOOQ_INDEPENDENT_20260911_R3','parent':'DBMF_IMPLEMENTATION_SURVIVOR','source':{'provider':'Stooq','symbols':SYMS,'endpoint_pattern':'https://stooq.com/q/d/l/','independent_from_prior':'Prior R1/R2 used yfinance/Yahoo-derived prices; this run downloads Stooq daily CSV directly.'},'claim':'The DBMF implementation-specific survivor should reproduce on an independent public price source without changing products, dates, costs, cash hurdle, or orthogonal persistence tests.','contract':{'endpoint_cost_bps_each':25,'cash_control':'BIL','opportunity_control':'SPY','windows':list(windows),'blocks':list(blocks),'rolling_horizon_months':12,'minimum_positive_rolling_fraction':0.60,'severe_spy_month':'<= -5%','parameter_search':False},'windows':windows,'blocks':blocks,'rolling12':rolling,'conditional':conditional,'positive_windows':positive_windows,'positive_blocks':positive_blocks,'decision_rule':'SUPPORTED only if DBMF beats BIL after costs in all 3 fixed windows, >=2/3 chronology blocks, remains positive from 2024+, independently repeats >=60% positive rolling-12m cash excess with positive median, and has positive BIL excess in SPY-down and severe-down months with >=5 severe observations. No source/date/product/cost/threshold rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'positive_windows':positive_windows,'positive_blocks':positive_blocks,'2021_cash_pp':round(windows['2021+']['cash_excess_cagr_pp'],3),'2024_cash_pp':round(windows['2024+']['cash_excess_cagr_pp'],3),'spy_corr':round(windows['2021+']['spy_corr'],3),'roll_pos':round(rolling['positive_fraction'],3),'roll_med_pp':round(rolling['median_excess_pp'],3),'down_pp':round(conditional['down_cash_excess_mean_pp'],3),'severe_n':conditional['severe_months'],'severe_pp':round(conditional['severe_cash_excess_mean_pp'],3)},sort_keys=True))
