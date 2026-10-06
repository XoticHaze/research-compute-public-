from __future__ import annotations

"""Exact-byte refiller for the already-admitted MNQ 12Min research replay corpus.

This module owns no scientific or market-data semantics. It reconstructs one
content-addressed research artifact only from the lineage already pinned by
CommandCenter/research-foundry authority, and fails closed unless the final CSV
is byte-for-byte the admitted corpus identity.

The resulting exact corpus is gzip-compressed, encrypted to a one-run X25519
recipient, and published only as ciphertext chunks plus an envelope on the
rendezvous-exchange branch. No plaintext corpus is committed.
"""

import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

import pandas as pd
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PUBLIC_REPO = "XoticHaze/research-compute-public-"
EXCHANGE_BRANCH = "rendezvous-exchange"
SOURCE_REPO = "https://github.com/mbytes21/MNQ_DATA.git"
SOURCE_COMMIT = "fc5508e2c152938d6d9eb70a36b888ae26107176"
SUPPLEMENT_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/"
    "brandenmorris/mnq-1m-q4-2022-q4-2025-ts-ohlcv-sym"
    "?dataset_version_number=1"
)
SUPPLEMENT_ARCHIVE_SHA256 = "633eb4338a3aa60aedb542b12085acca29ff237c7cadff65442a638466f37667"
CORPUS_SHA256 = "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e"
CORPUS_BYTES = 18_026_715
CORPUS_ROWS = 192_553
FIRST_TIMESTAMP = "2019-05-05T22:00:00+00:00"
LAST_TIMESTAMP = "2026-02-19T02:12:00+00:00"
SOURCE_TIMEZONE = "America/New_York"

RECIPIENT_SCHEMA = "mnq-corpus-ephemeral-recipient-v1"
ENVELOPE_SCHEMA = "mnq-corpus-ephemeral-x25519-v1"
AUTHORITY = "research_only"
HARNESS = "mnq_replay_identity_probe_v1"
INFO = b"commandcenter-ephemeral-chunked-v1"
CHUNK_CHARS = 700_000

NATIVE_HEADER = ("datetime", "open", "high", "low", "close", "volume")
OUTPUT_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "observed_minutes",
    "source_contract",
    "source_session",
    "roll_reason",
]
CONTRACT_RE = re.compile(r"^MNQ (?P<month>03|06|09|12)-(?P<year>\d{2})$")
LAST_RE = re.compile(r"^(?P<date>\d{8})\.Last\.csv$")
SYMBOL_RE = re.compile(r"^MNQ(?P<month>[HMUZ])(?P<year>\d{1,2})$")
MONTH_BY_CODE = {"H": 3, "M": 6, "U": 9, "Z": 12}
MISSING_CONTRACTS = {"MNQ 12-22", "MNQ 12-23", "MNQ 12-24", "MNQ 12-25"}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contract_key(name: str) -> tuple[int, int]:
    match = CONTRACT_RE.fullmatch(name)
    if not match:
        raise RuntimeError(f"unsupported_contract:{name}")
    return 2000 + int(match.group("year")), int(match.group("month"))


def contract_from_symbol(symbol: str) -> str | None:
    match = SYMBOL_RE.fullmatch(str(symbol).strip())
    if not match:
        return None
    year_token = match.group("year")
    year = 2020 + int(year_token) if len(year_token) == 1 else 2000 + int(year_token)
    return f"MNQ {MONTH_BY_CODE[match.group('month')]:02d}-{year % 100:02d}"


