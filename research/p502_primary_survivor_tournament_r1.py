from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p502_primary_survivor_tournament_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
CROSS=('SPY','QQQ','TLT','GLD','DBC');IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI');IND2=('XAR','XBI','XHB','XME','XOP','XPH','XRT','XSD','XSW','XTN','KRE')
T=list(dict.fromkeys((*CROSS,*IND,*IND2,'AVUV','AVDV','IJR','VSS','SPMO','IJS')));P64BP=50;P36BP=50;SVBP=10;INDBP=25;P308BP=25
raw=yf.download(T,start='2005-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False);c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw).dropna(how='all').astype(float);m=c.resample('ME').last();r=m.pct_change(fill_method=None)
def stats(s):
 q=pd.Series(s,dtype=float).dropna();w=(1+q).cumprod();vol=q.std(ddof=1)*math.sqrt(12);return {'months':len(q),'cagr':float(w.iloc[-1]**(12/len(q))-1),'sharpe':float(q.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def endpoint(s,bps):
 q=pd.Series(s,dtype=float).dropna().copy();f=bps/10000
 if len(q):q.iloc[0]-=f;q.iloc[-1]-=f
 return q
def rank_frame(symbols,topk):
 mm=c[list(symbols)].resample('ME').last();mom=mm.pct_change(6);trend=(c[list(symbols)]/c[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last();prev={s:0. for s in symbols};rows=[]
 for dt in mm.index:
  b=pd.DataFrame({'mom':mom.loc[dt,list(symbols)],'trend':trend.loc[dt,list(symbols)]},index=list(symbols));loc=mm.index.get_loc(dt)
  if b.isna().any().any() or not isinstance(loc,(int,np.integer)) or loc+1>=len(mm):continue
  score=b.rank(axis=0,pct=True).mean(axis=1);nxt=mm.index[loc+1];rr=mm.loc[nxt,list(symbols)]/mm.loc[dt,list(symbols)]-1
  if rr.isna().any():continue
  chosen=score.nlargest(topk).index;w={s:(1/topk if s in chosen else 0.) for s in symbols};to=.5*sum(abs(w[s]-prev[s]) for s in symbols);rows.append((nxt,sum(w[s]*float(rr[s]) for s in symbols),float(rr.mean()),to));prev=w
 return pd.DataFrame(rows,columns=['date','gross','matched','turn']).set_index('date')
a=rank_frame(CROSS,2);b=rank_frame(IND,3);ix=a.index.intersection(b.index);p64=pd.DataFrame({'x':.5*(a.loc[ix].gross-a.loc[ix].turn*P64BP/10000)+.5*(b.loc[ix].gross-b.loc[ix].turn*P64BP/10000),'ctl':.5*a.loc[ix].matched+.5*b.loc[ix].matched},index=ix);p64.index=p64.index.to_period('M').to_timestamp('M')
def p36():
 z=c[['SOXX','QQQ']].dropna();idx=z.index;mm=z.resample('ME').last();rel=mm.SOXx.pct_change(6)-mm.QQQ.pct_change(6) if 'SOXx' in mm.columns else mm.SOXx;sig={dt:(1. if rel.loc[dt]>0 else 0.) for dt in mm.index if pd.notna(rel.loc[dt])};labs=list(sig);prev=None;rows=[]
 for i in range(len(labs)-1):
  dt,nxt=labs[i],labs[i+1];i0=idx.get_indexer([dt],method='pad')[0]+1;i1=idx.get_indexer([nxt],method='pad')[0]+1
  if i0<0 or i1<0 or i1>=len(idx):continue
  w=sig[dt];ar=float(z.iloc[i1].SOXX/z.iloc[i0].SOXX-1);qr=float(z.iloc[i1].QQQ/z.iloc[i0].QQQ-1);to=1. if prev is None else abs(w-prev);rows.append((idx[i1],w*ar+(1-w)*qr-to*P36BP/10000,.5*(ar+qr)));prev=w
 q=pd.DataFrame(rows,columns=['date','x','ctl']).set_index('date');q.index=q.index.to_period('M').to_timestamp('M');return q
p36x=p36();svr=m[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None);sv=.5*(svr.AVUV+svr.AVDV);svctl=.5*(svr.IJR+svr.VSS)
base=sv.to_frame('sv').join(svctl.rename('svctl')).join(p64.rename(columns={'x':'p64','ctl':'p64ctl'})).join(p36x.rename(columns={'x':'p36','ctl':'p36ctl'})).dropna();p249=pd.DataFrame({'x':(base.sv+base.p64+base.p36)/3,'ctl':(base.svctl+base.p64ctl+base.p36ctl)/3},index=base.index)
def industry():
 mm=m[list(IND2)].dropna();ret=mm.pct_change();score=mm.shift(1)/mm.shift(12)-1;w=pd.DataFrame(0.,index=mm.index,columns=IND2)
 for dt,row in score.iterrows():
  if row.notna().sum()==len(IND2):w.loc[dt,row.nlargest(3).index]=1/3
 gross=(w*ret).sum(axis=1);turn=.5*w.diff().abs().sum(axis=1);active=w.sum(axis=1)>0
 if active.any():turn.loc[active.idxmax()]=1.
 cand=gross-turn*INDBP/10000;ctl=ret.mean(axis=1).copy()
 if active.any():ctl.loc[active.idxmax()]-=INDBP/10000
 return pd.DataFrame({'x':cand,'ctl':ctl})
ind=industry();p272=base.join(ind.rename(columns={'x':'ind','ctl':'indctl'})).dropna();p272=pd.DataFrame({'x':(p272.sv+p272.p64+p272.p36+p272.ind)/4,'ctl':(p272.svctl+p272.p64ctl+p272.p36ctl+p272.indctl)/4},index=p272.index)
gross=.5*r.SPMO+.5*r.IJS;drift=.5*(1+r.SPMO)/(1+gross);turn=2*(drift-.5).abs();p308=pd.DataFrame({'x':gross-turn*P308BP/10000,'ctl':.5*r.SPY+.5*r.IJR},index=r.index)
q=p249.rename(columns={'x':'p249','ctl':'p249ctl'}).join(p272.rename(columns={'x':'p272','ctl':'p272ctl'})).join(p308.rename(columns={'x':'p308','ctl':'p308ctl'})).join(r.SPY.rename('spy')).dropna().loc['2020-01-01':]
# Apply only the historical endpoint small-value friction still external to P249/P272; P308 turnover cost is embedded.
series={'P249':endpoint(q.p249,SVBP/3),'P249_P266':endpoint(q.p272,SVBP/4),'P308':q.p308,'SPY':endpoint(q.spy,25)};ctls={'P249':endpoint(q.p249ctl,SVBP/3),'P249_P266':endpoint(q.p272ctl,SVBP/4),'P308':q.p308ctl}
def evaluate(z):
 out={}
 for k in ['P249','P249_P266','P308']:
  s=series[k].reindex(z).dropna();ctl=ctls[k].reindex(z).dropna();sm=stats(s);cm=stats(ctl);out[k]={**sm,'matched_excess_cagr':sm['cagr']-cm['cagr'],'vs_spy_cagr':sm['cagr']-stats(series['SPY'].reindex(z))['cagr']}
 ret=pd.DataFrame({k:series[k].reindex(z) for k in ['P249','P249_P266','P308']}).dropna();out['correlation']=ret.corr().to_dict();neg=ret<0;out['all_three_negative_fraction']=float(neg.all(axis=1).mean());return out
full=evaluate(q.index);sizes=[len(q)//3,len(q)//3,len(q)-2*(len(q)//3)];chrono={};off=0
for i,n in enumerate(sizes,1):chrono[f'block_{i}']=evaluate(q.index[off:off+n]);off+=n
# Scientific evidence rule only: robust leader must rank first in matched excess and Sharpe, not have >2pp worse maxDD than best, beat SPY, and be first in matched excess in >=2/3 blocks.
keys=['P249','P249_P266','P308'];bestdd=max(full[k]['max_drawdown'] for k in keys);leader=None
for k in keys:
 wins=sum(full[k]['matched_excess_cagr']>=full[j]['matched_excess_cagr'] for j in keys);swins=sum(full[k]['sharpe']>=full[j]['sharpe'] for j in keys);blocks=sum(chrono[b][k]['matched_excess_cagr']>=max(chrono[b][j]['matched_excess_cagr'] for j in keys) for b in chrono)
 if wins==3 and swins==3 and full[k]['max_drawdown']>=bestdd-.02 and full[k]['vs_spy_cagr']>0 and blocks>=2:leader=k
out={'schema':'research.p502_primary_survivor_tournament_r1.v1','workload_id':'P502_PRIMARY_SURVIVOR_TOURNAMENT_R1','parent':'FUND_MODEL_SURVIVOR_TOURNAMENT','claim':'Execute the Coordinator-reserved fixed scientific tournament across P249 core, frozen P249+P266 equal-quarter P272 construction, and P308 SPMO+IJS on one common aligned sample with frozen costs and matched/broad opportunity controls. Scientific evidence only; Coordinator retains capital ranking/allocation.','coverage':{'start':str(q.index.min().date()),'end':str(q.index.max().date()),'months':len(q),'block_sizes':sizes},'full_sample':full,'chronology':chrono,'decision':'SCIENTIFIC_EVIDENCE_LEADER_'+leader if leader else 'PRIMARY_TOURNAMENT_NO_ROBUST_SCIENTIFIC_LEADER','decision_rule':'A scientific evidence leader must be first in full-sample matched excess and Sharpe, maxDD within 2pp of best, positive versus SPY, and first in matched excess in >=2/3 fixed chronology blocks. This is not portfolio allocation authority.','forbidden':['weight search','regime search','lookback/top-k search','product substitution','window selection','post-hoc capital rule tuning'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':out['decision'],'months':len(q),'metrics':{k:{m:round(full[k][m]*100,3) if m!='sharpe' else round(full[k][m],3) for m in ['cagr','matched_excess_cagr','vs_spy_cagr','max_drawdown','sharpe']} for k in keys},'block_matched_excess':{b:{k:round(chrono[b][k]['matched_excess_cagr']*100,3) for k in keys} for b in chrono}},sort_keys=True))
