#!/usr/bin/env python3
"""P10 held-out fair-value challenger matrix using public GPU rental history only.

The experiment intentionally reduces every provider/date/pricing/generation to one
median $/GPU-hour index before fitting, so providers with many regions or instance
rows do not dominate merely by row count. It then compares categorical generation
baselines with bandwidth-based challengers under chronological and leave-provider-out
holdouts. The output is research evidence only, never procurement/trading authority.
"""
from __future__ import annotations

import argparse, csv, datetime as dt, gzip, hashlib, json, math, statistics, tempfile, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

TARGET=("H100","H200","B200")
SCHEMA="research_compute_public.p10_fair_value_challenger.v1"


def fnum(x):
    try: v=float(x)
    except (TypeError,ValueError): return None
    return v if math.isfinite(v) and v>0 else None


def inum(x):
    try: v=int(float(x))
    except (TypeError,ValueError): return None
    return v if v>0 else None


def gpu_name(x):
    u=(x or "").upper().replace("NVIDIA"," ")
    for g in TARGET:
        if g in u: return g
    return None


def gpu_price(r):
    p=fnum(r.get("price_per_gpu_hour"))
    if p is not None: return p
    total=fnum(r.get("price_per_hour")); n=inum(r.get("gpu_count"))
    return total/n if total is not None and n else None


def download(spec,dst):
    h=hashlib.sha256(); size=0
    with urllib.request.urlopen(spec["url"],timeout=180) as src,dst.open("wb") as out:
        while True:
            b=src.read(1024*1024)
            if not b: break
            h.update(b); out.write(b); size+=len(b)
    got=h.hexdigest()
    if got!=spec["sha256"]: raise RuntimeError(f"digest mismatch {got} != {spec['sha256']}")
    return {"url":spec["url"],"sha256":got,"bytes":size}


def median_map(rows,key_fn,val_fn):
    d=defaultdict(list)
    for r in rows:
        v=val_fn(r)
        if v is not None: d[key_fn(r)].append(v)
    return {k:statistics.median(vs) for k,vs in d.items() if vs}


def fit(rows,bw):
    gg=median_map(rows,lambda r:(r["pricing_type"],r["gpu"]),lambda r:r["price"])
    gg_fallback=median_map(rows,lambda r:r["gpu"],lambda r:r["price"])
    gb=median_map(rows,lambda r:r["pricing_type"],lambda r:r["price"]/bw[r["gpu"]])
    gb_all=statistics.median([r["price"]/bw[r["gpu"]] for r in rows]) if rows else None
    pg=median_map(rows,lambda r:(r["provider"],r["pricing_type"],r["gpu"]),lambda r:r["price"])
    pb=median_map(rows,lambda r:(r["provider"],r["pricing_type"]),lambda r:r["price"]/bw[r["gpu"]])

    # Global generation correction around the provider-bandwidth surface. This keeps
    # provider+contract state while testing whether residual generation structure is
    # still needed after bandwidth enters.
    ratios=defaultdict(list)
    for r in rows:
        level=pb.get((r["provider"],r["pricing_type"]))
        if level:
            ratios[(r["pricing_type"],r["gpu"])].append(r["price"]/(level*bw[r["gpu"]]))
    corr={k:statistics.median(v) for k,v in ratios.items()}
    corr_global=median_map(
        [{**r,"ratio":r["price"]/(pb[(r["provider"],r["pricing_type"])]*bw[r["gpu"]])}
         for r in rows if (r["provider"],r["pricing_type"]) in pb],
        lambda r:r["gpu"],lambda r:r["ratio"])
    return {"global_generation":gg,"global_generation_fallback":gg_fallback,
            "global_bandwidth":gb,"global_bandwidth_all":gb_all,
            "provider_generation":pg,"provider_bandwidth":pb,
            "generation_correction":corr,"generation_correction_fallback":corr_global}


def predict(model,r,bw,name):
    pt,g,p=r["pricing_type"],r["gpu"],r["provider"]
    if name=="global_generation":
        return model["global_generation"].get((pt,g),model["global_generation_fallback"].get(g))
    if name=="global_bandwidth":
        level=model["global_bandwidth"].get(pt,model["global_bandwidth_all"])
        return level*bw[g] if level else None
    if name=="provider_generation":
        return model["provider_generation"].get((p,pt,g),predict(model,r,bw,"global_generation"))
    if name in {"provider_bandwidth","provider_bandwidth_generation_correction"}:
        level=model["provider_bandwidth"].get((p,pt),model["global_bandwidth"].get(pt,model["global_bandwidth_all"]))
        if not level: return None
        pred=level*bw[g]
        if name.endswith("generation_correction"):
            c=model["generation_correction"].get((pt,g),model["generation_correction_fallback"].get(g,1.0))
            pred*=c
        return pred
    raise KeyError(name)


