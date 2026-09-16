from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p501_p249_vs_p305_dbmf25_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
CROSS=('SPY','QQQ','TLT','GLD','DBC'); IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
T=list(dict.fromkeys((*CROSS,*IND,'AVUV','AVDV','IJR','VSS','SPMO','IJS','DBMF','BIL')))
P64_BP=50;P36_BP=50;SV_BP=10;EP=.0025
raw=yf.download(T,start='2005-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;close=close.dropna(how='all').astype(float);cm=close.resample('ME').last();r=cm.pct_change(fill_method=None)
def metrics(s):
 q=pd.Series(s,dtype=float).dropna();n=len(q);w=(1+q).cumprod();vol=q.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(q.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ep(s,bps):
 q=pd.Series(s,dtype=float).dropna().copy();f=bps/10000
 if len(q):q.iloc[0]-=f;q.iloc[-1]-=f
 return q
def rank_frame(symbols,topk):
 m=close[list(symbols)].resample('ME').last();mom=m.pct_change(6);trend=(close[list(symbols)]/close[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last();prev={s:0. for s in symbols};rec=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(symbols)],'trend200':trend.loc[dt,list(symbols)]},index=list(symbols))
  if b.isna().any().any():continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1);loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m):continue
  nxt=m.index[loc+1];rr=m.loc[nxt,list(symbols)]/m.loc[dt,list(symbols)]-1
  if rr.isna().any():continue
  chosen=score.sort_values(ascending=False).head(topk).index;w={s:(1/topk if s in chosen else 0.) for s in symbols};to=.5*sum(abs(w[s]-prev[s]) for s in symbols);rec.append((nxt,sum(w[s]*float(rr[s]) for s in symbols),float(rr.mean()),to));prev=w
 return pd.DataFrame(rec,columns=['date','gross','matched','turnover']).set_index('date')
a=rank_frame(CROSS,2);b=rank_frame(IND,3);ix=a.index.intersection(b.index);p64=pd.DataFrame({'candidate':.5*(a.loc[ix].gross-a.loc[ix].turnover*P64_BP/10000)+.5*(b.loc[ix].gross-b.loc[ix].turnover*P64_BP/10000),'matched':.5*a.loc[ix].matched+.5*b.loc[ix].matched},index=ix);p64.index=p64.index.to_period('M').to_timestamp('M')
def p36_exact():
 c=close[['SOXX','QQQ']].dropna().sort_index();idx=c.index;m=c.resample('ME').last();rel=m.SOXx.pct_change(6)-m.QQQ.pct_change(6) if 'SOXx' in m.columns else m['SOXX'].pct_change(6)-m['QQQ'].pct_change(6);sig={pd.Timestamp(dt):(1. if rel.loc[dt]>0 else 0.) for dt in m.index if pd.notna(rel.loc[dt])};labels=list(sig);prev=None;rec=[]
 for i in range(len(labels)-1):
  dt,nxt=labels[i],labels[i+1];a0=idx.get_indexer([dt],method='pad')[0]+1;z0=idx.get_indexer([nxt],method='pad')[0]+1
  if a0<0 or z0<0 or z0>=len(idx):continue
  w=sig[dt];ar=float(c.iloc[z0].SOXX/c.iloc[a0].SOXX-1);qr=float(c.iloc[z0].QQQ/c.iloc[a0].QQQ-1);turn=1. if prev is None else abs(w-prev);rec.append((idx[z0],w*ar+(1-w)*qr-turn*P36_BP/10000,.5*ar+.5*qr));prev=w
 z=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date');z.index=z.index.to_period('M').to_timestamp('M');return z
