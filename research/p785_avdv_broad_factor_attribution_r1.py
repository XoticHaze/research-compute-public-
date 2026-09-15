import csv
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ASSETS = ["AVDV", "VSS"]
WINDOWS = {"2020": "2020-01-01", "2021": "2021-01-01", "2022": "2022-01-01"}
START = "2019-10-01"
END = "2026-08-02"  # fixed common cutoff: French monthly factors currently through 2026-07
COST_BPS = 10
NW_LAG = 3
MIN_MATERIAL_ALPHA_ANN = 0.02
MIN_HAC_T_2020 = 1.5
STYLE_EXPLAINS_RATIO = 0.50
FF5_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_ex_US_5_Factors_CSV.zip"
MOM_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_ex_US_Mom_Factor_CSV.zip"


def _download_zip_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-compute-public/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError(f"no CSV member in {url}")
        return zf.read(names[0]).decode("latin1")


def _parse_monthly_table(text, required=None, single_name=None):
    lines = text.splitlines()
    header_idx = None
    header = None
    for i, line in enumerate(lines):
        row = next(csv.reader([line]))
        cleaned = [x.strip() for x in row]
        if len(cleaned) < 2:
            continue
        cols = cleaned[1:]
        if required and all(x in cols for x in required):
            header_idx, header = i, cleaned
            break
        if single_name and cleaned[0] == "" and any(cols):
            nxt = next((ln for ln in lines[i + 1 :] if re.match(r"^\s*\d{6}\s*,", ln)), None)
            if nxt is not None:
                header_idx, header = i, cleaned
                break
    if header_idx is None:
        raise RuntimeError("factor header not found")
    records = []
    for line in lines[header_idx + 1 :]:
        row = [x.strip() for x in next(csv.reader([line]))]
        if not row or not re.fullmatch(r"\d{6}", row[0]):
            if records:
                break
            continue
        vals = []
        for x in row[1 : len(header)]:
            vals.append(float(x) / 100.0)
        records.append([row[0], *vals])
    if not records:
        raise RuntimeError("no monthly factor rows parsed")
    cols = [x.strip() for x in header[1 :]]
    frame = pd.DataFrame(records, columns=["yyyymm", *cols])
    frame.index = pd.to_datetime(frame.pop("yyyymm"), format="%Y%m") + pd.offsets.MonthEnd(0)
    if single_name:
        first = frame.columns[0]
        frame = frame[[first]].rename(columns={first: single_name})
    return frame.sort_index()


def load_factors():
    ff5 = _parse_monthly_table(
        _download_zip_csv(FF5_URL),
        required=["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"],
    )
    mom = _parse_monthly_table(_download_zip_csv(MOM_URL), single_name="MOM")
    factors = ff5.join(mom, how="inner")
    return factors[["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM", "RF"]]


def load_assets():
    raw = yf.download(
        ASSETS,
        start=START,
        end=END,
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=False,
    )
    close = raw["Close"][ASSETS] if isinstance(raw.columns, pd.MultiIndex) else raw[ASSETS]
    close = close.dropna(how="any").resample("ME").last()
    return close.pct_change().dropna(how="any")


def nw_regression(y, x, lag=NW_LAG):
    data = pd.concat([y.rename("y"), x], axis=1).dropna()
    yy = data.pop("y").to_numpy(float)
    names = list(data.columns)
    xx0 = data.to_numpy(float)
    xx = np.column_stack([np.ones(len(data)), xx0])
    inv = np.linalg.pinv(xx.T @ xx)
    beta = inv @ (xx.T @ yy)
    resid = yy - xx @ beta
    k = xx.shape[1]
    meat = np.zeros((k, k))
    for t in range(len(data)):
        meat += resid[t] ** 2 * np.outer(xx[t], xx[t])
    for l in range(1, min(lag, len(data) - 1) + 1):
        weight = 1 - l / (lag + 1)
        gamma = np.zeros((k, k))
        for t in range(l, len(data)):
            gamma += resid[t] * resid[t - l] * np.outer(xx[t], xx[t - l])
        meat += weight * (gamma + gamma.T)
    cov = inv @ meat @ inv
    alpha_se = float(np.sqrt(max(cov[0, 0], 0.0)))
    alpha_t = float(beta[0] / alpha_se) if alpha_se else None
    return {
        "rows": int(len(data)),
        "alpha_ann": float(beta[0] * 12),
        "alpha_t_hac": alpha_t,
        "nw_lag": lag,
        "betas": {name: float(beta[i + 1]) for i, name in enumerate(names)},
        "residual_vol_ann": float(np.std(resid, ddof=1) * np.sqrt(12)) if len(resid) > 1 else None,
    }


