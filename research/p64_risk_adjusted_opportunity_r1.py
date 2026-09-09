from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p64_component_contribution_r1 as p64

WINDOWS={'2015_forward':'2015-01-01','2020_forward':'2020-01-01','2022_forward':'2022-01-01'}


def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)

def vol(r):
    r=pd.Series(r,dtype=float).dropna(); return float(r.std(ddof=1)*np.sqrt(12))

def sharpe(r):
    r=pd.Series(r,dtype=float).dropna(); s=r.std(ddof=1); return float(r.mean()/s*np.sqrt(12)) if s>0 else float('nan')

def sortino(r):
    r=pd.Series(r,dtype=float).dropna(); d=r[r<0]; ds=np.sqrt(np.mean(np.square(d))) if len(d) else 0; return float(r.mean()*12/(ds*np.sqrt(12))) if ds>0 else float('nan')

def mdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); return float((e/e.cummax()-1).min())

def metrics(r):
    dd=mdd(r); cg=cagr(r)
    return {'cagr':cg,'vol':vol(r),'sharpe_rf0':sharpe(r),'sortino_rf0':sortino(r),'max_drawdown':dd,'calmar':float(cg/abs(dd)) if dd<0 else None}

def main():
    f,cc,ic,cutoff=p64.build()
    blend=.5*f.cross+.5*f.industry
    matched=.5*f.cross_ctrl+.5*f.industry_ctrl
    qqq=f.qqq
    out={'schema':'research.p64_risk_adjusted_opportunity_r1','parent':'P64','hypothesis':'P64 may remain economically useful despite lower raw CAGR than QQQ if its fixed 50-bps blend delivers superior risk-adjusted and drawdown efficiency on later chronology.','scientific_contract':{'component_cost_bps':50,'sleeve_weights':[0.5,0.5],'controls':['fixed matched blend','QQQ'],'windows':WINDOWS,'metrics':['CAGR','annualized volatility','Sharpe rf0','Sortino rf0','max drawdown','Calmar'],'complete_months_only':True,'no_parameter_or_gate_tuning':True},'tests':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','cross_panel_sha256':p64.base.source_hash(cc),'industry_panel_sha256':p64.base.source_hash(ic),'last_complete_month_end':str(cutoff.date())}}
    for name,start in WINDOWS.items():
        q=pd.DataFrame({'candidate':blend,'matched':matched,'qqq':qqq}).loc[pd.Timestamp(start):].dropna()
        cm,mm,qm=metrics(q.candidate),metrics(q.matched),metrics(q.qqq)
        out['tests'][name]={'months':len(q),'candidate':cm,'matched':mm,'qqq':qm,'cagr_excess_vs_matched':cm['cagr']-mm['cagr'],'cagr_excess_vs_qqq':cm['cagr']-qm['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-mm['sharpe_rf0'],'sharpe_delta_vs_qqq':cm['sharpe_rf0']-qm['sharpe_rf0'],'calmar_delta_vs_matched':cm['calmar']-mm['calmar'],'calmar_delta_vs_qqq':cm['calmar']-qm['calmar']}
    r=out['tests']['2022_forward']
    out['decision']='P64_RECENT_RISK_ADJUSTED_OPPORTUNITY_SUPPORTED' if r['sharpe_delta_vs_qqq']>0 and r['calmar_delta_vs_qqq']>0 and r['cagr_excess_vs_matched']>0 else 'P64_RISK_ADJUSTED_OPPORTUNITY_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_risk_adjusted_opportunity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