def run_git(args: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def download(url: str, target: Path, *, timeout: int = 600) -> None:
    req = Request(
        url,
        headers={
            "User-Agent": "mnq-exact-corpus-refiller/1",
            "Accept": "*/*",
        },
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with urlopen(req, timeout=timeout) as response, tmp.open("wb") as out:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            out.write(block)
    os.replace(tmp, target)


def normalize_trade_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if tuple(frame.columns) != NATIVE_HEADER:
        raise RuntimeError(f"native_schema_rejected:{path}")
    ts = pd.to_datetime(frame["datetime"], errors="raise")
    if ts.dt.tz is not None:
        raise RuntimeError(f"native_timestamp_must_be_naive:{path}")
    localized = ts.dt.tz_localize(SOURCE_TIMEZONE, ambiguous="infer", nonexistent="raise")
    frame = frame.copy()
    frame["timestamp"] = localized.dt.tz_convert("UTC") - pd.Timedelta(minutes=1)
    if not frame["timestamp"].is_monotonic_increasing or frame["timestamp"].duplicated().any():
        raise RuntimeError(f"native_timestamp_order_rejected:{path}")
    for column in NATIVE_HEADER[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame[["timestamp", "open", "high", "low", "close", "volume"]]


def materialize_missing_december_contracts(source_root: Path, archive: Path) -> None:
    if sha256_file(archive) != SUPPLEMENT_ARCHIVE_SHA256:
        raise RuntimeError("supplement_archive_identity_mismatch")
    if not zipfile.is_zipfile(archive):
        raise RuntimeError("supplement_archive_not_zip")

    seen: dict[tuple[str, int], tuple[float, float, float, float, float]] = {}
    buckets: dict[tuple[str, str], list[tuple[str, float, float, float, float, float]]] = {}

    with zipfile.ZipFile(archive) as zf:
        candidates = [
            info
            for info in zf.infolist()
            if not info.is_dir() and Path(info.filename).name.lower() == "mnq-ohlcv-1m.csv"
        ]
        if len(candidates) != 1:
            raise RuntimeError("supplement_aggregate_member_rejected")
        with zf.open(candidates[0], "r") as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            expected = (
                "timestamp",
                "rtype",
                "publisher_id",
                "instrument_id",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "symbol",
            )
            if tuple(reader.fieldnames or ()) != expected:
                raise RuntimeError("supplement_schema_rejected")
            for row in reader:
                contract = contract_from_symbol(row["symbol"])
                if contract not in MISSING_CONTRACTS:
                    continue
                start = pd.Timestamp(row["timestamp"])
                if start.tzinfo is None:
                    raise RuntimeError("supplement_timestamp_must_be_aware")
                start = start.tz_convert("UTC")
                payload = (
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]),
                )
                identity = (contract, int(start.value))
                prior = seen.get(identity)
                if prior is not None:
                    if prior != payload:
                        raise RuntimeError("supplement_duplicate_conflict")
                    continue
                seen[identity] = payload

                local_close = (
                    start.tz_convert(SOURCE_TIMEZONE) + pd.Timedelta(minutes=1)
                ).tz_localize(None)
                close_label = local_close.strftime("%Y-%m-%d %H:%M:%S")
                session = (local_close - pd.Timedelta(minutes=1)).strftime("%Y%m%d")
                buckets.setdefault((contract, session), []).append((close_label, *payload))

    present = {contract for contract, _ in buckets}
    if present != MISSING_CONTRACTS:
        raise RuntimeError("supplement_missing_contracts")

    for contract in MISSING_CONTRACTS:
        target = source_root / contract
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

    for (contract, session), rows in sorted(buckets.items()):
        rows.sort(key=lambda row: row[0])
        path = source_root / contract / f"{session}.Last.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(NATIVE_HEADER)
            writer.writerows(rows)


def inventory_sessions(
    source_root: Path,
) -> tuple[dict[tuple[str, str], pd.DataFrame], pd.DataFrame]:
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    inventory: list[dict[str, Any]] = []
    dirs = sorted(
        (p for p in source_root.glob("MNQ ??-??") if p.is_dir()),
        key=lambda p: contract_key(p.name),
    )
    for contract_dir in dirs:
        for path in sorted(contract_dir.glob("*.Last.csv")):
            match = LAST_RE.fullmatch(path.name)
            if not match:
                continue
            session = match.group("date")
            frame = normalize_trade_file(path)
            if frame.empty:
                continue
            frame = frame.copy()
            frame["source_contract"] = contract_dir.name
            frame["source_session"] = session
            frames[(session, contract_dir.name)] = frame
            inventory.append(
                {
                    "session": session,
                    "contract": contract_dir.name,
                    "volume": float(frame["volume"].sum()),
                    "rows": int(len(frame)),
                }
            )
    if not inventory:
        raise RuntimeError("native_inventory_empty")
    table = pd.DataFrame(inventory).sort_values(["session", "contract"]).reset_index(drop=True)
    return frames, table


def build_roll_schedule(inventory: pd.DataFrame, confirmation_sessions: int = 2) -> pd.DataFrame:
    contracts = sorted(inventory["contract"].unique(), key=contract_key)
    sessions = sorted(inventory["session"].unique())
    volume = {(r.session, r.contract): float(r.volume) for r in inventory.itertuples()}
    active = 0
    streak = 0
    pending = False
    schedule: list[dict[str, Any]] = []

    for session in sessions:
        reason = "hold"
        if pending and active + 1 < len(contracts):
            active += 1
            streak = 0
            pending = False
            reason = "volume_crossover_confirmed_prior_session"

        while (
            active + 1 < len(contracts)
            and volume.get((session, contracts[active]), 0.0) <= 0
            and volume.get((session, contracts[active + 1]), 0.0) > 0
        ):
            active += 1
            streak = 0
            reason = "current_contract_unavailable"

        current = contracts[active]
        current_volume = volume.get((session, current), 0.0)
        next_contract = contracts[active + 1] if active + 1 < len(contracts) else None
        next_volume = volume.get((session, next_contract), 0.0) if next_contract else 0.0

        if current_volume <= 0:
            later = [
                c
                for c in contracts[active + 1 :]
                if volume.get((session, c), 0.0) > 0
            ]
            if later:
                active = contracts.index(later[0])
                current = contracts[active]
                current_volume = volume.get((session, current), 0.0)
                next_contract = contracts[active + 1] if active + 1 < len(contracts) else None
                next_volume = volume.get((session, next_contract), 0.0) if next_contract else 0.0
                streak = 0
                reason = "later_contract_availability_fallback"

        if current_volume > 0 and next_volume > current_volume:
            streak += 1
            if streak >= confirmation_sessions:
                pending = True
        elif current_volume > 0:
            streak = 0

        schedule.append(
            {
                "session": session,
                "selected_contract": current,
                "selected_volume": current_volume,
                "next_contract": next_contract,
                "next_volume": next_volume,
                "next_dominance_streak": streak,
                "roll_reason": reason,
            }
        )
    return pd.DataFrame(schedule)


def stitch_exact_session_seams(
    frames: dict[tuple[str, str], pd.DataFrame],
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    selected: list[pd.DataFrame] = []
    for row in schedule.itertuples():
        frame = frames.get((row.session, row.selected_contract))
        if frame is None or frame.empty:
            continue
        copy = frame.copy()
        copy["roll_reason"] = row.roll_reason
        selected.append(copy)
    if not selected:
        raise RuntimeError("roll_schedule_selected_no_rows")

    out = (
        pd.concat(selected, ignore_index=True)
        .sort_values(["timestamp", "source_session"])
        .reset_index(drop=True)
    )
    duplicate_mask = out["timestamp"].duplicated(keep=False)
    if duplicate_mask.any():
        keep = pd.Series(True, index=out.index)
        market_columns = ["open", "high", "low", "close", "volume", "source_contract"]
        for timestamp, group in out.loc[duplicate_mask].groupby("timestamp", sort=False):
            reference = group.iloc[0]
            for _, candidate in group.iloc[1:].iterrows():
                if not all(candidate[column] == reference[column] for column in market_columns):
                    raise RuntimeError(f"conflicting_session_seam:{timestamp}")
            keep.loc[group.index[1:]] = False
        out = out.loc[keep].sort_values("timestamp").reset_index(drop=True)

    if out["timestamp"].duplicated().any() or not out["timestamp"].is_monotonic_increasing:
        raise RuntimeError("stitched_timestamp_order_rejected")
    return out


def build_12min(stitched: pd.DataFrame) -> pd.DataFrame:
    work = stitched.set_index("timestamp")
    bars = work.resample("12min", origin="start_day", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        observed_minutes=("close", "count"),
        source_contract=("source_contract", "first"),
        source_contract_last=("source_contract", "last"),
        source_session=("source_session", "first"),
        roll_reason=("roll_reason", "first"),
    )
    bars = bars[bars["observed_minutes"] > 0].copy()
    mixed = bars["source_contract"] != bars["source_contract_last"]
    if mixed.any():
        bars = bars.loc[~mixed].copy()
    return bars.drop(columns=["source_contract_last"]).reset_index()


def validate_exact_corpus(path: Path) -> None:
    if path.stat().st_size != CORPUS_BYTES:
        raise RuntimeError(f"corpus_bytes_mismatch:{path.stat().st_size}")
    if sha256_file(path) != CORPUS_SHA256:
        raise RuntimeError("corpus_sha256_mismatch")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != OUTPUT_COLUMNS:
            raise RuntimeError("corpus_columns_mismatch")
        count = 0
        first = None
        last = None
        for row in reader:
            if first is None:
                first = row["timestamp"]
            last = row["timestamp"]
            count += 1
    if count != CORPUS_ROWS or first != FIRST_TIMESTAMP or last != LAST_TIMESTAMP:
        raise RuntimeError(
            f"corpus_shape_mismatch:rows={count}:first={first}:last={last}"
        )


def rebuild_exact_corpus(work_root: Path, output: Path) -> None:
    checkout = work_root / "MNQ_DATA"
    run_git(["clone", "--no-checkout", SOURCE_REPO, str(checkout)])
    run_git(["fetch", "--depth", "1", "origin", SOURCE_COMMIT], cwd=checkout)
    run_git(["checkout", "--detach", SOURCE_COMMIT], cwd=checkout)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    if actual != SOURCE_COMMIT:
        raise RuntimeError("native_source_commit_mismatch")

    source_root = checkout / "plaintext_csv"
    supplement = work_root / "mnq-q4-v1.zip"
    download(SUPPLEMENT_URL, supplement)
    materialize_missing_december_contracts(source_root, supplement)

    frames, inventory = inventory_sessions(source_root)
    schedule = build_roll_schedule(inventory, confirmation_sessions=2)
    stitched = stitch_exact_session_seams(frames, schedule)
    bars = build_12min(stitched)
    serializable = bars[OUTPUT_COLUMNS].copy()
    serializable["timestamp"] = serializable["timestamp"].map(
        lambda value: pd.Timestamp(value).isoformat()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    serializable.to_csv(output, index=False, lineterminator="\n")
    validate_exact_corpus(output)


def ensure_exact_corpus(cache_path: Path, work_root: Path) -> Path:
    if cache_path.is_file():
        try:
            validate_exact_corpus(cache_path)
            print("MNQ_EXACT_CORPUS_CACHE_HIT=1")
            return cache_path
        except Exception:
            cache_path.unlink()
    print("MNQ_EXACT_CORPUS_CACHE_HIT=0")
    rebuild_exact_corpus(work_root, cache_path)
    return cache_path


def api_raw(token: str, path: str, *, ref: str) -> bytes:
    encoded = "/".join(quote(part, safe="") for part in path.split("/"))
    url = f"https://api.github.com/repos/{PUBLIC_REPO}/contents/{encoded}?ref={quote(ref, safe='')}"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mnq-exact-corpus-producer-r1",
        },
    )
    with urlopen(req, timeout=30) as response:
        return response.read()


def api_create(token: str, path: str, raw: bytes, *, message: str) -> None:
    encoded = "/".join(quote(part, safe="") for part in path.split("/"))
    url = f"https://api.github.com/repos/{PUBLIC_REPO}/contents/{encoded}"
    body = json.dumps(
        {
            "message": message,
            "branch": EXCHANGE_BRANCH,
            "content": base64.b64encode(raw).decode("ascii"),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mnq-exact-corpus-producer-r1",
        },
    )
    with urlopen(req, timeout=60) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"github_write_status:{response.status}")


