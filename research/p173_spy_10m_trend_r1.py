import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['SPY','BIL']
COSTS=[10,25,50]
WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}
PRIMARY_COST=25

def cagr(r):
    r=pd.Series(r).dropna()
    if len(r)==0:return float('nan')
    return float((1+r).prod()**(12/len(r))-1)

def maxdd(r):
    eq=(1+pd.Series(r).fillna(0)).cumprod(); peak=eq.cummax()
    return float((eq/peak-1).min())

def sharpe(r):
    r=pd.Series(r).dropna()
    return float(np.sqrt(12)*r.mean()/r.std(ddof=1)) if len(r)>1 and r.std(ddof=1)>0 else float('nan')

def eval_slice(df,cost_bps):
    cost=cost_bps/10000.0
    sig=df['signal'].astype(float)
    mean_exposure=float(sig.mean())
    gross=sig*df['SPY_ret']+(1-sig)*df['BIL_ret']
    turnover=sig.diff().abs().fillna(sig.iloc[0])
    cand=gross-turnover*cost
    matched=mean_exposure*df['SPY_ret']+(1-mean_exposure)*df['BIL_ret']
    spy=df['SPY_ret']
    return {'candidate':{'cagr':cagr(cand),'maxdd':maxdd(cand),'sharpe':sharpe(cand)},
            'matched':{'cagr':cagr(matched),'maxdd':maxdd(matched),'sharpe':sharpe(matched)},
            'spy':{'cagr':cagr(spy),'maxdd':maxdd(spy),'sharpe':sharpe(spy)},
            'excess_matched':cagr(cand)-cagr(matched),'excess_spy':cagr(cand)-cagr(spy),
            'mean_spy_exposure':mean_exposure,'months':int(len(df))}

def folds(df,cost_bps,n=5):
    out=[]
    for i,idx in enumerate(np.array_split(np.arange(len(df)),n),1):
        x=eval_slice(df.iloc[idx],cost_bps)
        out.append({'fold':i,'matched_excess':x['excess_matched'],'spy_excess':x['excess_spy']})
    return out

raw=yf.download(TICKERS,start='2003-01-01',end='2026-09-01',auto_adjust=True,progress=False,group_by='column')
if isinstance(raw.columns,pd.MultiIndex): close=raw['Close'][TICKERS]
else: close=raw[TICKERS]
close=close.dropna(how='all').ffill().dropna()
monthly=close.resample('ME').last()
# completed-month 10-month SMA, signal held during following month
sma10=monthly['SPY'].rolling(10,min_periods=10).mean()
signal=(monthly['SPY']>sma10).astype(float).shift(1)
rets=monthly.pct_change()
df=pd.DataFrame({'SPY_ret':rets['SPY'],'BIL_ret':rets['BIL'],'signal':signal}).dropna()
panel_bytes=close.to_csv().encode(); panel_sha=hashlib.sha256(panel_bytes).hexdigest()
res={'schema':'research.p173_spy_10m_trend_r1','parent':'P173',
     'hypothesis':'A fixed completed-month 10-month SPY trend rule adds after-cost value beyond simply holding the same average equity exposure, while also competing with full SPY opportunity cost.',
     'contract':{'signal':'SPY completed-month close above trailing 10 completed-month SMA; apply next month','cash_proxy':'BIL','cost_bps':COSTS,'primary_cost_bps':PRIMARY_COST,'windows':WINDOWS,'folds':5,'matched':'static SPY/BIL blend at evaluated mean SPY exposure','opportunity_control':'SPY','predeclared_gate':'2015+ at 25 bps must have positive matched CAGR excess, >=3/5 positive matched folds, and non-inferior drawdown; SPY opportunity gap reported separately','no_search':True},
     'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(monthly.index[-1].date()),'panel_sha256':panel_sha},'tests':{}}
for cb in COSTS:
    res['tests'][str(cb)]={}
    for k,start in WINDOWS.items():
        z=df.loc[pd.Timestamp(start):].copy(); x=eval_slice(z,cb); fs=folds(z,cb)
        x['folds']=fs; x['positive_matched_folds']=sum(q['matched_excess']>0 for q in fs); x['positive_spy_folds']=sum(q['spy_excess']>0 for q in fs)
        res['tests'][str(cb)][k]=x
p=res['tests'][str(PRIMARY_COST)]['2015']
res['decision']='P173_SPY_10M_TREND_SURVIVOR' if (p['excess_matched']>0 and p['positive_matched_folds']>=3 and p['candidate']['maxdd']>=p['matched']['maxdd']) else 'P173_SPY_10M_TREND_REJECT'
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/p173_spy_10m_trend_r1.json').write_text(json.dumps(res,sort_keys=True,indent=2))
print(json.dumps(res,sort_keys=True))
