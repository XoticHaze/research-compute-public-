from __future__ import annotations
import json,hashlib,time
from pathlib import Path
import pandas as pd,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC')
def snap():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut,list(U)]; b=d.reset_index().to_csv(index=False,float_format='%.10g').encode(); return d,cut,hashlib.sha256(b).hexdigest()
def main():
 a,ca,ha=snap(); time.sleep(2); b,cb,hb=snap(); idx=a.index.intersection(b.index); cols=list(U); x=a.loc[idx,cols]; y=b.loc[idx,cols]; diff=(x-y).abs(); changed=int((diff>1e-10).sum().sum()); maxdiff=float(diff.max().max()) if len(diff) else None
 out={'schema':'research.yahoo_complete_month_panel_stability_r1','purpose':'Determine whether identical research-only Yahoo adjusted-price requests produce stable complete-month bytes and values within one execution.','request':{'symbols':list(U),'start':'2005-01-01','auto_adjust':True,'complete_month_only':True},'snapshots':[{'rows':len(a),'cut':str(ca.date()),'sha256':ha},{'rows':len(b),'cut':str(cb.date()),'sha256':hb}],'comparison':{'same_hash':ha==hb,'common_rows':len(idx),'changed_cells_gt_1e-10':changed,'max_abs_diff':maxdiff},'classification':'STABLE_WITHIN_EXECUTION' if ha==hb and changed==0 else ('BYTE_HASH_DRIFT_VALUE_STABLE' if changed==0 else 'VALUE_INSTABILITY_DETECTED')}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/yahoo_complete_month_panel_stability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
