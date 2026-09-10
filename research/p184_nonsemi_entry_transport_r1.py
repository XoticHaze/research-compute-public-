from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRAIN = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")
EXTERNAL = {"CAT":"industrials", "JPM":"financials", "UNH":"healthcare", "WMT":"consumer", "XOM":"energy", "LIN":"materials"}
CONTEXT = ("SMH", "QQQ")
START, END = "2014-01-01", "2026-09-03"
HOLD, DELAY, FOLDS, MIN_TRAIN, PURGE = 20, 1, 6, 756, 22
BASE_COST = 25.0
COSTS = (25, 50, 100, 150, 200)
EVAL_FIRST_FOLD = 2
FEATURES = [
    "mom5","mom20","mom60","mom100","mom20_z252","mom20_accel5","vol20","vol20_z252",
    "distance_high60","rs_smh20","rs_smh60","rs_qqq20","rs_qqq60","smh_mom20","smh_mom100",
    "qqq_mom20","qqq_mom100","survivor_breadth_positive20","survivor_cross_section_mom20_pct",
]
OUTPUT = Path("artifacts/p184_nonsemi_entry_transport_r1.json")


def epoch(text):
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def load(symbol):
    q = urlencode({"period1":epoch(START),"period2":epoch(END),"interval":"1d","events":"history","includeAdjustedClose":"true"})
    req = Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}", headers={"User-Agent":"Mozilla/5.0 research-compute/1.0"})
    with urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode())
    result = (payload.get("chart",{}).get("result") or [None])[0]
    if not result: raise RuntimeError(f"{symbol}: no chart result")
    ind = result.get("indicators",{})
    adj = (ind.get("adjclose") or [{}])[0].get("adjclose")
    close = adj or (ind.get("quote") or [{}])[0].get("close")
    return pd.DataFrame({"timestamp":pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True), "price":pd.to_numeric(pd.Series(close), errors="coerce")}).dropna().drop_duplicates("timestamp",keep="last").sort_values("timestamp").reset_index(drop=True)


def folds(n):
    edges = np.linspace(MIN_TRAIN, n-(HOLD+DELAY+1), FOLDS+1, dtype=int)
    return [(int(edges[i]),int(edges[i+1])) for i in range(FOLDS)]


def engineer(prices, calendar):
    out={}
    for symbol,price in prices.items():
        df=pd.DataFrame({"timestamp":calendar,"price":price.to_numpy(float)})
        df["ret1"]=df.price.pct_change()
        for n in (5,20,60,100): df[f"mom{n}"]=df.price.pct_change(n)
        df["vol20"]=df.ret1.rolling(20,min_periods=20).std(ddof=0)
        pm,pv=df.mom20.shift(1),df.vol20.shift(1)
        mm,ms=pm.rolling(252,min_periods=126).mean(),pm.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan)
        vm,vs=pv.rolling(252,min_periods=126).mean(),pv.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan)
        df["mom20_z252"]=(df.mom20-mm)/ms; df["vol20_z252"]=(df.vol20-vm)/vs
        df["mom20_accel5"]=df.mom20-df.mom20.shift(5)
        df["distance_high60"]=df.price/df.price.rolling(60,min_periods=60).max()-1
        df["enter20_after25_bps"]=(df.price.shift(-(DELAY+HOLD))/df.price.shift(-DELAY)-1)*10000-BASE_COST
        out[symbol]=df
    smh,qqq=out["SMH"],out["QQQ"]
    surv=pd.DataFrame({s:out[s].mom20 for s in TRAIN})
    breadth=(surv>0).mean(axis=1)
    for symbol in (*TRAIN,*EXTERNAL):
        df=out[symbol]
        df["rs_smh20"]=df.mom20-smh.mom20; df["rs_smh60"]=df.mom60-smh.mom60
        df["rs_qqq20"]=df.mom20-qqq.mom20; df["rs_qqq60"]=df.mom60-qqq.mom60
        df["smh_mom20"]=smh.mom20; df["smh_mom100"]=smh.mom100
        df["qqq_mom20"]=qqq.mom20; df["qqq_mom100"]=qqq.mom100
        df["survivor_breadth_positive20"]=breadth
        df["survivor_cross_section_mom20_pct"]=[np.nan if pd.isna(v) else float((surv.iloc[i] <= v).mean()) for i,v in enumerate(df.mom20)]
    return out


def frame(symbols,data,fs):
    rows=[]
    for s in symbols:
        df=data[s].copy(); df["symbol"]=s; df["signal_i"]=np.arange(len(df)); fc=np.zeros(len(df),dtype=int)
        for fold,(start,stop) in enumerate(fs,1): fc[start:max(start,stop-(DELAY+HOLD))]=fold
        df["fold"]=fc
        rows.append(df[df.fold>0][["symbol","signal_i","fold",*FEATURES,"enter20_after25_bps","mom20"]])
    return pd.concat(rows,ignore_index=True).replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES+["enter20_after25_bps"])


def fit(train):
    model=Pipeline([("scale",StandardScaler()),("ridge",Ridge(alpha=10.0))])
    model.fit(train[FEATURES].to_numpy(float),train.enter20_after25_bps.to_numpy(float)); return model


