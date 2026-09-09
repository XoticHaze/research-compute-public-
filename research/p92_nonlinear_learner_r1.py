from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier

COSTS=(25,50,100)
ASSETS=['QQQ','RSP','SPY','TLT','GLD']

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod()
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan')
    dd=float((eq/eq.cummax()-1).min()) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'max_drawdown':dd}

def main():
    raw=yf.download(ASSETS,start='2004-11-01',auto_adjust=True,progress=False,threads=False)
    c=raw['Close'].dropna().astype(float); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=c.resample('ME').last(); m=m[m.index<=cutoff]; mr=m.pct_change()
    feats={}
    for a in ASSETS:
        for h in (1,3,6): feats[f'{a}_ret{h}']=m[a].pct_change(h)
        feats[f'{a}_vol6']=mr[a].rolling(6).std(ddof=1)
    X=pd.DataFrame(feats,index=m.index); X['qqq_rsp_rel3']=m.QQQ.pct_change(3)-m.RSP.pct_change(3); X['qqq_rsp_rel6']=m.QQQ.pct_change(6)-m.RSP.pct_change(6)
    nxt=m.shift(-1)/m-1; y=(nxt.QQQ>nxt.RSP).astype(int)
    frame=X.copy(); frame['y']=y; frame['qqq_next']=nxt.QQQ; frame['rsp_next']=nxt.RSP; frame['spy_next']=nxt.SPY; frame=frame.dropna()
    feature_cols=list(X.columns); min_train=60; rows=[]; prev=np.array([.5,.5])
    for i in range(min_train,len(frame)):
        train=frame.iloc[:i]; cur=frame.iloc[[i]]
        model=RandomForestClassifier(n_estimators=300,max_depth=3,min_samples_leaf=8,max_features='sqrt',class_weight='balanced',random_state=23,n_jobs=-1)
        model.fit(train[feature_cols],train.y); p=float(model.predict_proba(cur[feature_cols])[0,1]); choose=p>=.5
        w=np.array([1.,0.]) if choose else np.array([0.,1.]); r=np.array([float(cur.qqq_next.iloc[0]),float(cur.rsp_next.iloc[0])]); turn=.5*float(abs(w-prev).sum())
        rows.append({'date':cur.index[0],'gross':float(w@r),'turnover':turn,'matched':float(.5*r.sum()),'qqq':float(r[0]),'spy':float(cur.spy_next.iloc[0]),'p_qqq':p,'correct':int((r[0]>r[1])==choose)})
        prev=w
    f=pd.DataFrame(rows).set_index('date')
    out={'schema':'research.p92_nonlinear_learner_r1','parent':'P92','hypothesis':'A strict expanding-window shallow random-forest classifier on the unchanged P91 lagged monthly representation can recover nonlinear QQQ-versus-RSP selection alpha.','contract':{'model':'RandomForestClassifier n=300 depth=3 min_leaf=8 sqrt balanced fixed','training':'expanding window, 60-month minimum, no future rows','features':feature_cols,'allocation':'100% QQQ if p>=0.5 else 100% RSP','costs_bps':list(COSTS),'matched_control':'static 50/50 QQQ-RSP','opportunity_controls':['QQQ','SPY'],'windows':['all_oos','2015_forward','2020_forward'],'folds':5,'no_hyperparameter_search':True},'tests':{}}
    for name,start in [('all_oos',None),('2015_forward','2015-01-01'),('2020_forward','2020-01-01')]:
        q=f if start is None else f.loc[start:]; z={'months':len(q),'classification_accuracy':float(q.correct.mean()),'controls':{'matched':metrics(q.matched),'qqq':metrics(q.qqq),'spy':metrics(q.spy)},'costs':{}}
        ids=np.array_split(np.arange(len(q)),5)
        for bp in COSTS:
            net=q.gross-q.turnover*bp/10000; cm=metrics(net); folds=[]
            for j,ix in enumerate(ids,1):
                a=q.iloc[ix]; cand=a.gross-a.turnover*bp/10000; folds.append({'fold':j,'excess_cagr_vs_matched':cagr(cand)-cagr(a.matched),'excess_cagr_vs_qqq':cagr(cand)-cagr(a.qqq)})
            z['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_matched':cm['cagr']-z['controls']['matched']['cagr'],'excess_cagr_vs_qqq':cm['cagr']-z['controls']['qqq']['cagr'],'excess_cagr_vs_spy':cm['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-z['controls']['matched']['sharpe_rf0'],'max_drawdown_delta_vs_matched':cm['max_drawdown']-z['controls']['matched']['max_drawdown'],'positive_matched_folds':sum(x['excess_cagr_vs_matched']>0 for x in folds),'positive_qqq_folds':sum(x['excess_cagr_vs_qqq']>0 for x in folds),'folds':folds}
        out['tests'][name]=z
    p=out['tests']['2020_forward']['costs']['50']; out['decision']='P92_NONLINEAR_LEARNER_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 and p['sharpe_delta_vs_matched']>0 else 'P92_NONLINEAR_LEARNER_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p92_nonlinear_learner_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
