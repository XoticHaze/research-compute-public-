from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

DEV = ["PLD","AMT","EQIX","WELL","SPG","O","PSA","CCI"]
PRIMARY = "VNQ"
BROAD = ["SPY","QQQ"]
RATES = ["TLT","IEF"]
ALL = DEV + [PRIMARY] + BROAD + RATES
START = "2013-01-01"
END = "2026-09-05"
H = 40
COST_BPS = 50.0
RIDGE_ALPHA = 10.0
FOLDS = 6
MIN_SYMBOL_STATES = 20
MIN_POS_FOLDS = 3
MIN_SYMBOL_PASSES = 5
OUT = Path("reit-rate-context-stage1-receipt.json")

GENERIC_FEATURES = [
    "mom20","mom60","mom120","rel_vnq20","rel_vnq60","rel_vnq120",
    "vol20","vol60","distance_high60","vnq_mom20","vnq_mom60"
]
RATE_FEATURES = GENERIC_FEATURES + ["tlt_mom20","tlt_mom60","ief_mom20","ief_mom60"]

def bps(a: float, b: float) -> float:
    return (b / a - 1.0) * 10000.0

def download_close() -> pd.DataFrame:
    raw = yf.download(ALL, start=START, end=END, auto_adjust=True, progress=False,
                      group_by="column", threads=False)
    if raw.empty:
        raise RuntimeError("yfinance returned empty panel")
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            close = raw["Close"].copy()
        elif "Close" in raw.columns.get_level_values(1):
            close = raw.xs("Close", axis=1, level=1).copy()
        else:
            raise RuntimeError("Close field absent")
    else:
        raise RuntimeError("expected multi-symbol MultiIndex")
    close = close.reindex(columns=ALL).sort_index()
    close.index = pd.to_datetime(close.index, utc=True)
    missing = [c for c in ALL if c not in close.columns or close[c].isna().all()]
    if missing:
        raise RuntimeError(f"missing symbols: {missing}")
    common = close.dropna(how="any")
    if len(common) < 1800:
        raise RuntimeError(f"insufficient common rows: {len(common)}")
    return common

def rolling_features(px: pd.DataFrame, sym: str) -> pd.DataFrame:
    s = px[sym]
    r = s.pct_change()
    f = pd.DataFrame(index=px.index)
    for n in (20,60,120):
        f[f"mom{n}"] = s / s.shift(n) - 1.0
        f[f"rel_vnq{n}"] = (s / s.shift(n)) / (px[PRIMARY] / px[PRIMARY].shift(n)) - 1.0
    f["vol20"] = r.rolling(20).std() * np.sqrt(252.0)
    f["vol60"] = r.rolling(60).std() * np.sqrt(252.0)
    f["distance_high60"] = s / s.rolling(60).max() - 1.0
    f["vnq_mom20"] = px[PRIMARY] / px[PRIMARY].shift(20) - 1.0
    f["vnq_mom60"] = px[PRIMARY] / px[PRIMARY].shift(60) - 1.0
    for rate in RATES:
        low = rate.lower()
        f[f"{low}_mom20"] = px[rate] / px[rate].shift(20) - 1.0
        f[f"{low}_mom60"] = px[rate] / px[rate].shift(60) - 1.0
    return f

