from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pitindex

PIT_PIN = "2df030e5c9be7c83cf4b28c3d8597d74d274757e"
DATAMULE_PIN = "93168b53b5502d0eb05b4a9dcc022bfe44b3e279"
YEARS = list(range(2018, 2025))
N = 40
OUT = Path("research/artifacts/p388_cik_integrity_r2_20260912.json")
OUT.parent.mkdir(parents=True, exist_ok=True)
UA = "XoticHaze Market Research source-validation contact@example.com"

NAME_FILES = [
    f"https://raw.githubusercontent.com/john-friedman/datamule-data/{DATAMULE_PIN}/data/filer_metadata/listed_filer_names.csv.gz",
    f"https://raw.githubusercontent.com/john-friedman/datamule-data/{DATAMULE_PIN}/data/filer_metadata/unlisted_filer_names.csv.gz",
]

FLOW_ALIASES = {
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "InterestAndDividendIncomeOperating",
    ],
}
INSTANT_ALIASES = {
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "PartnersCapital",
    ],
    "assets": ["Assets"],
}


def norm_name(value: object, strip_suffixes: bool = False) -> str:
    s = "" if value is None else str(value)
    s = s.upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    toks = [x for x in s.split() if x]
    if strip_suffixes:
        suffix = {
            "THE", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
            "LTD", "LIMITED", "PLC", "LLC", "LP", "L", "P", "HOLDING", "HOLDINGS",
            "NEW", "DE", "DEL", "GROUP",
        }
        while toks and toks[-1] in suffix:
            toks.pop()
    return " ".join(toks)


