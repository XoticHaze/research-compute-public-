import json
import numpy as np
import pandas as pd
import yfinance as yf

COST=0.0025
START='2012-01-01'
END='2026-09-01'
TICKERS=['CPER','GLD','FCX','SCCO']

def cagr(r):
    eq=(1+r).prod(); return eq**(12/len(r))-1 if len(r) and eq>0 else -1.0

def maxdd(r):
    eq=(1+r).cumprod(); return float((eq/eq.cummax()-1).min())

def evaluate(mask,risky,gld):
    pos=mask.astype(int); gross=pd.Series(np.where(pos.eq(1),risky,gld),index=mask.index)
    switches=pos.diff().abs().fillna(0); net=gross-switches*COST; p=float(pos.mean()); matched=p*risky+(1-p)*gld
    return {'cagr':cagr(net),'matched_cagr':cagr(matched),'excess':cagr(net)-cagr(matched),'maxdd':maxdd(net),'months':len(net),'switches':int(switches.sum()),'risky_participation':p}

def main():
    px=yf.download(TICKERS,start=START,end=END,auto_adjust=True,progress=False)['Close']
    m=px.resample('ME').last().dropna(); ret=m.pct_change().dropna()
    sig=(m['CPER'].pct_change(6)>0).shift(1).reindex(ret.index).fillna(False)
    idx=ret.index[ret.index>=pd.Timestamp('2015-01-31')]; ret=ret.loc[idx]; sig=sig.loc[idx]
    basket=ret[['FCX','SCCO']].mean(axis=1)
    actual=evaluate(sig,basket,ret['GLD'])
    components={t:evaluate(sig,ret[t],ret['GLD']) for t in ['FCX','SCCO']}
    windows={}; positive=0
    for name,a,b in [('2015_2018','2015-01-31','2018-12-31'),('2019_2021','2019-01-31','2021-12-31'),('2022_2024','2022-01-31','2024-12-31'),('2025_plus','2025-01-31','2026-08-31')]:
        z=ret.loc[a:b]; s=sig.reindex(z.index); rb=basket.reindex(z.index)
        if len(z):
            windows[name]=evaluate(s,rb,z['GLD']); positive+=int(windows[name]['excess']>0)
    component_support=sum(int(v['excess']>0) for v in components.values())
    decision='SUPPORT_PRODUCER_TRANSPORT' if actual['excess']>0 and positive>=3 and component_support==2 else 'FAIL_PRODUCER_TRANSPORT'
    out={'experiment':'B10_CPER_TREND_ALT_COPPER_PRODUCER_TRANSPORT_R1','frozen_rule':'prior completed-month 6m CPER > 0 selects equal-weight FCX+SCCO else GLD','cost_one_way':COST,'signal_lag_months':1,'actual':actual,'components':components,'positive_chronology_windows':positive,'windows':windows,'decision':decision,'protected_p01_holdout_read':False}
    print(json.dumps(out,indent=2,default=str))
    with open('mr_b10_copper_producer_transport.json','w') as f: json.dump(out,f,indent=2,default=str)
if __name__=='__main__': main()
