import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

START='2005-01-01'
END=None
COST_BPS=(0,10,25,50)


def load():
    px=yf.download(['SMH','QQQ','SPY'],start=START,end=END,auto_adjust=True,progress=False,threads=False)
    if px.empty: raise RuntimeError('empty_yfinance_download')
    c=px['Close'] if isinstance(px.columns,pd.MultiIndex) else px
    c=c[['SMH','QQQ','SPY']].dropna().astype(float)
    if len(c)<1500: raise RuntimeError(f'insufficient_rows:{len(c)}')
    return c


def rebalance_dates(idx):
    s=pd.Series(idx,index=idx)
    return s.groupby(idx.to_period('M')).first().values


def weights_static(px):
    return pd.DataFrame({'SMH':0.5,'QQQ':0.5,'SPY':0.0},index=px.index)


def weights_relmom(px, hi=.8):
    rel=px['SMH'].pct_change(126)-px['QQQ'].pct_change(126)
    raw=pd.DataFrame(index=px.index,columns=['SMH','QQQ','SPY'],dtype=float)
    raw['SMH']=np.where(rel>=0,hi,1-hi); raw['QQQ']=1-raw['SMH']; raw['SPY']=0.0
    m=raw.loc[rebalance_dates(px.index)].copy()
    return m.reindex(px.index).ffill().fillna(weights_static(px))


def weights_relmom_risk(px):
    base=weights_relmom(px,.8)
    r=px['SPY'].pct_change()
    vol=r.rolling(63).std()*np.sqrt(252)
    threshold=vol.rolling(252,min_periods=126).median().shift(1)
    high=(vol>threshold).astype(float)
    # In high-risk states, cap semiconductor concentration and hold 30% SPY.
    out=base.copy()
    risky=high.reindex(px.index).fillna(0).astype(bool)
    out.loc[risky,'SMH']=np.minimum(out.loc[risky,'SMH'],0.45)
    out.loc[risky,'QQQ']=0.25
    out.loc[risky,'SPY']=1-out.loc[risky,'SMH']-out.loc[risky,'QQQ']
    m=out.loc[rebalance_dates(px.index)]
    return m.reindex(px.index).ffill().fillna(weights_static(px))


def weights_invvol(px):
    rv=px[['SMH','QQQ']].pct_change().rolling(63).std().shift(1)
    inv=1/rv.replace(0,np.nan)
    w=inv.div(inv.sum(axis=1),axis=0).clip(lower=.25,upper=.75)
    w=w.div(w.sum(axis=1),axis=0)
    out=pd.DataFrame({'SMH':w['SMH'],'QQQ':w['QQQ'],'SPY':0.0},index=px.index)
    m=out.loc[rebalance_dates(px.index)]
    return m.reindex(px.index).ffill().fillna(weights_static(px))


def portfolio(px,w,cost_bps):
    r=px.pct_change().fillna(0)
    w=w.shift(1).fillna(method='bfill')
    gross=(w*r).sum(axis=1)
    turnover=w.diff().abs().sum(axis=1).fillna(0)/2
    net=gross-turnover*(cost_bps/10000)
    return net,turnover


def metrics(r,turnover):
    r=r.dropna(); eq=(1+r).cumprod(); yrs=max(len(r)/252,1e-9)
    cagr=float(eq.iloc[-1]**(1/yrs)-1)
    ann=float(r.mean()*252); vol=float(r.std(ddof=0)*np.sqrt(252)); sharpe=ann/vol if vol>0 else np.nan
    dd=eq/eq.cummax()-1; mdd=float(dd.min()); calmar=cagr/abs(mdd) if mdd<0 else np.nan
    return {'cagr':cagr,'sharpe':float(sharpe),'max_drawdown':mdd,'calmar':float(calmar),'annual_turnover':float(turnover.mean()*252),'final_equity':float(eq.iloc[-1])}


def folds(r,t,n=5):
    idx=np.array_split(np.arange(len(r)),n); out=[]
    for i,a in enumerate(idx,1):
        rr=r.iloc[a]; tt=t.iloc[a]; m=metrics(rr,tt); m['fold']=i; m['start']=str(rr.index[0].date()); m['end']=str(rr.index[-1].date()); out.append(m)
    return out


def evaluate(px,name,w,baseline_w):
    result={'candidate':name,'window':{'start':str(px.index[0].date()),'end':str(px.index[-1].date()),'rows':len(px)},'cost_sensitivity':{}}
    for bps in COST_BPS:
        r,t=portfolio(px,w,bps); br,bt=portfolio(px,baseline_w,bps)
        m=metrics(r,t); bm=metrics(br,bt)
        fs=folds(r,t); bfs=folds(br,bt)
        excess=[a['cagr']-b['cagr'] for a,b in zip(fs,bfs)]
        result['cost_sensitivity'][str(bps)]={'candidate':m,'baseline':bm,'excess_cagr':m['cagr']-bm['cagr'],'positive_excess_folds':int(sum(x>0 for x in excess)),'folds':fs,'baseline_folds':bfs,'fold_excess_cagr':excess}
    x=result['cost_sensitivity']['25']
    result['decision']='PROMOTE' if x['excess_cagr']>0 and x['positive_excess_folds']>=3 and x['candidate']['sharpe']>=x['baseline']['sharpe'] else ('ITERATE' if x['excess_cagr']>0 else 'PARK')
    return result


def run(child):
    px=load(); static=weights_static(px)
    if child=='persistence':
        return evaluate(px,'SMH_QQQ_126D_RELATIVE_MOMENTUM_80_20',weights_relmom(px,.8),static)
    if child=='risk_state':
        return evaluate(px,'RELATIVE_MOMENTUM_WITH_EXPANDING_SPY_VOL_RISK_CAP',weights_relmom_risk(px),weights_relmom(px,.8))
    if child=='allocation':
        rel=evaluate(px,'RELATIVE_MOMENTUM_80_20',weights_relmom(px,.8),static)
        iv=evaluate(px,'CAPPED_63D_INVERSE_VOL',weights_invvol(px),static)
        # direct competition under same baseline
        winner=max([rel,iv],key=lambda z:z['cost_sensitivity']['25']['candidate']['calmar'])
        return {'candidate':'ALLOCATION_CHALLENGER','children':[rel,iv],'winner_by_25bps_calmar':winner['candidate'],'decision':winner['decision']}
    if child=='diversification':
        rel=weights_relmom(px,.8)
        mix=rel.copy(); mix[['SMH','QQQ']]*=.70; mix['SPY']=.30
        return evaluate(px,'70PCT_RELATIVE_MOMENTUM_PLUS_30PCT_SPY',mix,rel)
    raise ValueError(child)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--child',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    result=run(a.child)
    result['schema']='fund_model_parallel_eval_r1'; result['child']=a.child; result['data_source']='Yahoo Finance via yfinance; adjusted daily close'; result['lookahead_controls']='signals use trailing data; volatility threshold shifted; portfolio weights shifted one day; monthly rebalance'
    Path(a.out).write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'child':a.child,'decision':result.get('decision'),'out':a.out},indent=2))

if __name__=='__main__': main()