def load_name_authority():
    frames = []
    source_hashes = {}
    for url in NAME_FILES:
        # pandas reads the gzip stream directly; pinning the Git commit makes the bytes immutable.
        df = pd.read_csv(url, compression="gzip", dtype=str)
        cols = {c.lower(): c for c in df.columns}
        if "cik" not in cols or "name" not in cols:
            raise RuntimeError(f"unexpected datamule schema for {url}: {list(df.columns)}")
        sub = df[[cols["cik"], cols["name"]]].rename(columns={cols["cik"]: "cik", cols["name"]: "name"})
        sub["source_url"] = url
        frames.append(sub)
        # Hash the canonical relevant rows rather than relying on transport metadata.
        canon = sub.fillna("").astype(str).sort_values(["cik", "name"]).to_csv(index=False)
        source_hashes[url] = hashlib.sha256(canon.encode()).hexdigest()
    names = pd.concat(frames, ignore_index=True).dropna(subset=["cik", "name"])
    names["cik"] = names["cik"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(10)
    exact = defaultdict(set)
    stripped = defaultdict(set)
    for _, r in names.iterrows():
        cik = r["cik"]
        if not cik.isdigit():
            continue
        e = norm_name(r["name"], False)
        q = norm_name(r["name"], True)
        if e:
            exact[e].add(cik)
        if q:
            stripped[q].add(cik)
    return exact, stripped, source_hashes, len(names)


def resolve_cik(name: str, existing: object, exact, stripped):
    if not pd.isna(existing):
        s = str(existing).strip()
        if s and s not in {"nan", "None", "<NA>"}:
            try:
                return str(int(float(s))).zfill(10), "pitindex", []
            except Exception:
                pass
    e = sorted(exact.get(norm_name(name, False), set()))
    if len(e) == 1:
        return e[0], "datamule_exact_name", e
    if len(e) > 1:
        return None, "ambiguous_exact_name", e
    q = sorted(stripped.get(norm_name(name, True), set()))
    if len(q) == 1:
        return q[0], "datamule_suffix_normalized_name", q
    if len(q) > 1:
        return None, "ambiguous_suffix_name", q
    return None, "unresolved", []


def get_companyfacts(cik: str):
    req = urllib.request.Request(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())


def candidates(data, aliases, kind, asof):
    us = data.get("facts", {}).get("us-gaap", {})
    out = []
    for rank, concept in enumerate(aliases):
        for unit, vals in us.get(concept, {}).get("units", {}).items():
            for v in vals:
                if v.get("form") != "10-K" or not v.get("filed") or not v.get("end") or v.get("val") is None:
                    continue
                if v["filed"] > asof or v["end"] > asof:
                    continue
                dur = None
                if v.get("start"):
                    try:
                        dur = (pd.Timestamp(v["end"]) - pd.Timestamp(v["start"])).days
                    except Exception:
                        dur = None
                if kind == "flow" and not (dur is not None and 300 <= dur <= 430):
                    continue
                if kind == "instant" and v.get("start"):
                    continue
                out.append({
                    "concept": concept,
                    "rank": rank,
                    "unit": unit,
                    "filed": v["filed"],
                    "start": v.get("start"),
                    "end": v["end"],
                    "accn": v.get("accn"),
                    "val": float(v["val"]),
                    "duration_days": dur,
                })
    return out


def select_comparable(rows):
    if not rows:
        return None
    end = max(r["end"] for r in rows)
    q = [r for r in rows if r["end"] == end]
    filed = max(r["filed"] for r in q)
    q = [r for r in q if r["filed"] == filed]
    usd = [r for r in q if r["unit"] == "USD"] or q
    best = sorted(usd, key=lambda r: (r["rank"], r.get("accn") or ""))[0]
    scale = max(abs(best["val"]), 1.0)
    conflict = any(abs(r["val"] - best["val"]) / scale > 0.01 for r in usd)
    return {
        "selected": best,
        "candidate_count": len(usd),
        "material_conflict": conflict,
        "candidate_values": [r["val"] for r in usd[:8]],
    }


exact, stripped, source_hashes, name_rows = load_name_authority()
cache = {}
year_rows = []
all_missing_members = {}
sample_unresolved = []
sec_fetch_errors = []
field_checks = []

for y in YEARS:
    asof = f"{y}-06-30"
    u = pitindex.get_constituents(asof, index="sp500")[["ticker", "name", "cik"]].copy()
    u["ticker"] = u["ticker"].astype(str).str.upper().str.replace(".", "-", regex=False)
    u = u.sort_values(["ticker", "name"], na_position="last").drop_duplicates("ticker").reset_index(drop=True)
    resolved = []
    methods = defaultdict(int)
    missing_before = 0
    for _, r in u.iterrows():
        cik0 = r["cik"]
        missing = pd.isna(cik0) or str(cik0).strip() in {"", "nan", "None", "<NA>"}
        missing_before += int(missing)
        if missing:
            all_missing_members.setdefault((r["ticker"], str(r["name"])), []).append(asof)
        cik, method, candidates_ = resolve_cik(str(r["name"]), cik0, exact, stripped)
        methods[method] += 1
        resolved.append(cik)
    u["resolved_cik"] = resolved
    # IMPORTANT: deterministic sample is taken from the full PIT universe before identifier filtering.
    idx = [round(i * (len(u) - 1) / (N - 1)) for i in range(N)]
    s = u.iloc[idx].drop_duplicates("ticker").copy()
    missing_sample = s["resolved_cik"].isna()
    for _, r in s[missing_sample].iterrows():
        sample_unresolved.append({"year": y, "ticker": r["ticker"], "name": r["name"]})

    # Audit the exact annual fields used by the frozen ROE and asset-turnover children.
    feature_ready = 0
    feature_conflict = 0
    for _, r in s.iterrows():
        cik = r["resolved_cik"]
        rec = {"year": y, "ticker": r["ticker"], "name": r["name"], "cik": cik}
        if cik is None or pd.isna(cik):
            rec["status"] = "identifier_unresolved"
            field_checks.append(rec)
            continue
        try:
            if cik not in cache:
                cache[cik] = get_companyfacts(cik)
                time.sleep(0.05)
            data = cache[cik]
        except Exception as e:
            sec_fetch_errors.append({"year": y, "ticker": r["ticker"], "cik": cik, "error": repr(e)})
            rec["status"] = "companyfacts_fetch_error"
            field_checks.append(rec)
            continue
        ni = select_comparable(candidates(data, FLOW_ALIASES["net_income"], "flow", asof))
        eq = select_comparable(candidates(data, INSTANT_ALIASES["equity"], "instant", asof))
        rev = select_comparable(candidates(data, FLOW_ALIASES["revenue"], "flow", asof))
        assets = select_comparable(candidates(data, INSTANT_ALIASES["assets"], "instant", asof))
        conflicts = [x for x in (ni, eq, rev, assets) if x and x["material_conflict"]]
        roe_ok = bool(ni and eq and not ni["material_conflict"] and not eq["material_conflict"] and eq["selected"]["val"] > 0)
        turn_ok = bool(rev and assets and not rev["material_conflict"] and not assets["material_conflict"] and assets["selected"]["val"] > 0)
        if roe_ok or turn_ok:
            feature_ready += 1
        feature_conflict += int(bool(conflicts))
        rec.update({
            "status": "checked",
            "roe_comparable": roe_ok,
            "turnover_comparable": turn_ok,
            "material_conflict_any": bool(conflicts),
            "net_income": ni,
            "equity": eq,
            "revenue": rev,
            "assets": assets,
        })
        field_checks.append(rec)

    year_rows.append({
        "year": y,
        "asof": asof,
        "universe_n": len(u),
        "missing_cik_before_bridge": missing_before,
        "missing_cik_before_bridge_pct": 100 * missing_before / len(u),
        "resolved_cik_after_bridge": int(u["resolved_cik"].notna().sum()),
        "unresolved_cik_after_bridge": int(u["resolved_cik"].isna().sum()),
        "sample_n": len(s),
        "sample_unresolved_cik": int(missing_sample.sum()),
        "resolution_methods": dict(methods),
        "sample_any_feature_comparable_n": feature_ready,
        "sample_material_conflict_any_n": feature_conflict,
    })

sample_checks = [r for r in field_checks if r.get("status") == "checked"]
roe_comparable = sum(bool(r.get("roe_comparable")) for r in sample_checks)
turn_comparable = sum(bool(r.get("turnover_comparable")) for r in sample_checks)
total_sample_slots = sum(r["sample_n"] for r in year_rows)
unresolved_slots = len(sample_unresolved)
conflict_slots = sum(bool(r.get("material_conflict_any")) for r in sample_checks)
identifier_complete = unresolved_slots == 0
fetch_clean = len(sec_fetch_errors) == 0
# Inherit P309's <=5% material-conflict representation gate, but apply it only to the exact annual fields used downstream.
conflict_fraction = conflict_slots / len(sample_checks) if sample_checks else 1.0
annual_comparability_admitted = identifier_complete and fetch_clean and conflict_fraction <= 0.05

if not identifier_complete:
    decision = "P388_IDENTIFIER_BRIDGE_PARTIAL__FROZEN_SELECTOR_RERUN_BLOCKED"
elif not fetch_clean:
    decision = "P388_IDENTIFIER_COMPLETE__COMPANYFACTS_TRANSPORT_NOT_READY"
elif not annual_comparability_admitted:
    decision = "P388_IDENTIFIER_COMPLETE__ANNUAL_FIELD_COMPARABILITY_NOT_ADMITTED"
else:
    decision = "P388_IDENTIFIER_AND_ANNUAL_COMPARABILITY_READY__RERUN_FROZEN_SELECTORS"

out = {
    "schema": "research.p388_cik_integrity_r2_20260912.v1",
    "parent": "P388_POINT_IN_TIME_FUNDAMENTAL_SELECTION",
    "claim": "Correct the prior CIK-readiness bug, preserve full PIT membership before sampling, deterministically bridge missing historical names through a pinned SEC-submissions-derived name authority, and audit only the annual SEC fields actually used by the frozen ROE and asset-turnover children before any rerun.",
    "sources": {
        "pitindex_commit": PIT_PIN,
        "datamule_commit": DATAMULE_PIN,
        "datamule_name_rows": name_rows,
        "datamule_canonical_hashes": source_hashes,
        "companyfacts": "https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json",
    },
    "contract": {
        "years": YEARS,
        "sample_n": N,
        "sample_order": "full PIT universe ticker/name sorted; 40 evenly spaced positions BEFORE any CIK filtering",
        "identifier_resolution": "existing PIT CIK else unique exact normalized SEC-derived company name else unique suffix-normalized company name; no fuzzy matching",
        "fuzzy_matching_forbidden": True,
        "silent_member_dropping_forbidden": True,
        "annual_flow_duration_days": [300, 430],
        "annual_forms": ["10-K"],
        "material_value_conflict_threshold": 0.01,
        "aggregate_conflict_gate_inherited_from_p309": 0.05,
        "alpha_inference_forbidden": True,
    },
    "yearly": year_rows,
    "historical_missing_cik_members": [
        {"ticker": k[0], "name": k[1], "asofs": v} for k, v in sorted(all_missing_members.items())
    ],
    "sample_unresolved": sample_unresolved,
    "companyfacts_fetch_errors": sec_fetch_errors,
    "field_checks": field_checks,
    "summary": {
        "total_sample_slots": total_sample_slots,
        "sample_unresolved_slots": unresolved_slots,
        "identifier_complete": identifier_complete,
        "companyfacts_fetch_clean": fetch_clean,
        "checked_sample_slots": len(sample_checks),
        "material_conflict_slots": conflict_slots,
        "material_conflict_fraction": conflict_fraction,
        "roe_comparable_slots": roe_comparable,
        "turnover_comparable_slots": turn_comparable,
        "annual_comparability_admitted": annual_comparability_admitted,
    },
    "decision": decision,
    "boundaries": {
        "scientific_authority": True,
        "data_representation_authority": True,
        "alpha_inference": False,
        "portfolio_ranking": False,
        "allocation_authority": False,
        "runtime": False,
        "broker": False,
        "live_trading": False,
    },
}
OUT.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False, default=str))
print(json.dumps({"decision": decision, "summary": out["summary"], "yearly": year_rows, "unresolved_examples": sample_unresolved[:20]}, sort_keys=True))
