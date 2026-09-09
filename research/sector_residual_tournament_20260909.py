import importlib.util, json
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
SOURCE='/tmp/source.py'; spec=importlib.util.spec_from_file_location('src',SOURCE); src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
FAMILIES={
 'healthcare':('XLV',('LLY','JNJ','UNH','ABBV','MRK','TMO','ABT','AMGN')),
 'energy':('XLE',('XOM','CVX','COP','EOG','SLB','MPC','PSX','OXY')),
 'software':('IGV',('MSFT','ORCL','ADBE','CRM','INTU','NOW','ADSK','CDNS')),
 'homebuilders':('ITB',('DHI','LEN','PHM','NVR','TOL','KBH','MTH','TMHC')),
}
H=20; DELAY=1; STEP=20; FEATURES=('rs20','rs60','rs126','beta126','resid_vol20','resid_vol60','rel_dd60','rs_accel')
def mom(x,n): return x/x.shift(n)-1
def evaluate(name, benchmark, stocks):
    allsym=(*stocks,benchmark,'SPY','QQQ'); raw={}
    try:
        for s in allsym: raw[s]=src._load(s)
    except Exception as exc:
        return {'family':name,'benchmark':benchmark,'stocks':stocks,'decision':'SOURCE_BLOCKED','error':f'{type(exc).__name__}: {exc}'}
    common=set(raw[allsym[0]].timestamp)
    for s in allsym[1:]: common &= set(raw[s].timestamp)
    cal=pd.DatetimeIndex(sorted(common)); px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in allsym}
    if len(cal)<1800 or any(v.isna().any() for v in px.values()): return {'family':name,'decision':'CALENDAR_INSUFFICIENT','calendar_rows':len(cal)}
    br=px[benchmark].pct_change(); rows=[]
    for s in stocks:
        p=px[s]; r=p.pct_change(); f=pd.DataFrame(index=cal); f['i']=np.arange(len(cal))
        for n in (20,60,126): f[f'rs{n}']=mom(p,n)-mom(px[benchmark],n)
        beta=r.rolling(126).cov(br)/br.rolling(126).var(); f['beta126']=beta; resid=r-beta*br
        f['resid_vol20']=resid.rolling(20).std(ddof=0); f['resid_vol60']=resid.rolling(60).std(ddof=0)
        f['rel_dd60']=(p/p.rolling(60).max()-1)-(px[benchmark]/px[benchmark].rolling(60).max()-1); f['rs_accel']=f.rs20-f.rs60
        f['target']=((p.shift(-(DELAY+H))/p.shift(-DELAY)-1)-(px[benchmark].shift(-(DELAY+H))/px[benchmark].shift(-DELAY)-1))*10000
        f['symbol']=s; rows.append(f.reset_index(names='timestamp'))
    panel=pd.concat(rows,ignore_index=True).replace([np.inf,-np.inf],np.nan); ds=[]
    for i in range(756,len(cal)-(H+DELAY),STEP):
        train=panel[(panel.i<i-(H+DELAY))&(panel.i%5==0)].dropna(subset=[*FEATURES,'target']); test=panel[panel.i==i].dropna(subset=[*FEATURES])
        if len(train)<3000 or len(test)!=len(stocks): continue
        model=Pipeline([('s',StandardScaler()),('r',Ridge(alpha=10.0))]); model.fit(train[list(FEATURES)],train.target)
        test=test.copy(); test['pred']=model.predict(test[list(FEATURES)]); chosen=test.nlargest(3,'pred').symbol.tolist(); e=i+DELAY; x=e+H
        rec={'year':int(cal[e].year),'gross':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in chosen])*10000),'equal':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in stocks])*10000),'bench':float((px[benchmark].iloc[x]/px[benchmark].iloc[e]-1)*10000),'spy':float((px['SPY'].iloc[x]/px['SPY'].iloc[e]-1)*10000),'qqq':float((px['QQQ'].iloc[x]/px['QQQ'].iloc[e]-1)*10000)}; ds.append(rec)
    if len(ds)<30: return {'family':name,'benchmark':benchmark,'stocks':stocks,'decisions':len(ds),'decision':'SAMPLE_INSUFFICIENT'}
    df=pd.DataFrame(ds); metrics={}
    for cost in (25.,50.,100.):
        net=df.gross-cost; mm={}
        for k,col in [('benchmark','bench'),('equal','equal'),('SPY','spy'),('QQQ','qqq')]:
            ex=net-df[col]; ys={str(y):float(ex[df.year==y].mean()) for y in sorted(df.year.unique())}; mm[k]={'excess_bps_per_decision':float(ex.mean()),'positive_years':sum(v>0 for v in ys.values()),'year_count':len(ys)}
        metrics[str(int(cost))]=mm
    p=metrics['50']; checks={'benchmark_positive':p['benchmark']['excess_bps_per_decision']>0,'equal_positive':p['equal']['excess_bps_per_decision']>0,'year_breadth':p['benchmark']['positive_years']>=max(4,(p['benchmark']['year_count']+1)//2),'cost100_positive':metrics['100']['benchmark']['excess_bps_per_decision']>0}
    return {'family':name,'benchmark':benchmark,'stocks':stocks,'decisions':len(ds),'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'metrics':metrics,'checks':checks,'decision':'SURVIVES_MATCHED_ALPHA_GATE' if all(checks.values()) else 'REJECT_OR_ROTATE_EXACT_MODEL'}
results={k:evaluate(k,*v) for k,v in FAMILIES.items()}; survivors=[k for k,v in results.items() if v.get('decision')=='SURVIVES_MATCHED_ALPHA_GATE']
out={'schema':'sector_residual_tournament.v1','contract':{'model':'expanding pooled StandardScaler+Ridge(alpha=10)','features':FEATURES,'target':'forward20_stock_minus_sector_etf','selection':'top3_of8','costs_bps':[25,50,100],'no_parameter_tuning':True},'results':results,'survivors':survivors,'decision':'HAS_SURVIVOR_REQUIRES_HOLDOUT' if survivors else 'RESIDUAL_SELECTOR_TRANSPORT_NOT_SUPPORTED','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('SECTOR_RESIDUAL_TOURNAMENT='+json.dumps(out,sort_keys=True))
