import json, math
import numpy as np
import pandas as pd
import yfinance as yf

COST=0.0025
START='2012-01-01'
END='2026-09-01'
TICKERS=['COPX','CPER','GLD']

def cagr(r):
    if len(r)==0: return float('nan')
    eq=(1+r).prod(); return eq**(12/len(r))-1 if eq>0 else -1

def maxdd(r):
    eq=(1+r).cumprod(); return float((eq/eq.cummax()-1).min())

def evaluate(mask, copx, gld):
    pos=mask.astype(int)
    gross=np.where(pos.eq(1),copx,gld)
    switches=pos.diff().abs().fillna(0)
    net=pd.Series(gross,index=mask.index)-switches*COST
    p=float(pos.mean())
    matched=p*copx+(1-p)*gld
    return {'cagr':cagr(net),'matched_cagr':cagr(matched),'excess':cagr(net)-cagr(matched),'maxdd':maxdd(net),'months':len(net),'switches':int(switches.sum()),'copx_participation':p}

def main():
    px=yf.download(TICKERS,start=START,end=END,auto_adjust=True,progress=False)['Close']
    m=px.resample('ME').last().dropna()
    ret=m.pct_change().dropna()
    sig=(m['CPER'].pct_change(6)>0).shift(1).reindex(ret.index).fillna(False)
    idx=ret.index[ret.index>=pd.Timestamp('2015-01-31')]
    ret=ret.loc[idx]; sig=sig.loc[idx]
    parent=evaluate(sig,ret['COPX'],ret['GLD'])
    windows={}
    for name,a,b in [('2015_2018','2015-01-31','2018-12-31'),('2019_2021','2019-01-31','2021-12-31'),('2022_2024','2022-01-31','2024-12-31'),('2025_plus','2025-01-31','2026-08-31')]:
        z=ret.loc[a:b]; s=sig.reindex(z.index)
        if len(z): windows[name]=evaluate(s,z['COPX'],z['GLD'])
    out={'experiment':'B9_COPPER_PRODUCER_TREND_TRANSPORT','hypothesis':'prior completed-month 6m CPER > 0 selects COPX else GLD','cost_one_way':COST,'signal_lag_months':1,'full':parent,'windows':windows,'protected_p01_holdout_read':False}
    print(json.dumps(out,indent=2,default=str))
    with open('mr_b9_copper_trend_transport.json','w') as f: json.dump(out,f,indent=2,default=str)
if __name__=='__main__': main()
