from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SYMBOLS=('SPY','QQQ','TLT','GLD','DBC')
FEATURES=('mom1','mom3','mom6','mom12','vol3','dd6')
COSTS=(25,50,100)
RIDGE_ALPHA=1.0
MIN_TRAIN_MONTHS=60
TOP_K=2


def load():
    px=yf.download(list(SYMBOLS),start='2005-01-01',auto_adjust=True,progress=False,group_by='column')['Close']
    if isinstance(px,pd.Series): px=px.to_frame()
    px=px[list(SYMBOLS)].dropna(how='all')
    cutoff=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    return px.loc[px.index<cutoff].dropna()


def cagr(x):
    x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1) if len(x) else float('nan')

def mdd(x):
    w=(1+pd.Series(x,dtype=float).dropna()).cumprod(); return float((w/w.cummax()-1).min()) if len(w) else float('nan')

def sharpe(x):
    x=pd.Series(x,dtype=float).dropna(); return float(x.mean()/x.std(ddof=0)*math.sqrt(12)) if len(x)>1 and x.std(ddof=0)>0 else float('nan')


def panel(monthly):
    ret=monthly.pct_change()
    out=[]
    for i in range(12,len(monthly)-1):
        dt=monthly.index[i]; nxt=monthly.index[i+1]
        feats=pd.DataFrame(index=SYMBOLS)
        feats['mom1']=monthly.iloc[i]/monthly.iloc[i-1]-1
        feats['mom3']=monthly.iloc[i]/monthly.iloc[i-3]-1
        feats['mom6']=monthly.iloc[i]/monthly.iloc[i-6]-1
        feats['mom12']=monthly.iloc[i]/monthly.iloc[i-12]-1
        feats['vol3']=ret.iloc[i-2:i+1].std(ddof=0)
        feats['dd6']=monthly.iloc[i]/monthly.iloc[i-5:i+1].max()-1
        for c in FEATURES:
            s=feats[c]; sd=float(s.std(ddof=0)); feats[c]=(s-float(s.mean()))/(sd if sd>1e-12 else 1.0)
        future=monthly.iloc[i+1]/monthly.iloc[i]-1
        if feats.isna().any().any() or future.isna().any(): continue
        for s in SYMBOLS:
            out.append({'signal':dt,'outcome':nxt,'symbol':s,'target':float(future[s]),**{c:float(feats.loc[s,c]) for c in FEATURES}})
    return pd.DataFrame(out)


def fit_predict(train,cur):
    X=train[list(FEATURES)].to_numpy(float); y=train.target.to_numpy(float)
    X=np.c_[np.ones(len(X)),X]; xc=cur[list(FEATURES)].to_numpy(float); xc=np.c_[np.ones(len(xc)),xc]
    pen=np.eye(X.shape[1]); pen[0,0]=0
    b=np.linalg.solve(X.T@X+RIDGE_ALPHA*pen,X.T@y)
    return xc@b


def build(monthly):
    p=panel(monthly); signals=sorted(p.signal.unique()); rec=[]; prev={s:0.0 for s in SYMBOLS}
    for k,dt in enumerate(signals):
        if k<MIN_TRAIN_MONTHS: continue
        cur=p[p.signal==dt].copy(); train=p[p.outcome<=dt]
        if len(cur)!=len(SYMBOLS) or train.signal.nunique()<MIN_TRAIN_MONTHS: continue
        cur['pred']=fit_predict(train,cur); chosen=set(cur.sort_values(['pred','symbol'],ascending=[False,True]).head(TOP_K).symbol)
        w={s:(1/TOP_K if s in chosen else 0.0) for s in SYMBOLS}; turn=.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS)
        outdt=pd.Timestamp(cur.outcome.iloc[0]); r=monthly.loc[outdt]/monthly.loc[pd.Timestamp(dt)]-1
        rec.append({'date':outdt,'gross':sum(w[s]*float(r[s]) for s in SYMBOLS),'matched':float(r.mean()),'qqq':float(r['QQQ']),'turnover':turn})
        prev=w
    return pd.DataFrame(rec).set_index('date')


def score(f,bps,mask=None):
    q=f if mask is None else f.loc[mask]
    cand=q.gross-q.turnover*bps/10000.0; folds=[]
    for n,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
        z=q.iloc[ids]; c=z.gross-z.turnover*bps/10000.0
        folds.append({'fold':n,'excess_vs_matched':cagr(c)-cagr(z.matched),'excess_vs_qqq':cagr(c)-cagr(z.qqq)})
    return {'months':len(q),'start':str(q.index.min().date()),'end':str(q.index.max().date()),'candidate_cagr':cagr(cand),'matched_cagr':cagr(q.matched),'qqq_cagr':cagr(q.qqq),'excess_vs_matched':cagr(cand)-cagr(q.matched),'excess_vs_qqq':cagr(cand)-cagr(q.qqq),'candidate_max_drawdown':mdd(cand),'matched_max_drawdown':mdd(q.matched),'qqq_max_drawdown':mdd(q.qqq),'candidate_sharpe':sharpe(cand),'matched_sharpe':sharpe(q.matched),'positive_folds_vs_matched':sum(x['excess_vs_matched']>0 for x in folds),'positive_folds_vs_qqq':sum(x['excess_vs_qqq']>0 for x in folds),'annual_turnover':float(q.turnover.mean()*12),'folds':folds}


def main():
    close=load(); monthly=close.resample('ME').last(); f=build(monthly)
    tests={}
    for bp in COSTS:
        tests[str(bp)]={'full':score(f,bp),'2019_forward':score(f,bp,f.index>=pd.Timestamp('2019-01-01')),'2022_forward':score(f,bp,f.index>=pd.Timestamp('2022-01-01'))}
    p=tests['50']; support=p['full']['excess_vs_matched']>0 and p['full']['positive_folds_vs_matched']>=3 and p['2022_forward']['excess_vs_matched']>0
    decision='P83_EXPANDING_RIDGE_SUPPORTED_FOR_DEEPER_VALIDATION' if support else 'P83_EXPANDING_RIDGE_NOT_SUPPORTED'
    out={'schema':'research.p83_expanding_ridge_crossasset_r1','parent':'P83','hypothesis':'A fixed causal expanding-window linear ranker combining multi-horizon momentum, volatility and drawdown can add after-cost selection alpha beyond same-universe equal weight without hand-tuned regime rules.','scientific_contract':{'universe':list(SYMBOLS),'features':list(FEATURES),'ridge_alpha':RIDGE_ALPHA,'min_train_months':MIN_TRAIN_MONTHS,'top_k':TOP_K,'monthly_refit':True,'training_rule':'only rows whose realized target month is complete by the signal month','cross_sectional_feature_standardization':True,'costs_bps':list(COSTS),'matched_control':'same-universe equal weight exact months','opportunity_control':'QQQ exact months','no_hyperparameter_search':True},'tests':tests,'decision':decision,'next_rule':'If supported, next test must be coefficient/sign stability plus an independent representation or frozen forward split. If not supported, kill this fixed learned family rather than tune ridge alpha/top-k/features.'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p83_expanding_ridge_crossasset_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'tests':tests},sort_keys=True))

if __name__=='__main__': main()
