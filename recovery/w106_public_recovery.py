from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

# Frozen private scientific identities. This public executable has execution-only authority.
MM_W106_PRODUCER_SHA = "76aa7e9bb64a1aca36865076df1fa4b25f1b06a9"
MM_RECOVERY_CONSUMER_HEAD = "e6c92a6049208c5e4bcd338f3234c1876662eed5"
MNQ_SOURCE_SHA = "fc5508e2c152938d6d9eb70a36b888ae26107176"
STRATEGY_SPEC_DIGEST = "3680e21e3bdbc38a1729cc38fd0c9d42d66242d970cce1617bbdd71c761a1ac6"
SOURCE_TIMEZONE = "America/New_York"
EXPECTED_BARS_SHA256 = "bd4f583e535712e66bd95dcf61b1bc29e211744fd021a73a694ebb68d75edde8"
EXPECTED_ROWS = 88581
FIRST_TIMESTAMP = pd.Timestamp("2021-12-29T17:24:00Z")
LAST_TIMESTAMP = pd.Timestamp("2025-09-12T18:24:00Z")
CONTRACT_RE = re.compile(r"^MNQ (?P<month>03|06|09|12)-(?P<year>\d{2})$")
LAST_RE = re.compile(r"^(?P<date>\d{8})\.Last\.csv$")

WINDOW = 106
ENTRY = -2.7
EXIT = 4.25
LADDER = [2.5, 5.0, 6.0, 8.0]
TRANCHE_FRACTION = 0.2
COMMISSION_POINTS_PER_CONTRACT_SIDE = 0.3
EXPECTED = {
    "closed_trades": 107,
    "mean_dca_adds": 0.5887850467289719,
    "mean_peak_deployed_fraction_closed": 0.3177570093457944,
    "full_budget_deployed_trade_fraction": 0.009345794392523364,
    "net_points_per_max_contract_equivalent": 10208.350000000011,
    "max_drawdown_points_per_max_contract_equivalent": 733.2800000000016,
    "profit_factor": 4.684327348190937,
}

