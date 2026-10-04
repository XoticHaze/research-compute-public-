from __future__ import annotations
import hashlib,io,zipfile
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
