from __future__ import annotations

"""Route-2 transport shim for the semiconductor SEC Company Facts preflight.

The first public-mirror attempt proved Hugging Face `/search` returns HTTP 500 on
this large flattened dataset. This shim leaves the frozen scientific contract
unchanged and replaces only source-folder discovery with exact `/filter` probes.
"""

import json

import semiconductor_hf_sec_fundamental_cache_20260906 as base


FOLDER_CANDIDATES = {
    "0000006951": (
        "CIK0000006951_APPLIED_MATERIALS_INC_DE",
        "CIK0000006951_APPLIED_MATERIALS_INC",
        "CIK0000006951_Applied_Materials_Inc",
        "CIK0000006951_Applied_Materials_Inc_DE",
    ),
    "0000820313": (
        "CIK0000820313_AMPHENOL_CORP",
        "CIK0000820313_AMPHENOL_CORP_DE",
        "CIK0000820313_Amphenol_Corp",
        "CIK0000820313_Amphenol_Corp_DE",
    ),
    "0000319201": (
        "CIK0000319201_KLA_CORP",
        "CIK0000319201_KLA_TENCOR_CORP",
        "CIK0000319201_KLA_Corp",
        "CIK0000319201_KLA_Tencor_Corp",
    ),
    "0000707549": (
        "CIK0000707549_LAM_RESEARCH_CORP",
        "CIK0000707549_LAM_RESEARCH_CORPORATION",
        "CIK0000707549_Lam_Research_Corp",
        "CIK0000707549_Lam_Research_Corporation",
    ),
    "0000097476": (
        "CIK0000097476_TEXAS_INSTRUMENTS_INC",
        "CIK0000097476_Texas_Instruments_Inc",
    ),
    "0001413447": (
        "CIK0001413447_NXP_SEMICONDUCTORS_NV",
        "CIK0001413447_NXP_SEMICONDUCTORS_N_V",
        "CIK0001413447_NXP_Semiconductors_NV",
        "CIK0001413447_NXP_Semiconductors_N_V",
    ),
    "0000006281": (
        "CIK0000006281_ANALOG_DEVICES_INC",
        "CIK0000006281_Analog_Devices_Inc",
    ),
}


def discover_folder_via_filter(cik: str) -> str:
    attempts = []
    for folder in FOLDER_CANDIDATES[cik]:
        try:
            payload = base.get_json(
                base.API + "/filter",
                {
                    "dataset": base.DATASET,
                    "config": "default",
                    "split": "train",
                    "where": f'"source_folder"=\'{base.q(folder)}\'',
                    "offset": 0,
                    "length": 1,
                },
            )
        except Exception as exc:
            attempts.append({"folder": folder, "transport_error": str(exc)})
            continue
        rows = base.rows_from(payload)
        if rows:
            observed = str(rows[0].get("source_folder") or "")
            if observed != folder:
                raise RuntimeError(
                    f"CIK{cik}: filter returned mismatched source_folder {observed!r} for {folder!r}"
                )
            print(
                "SEMICONDUCTOR_HF_SEC_ROUTE2_FOLDER="
                + json.dumps({"cik": cik, "source_folder": folder}, sort_keys=True)
            )
            return folder
        attempts.append({"folder": folder, "rows": 0})
    raise RuntimeError(
        f"CIK{cik}: no deterministic source_folder candidate resolved via /filter; attempts={attempts}"
    )


base.discover_folder = discover_folder_via_filter


if __name__ == "__main__":
    base.main()
