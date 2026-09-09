from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p66_combination_serial_persistence_r1 as p66

BP=50; P36_DELAY=1; WINDOWS={'full':'2005-01-01','2015_forward':'2015-01-01','2022_forward':'2022-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); ann=float(r.mean()*12)
    return {'cagr':cagr(r),'max_drawdown':float((e/e.cummax()-1).min()),'annualized_vol':v,'sharpe_rf0':ann/v if v else float('nan')}

def p36_frame():
    close=base.load(('SOXX',)).dropna(subset=['SOXX','QQQ']).sort_index(); idx=close.index
    mes=pd.Series(idx,index=idx).groupby(idx.to_period('M')).max().tolist(); mes=[pd.Timestamp(x) for x in mes]; m=close.loc[mes]
    rel=m['SOXX'].pct_change(6)-m['QQQ'].pct_change(6); sig={pd.Timestamp(dt):(1.0 if rel.loc[dt]>0 else 0.0) for dt in m.index if pd.notna(rel.loc[dt])}; labels=list(sig); rec=[]; prev=None
    for i in range(len(labels)-1):
        dt,nxt=labels[i],labels[i+1]; a0=idx.get_indexer([dt],method='pad')[0]+P36_DELAY; z0=idx.get_indexer([nxt],method='pad')[0]+P36_DELAY
        if a0<0 or z0<0 or z0>=len(idx): continue
        w=sig[dt]; ar=float(close.iloc[z0]['SOXX']/close.iloc[a0]['SOXX']-1); qr=float(close.iloc[z0]['QQQ']/close.iloc[a0]['QQQ']-1); turn=1.0 if prev is None else abs(w-prev)
        rec.append((idx[z0],w*ar+(1-w)*qr-turn*BP/10000,0.5*ar+0.5*qr,qr)); prev=w
    return pd.DataFrame(rec,columns=['date','p36','p36_matched','qqq']).set_index('date'),close

def main():
    p64,_=p66.frame(BP); p36,close=p36_frame(); idx=p64.index.intersection(p36.index)
    fr=pd.DataFrame(index=idx)
    fr['candidate']=0.5*p64.loc[idx,'candidate']+0.5*p36.loc[idx,'p36']
    fr['matched']=0.5*p64.loc[idx,'matched']+0.5*p36.loc[idx,'p36_matched']
    fr['qqq']=p36.loc[idx,'qqq']
    tests={}
    for name,start in WINDOWS.items():
        q=fr.loc[fr.index>=pd.Timestamp(start)].copy(); folds=[]
        for i,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
            z=q.iloc[ids]
            if len(z): folds.append({'fold':i,'excess_vs_matched':cagr(z.candidate)-cagr(z.matched),'excess_vs_qqq':cagr(z.candidate)-cagr(z.qqq)})
        tests[name]={'months':len(q),'candidate':metrics(q.candidate),'matched':metrics(q.matched),'qqq':metrics(q.qqq),'excess_cagr_vs_matched':cagr(q.candidate)-cagr(q.matched),'excess_cagr_vs_qqq':cagr(q.candidate)-cagr(q.qqq),'positive_folds_vs_matched':sum(x['excess_vs_matched']>0 for x in folds),'positive_folds_vs_qqq':sum(x['excess_vs_qqq']>0 for x in folds)}
    recent=tests['2022_forward']; support=recent['excess_cagr_vs_matched']>0 and recent['positive_folds_vs_matched']>=3 and recent['excess_cagr_vs_qqq']>0
    out={'schema':'research.p82_p64_p36_fixed_blend_r1','parent':'P82','hypothesis':'A prospectively fixed 50/50 blend of the P64 fund-selection sleeve and the only P36 implementation-delay survivor (SOXX, 1 trading day) can preserve matched alpha while improving direct QQQ opportunity cost without tuning either component.','scientific_contract':{'sleeve_weights':[0.5,0.5],'component_cost_bps':BP,'p36_entry_delay_trading_days':P36_DELAY,'p36_representation':'SOXX_vs_QQQ','p64':'unchanged fixed 50/50 parsimonious cross-asset + independent-industry blend','matched_control':'same 50/50 blend of P64 matched static universe and P36 static SOXX/QQQ','opportunity_control':'QQQ','windows':WINDOWS,'chronological_folds':5,'no_parameter_or_weight_tuning':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','soxx_qqq_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P82_FIXED_BLEND_SUPPORTED' if support else 'P82_FIXED_BLEND_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p82_p64_p36_fixed_blend_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