RECOVERY_FEATURES = ["return_5", "return_20", "return_60", "volatility_20", "distance_ma20", "distance_ma60"]
RECOVERY_NEIGHBORS = 20
RECOVERY_HORIZONS = (20, 60)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_trade_minutes(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = ("datetime", "open", "high", "low", "close", "volume")
    if tuple(frame.columns) != required:
        raise ValueError(f"unexpected schema in {path}: {tuple(frame.columns)!r}")
    ts = pd.to_datetime(frame["datetime"], errors="raise")
    if ts.dt.tz is not None:
        raise ValueError("source timestamps must be naive before timezone assertion")
    frame = frame.copy()
    frame["timestamp"] = ts.dt.tz_localize(SOURCE_TIMEZONE, ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")
    if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
        raise ValueError(f"timestamps not unique/increasing: {path}")
    for column in required[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame[["timestamp", "open", "high", "low", "close", "volume"]]


def contract_key(name: str) -> tuple[int, int]:
    m = CONTRACT_RE.fullmatch(name)
    if not m:
        raise ValueError(f"unsupported MNQ contract directory: {name!r}")
    return 2000 + int(m.group("year")), int(m.group("month"))


def rebuild_bars(source_root: Path, output: Path) -> pd.DataFrame:
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    inventory = []
    dirs = sorted((p for p in source_root.glob("MNQ ??-??") if p.is_dir()), key=lambda p: contract_key(p.name))
    for contract_dir in dirs:
        for path in sorted(contract_dir.glob("*.Last.csv")):
            m = LAST_RE.fullmatch(path.name)
            if not m:
                continue
            session = m.group("date")
            frame = load_trade_minutes(path)
            if frame.empty:
                continue
            frame = frame.copy()
            frame["source_contract"] = contract_dir.name
            frame["source_session"] = session
            frames[(session, contract_dir.name)] = frame
            inventory.append({"session": session, "contract": contract_dir.name, "volume": float(frame["volume"].sum())})
    inv = pd.DataFrame(inventory).sort_values(["session", "contract"]).reset_index(drop=True)
    contracts = sorted(inv["contract"].unique(), key=contract_key)
    sessions = sorted(inv["session"].unique())
    volume = {(r.session, r.contract): float(r.volume) for r in inv.itertuples()}
    active = 0
    streak = 0
    pending_switch = False
    schedule = []
    for session in sessions:
        reason = "hold"
        if pending_switch and active + 1 < len(contracts):
            active += 1; streak = 0; pending_switch = False; reason = "volume_crossover_confirmed_prior_session"
        while active + 1 < len(contracts) and volume.get((session, contracts[active]), 0.0) <= 0 and volume.get((session, contracts[active + 1]), 0.0) > 0:
            active += 1; streak = 0; reason = "current_contract_unavailable"
        current = contracts[active]
        cv = volume.get((session, current), 0.0)
        nxt = contracts[active + 1] if active + 1 < len(contracts) else None
        nv = volume.get((session, nxt), 0.0) if nxt else 0.0
        if cv <= 0:
            later = [c for c in contracts[active + 1:] if volume.get((session, c), 0.0) > 0]
            if later:
                active = contracts.index(later[0]); current = contracts[active]; cv = volume.get((session, current), 0.0)
                nxt = contracts[active + 1] if active + 1 < len(contracts) else None
                nv = volume.get((session, nxt), 0.0) if nxt else 0.0; streak = 0; reason = "later_contract_availability_fallback"
        if cv > 0 and nv > cv:
            streak += 1
            if streak >= 2: pending_switch = True
        elif cv > 0:
            streak = 0
        schedule.append({"session": session, "selected_contract": current, "roll_reason": reason})
    selected = []
    for r in pd.DataFrame(schedule).itertuples():
        frame = frames.get((r.session, r.selected_contract))
        if frame is None or frame.empty: continue
        cp = frame.copy(); cp["roll_reason"] = r.roll_reason; selected.append(cp)
    stitched = pd.concat(selected, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    work = stitched.set_index("timestamp")
    bars = work.resample("12min", origin="start_day", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"), observed_minutes=("close", "count"), source_contract=("source_contract", "first"),
        source_contract_last=("source_contract", "last"), source_session=("source_session", "first"), roll_reason=("roll_reason", "first"),
    )
    bars = bars[bars["observed_minutes"] > 0].copy()
    bars = bars.loc[bars["source_contract"] == bars["source_contract_last"]].drop(columns=["source_contract_last"]).reset_index()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True, errors="raise")
    bars = bars[(bars["timestamp"] >= FIRST_TIMESTAMP) & (bars["timestamp"] <= LAST_TIMESTAMP)].copy().reset_index(drop=True)
    bars = bars[["timestamp","open","high","low","close","volume","observed_minutes","source_contract","source_session","roll_reason"]]
    if len(bars) != EXPECTED_ROWS:
        raise SystemExit(f"W106_BAR_ROWS_MISMATCH expected={EXPECTED_ROWS} actual={len(bars)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    bars.to_csv(output, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
    actual = sha256_file(output)
    print(f"W106_BARS_SHA256={actual}")
    if actual != EXPECTED_BARS_SHA256:
        raise SystemExit(f"W106_BAR_SHA_MISMATCH expected={EXPECTED_BARS_SHA256} actual={actual}")
    return bars


def _segment_features(group: pd.DataFrame) -> pd.DataFrame:
    g = group.copy()
    close = g["close"].astype(float)
    mean = close.rolling(WINDOW).mean()
    std1 = close.rolling(WINDOW).std()  # canonical strategy path (ddof=1)
    std0 = close.rolling(WINDOW, min_periods=WINDOW).std(ddof=0)  # crw_pine DCA path
    ema_canonical = close.ewm(span=50, adjust=False).mean()
    ema_pine = close.ewm(span=50, adjust=False, min_periods=50).mean()
    g["_z1"] = (close - mean) / std1.replace(0, np.nan)
    g["_z0"] = (close - mean) / std0.replace(0, np.nan)
    g["_std1"] = std1
    g["_std0"] = std0
    g["_ema_canonical"] = ema_canonical
    g["_ema_pine"] = ema_pine
    g["_contract_i"] = np.arange(len(g))
    return g


def _new_trade(signal: pd.Series, fill: pd.Series) -> dict:
    px = float(fill.open)
    return {"source_contract":str(fill.source_contract),"entry_signal_timestamp":pd.Timestamp(signal.timestamp).isoformat(),"entry_fill_timestamp":pd.Timestamp(fill.timestamp).isoformat(),"entry_signal_score":float(signal._z1),"first_entry_price":px,"avg_entry_price":px,"last_buy_fill_price":px,"qty":1,"dca_count":0,"fills":[{"kind":"entry","timestamp":pd.Timestamp(fill.timestamp).isoformat(),"price":px,"qty":1}],"min_low":float(fill.low),"max_high":float(fill.high),"min_mtm_contract_points":float(fill.low-px),"max_mtm_contract_points":float(fill.high-px),"entry_fill_index":int(fill.name)}


def _update_excursion(t: dict, row: pd.Series) -> None:
    t["min_low"] = min(float(t["min_low"]), float(row.low)); t["max_high"] = max(float(t["max_high"]), float(row.high))
    qty=int(t["qty"]); avg=float(t["avg_entry_price"])
    t["min_mtm_contract_points"] = min(float(t["min_mtm_contract_points"]), qty*(float(row.low)-avg))
    t["max_mtm_contract_points"] = max(float(t["max_mtm_contract_points"]), qty*(float(row.high)-avg))


def _finalize(t: dict, signal: pd.Series, fill: pd.Series) -> dict:
    px=float(fill.open); qty=int(t["qty"]); entry_cost=sum(float(x["price"])*int(x["qty"]) for x in t["fills"]); gross=px*qty-entry_cost
    first=float(t["first_entry_price"]); avg=float(t["avg_entry_price"]); mfe=float(t["max_high"])-first; mae=first-float(t["min_low"]); base=px-first
    return {"source_contract":t["source_contract"],"entry_signal_timestamp":t["entry_signal_timestamp"],"entry_fill_timestamp":t["entry_fill_timestamp"],"exit_signal_timestamp":pd.Timestamp(signal.timestamp).isoformat(),"exit_fill_timestamp":pd.Timestamp(fill.timestamp).isoformat(),"entry_signal_score":t["entry_signal_score"],"exit_signal_score":float(signal._z1),"first_entry_price":first,"final_avg_entry_price":avg,"exit_price":px,"final_qty":qty,"dca_count":int(t["dca_count"]),"dca_used":bool(t["dca_count"]),"dca_entry_price_improvement_points":first-avg,"gross_contract_points":gross,"gross_points_vs_first_entry_one_contract":base,"dca_incremental_contract_points_at_exit":gross-base,"path_mfe_points_from_first_entry":mfe,"path_mae_points_from_first_entry":mae,"max_mtm_contract_points":float(t["max_mtm_contract_points"]),"min_mtm_contract_points":float(t["min_mtm_contract_points"]),"hold_bars":int(fill.name)-int(t["entry_fill_index"]),"hold_hours":(pd.Timestamp(fill.timestamp)-pd.Timestamp(t["entry_fill_timestamp"])).total_seconds()/3600.0,"fills_json":json.dumps(t["fills"],separators=(",",":")),"censored":False}


def replay_w106(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    pieces=[]
    for _,g in bars.groupby(bars["source_contract"].ne(bars["source_contract"].shift()).cumsum(), sort=False): pieces.append(_segment_features(g))
    work=pd.concat(pieces).sort_index()
    trades=[]; current=None; pending=None; prev=None
    for i,row in work.iterrows():
        contract=str(row.source_contract)
        if prev is not None and contract != prev:
            current=None; pending=None
        prev=contract
        if pending is not None:
            action=pending["action"]
            if action=="entry": current=_new_trade(pending["row"],row)
            elif action=="dca":
                old=int(current["qty"]); px=float(row.open); current["avg_entry_price"]=(float(current["avg_entry_price"])*old+px)/(old+1); current["last_buy_fill_price"]=px; current["qty"]=old+1; current["dca_count"]+=1; current["fills"].append({"kind":"dca","timestamp":pd.Timestamp(row.timestamp).isoformat(),"price":px,"qty":1})
            elif action=="exit": trades.append(_finalize(current,pending["row"],row)); current=None
            pending=None
        if current is not None: _update_excursion(current,row)
        z=float(row._z1) if pd.notna(row._z1) else math.nan
        if not math.isfinite(z) or i+1>=len(work) or str(work.iloc[i+1].source_contract)!=contract: continue
        canonical_band_entry = bool(pd.notna(row._std1) and pd.notna(row._ema_canonical) and float(row.close) < float(row._ema_canonical-row._std1))
        canonical_band_exit = bool(pd.notna(row._std1) and pd.notna(row._ema_canonical) and float(row.close) > float(row._ema_canonical+row._std1))
        action=None
        if current is None:
            if z < ENTRY and canonical_band_entry: action="entry"
        else:
            if z > EXIT and canonical_band_exit:
                action="exit"
            elif int(current["dca_count"]) < len(LADDER) and float(row.low) <= float(current["last_buy_fill_price"]):
                ci=int(row._contract_i)
                ready=ci>=200
                hour=pd.Timestamp(row.timestamp).hour
                in_session=9 <= hour < 16
                pine_band_entry=bool(pd.notna(row._std0) and pd.notna(row._ema_pine) and float(row.close) < float(row._ema_pine-row._std0))
                pine_logic_exit=bool(pd.notna(row._z0) and float(row._z0)>EXIT and pd.notna(row._std0) and pd.notna(row._ema_pine) and float(row.close)>float(row._ema_pine+row._std0))
                tier=LADDER[int(current["dca_count"])]
                trigger=float(current["last_buy_fill_price"])*(1.0-tier/100.0)
                if ready and in_session and pine_band_entry and float(row.low)<=trigger and not pine_logic_exit: action="dca"
        if action is not None: pending={"action":action,"row":row.copy()}
    trades_df=pd.DataFrame(trades)
    events=[]
    ts_to_i={pd.Timestamp(v):int(i) for i,v in enumerate(pd.to_datetime(work.timestamp,utc=True))}
    for ti,t in trades_df.reset_index(drop=True).iterrows():
        fills=json.loads(t.fills_json)
        for ordinal,f in enumerate([x for x in fills if x.get("kind")=="dca"],start=1):
            fill_ts=pd.to_datetime(f["timestamp"],utc=True); fi=ts_to_i[fill_ts]; decision=work.iloc[fi-1]
            events.append({"trade_index":int(ti),"add_ordinal":ordinal,"wide_level_pct":float(LADDER[ordinal-1]),"decision_timestamp":pd.Timestamp(decision.timestamp).isoformat(),"fill_timestamp":fill_ts.isoformat(),"source_contract":str(t.source_contract),"add_fill_price":float(f["price"]),"add_fill_qty_contract_equivalent":TRANCHE_FRACTION,"capital_already_deployed_before_add":float(ordinal*TRANCHE_FRACTION),"capital_deployed_after_add":float((ordinal+1)*TRANCHE_FRACTION),"exit_fill_timestamp":str(t.exit_fill_timestamp),"exit_price":float(t.exit_price),"incremental_add_points_per_max_contract_equivalent":float((float(t.exit_price)-float(f["price"]))*TRANCHE_FRACTION)})
    return trades_df,pd.DataFrame(events)


def normalized_metrics(trades: pd.DataFrame, events: pd.DataFrame) -> dict:
    rows=[]
    for _,t in trades.iterrows():
        fills=json.loads(t.fills_json); units=len(fills); gross=float(t.gross_contract_points)*TRANCHE_FRACTION; net=gross-2*COMMISSION_POINTS_PER_CONTRACT_SIDE*units*TRANCHE_FRACTION
        rows.append({"dca_count":int(t.dca_count),"peak":units*TRANCHE_FRACTION,"full":units==5,"net":net})
    n=pd.DataFrame(rows); vals=n.net.to_numpy(float); curve=np.cumsum(vals); aug=np.r_[0.,curve]; dd=float(np.max(np.maximum.accumulate(aug)-aug)); pos=vals[vals>0]; neg=vals[vals<0]
    return {"closed_trades":int(len(n)),"mean_dca_adds":float(n.dca_count.mean()),"mean_peak_deployed_fraction_closed":float(n.peak.mean()),"full_budget_deployed_trade_fraction":float(n.full.mean()),"net_points_per_max_contract_equivalent":float(vals.sum()),"max_drawdown_points_per_max_contract_equivalent":dd,"profit_factor":float(pos.sum()/-neg.sum()),"wide_dca_fill_events":int(len(events))}


def assert_w106_parity(metrics: dict) -> dict:
    checks={}
    for k,e in EXPECTED.items():
        a=metrics[k]; tol=1e-9 if k=="closed_trades" else max(1e-9,abs(float(e))*1e-8); checks[k]={"actual":a,"expected":e,"pass":abs(float(a)-float(e))<=tol}
    ok=all(v["pass"] for v in checks.values())
    print("W106_ACCEPTED_PARITY="+("PASS" if ok else "FAIL")); print(json.dumps(checks,sort_keys=True))
    if not ok: raise SystemExit("public W106 extraction failed accepted-screen parity")
    return checks


def recovery_state(bars: pd.DataFrame):
    c=bars.close.to_numpy(float); lr=np.diff(np.log(c),prepend=np.log(c[0])); idx=np.arange(60,len(bars)-61); cc=np.cumsum(np.r_[0.,c]); cs=np.cumsum(np.r_[0.,lr]); cs2=np.cumsum(np.r_[0.,lr**2]); r5=c[idx]/c[idx-5]-1; r20=c[idx]/c[idx-20]-1; r60=c[idx]/c[idx-60]-1; s=cs[idx+1]-cs[idx-19]; s2=cs2[idx+1]-cs2[idx-19]; vol=np.sqrt(np.maximum((s2-s*s/20)/19,0)); ma20=(cc[idx+1]-cc[idx-19])/20; ma60=(cc[idx+1]-cc[idx-59])/60; x=np.c_[r5,r20,r60,vol,c[idx]/ma20-1,c[idx]/ma60-1]; regime=np.where((c[idx]>=ma60)&(r20>=0),0,np.where((c[idx]<ma60)&(r20<0),1,2)); return idx,x,regime


def recovery_labels(bars: pd.DataFrame, idx: np.ndarray, horizon: int):
    o=bars.open.to_numpy(float); h=bars.high.to_numpy(float); l=bars.low.to_numpy(float); c=bars.close.to_numpy(float); contracts=bars.source_contract.astype(str).to_numpy(); out=[]
    for i in idx:
        fill=i+1; end=fill+horizon
        if end>len(bars) or np.any(contracts[fill:end]!=contracts[fill]): out.append(None); continue
        ref=o[fill]; lows=l[fill:end]; highs=h[fill:end]; worst=int(np.argmin(lows)); mae=float(lows[worst]-ref); mfe=float(highs.max()-ref); later=highs[worst+1:]; hits=np.flatnonzero(later>=ref); recovered=bool(len(hits)); rt=int(hits[0]+1) if recovered else None; out.append((mae,mfe,recovered,rt,float(c[end-1]-ref)))
    return out


def recovery_separator(bars: pd.DataFrame, events: pd.DataFrame) -> dict:
    idx,x,regime=recovery_state(bars); years=bars.loc[idx,"timestamp"].dt.year.to_numpy(int); pos={int(v):i for i,v in enumerate(idx)}; labels={h:recovery_labels(bars,idx,h) for h in RECOVERY_HORIZONS}; lookup={pd.Timestamp(v):i for i,v in enumerate(pd.to_datetime(bars.timestamp,utc=True))}; rows=[]
    for _,e in events.iterrows():
        ts=pd.to_datetime(e.decision_timestamp,utc=True); contract=str(e.source_contract)
        if ts not in lookup or lookup[ts] not in pos: continue
        qi=pos[lookup[ts]]; year=int(ts.year)
        if str(bars.iloc[lookup[ts]].source_contract)!=contract or regime[qi]!=1: continue
        train=np.where((years<year)&(regime==1))[0]; valid=np.array([p for p in train if labels[60][p] is not None])
        if len(valid)<RECOVERY_NEIGHBORS: continue
        scale=x[valid].std(axis=0,ddof=1); scale=np.where(scale>1e-12,scale,1.); d=np.sqrt(np.mean(((x[valid]-x[qi])/scale)**2,axis=1)); near=valid[np.argpartition(d,RECOVERY_NEIGHBORS-1)[:RECOVERY_NEIGHBORS]]; row={"year":year}
        for horizon in RECOVERY_HORIZONS:
            actual=labels[horizon][qi]
            if actual is None: continue
            pool=np.array([p for p in valid if labels[horizon][p] is not None]); nn=np.array([p for p in near if labels[horizon][p] is not None])
            def pred(sel):
                z=[labels[horizon][p] for p in sel]; rec=np.array([v[2] for v in z],float); rt=[v[3] for v in z if v[3] is not None]; return {"mae":float(np.mean([v[0] for v in z])),"recovery_p":float(rec.mean()),"recovery_time":float(np.mean(rt)) if rt else None}
            row[str(horizon)]={"actual":{"mae":actual[0],"recovered":actual[2],"recovery_time":actual[3]},"control":pred(pool),"challenger":pred(nn)}
        if "60" in row: rows.append(row)
    folds=[]
    for year in sorted({r["year"] for r in rows}):
        g=[r for r in rows if r["year"]==year]; f={"year":year,"queries":len(g)}
        for name in ("control","challenger"):
            p=np.array([r["60"][name]["recovery_p"] for r in g]); y=np.array([r["60"]["actual"]["recovered"] for r in g],float); f[name]={"recovery_60_brier":float(np.mean((p-y)**2)),"mae_60_error":float(np.mean([abs(r["60"][name]["mae"]-r["60"]["actual"]["mae"]) for r in g]))}
        folds.append(f)
    wins={}
    for metric in ("recovery_60_brier","mae_60_error"):
        a=np.array([f["control"][metric] for f in folds]); b=np.array([f["challenger"][metric] for f in folds]); wins[metric]={"control_mean":float(a.mean()),"challenger_mean":float(b.mean()),"better_years":int((b<a).sum()),"robust_win":bool(b.mean()<a.mean() and (b<a).sum()>=3)}
    decision="CONTINUE_REGIME1_RECOVERY_SEPARATOR" if wins.get("recovery_60_brier",{}).get("robust_win") and wins.get("mae_60_error",{}).get("robust_win") else "CHANGE_REGIME1_RECOVERY_SEPARATOR" if wins.get("recovery_60_brier",{}).get("robust_win") else "REJECT_REGIME1_RECOVERY_SEPARATOR"
    return {"schema":"public_compute.mnq_w106_regime1_recovery.v1","source_private_producer_sha":MM_W106_PRODUCER_SHA,"source_private_consumer_head":MM_RECOVERY_CONSUMER_HEAD,"strategy_spec_digest":STRATEGY_SPEC_DIGEST,"mnq_source_sha":MNQ_SOURCE_SHA,"events":len(rows),"folds":folds,"aggregate":wins,"decision":decision,"promotion_authority":False,"runtime_authority":False,"broker_authority":False,"live_trading_change":False}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--source-root",type=Path,required=True); ap.add_argument("--workdir",type=Path,default=Path("artifacts/w106")); a=ap.parse_args(); a.workdir.mkdir(parents=True,exist_ok=True)
    bars=rebuild_bars(a.source_root,a.workdir/"mnq-crw-join-bars.csv"); trades,events=replay_w106(bars); trades.to_csv(a.workdir/"mnq-w106-wide-trades.csv",index=False); events.to_csv(a.workdir/"mnq-w106-wide-dca-events.csv",index=False); metrics=normalized_metrics(trades,events); parity=assert_w106_parity(metrics); result=recovery_separator(bars,events); result["w106_metrics"]=metrics; result["w106_parity"]=parity; (a.workdir/"recovery-receipt.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); print("=== W106_RECOVERY_RECEIPT ==="); print(json.dumps(result,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