symbols=(*TRAIN,*EXTERNAL,*CONTEXT)
raw={s:load(s) for s in symbols}
cutoff=min(df.iloc[-1].timestamp for df in raw.values())
sets=[set(df.loc[df.timestamp<=cutoff,"timestamp"]) for df in raw.values()]
calendar=pd.DatetimeIndex(sorted(set.intersection(*sets)))
if len(calendar)<1500: raise RuntimeError(f"insufficient common calendar {len(calendar)}")
prices={s:raw[s].set_index("timestamp").price.reindex(calendar) for s in raw}
if any(v.isna().any() for v in prices.values()): raise RuntimeError("missing common-calendar price")
data=engineer(prices,calendar); fs=folds(len(calendar)); train_states=frame(TRAIN,data,fs); test_states=frame(tuple(EXTERNAL),data,fs)
per=[]
for symbol,group in EXTERNAL.items():
    fold_rows=[]; all_model=[]; all_out=[]; all_frozen=[]; all_uncond=[]
    for fold in range(EVAL_FIRST_FOLD,FOLDS+1):
        start,_=fs[fold-1]; tr=train_states[train_states.signal_i < start-PURGE]; te=test_states[(test_states.symbol==symbol)&(test_states.fold==fold)]
        if len(tr)<1000 or len(te)<200: raise RuntimeError(f"{symbol} fold {fold}: support train={len(tr)} test={len(te)}")
        model=fit(tr); pred=model.predict(te[FEATURES].to_numpy(float)); chosen=te.loc[pred>0].copy()
        prior=data[symbol].iloc[:start-PURGE].mom20.dropna(); threshold=float(prior.quantile(.70)); frozen=te.loc[te.mom20>=threshold].copy(); outside=chosen.loc[chosen.mom20<threshold].copy()
        def gross(x): return x.enter20_after25_bps.to_numpy(float)+BASE_COST
        cg,og,fg,ug=gross(chosen),gross(outside),gross(frozen),gross(te)
        all_model.extend(cg); all_out.extend(og); all_frozen.extend(fg); all_uncond.extend(ug)
        fold_rows.append({"fold":fold,"states":len(te),"model_trades":len(cg),"outside_frozen_trades":len(og),"model_net_mean_25":None if not len(cg) else float((cg-25).mean()),"outside_frozen_net_mean_25":None if not len(og) else float((og-25).mean()),"frozen_net_mean_25":None if not len(fg) else float((fg-25).mean()),"unconditional_net_mean_25":float((ug-25).mean())})
    arrays={"model":np.asarray(all_model),"outside":np.asarray(all_out),"frozen":np.asarray(all_frozen),"unconditional":np.asarray(all_uncond)}
    costs={}
    for c in COSTS:
        costs[str(c)]={k:{"trades":int(len(v)),"mean_bps":None if not len(v) else float((v-c).mean()),"median_bps":None if not len(v) else float(np.median(v-c))} for k,v in arrays.items()}
    positive_model_folds=sum((r["model_net_mean_25"] if r["model_net_mean_25"] is not None else -1)>0 for r in fold_rows)
    positive_out_folds=sum((r["outside_frozen_net_mean_25"] if r["outside_frozen_net_mean_25"] is not None else -1)>0 for r in fold_rows)
    transport=bool(len(arrays["outside"])>=20 and costs["25"]["outside"]["mean_bps"]>0 and positive_model_folds>=3 and positive_out_folds>=3)
    per.append({"symbol":symbol,"group":group,"transport_pass":transport,"positive_model_folds":positive_model_folds,"positive_outside_folds":positive_out_folds,"costs":costs,"folds":fold_rows})
passing=sum(x["transport_pass"] for x in per)
panel_sha=hashlib.sha256(pd.concat(prices,axis=1).to_csv().encode()).hexdigest()
out={"schema":"research.p184_nonsemi_entry_transport_r1","parent":"P184","hypothesis":"The frozen semiconductor-trained Ridge positive-value region is sector-specific rather than a generic continuation detector. Transporting the unchanged model to a predeclared heterogeneous non-semiconductor universe should therefore fail broad outside-frozen economic transport.","contract":{"train_universe":list(TRAIN),"external_universe":EXTERNAL,"model":"Ridge(alpha=10) with StandardScaler, refit causally by fold only on seven semiconductor training symbols","features":FEATURES,"target":"fixed20 net value after 25 bps, +1-session entry delay","selection":"predicted value > 0","matched_comparators":["each external symbol's prior-only top-30% 20-session momentum rule","unconditional external-symbol states"],"cost_stress_bps":list(COSTS),"folds":FOLDS,"primary_test":"25 bps, folds 2-6","broad_transport_gate":">=4/6 external symbols each with >=20 outside-frozen trades, positive outside-frozen mean, >=3/5 positive model folds and >=3/5 positive outside-frozen folds","interpretation":"broad PASS falsifies semiconductor-specificity claim and reclassifies learned region toward generic continuation/state transport; broad FAIL preserves semiconductor-conditional scope but does not weaken prior semiconductor evidence","no_refit_on_external":True,"no_threshold_hyperparameter_universe_or_cost_search":True},"source":{"provider":"Yahoo chart adjusted daily close; research-only","common_cutoff":cutoff.isoformat(),"common_calendar_rows":len(calendar),"panel_sha256":panel_sha},"per_symbol":per,"passing_symbols":passing,"broad_transport":passing>=4,"decision":"P184_SPECIFICITY_FALSIFIED_GENERIC_TRANSPORT" if passing>=4 else "P184_SPECIFICITY_SUPPORTED_NONSEMI_TRANSPORT_FAIL","boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}
OUTPUT.parent.mkdir(exist_ok=True); OUTPUT.write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
