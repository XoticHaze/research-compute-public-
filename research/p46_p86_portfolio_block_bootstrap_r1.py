from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import p46_p86_portfolio_complementarity_r1 as base

REPS=3000
BLOCK=12
SEED=20260909


def cagr(r):
    r=np.asarray(r,float); return float(np.prod(1+r)**(12/len(r))-1)


def sharpe(r):
    r=np.asarray(r,float); s=float(np.std(r,ddof=1)); return float(np.mean(r)/s*math.sqrt(12)) if s else float('nan')


def moving_block_indices(n,rng):
    starts=np.arange(max(1,n-BLOCK+1)); out=[]
    while len(out)<n:
        s=int(rng.choice(starts)); out.extend(range(s,min(s+BLOCK,n)))
    return np.asarray(out[:n],int)


def test(frame,seed):
    p46=(frame.p46_gross-frame.p46_turnover*base.BP/10000).to_numpy(float)
    p86=(frame.p86_gross-frame.p86_turnover*base.BP/10000).to_numpy(float)
    qqq=frame.qqq.to_numpy(float); blend=.5*p46+.5*p86
    point={"blend_minus_p86_cagr":cagr(blend)-cagr(p86),"blend_minus_qqq_cagr":cagr(blend)-cagr(qqq),"blend_minus_p86_sharpe":sharpe(blend)-sharpe(p86),"blend_minus_qqq_sharpe":sharpe(blend)-sharpe(qqq)}
    rng=np.random.default_rng(seed); rows=[]
    for _ in range(REPS):
        ix=moving_block_indices(len(frame),rng); z=blend[ix]; a=p86[ix]; q=qqq[ix]
        rows.append((cagr(z)-cagr(a),cagr(z)-cagr(q),sharpe(z)-sharpe(a),sharpe(z)-sharpe(q)))
    a=np.asarray(rows)
    return {"months":len(frame),"point":point,"bootstrap":{"reps":REPS,"block_months":BLOCK,"p_blend_cagr_le_p86":float(np.mean(a[:,0]<=0)),"p_blend_cagr_le_qqq":float(np.mean(a[:,1]<=0)),"p_blend_sharpe_le_p86":float(np.mean(a[:,2]<=0)),"p_blend_sharpe_le_qqq":float(np.mean(a[:,3]<=0)),"blend_minus_p86_cagr_ci95":[float(np.quantile(a[:,0],.025)),float(np.quantile(a[:,0],.975))],"blend_minus_p86_sharpe_ci95":[float(np.quantile(a[:,2],.025)),float(np.quantile(a[:,2],.975))]}}


def main():
    raw=yf.download(list(base.ALL),start='2005-01-01',auto_adjust=True,progress=False,threads=False); close=raw['Close'].dropna(how='all').astype(float)
    last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); close=close.loc[close.index<=cutoff]
    x=base.p46_frame(close); y=base.p86_frame(close); idx=x.index.intersection(y.index); f=pd.DataFrame(index=idx)
    f['p46_gross']=x.gross; f['p46_turnover']=x.turnover; f['p86_gross']=y.gross; f['p86_turnover']=y.turnover; f['qqq']=x.qqq
    tests={name:test(f.loc[start:],SEED+i) for i,(name,start) in enumerate(base.WINDOWS.items())}
    t=tests['2020_forward']; b=t['bootstrap']; decision='P46_P86_PORTFOLIO_UTILITY_BOOTSTRAP_SUPPORTED' if t['point']['blend_minus_p86_cagr']>0 and t['point']['blend_minus_p86_sharpe']>0 and b['p_blend_sharpe_le_p86']<=.10 else 'P46_P86_PORTFOLIO_UTILITY_BOOTSTRAP_FRAGILE'
    out={"schema":"research.p46_p86_portfolio_block_bootstrap_r1","parents":["P46","P86"],"hypothesis":"The fixed 50/50 P46+P86 portfolio utility versus P86 alone is not a sample-path accident under 12-month moving-block resampling.","contract":{"weights":{"P46":0.5,"P86":0.5},"cost_bps_each_sleeve":base.BP,"bootstrap_reps":REPS,"block_months":BLOCK,"windows":base.WINDOWS,"controls":["P86 standalone","QQQ"],"no_weight_or_parameter_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","last_complete_month_end":str(cutoff.date())},"tests":tests,"decision":decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p86_portfolio_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
