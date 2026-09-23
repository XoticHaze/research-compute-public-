from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tempfile
from pathlib import Path

SCHEMA = "p01-crw-dca-payload-package-v1"
EXPECTED_CORPUS_SHA256 = "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e"
EXPECTED_CORPUS_BYTES = 18026715
CORPUS_NAME = "mnq-strategy-backtest-12min.csv"
SEED_NAME = "w96_seed_request.json"
SOURCE_NAME = "mm-IBKR"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_seed(path: Path) -> dict:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise SystemExit("W96 seed must be a JSON object")
    params = node.get("params")
    if not isinstance(params, dict):
        raise SystemExit("W96 seed params missing")
    if not bool(params.get("ENABLE_DCA", False)):
        raise SystemExit("W96 seed must already have ENABLE_DCA=true")
    for key in ("DCA_BASE_QTY", "DCA_MAX_CONTRACTS"):
        if params.get(key) is None:
            raise SystemExit(f"W96 seed missing matched-capital control {key}")
    return node


def add_tree(tf: tarfile.TarFile, source: Path, arcname: str) -> None:
    for path in sorted(source.rglob("*"), key=lambda p: p.as_posix()):
        if path.is_symlink():
            raise SystemExit(f"symlink forbidden in admitted MM source: {path}")
        info = tf.gettarinfo(str(path), arcname=f"{arcname}/{path.relative_to(source).as_posix()}")
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        if path.is_file():
            with path.open("rb") as f:
                tf.addfile(info, f)
        else:
            tf.addfile(info)


def add_file(tf: tarfile.TarFile, source: Path, arcname: str) -> None:
    info = tf.gettarinfo(str(source), arcname=arcname)
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    with source.open("rb") as f:
        tf.addfile(info, f)


def main() -> int:
    p = argparse.ArgumentParser(description="Build the admitted plaintext package consumed by P01 CRW DCA rendezvous encryption.")
    p.add_argument("--mm-source-root", required=True)
    p.add_argument("--mm-commit", required=True)
    p.add_argument("--source-archive-sha256", required=True)
    p.add_argument("--seed-request", required=True)
    p.add_argument("--seed-authority", required=True, help="Governed seed lineage/artifact identity")
    p.add_argument("--corpus", required=True)
    p.add_argument("--corpus-authority", required=True, help="Governed Foundry/MM lineage identity")
    p.add_argument("--output", required=True)
    p.add_argument("--manifest-output", required=True)
    args = p.parse_args()

    source = Path(args.mm_source_root).resolve()
    seed = Path(args.seed_request).resolve()
    corpus = Path(args.corpus).resolve()
    output = Path(args.output).resolve()
    manifest_output = Path(args.manifest_output).resolve()

    if not source.is_dir() or not (source / "scripts" / "operator" / "crw_backtest_summary_13z.py").is_file():
        raise SystemExit("admitted MM source root/canonical CRW entrypoint missing")
    if len(args.mm_commit) != 40 or any(c not in "0123456789abcdef" for c in args.mm_commit.lower()):
        raise SystemExit("mm-commit must be exact 40-hex SHA")
    if len(args.source_archive_sha256) != 64:
        raise SystemExit("source archive SHA256 must be exact")

    seed_node = require_seed(seed)
    corpus_sha = sha256_file(corpus)
    corpus_bytes = corpus.stat().st_size
    if corpus_sha != EXPECTED_CORPUS_SHA256 or corpus_bytes != EXPECTED_CORPUS_BYTES:
        raise SystemExit("frozen development corpus identity mismatch")

    seed_sha = sha256_file(seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with tarfile.open(tmp_path, "w") as tf:
            add_tree(tf, source, SOURCE_NAME)
            add_file(tf, seed, SEED_NAME)
            add_file(tf, corpus, CORPUS_NAME)
        tmp_path.replace(output)
    finally:
        tmp_path.unlink(missing_ok=True)

    manifest = {
        "schema": SCHEMA,
        "authority": "research_only",
        "mm_source": {
            "commit": args.mm_commit.lower(),
            "archive_sha256": args.source_archive_sha256.lower(),
            "package_member": SOURCE_NAME,
        },
        "seed": {
            "authority_identity": args.seed_authority,
            "sha256": seed_sha,
            "package_member": SEED_NAME,
            "enable_dca": True,
            "dca_base_qty": seed_node["params"]["DCA_BASE_QTY"],
            "dca_max_contracts": seed_node["params"]["DCA_MAX_CONTRACTS"],
        },
        "corpus": {
            "authority_identity": args.corpus_authority,
            "sha256": corpus_sha,
            "bytes": corpus_bytes,
            "package_member": CORPUS_NAME,
        },
        "payload": {
            "sha256": sha256_file(output),
            "bytes": output.stat().st_size,
        },
        "forbidden_authorities": {
            "strategy_spec_write": False,
            "runtime_activation": False,
            "broker_submit": False,
            "paper_live_mutation": False,
            "allocation_mutation": False,
            "promotion_mutation": False,
            "live_trading_change": False,
        },
        "protected_holdout_read": False,
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