def build_states(px: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    idx=px.index
    decision_positions=list(range(252, len(idx)-H-1, H))
    feat_by={s:rolling_features(px,s) for s in DEV}
    for pos in decision_positions:
        entry=pos+1; exit_=entry+H
        if exit_ >= len(idx):
            continue
        for sym in DEV:
            vals=feat_by[sym].iloc[pos]
            if vals[RATE_FEATURES].isna().any():
                continue
            stock_gross=bps(px[sym].iloc[entry],px[sym].iloc[exit_])
            vnq_ret=bps(px[PRIMARY].iloc[entry],px[PRIMARY].iloc[exit_])
            spy_ret=bps(px["SPY"].iloc[entry],px["SPY"].iloc[exit_])
            qqq_ret=bps(px["QQQ"].iloc[entry],px["QQQ"].iloc[exit_])
            row={"symbol":sym,"signal_date":idx[pos],"entry_date":idx[entry],"exit_date":idx[exit_],
                 "stock_gross_bps":stock_gross,"stock_net50_bps":stock_gross-COST_BPS,
                 "vnq_bps":vnq_ret,"spy_bps":spy_ret,"qqq_bps":qqq_ret,
                 "target_vnq_excess50_bps":stock_gross-COST_BPS-vnq_ret}
            row.update({k:float(vals[k]) for k in RATE_FEATURES})
            rows.append(row)
    df=pd.DataFrame(rows).sort_values(["signal_date","symbol"]).reset_index(drop=True)
    dates=list(pd.Index(df["signal_date"].drop_duplicates()).sort_values())
    blocks=np.array_split(np.arange(len(dates), dtype=int), FOLDS)
    mapping={dates[int(j)]: i+1 for i, block in enumerate(blocks) for j in block}
    df["fold"]=df["signal_date"].map(mapping)
    if df["fold"].isna().any():
        raise RuntimeError("fold assignment produced unmapped signal dates")
    df["fold"]=df["fold"].astype(int)
    return df

def arm(df: pd.DataFrame, features: list[str], name: str) -> dict:
    selected=[]
    fold_rows=[]
    for fold in range(2,FOLDS+1):
        test=df[df.fold==fold].copy()
        if test.empty: raise RuntimeError(f"empty fold {fold}")
        first_entry=test.entry_date.min()
        train=df[df.exit_date < first_entry].copy()
        if len(train) < 200: raise RuntimeError(f"insufficient train fold {fold}: {len(train)}")
        sc=StandardScaler().fit(train[features])
        m=Ridge(alpha=RIDGE_ALPHA).fit(sc.transform(train[features]),train.target_vnq_excess50_bps)
        test["pred_vnq_excess50_bps"]=m.predict(sc.transform(test[features]))
        sel=test[test.pred_vnq_excess50_bps>0].copy()
        if not sel.empty:
            selected.append(sel)
        fold_rows.append({"fold":fold,"train_states":len(train),"test_states":len(test),"selected_states":len(sel),
                          "mean_net50_bps":None if sel.empty else float(sel.stock_net50_bps.mean()),
                          "mean_vnq_bps":None if sel.empty else float(sel.vnq_bps.mean()),
                          "mean_vnq_excess50_bps":None if sel.empty else float((sel.stock_net50_bps-sel.vnq_bps).mean()),
                          "mean_spy_excess50_bps":None if sel.empty else float((sel.stock_net50_bps-sel.spy_bps).mean()),
                          "mean_qqq_excess50_bps":None if sel.empty else float((sel.stock_net50_bps-sel.qqq_bps).mean())})
    sel=pd.concat(selected,ignore_index=True) if selected else df.iloc[0:0].copy()
    bysym=[]
    for sym in DEV:
        s=sel[sel.symbol==sym]
        per=[]
        for fold in range(2,FOLDS+1):
            sf=s[s.fold==fold]
            if len(sf): per.append(float((sf.stock_net50_bps-sf.vnq_bps).mean()))
        bysym.append({"symbol":sym,"selected_states":len(s),
                      "mean_net50_bps":None if s.empty else float(s.stock_net50_bps.mean()),
                      "mean_vnq_excess50_bps":None if s.empty else float((s.stock_net50_bps-s.vnq_bps).mean()),
                      "positive_vnq_excess_folds":int(sum(x>0 for x in per)),"supported_folds":len(per),
                      "passes_symbol_gate":bool(len(s)>=MIN_SYMBOL_STATES and len(per)>=MIN_POS_FOLDS and sum(x>0 for x in per)>=MIN_POS_FOLDS and float((s.stock_net50_bps-s.vnq_bps).mean())>0)})
    repriced={}
    for cost in (25.0,50.0,100.0):
        net=sel.stock_gross_bps-cost
        repriced[str(int(cost))]={"mean_candidate_net_bps":float(net.mean()),"mean_vnq_bps":float(sel.vnq_bps.mean()),
            "mean_spy_bps":float(sel.spy_bps.mean()),"mean_qqq_bps":float(sel.qqq_bps.mean()),
            "excess_vs_vnq_bps":float((net-sel.vnq_bps).mean()),"excess_vs_spy_bps":float((net-sel.spy_bps).mean()),
            "excess_vs_qqq_bps":float((net-sel.qqq_bps).mean())}
    pass_count=sum(x["passes_symbol_gate"] for x in bysym)
    primary=repriced["50"]
    broad_pass=bool(pass_count>=MIN_SYMBOL_PASSES and primary["excess_vs_vnq_bps"]>0 and primary["excess_vs_spy_bps"]>0)
    return {"name":name,"features":features,"selected_states":len(sel),"folds":fold_rows,"symbols":bysym,
            "symbol_pass_count":pass_count,"repriced_bps":repriced,"broad_gate_pass":broad_pass}

def main():
    px=download_close()
    states=build_states(px)
    generic=arm(states,GENERIC_FEATURES,"generic_no_rate_context")
    full=arm(states,RATE_FEATURES,"reit_rate_context")
    if full["broad_gate_pass"] and not generic["broad_gate_pass"]:
        cls="REIT_RATE_CONTEXT_INCREMENT_SUPPORTED"
    elif full["broad_gate_pass"] and generic["broad_gate_pass"]:
        cls="REIT_RELATIVE_VALUE_SUPPORTED_RATE_CONTEXT_NOT_NEEDED"
    else:
        cls="REIT_RATE_CONTEXT_RELATIVE_VALUE_REJECTED"
    receipt={"schema":"public-research.reit-rate-context-stage1.v1","generated_at":datetime.now(timezone.utc).isoformat(),
      "classification":cls,"window":{"common_start":str(px.index.min()),"common_end":str(px.index.max()),"rows":len(px)},
      "contract":{"development_symbols":DEV,"primary_benchmark":PRIMARY,"broad_benchmarks":BROAD,"rate_context":RATES,
        "frozen_external_holdouts_unopened":["DLR","VICI","AVB","EQR"],"horizon_sessions":H,"decision_spacing_sessions":H,
        "execution_delay_sessions":1,"primary_cost_bps":COST_BPS,"model":"StandardScaler + Ridge(alpha=10)",
        "admission":"predicted component-minus-VNQ excess after 50bps > 0","no_ticker_identity":True,
        "gate":f">={MIN_SYMBOL_PASSES}/8 symbols with >=20 states, positive mean VNQ excess and >=3 positive folds; aggregate excess vs VNQ and SPY positive"},
      "generic":generic,"rate_context":full,"research_only":True,"promotion_authority":False,"runtime_mutation":False,"live_trading_change":False}
    OUT.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps(receipt,sort_keys=True))

if __name__=="__main__":
    main()