def annualized_return(r):
    q = pd.Series(r).dropna()
    if q.empty:
        return None
    years = len(q) / 12.0
    return float(np.prod(1.0 + q.to_numpy(float)) ** (1.0 / years) - 1.0)


def endpoint_cost(r):
    q = pd.Series(r).dropna().copy()
    if len(q):
        q.iloc[0] -= COST_BPS / 10000.0
        q.iloc[-1] -= COST_BPS / 10000.0
    return q


assets = load_assets()
factors = load_factors()
data = assets.join(factors, how="inner").dropna()
if data.empty:
    raise RuntimeError("AVDV/VSS and factor data have no common monthly observations")

factor_cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]
tests = {}
for label, start in WINDOWS.items():
    d = data.loc[pd.Timestamp(start) :].copy()
    avdv_net = endpoint_cost(d["AVDV"])
    vss_net = endpoint_cost(d["VSS"])
    y_factor = avdv_net - d.loc[avdv_net.index, "RF"]
    multifactor = nw_regression(y_factor, d.loc[avdv_net.index, factor_cols])
    vss_relative = nw_regression(avdv_net, vss_net.to_frame("VSS"))
    tests[label] = {
        "sample_start": str(d.index.min().date()),
        "sample_end": str(d.index.max().date()),
        "sample_months": int(len(d)),
        "avdv_gross_ann_return": annualized_return(d["AVDV"]),
        "avdv_net_ann_return": annualized_return(avdv_net),
        "vss_gross_ann_return": annualized_return(d["VSS"]),
        "vss_net_ann_return": annualized_return(vss_net),
        "vss_relative_hac": vss_relative,
        "developed_ex_us_5_plus_mom_hac": multifactor,
        "alpha_retention_ratio_vs_vss": (
            float(multifactor["alpha_ann"] / vss_relative["alpha_ann"])
            if vss_relative["alpha_ann"] != 0
            else None
        ),
    }

all_material_positive = all(
    tests[w]["developed_ex_us_5_plus_mom_hac"]["alpha_ann"] >= MIN_MATERIAL_ALPHA_ANN
    for w in WINDOWS
)
base_t = tests["2020"]["developed_ex_us_5_plus_mom_hac"]["alpha_t_hac"]
retention_2020 = tests["2020"]["alpha_retention_ratio_vs_vss"]
if all_material_positive and base_t is not None and base_t >= MIN_HAC_T_2020:
    decision = "INDEPENDENT_ALPHA_STRENGTHENED"
elif (
    tests["2020"]["developed_ex_us_5_plus_mom_hac"]["alpha_ann"] <= 0
    or (retention_2020 is not None and retention_2020 <= STYLE_EXPLAINS_RATIO)
):
    decision = "STYLE_EXPOSURE_EXPLAINS_MOST_EXCESS"
else:
    decision = "INCONCLUSIVE_SAMPLE"

out = {
    "schema": "research.p785_avdv_broad_factor_attribution_r1",
    "parent": "P233/P234/P236/P785",
    "claim": "AVDV single-factor matched alpha is tested against a fixed developed-ex-US market/size/value/profitability/investment plus momentum model",
    "contract": {
        "candidate": "AVDV",
        "matched_product_baseline": "VSS",
        "factor_family": "Kenneth French Developed ex US 5 Factors plus Developed ex US Momentum",
        "factor_urls": [FF5_URL, MOM_URL],
        "factors": factor_cols,
        "risk_free": "RF from Developed ex US 5 Factors",
        "windows": WINDOWS,
        "fixed_common_cutoff": "2026-07",
        "newey_west_lag": NW_LAG,
        "cost_bps": COST_BPS,
        "promotion_min_alpha_ann": MIN_MATERIAL_ALPHA_ANN,
        "promotion_min_2020_hac_t": MIN_HAC_T_2020,
        "style_explains_retention_ratio_max": STYLE_EXPLAINS_RATIO,
        "no_factor_shopping": True,
        "no_start_date_search": True,
        "no_wrapper_substitution": True,
    },
    "tests": tests,
    "decision": decision,
    "limitations": [
        "AVDV live history is short",
        "factor data are current-library reconstructed histories rather than vintage archives",
        "wrapper-level attribution does not identify constituent selection mechanism",
    ],
    "boundaries": {
        "portfolio_ranking": False,
        "strategy_spec_mutation": False,
        "runtime_authority": False,
        "broker_submission": False,
        "live_trading": False,
    },
}
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/p785_avdv_broad_factor_attribution_r1.json").write_text(
    json.dumps(out, indent=2, sort_keys=True)
)
print(json.dumps(out, sort_keys=True))