def evaluate(train,test,bw,models):
    fitted=fit(train,bw); bymodel={m:[] for m in models}
    for r in test:
        for m in models:
            pred=predict(fitted,r,bw,m)
            if pred is None or pred<=0: continue
            ape=abs(pred-r["price"])/r["price"]
            bymodel[m].append({"provider":r["provider"],"pricing_type":r["pricing_type"],"date":r["date"],"gpu":r["gpu"],"ape":ape})
    out={}
    for m,errs in bymodel.items():
        slices=defaultdict(list)
        for e in errs: slices[(e["provider"],e["pricing_type"])].append(e["ape"])
        slice_medians=[statistics.median(v) for v in slices.values()]
        out[m]={
            "n":len(errs),
            "slice_count":len(slices),
            "median_ape":statistics.median([e["ape"] for e in errs]) if errs else None,
            "mean_ape":statistics.fmean([e["ape"] for e in errs]) if errs else None,
            "macro_slice_median_ape":statistics.median(slice_medians) if slice_medians else None,
            "slice_median_ape":{f"{k[0]}:{k[1]}":statistics.median(v) for k,v in sorted(slices.items())},
        }
    return out,fitted


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("contract",type=Path); ap.add_argument("output",type=Path)
    ns=ap.parse_args(); c=json.loads(ns.contract.read_text()); bw={k:float(v) for k,v in c["memory_bandwidth_tb_s"].items()}
    pts=set(c["pricing_types"]); raw=[]; receipts=[]
    with tempfile.TemporaryDirectory() as td:
        for i,spec in enumerate(c["archives"]):
            path=Path(td)/f"a{i}.csv.gz"; receipts.append(download(spec,path))
            with gzip.open(path,"rt",encoding="utf-8",newline="") as fh:
                for r in csv.DictReader(fh):
                    g=gpu_name(r.get("gpu_name")); pt=(r.get("pricing_type") or "").strip().lower()
                    if g not in TARGET or pt not in pts: continue
                    price=gpu_price(r); provider=(r.get("provider") or r.get("source") or "").strip().lower(); date=(r.get("snapshot_date") or "").strip()
                    if price is not None and provider and date:
                        raw.append({"provider":provider,"date":date,"pricing_type":pt,"gpu":g,"price":price})

    # Equal-weight daily provider index per generation, independent of row multiplicity.
    daily_lists=defaultdict(list)
    for r in raw: daily_lists[(r["provider"],r["date"],r["pricing_type"],r["gpu"])].append(r["price"])
    daily=[{"provider":k[0],"date":k[1],"pricing_type":k[2],"gpu":k[3],"price":statistics.median(v)} for k,v in daily_lists.items()]

    # Evaluation universe requires all three target generations on the same provider/date/contract.
    present=defaultdict(set)
    for r in daily: present[(r["provider"],r["date"],r["pricing_type"])].add(r["gpu"])
    good={k for k,v in present.items() if v==set(TARGET)}
    rows=[r for r in daily if (r["provider"],r["date"],r["pricing_type"]) in good]
    dates=sorted({r["date"] for r in rows})
    if not dates: raise RuntimeError("no matched three-generation provider/date/contract rows")

    maxd=dt.date.fromisoformat(dates[-1]); test_start=maxd-dt.timedelta(days=int(c["chronological_test_days"])-1)
    train=[r for r in rows if dt.date.fromisoformat(r["date"])<test_start]
    test=[r for r in rows if dt.date.fromisoformat(r["date"])>=test_start]
    models=["global_generation","global_bandwidth","provider_generation","provider_bandwidth","provider_bandwidth_generation_correction"]
    chron,_=evaluate(train,test,bw,models)

    # Leave-one-provider-out evaluates transport to entirely unseen provider state.
    provider_dates=defaultdict(set)
    for r in rows: provider_dates[(r["provider"],r["pricing_type"])].add(r["date"])
    eligible_providers=sorted({p for (p,pt),ds in provider_dates.items() if len(ds)>=int(c["minimum_slice_dates"])})
    loo={m:defaultdict(list) for m in models}
    for held in eligible_providers:
        tr=[r for r in rows if r["provider"]!=held]; te=[r for r in rows if r["provider"]==held]
        metrics,_=evaluate(tr,te,bw,models)
        for m in models:
            if metrics[m]["median_ape"] is not None: loo[m][held].append(metrics[m]["median_ape"])
    loo_summary={}
    for m,d in loo.items():
        vals={p:statistics.median(v) for p,v in d.items() if v}
        loo_summary[m]={"provider_count":len(vals),"provider_median_ape":vals,
                        "macro_provider_median_ape":statistics.median(vals.values()) if vals else None}

    # Select the best bandwidth-family challenger on chronological macro-slice error.
    bw_models=["global_bandwidth","provider_bandwidth","provider_bandwidth_generation_correction"]
    valid=[m for m in bw_models if chron[m]["macro_slice_median_ape"] is not None]
    best_bw=min(valid,key=lambda m:chron[m]["macro_slice_median_ape"]) if valid else None
    control="provider_generation"
    mat=float(c["material_improvement_fraction"])
    bw_ch=chron[best_bw]["macro_slice_median_ape"] if best_bw else None
    ctrl=chron[control]["macro_slice_median_ape"]
    global_bw_loo=loo_summary["global_bandwidth"]["macro_provider_median_ape"]
    global_gen_loo=loo_summary["global_generation"]["macro_provider_median_ape"]
    chron_material=(bw_ch is not None and ctrl is not None and bw_ch <= ctrl*(1-mat))
    chron_competitive=(bw_ch is not None and ctrl is not None and bw_ch <= ctrl*(1+mat))
    provider_transport=(global_bw_loo is not None and global_gen_loo is not None and global_bw_loo <= global_gen_loo*(1-mat))
    if chron_material and provider_transport:
        classification="CONDITIONAL_BANDWIDTH_FAIR_VALUE_CHALLENGER_WINS_HELD_OUT"
    elif chron_competitive and provider_transport:
        classification="BANDWIDTH_COMPETITIVE_CHRONOLOGICALLY_AND_TRANSPORTS_ACROSS_PROVIDERS"
    elif provider_transport:
        classification="BANDWIDTH_TRANSPORTS_ACROSS_PROVIDERS_BUT_PROVIDER_GENERATION_CONTROL_WINS_CHRONOLOGICAL"
    else:
        classification="BANDWIDTH_EXPLANATORY_NOT_BEST_HELD_OUT_FAIR_VALUE_PREDICTOR"

    # Latest-date residual ranking from the best bandwidth-family model, fitted only on earlier dates.
    latest=dates[-1]; latest_train=[r for r in rows if r["date"]<latest]; latest_rows=[r for r in rows if r["date"]==latest]
    fitted=fit(latest_train,bw); ranks=[]
    if best_bw:
        for r in latest_rows:
            pred=predict(fitted,r,bw,best_bw)
            if pred and pred>0:
                ranks.append({"provider":r["provider"],"pricing_type":r["pricing_type"],"gpu":r["gpu"],"observed":r["price"],"expected":pred,
                              "residual_fraction":(r["price"]-pred)/pred})
    ranks.sort(key=lambda x:x["residual_fraction"])

    result={
        "schema":SCHEMA,"research_only":True,"promotion_authority":False,"private_data_loaded":False,
        "source":{"dataset":"thatkavish/OpenComputePrices","archive_receipts":receipts},
        "daily_index_policy":c["daily_index_policy"],"raw_target_row_count":len(raw),"daily_index_row_count":len(daily),
        "matched_three_generation_row_count":len(rows),"matched_provider_date_contract_count":len(good),
        "date_range":{"first":dates[0],"last":dates[-1],"chronological_test_start":test_start.isoformat()},
        "chronological_holdout":chron,"leave_one_provider_out":loo_summary,
        "best_bandwidth_family_model":best_bw,"material_improvement_fraction":mat,
        "decision_inputs":{"best_bandwidth_chron_macro_slice_median_ape":bw_ch,"provider_generation_control_chron_macro_slice_median_ape":ctrl,
                           "global_bandwidth_loo_macro_provider_median_ape":global_bw_loo,"global_generation_loo_macro_provider_median_ape":global_gen_loo,
                           "chronological_material_win":chron_material,"chronological_competitive":chron_competitive,"provider_transport_material_win":provider_transport},
        "classification":classification,
        "latest_ranking":{"date":latest,"model":best_bw,"cheapest_residuals":ranks[:15],"most_expensive_residuals":list(reversed(ranks[-15:]))},
        "caveats":[
            "daily provider medians intentionally collapse region, instance bundle and availability details; residuals are research signals, not executable procurement quotes",
            "provider-generation categorical control is a memorization ceiling, not a preferred economic explanation",
            "provider holdout evaluates unseen-provider transport; provider-specific models fall back to their global counterpart by construction"
        ]
    }
    ns.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("P10_FAIR_VALUE_TERMINAL="+json.dumps({"classification":classification,"date_range":result["date_range"],"counts":{"raw":len(raw),"daily":len(daily),"matched":len(rows)},
        "best_bandwidth_family_model":best_bw,"decision_inputs":result["decision_inputs"],"chronological":{m:{"macro":chron[m]["macro_slice_median_ape"],"median":chron[m]["median_ape"],"n":chron[m]["n"]} for m in models},
        "provider_loo":{m:loo_summary[m]["macro_provider_median_ape"] for m in models},"latest_cheapest":ranks[:10]},sort_keys=True))


if __name__=="__main__": main()
