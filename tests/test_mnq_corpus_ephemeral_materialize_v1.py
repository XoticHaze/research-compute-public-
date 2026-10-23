from __future__ import annotations
import hashlib,io,zipfile,json,subprocess,sys
import pytest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_materialize_ticket_writes_exact_member(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import mnq_corpus_ephemeral_materialize_v1 as mod
    raw=b"timestamp,open,high,low,close,volume\nx,1,1,1,1,1\n"
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as zf: zf.writestr(mod.MEMBER,raw)
    payload=buf.getvalue()
    monkeypatch.setattr(mod.corpus,"_fetch_artifact",lambda ticket:payload)
    monkeypatch.setattr(mod.corpus,"_validate_zip",lambda p:{"ok":True})
    monkeypatch.setattr(mod.corpus,"DATASET_SHA256",hashlib.sha256(raw).hexdigest())
    out=mod.materialize_ticket(b"ticket",tmp_path)
    target=tmp_path/mod.OUTPUT_NAME
    assert target.read_bytes()==raw
    assert out["sha256"]==hashlib.sha256(raw).hexdigest()
    assert out["strategy_spec_write"] is False
    assert out["runtime_activation"] is False
    assert out["broker_submit"] is False
    assert out["live_trading_change"] is False


def test_materialize_payload_accepts_exact_direct_corpus(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import mnq_corpus_ephemeral_materialize_v1 as mod
    raw=b"timestamp,open,high,low,close,volume\\nx,1,1,1,1,1\\n"
    monkeypatch.setattr(mod.corpus,"DATASET_SHA256",hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(mod,"DATASET_BYTES",len(raw))
    out=mod.materialize_payload(raw,tmp_path)
    assert (tmp_path/mod.OUTPUT_NAME).read_bytes()==raw
    assert out["transport_mode"]=="direct_exact_corpus"
    assert out["sha256"]==hashlib.sha256(raw).hexdigest()
    assert out["strategy_spec_write"] is False
    assert out["runtime_activation"] is False
    assert out["broker_submit"] is False
    assert out["live_trading_change"] is False


def test_materialize_payload_rejects_wrong_direct_bytes(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import mnq_corpus_ephemeral_materialize_v1 as mod
    raw=b"not-the-admitted-corpus"
    monkeypatch.setattr(mod.corpus,"DATASET_SHA256","0"*64)
    monkeypatch.setattr(mod,"DATASET_BYTES",len(raw))
    import pytest
    with pytest.raises(RuntimeError,match="MNQ direct corpus identity mismatch"):
        mod.materialize_payload(raw,tmp_path)


def test_materialize_payload_accepts_exact_gzip_corpus(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import gzip
    import mnq_corpus_ephemeral_materialize_v1 as mod
    raw=b"timestamp,open,high,low,close,volume\\nx,1,1,1,1,1\\n"
    monkeypatch.setattr(mod.corpus,"DATASET_SHA256",hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(mod,"DATASET_BYTES",len(raw))
    payload=gzip.compress(raw,mtime=0)
    out=mod.materialize_payload(payload,tmp_path)
    assert (tmp_path/mod.OUTPUT_NAME).read_bytes()==raw
    assert out["transport_mode"]=="direct_exact_corpus_gzip"


def test_materialize_payload_rejects_gzip_identity_mismatch(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import gzip
    import pytest
    import mnq_corpus_ephemeral_materialize_v1 as mod
    raw=b"timestamp,open,high,low,close,volume\\nx,1,1,1,1,1\\n"
    monkeypatch.setattr(mod.corpus,"DATASET_SHA256","0"*64)
    monkeypatch.setattr(mod,"DATASET_BYTES",len(raw))
    with pytest.raises(RuntimeError,match="MNQ gzip corpus identity mismatch"):
        mod.materialize_payload(gzip.compress(raw,mtime=0),tmp_path)


@pytest.mark.parametrize("script,prefix,schema", [
    ("mnq_corpus_ephemeral_consumer_v1.py", "MNQ_CORPUS_EPHEMERAL_RECEIPT=", "mnq-corpus-ephemeral-receipt-v1"),
    ("mnq_corpus_ephemeral_materialize_v1.py", "MNQ_CORPUS_INPUT_ROOT_MATERIALIZED=", "mnq-corpus-input-root-materialization-v1"),
])
@pytest.mark.parametrize("failure", ["unknown_arg", "missing_private_file"])
def test_mnq_public_cli_failure_has_fixed_fields(tmp_path, script, prefix, schema, failure):
    """Nested/private argv or file names must never escape into public stdout/stderr."""
    sentinel = "PRIVATE_SENTINEL_MNQ_ACCOUNT_PATH_DO_NOT_ECHO"
    output_root = tmp_path / "materialized"
    if failure == "unknown_arg":
        argv = ["--not-allowed", sentinel]
    else:
        argv = [
            "--envelope", str(tmp_path / (sentinel + ".json")),
            "--ciphertext", str(tmp_path / "missing.enc"),
            "--private-key", str(tmp_path / "missing.key"),
            "--run-id", "synthetic-run",
            "--response-root", "synthetic-root",
        ]
        if "materialize" in script:
            argv += ["--output-root", str(output_root)]
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *argv],
        cwd=str(ROOT / "scripts"), capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 1
    assert result.stderr == ""
    assert sentinel not in result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith(prefix)
    assert json.loads(lines[0][len(prefix):]) == {"schema": schema, "status": "REJECTED"}
    assert not output_root.exists()


@pytest.mark.parametrize("script,prefix,schema", [
    ("consumer", "MNQ_CORPUS_EPHEMERAL_RECEIPT=", "mnq-corpus-ephemeral-receipt-v1"),
    ("materializer", "MNQ_CORPUS_INPUT_ROOT_MATERIALIZED=", "mnq-corpus-input-root-materialization-v1"),
])
def test_mnq_public_nested_private_exception_is_constant(tmp_path, monkeypatch, capsys,
                                                         script, prefix, schema):
    """Even a nested confidential exception must not appear in public output."""
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import mnq_corpus_ephemeral_consumer_v1 as consumer
    import mnq_corpus_ephemeral_materialize_v1 as materializer
    sentinel = "NESTED_PRIVATE_MEMBER_ACCOUNT_SENTINEL_DO_NOT_ECHO"
    envelope = tmp_path / "envelope.json"
    ciphertext = tmp_path / "ciphertext.bin"
    envelope.write_text("{}", encoding="utf-8")
    ciphertext.write_bytes(b"synthetic")

    def private_failure(*args, **kwargs):
        raise RuntimeError(sentinel)

    argv = [
        "--envelope", str(envelope), "--ciphertext", str(ciphertext),
        "--private-key", str(tmp_path / "unused.key"),
        "--run-id", "synthetic-run", "--response-root", "synthetic-root",
    ]
    if script == "consumer":
        monkeypatch.setattr(consumer, "decrypt_assembled_ciphertext",
                            lambda **kwargs: b"synthetic-ticket")
        monkeypatch.setattr(consumer, "_fetch_artifact", lambda _: b"synthetic-archive")
        monkeypatch.setattr(consumer, "_validate_zip", private_failure)
        target = consumer
    else:
        monkeypatch.setattr(materializer, "decrypt_assembled_ciphertext",
                            lambda **kwargs: b"synthetic-corpus")
        monkeypatch.setattr(materializer, "materialize_payload", private_failure)
        argv += ["--output-root", str(tmp_path / "output")]
        target = materializer
    monkeypatch.setattr(sys, "argv", [script, *argv])
    assert target.main() == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert sentinel not in captured.out + captured.err
    lines = captured.out.splitlines()
    assert len(lines) == 1 and lines[0].startswith(prefix)
    assert json.loads(lines[0][len(prefix):]) == {"schema": schema, "status": "REJECTED"}
