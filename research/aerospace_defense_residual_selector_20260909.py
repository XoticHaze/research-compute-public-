import importlib.util, json
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SOURCE='/tmp/source.py'
spec=importlib.util.spec_from_file_location('src',SOURCE)
src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
STOCKS=('LMT','NOC','GD','RTX','LHX','HII','TDG','HEI')
CTX=('ITA','SPY','QQQ')
H=20; DELAY=1; STEP=20
FEATURES=('rs20','rs60','rs126','beta126','resid_vol20','resid_vol60','rel_dd60','rs_accel')
ALL=(*STOCKS,*CTX)
raw={}
for s in ALL:
    try: raw[s]=src._load(s)
    except Exception as exc: raise RuntimeError(f'source_load_failed symbol={s}: {type(exc).__name__}: {exc}') from exc
common=set(raw[ALL[0]].timestamp)
for s in ALL[1:]: common &= set(raw[s].timestamp)
cal=pd.DatetimeIndex(sorted(common)); px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in ALL}
if len(cal)<1800 or any(v.isna().any() for v in px.values()): raise RuntimeError('insufficient matched aerospace-defense calendar')
def mom(x,n): return x/x.shift(n)-1
bench=px['ITA']; br=bench.pct_change(); rows=[]
for s in STOCKS:
    p=px[s]; r=p.pct_change(); f=pd.DataFrame(index=cal); f['i']=np.arange(len(cal))
    for n in (20,60,126): f[f'rs{n}']=mom(p,n)-mom(bench,n)
    beta=r.rolling(126).cov(br)/br.rolling(126).var(); f['beta126']=beta
    resid=r-beta*br; f['resid_vol20']=resid.rolling(20).std(ddof=0); f['resid_vol60']=resid.rolling(60).std(ddof=0)
    f['rel_dd60']=(p/p.rolling(60).max()-1)-(bench/bench.rolling(60).max()-1); f['rs_accel']=f.rs20-f.rs60
    f['target']=((p.shift(-(DELAY+H))/p.shift(-DELAY)-1)-(bench.shift(-(DELAY+H))/bench.shift(-DELAY)-1))*10000
    f['symbol']=s; rows.append(f.reset_index(names='timestamp'))
panel=pd.concat(rows,ignore_index=True).replace([np.inf,-np.inf],np.nan); decisions=[]
for i in range(756,len(cal)-(H+DELAY),STEP):
    train=panel[(panel.i<i-(H+DELAY)) & (panel.i%5==0)].dropna(subset=[*FEATURES,'target']); test=panel[panel.i==i].dropna(subset=[*FEATURES])
    if len(train)<3000 or len(test)!=len(STOCKS): continue
    m=Pipeline([('s',StandardScaler()),('r',Ridge(alpha=10.0))]); m.fit(train[list(FEATURES)],train.target)
    test=test.copy(); test['pred']=m.predict(test[list(FEATURES)]); chosen=test.nlargest(3,'pred').symbol.tolist(); e=i+DELAY; x=e+H
    gross=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in chosen])*10000); equal=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in STOCKS])*10000)
    rec={'signal':cal[i].isoformat(),'entry':cal[e].isoformat(),'exit':cal[x].isoformat(),'year':int(cal[e].year),'chosen':chosen,'gross_bps':gross,'equal_stocks_bps':equal}
    for b in CTX: rec[f'{b}_bps']=float((px[b].iloc[x]/px[b].iloc[e]-1)*10000)
    decisions.append(rec)
contract={'universe':STOCKS,'benchmark':'ITA','model':'expanding pooled StandardScaler+Ridge(alpha=10)','target':'forward20_stock_minus_ITA','features':FEATURES,'selection':'top3','rebalance_step_days':STEP,'entry_delay_days':DELAY,'costs_bps':[25,50,100],'no_parameter_tuning':True}
if len(decisions)<30:
    out={'schema':'aerospace_defense_residual_selector.v1','contract':contract,'window':{'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'decisions':len(decisions)},'metrics':{},'checks':{'minimum_30_decisions':False},'decision':'SAMPLE_INSUFFICIENT','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
else:
    df=pd.DataFrame(decisions); metrics={}
    for cost in (25.,50.,100.):
        net=df.gross_bps-cost; mm={}
        for b,col in [('ITA','ITA_bps'),('EQUAL_STOCKS','equal_stocks_bps'),('SPY','SPY_bps'),('QQQ','QQQ_bps')]:
            ex=net-df[col]; years={str(y):float(ex[df.year==y].mean()) for y in sorted(df.year.unique())}; mm[b]={'excess_bps_per_decision':float(ex.mean()),'positive_years':sum(v>0 for v in years.values()),'year_count':len(years),'year_excess_bps':years}
        metrics[str(int(cost))]=mm
    p=metrics['50']; checks={'minimum_30_decisions':True,'ita_positive':p['ITA']['excess_bps_per_decision']>0,'equal_positive':p['EQUAL_STOCKS']['excess_bps_per_decision']>0,'ita_year_breadth':p['ITA']['positive_years']>=max(4,(p['ITA']['year_count']+1)//2),'cost100_ita_positive':metrics['100']['ITA']['excess_bps_per_decision']>0}
    decision='SUPPORTED_REQUIRES_INDEPENDENT_HOLDOUT' if all(checks.values()) else 'AEROSPACE_DEFENSE_RESIDUAL_NOT_SUPPORTED'
    out={'schema':'aerospace_defense_residual_selector.v1','contract':contract,'window':{'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'first_entry':df.entry.min(),'last_exit':df.exit.max(),'decisions':len(df)},'metrics':metrics,'checks':checks,'decision':decision,'research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('AEROSPACE_DEFENSE_RESIDUAL='+json.dumps(out,sort_keys=True))