p36=p36_exact();svr=cm[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None);sv=.5*(svr.AVUV+svr.AVDV);svctl=.5*(svr.IJR+svr.VSS)
x=sv.to_frame('sv').join(svctl.rename('svctl')).join(p64.rename(columns={'candidate':'p64','matched':'p64ctl'})).join(p36.rename(columns={'candidate':'p36','matched':'p36ctl'})).dropna();p249=pd.DataFrame({'candidate':(x.sv+x.p64+x.p36)/3,'matched':(x.svctl+x.p64ctl+x.p36ctl)/3},index=x.index)
p305=pd.DataFrame({'candidate':.5*(r.SPMO+r.IJS),'matched':.5*(r.SPY+r.IJR)},index=r.index)
q=p249.rename(columns={'candidate':'p249','matched':'p249ctl'}).join(p305.rename(columns={'candidate':'p305','matched':'p305ctl'})).join(r[['DBMF','BIL']]).dropna().loc['2021-01-01':]
idx=q.index;n=len(q);periods=idx.to_period('M').astype(int);contiguous=bool(np.all(np.diff(periods)==1));sizes=[n//3,n//3,n-2*(n//3)];eligible=n>=54 and contiguous and min(sizes)>=18
if not eligible:
 out={'schema':'research.p501_p249_vs_p305_dbmf25_r1.v1','decision':'COVERAGE_GATE_FAILED','common_months':n,'contiguous':contiguous,'block_sizes':sizes};OUT.write_text(json.dumps(out,indent=2));print(json.dumps(out));raise SystemExit(0)
def ev(z):
 a=.75*z.p249+.25*z.DBMF;ac=.75*z.p249ctl+.25*z.BIL;b=.75*z.p305+.25*z.DBMF;bc=.75*z.p305ctl+.25*z.BIL
 am=metrics(ep(a,25));acm=metrics(ep(ac,25));bm=metrics(ep(b,25));bcm=metrics(ep(bc,25));am['matched_excess_cagr']=am['cagr']-acm['cagr'];bm['matched_excess_cagr']=bm['cagr']-bcm['cagr']
 return {'p249_dbmf25':am,'p249_control':acm,'p305_dbmf25':bm,'p305_control':bcm,'p249_minus_p305':{k:am[k]-bm[k] for k in ['cagr','sharpe','max_drawdown','matched_excess_cagr']}}
full=ev(q);chrono={};off=0
for i,sz in enumerate(sizes,1):z=q.iloc[off:off+sz];off+=sz;chrono[f'block_{i}']=ev(z)
adv=[v['p249_minus_p305']['matched_excess_cagr'] for v in chrono.values()];p249pos=sum(x>0 for x in adv);p305pos=sum(x<0 for x in adv);d=full['p249_minus_p305'];dd_ok_p249=d['max_drawdown']>=-.01;dd_ok_p305=d['max_drawdown']<=.01
if d['matched_excess_cagr']>0 and d['cagr']>0 and d['sharpe']>0 and dd_ok_p249 and p249pos>=2:decision='P249_DBMF25_SCIENTIFICALLY_DOMINATES_P305_DBMF25_ON_FIXED_TEST'
elif d['matched_excess_cagr']<0 and d['cagr']<0 and d['sharpe']<0 and dd_ok_p305 and p305pos>=2:decision='P305_DBMF25_SCIENTIFICALLY_DOMINATES_P249_DBMF25_ON_FIXED_TEST'
else:decision='DBMF25_SIBLINGS_TRADEOFF_NO_SCIENTIFIC_DOMINANCE'
out={'schema':'research.p501_p249_vs_p305_dbmf25_r1.v1','workload_id':'P501_P249_VS_P305_DBMF25_R1','parent':'DBMF_COMPLEMENTARITY_SIBLING_DISCRIMINATOR','claim':'Resolve the P455 identity seam by comparing exactly 75% P249 + 25% DBMF against exactly 75% P305 + 25% DBMF on one common sample. P249 is the frozen equal-third AVUV/AVDV small-value + P64 + P36 capital-role stack; P305 is the frozen 50/50 SPMO + IJS sleeve. This is scientific discrimination, not portfolio ranking.','coverage':{'common_months':n,'contiguous':contiguous,'block_sizes':sizes},'contract':{'p249':'equal thirds: 50/50 AVUV/AVDV small value + P64 + P36','p305':'50/50 SPMO + IJS','dbmf_dose':.25,'matched_dbmf_control':'BIL','endpoint_cost_bps':25,'support_rule':'scientific dominance requires higher full-sample matched excess, CAGR and Sharpe, maxDD not worse by >1pp, and same sibling matched-excess advantage in >=2/3 chronology blocks','no_weight_product_date_cost_threshold_search':True},'full_sample':full,'chronology':chrono,'chronology_p249_advantage_blocks':p249pos,'chronology_p305_advantage_blocks':p305pos,'decision':decision,'scientific_consequence':'Use this only to clarify which fixed sibling has stronger scientific evidence or whether the choice is a tradeoff. Coordinator retains ranking/allocation authority.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'months':n,'full_delta':{k:round(v*100,3) if k!='sharpe' else round(v,3) for k,v in d.items()},'chronology_matched_excess_adv_pp':[round(x*100,3) for x in adv]},sort_keys=True))