def load_recipient(token: str, run_id: str) -> dict[str, Any]:
    path = f"rendezvous/recipients/{run_id}-mnq-corpus.json"
    node = json.loads(api_raw(token, path, ref=EXCHANGE_BRANCH))
    if node.get("schema") != RECIPIENT_SCHEMA or str(node.get("run_id")) != run_id:
        raise RuntimeError("recipient_identity_rejected")
    raw = base64.b64decode(str(node.get("recipient_b64") or ""), validate=True)
    if len(raw) != 32:
        raise RuntimeError("recipient_key_size_rejected")
    key_id = "sha256:" + sha256_bytes(raw)
    if node.get("recipient_key_id") != key_id:
        raise RuntimeError("recipient_key_id_rejected")
    return {"public": raw, "key_id": key_id}


def aad_bytes(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": ENVELOPE_SCHEMA,
            "run_id": run_id,
            "authority": AUTHORITY,
            "harness": HARNESS,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def publish_encrypted_corpus(token: str, run_id: str, corpus_path: Path) -> dict[str, Any]:
    validate_exact_corpus(corpus_path)
    recipient = load_recipient(token, run_id)
    plain = gzip.compress(corpus_path.read_bytes(), compresslevel=9, mtime=0)

    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    aad = aad_bytes(run_id, recipient["key_id"])
    shared = sender.exchange(
        x25519.X25519PublicKey.from_public_bytes(recipient["public"])
    )
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=INFO,
    ).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plain, aad)
    encoded = base64.b64encode(ciphertext).decode("ascii")

    response_root = f"rendezvous/responses/{run_id}"
    chunks: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(encoded), CHUNK_CHARS)):
        text = encoded[start : start + CHUNK_CHARS]
        raw = text.encode("ascii")
        path = f"{response_root}/mnq-corpus-{index:03d}.txt"
        api_create(
            token,
            path,
            raw,
            message=f"rendezvous: publish exact MNQ corpus chunk for run {run_id}",
        )
        chunks.append(
            {
                "path": path,
                "sha256": sha256_bytes(raw),
                "chars": len(raw),
            }
        )
    if not chunks or len(chunks) > 64:
        raise RuntimeError(f"chunk_count_rejected:{len(chunks)}")

    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "run_id": run_id,
        "authority": AUTHORITY,
        "harness": HARNESS,
        "recipient_key_id": recipient["key_id"],
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": sha256_bytes(ciphertext),
        "plaintext_sha256": sha256_bytes(plain),
        "chunks": chunks,
    }
    envelope_raw = (json.dumps(envelope, sort_keys=True) + "\n").encode("utf-8")
    api_create(
        token,
        f"{response_root}/mnq-corpus-envelope.json",
        envelope_raw,
        message=f"rendezvous: complete exact MNQ corpus envelope for run {run_id}",
    )
    return {
        "schema": "mnq-exact-corpus-producer-receipt-v1",
        "run_id": run_id,
        "dataset_sha256": CORPUS_SHA256,
        "dataset_bytes": CORPUS_BYTES,
        "rows": CORPUS_ROWS,
        "transport": "direct_exact_corpus_gzip",
        "gzip_sha256": sha256_bytes(plain),
        "ciphertext_sha256": sha256_bytes(ciphertext),
        "chunk_count": len(chunks),
        "envelope_last": True,
        "research_only": True,
        "promotion_authority": False,
        "strategy_spec_write": False,
        "runtime_activation": False,
        "broker_submit": False,
        "live_trading_change": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cache-path", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.run_id.isdigit():
        raise SystemExit("run_id must be decimal GitHub run id")
    token = str(os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        raise SystemExit("GH_TOKEN missing")

    args.work_root.mkdir(parents=True, exist_ok=True)
    corpus = ensure_exact_corpus(args.cache_path, args.work_root)
    receipt = publish_encrypted_corpus(token, args.run_id, corpus)
    print("MNQ_EXACT_CORPUS_PRODUCER=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
