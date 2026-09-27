from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

ROOT = Path(__file__).resolve().parents[1]


def _recipient(run_id: str = "36298260603"):
    private = x25519.X25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return private_raw, {
        "schema": "mnq-corpus-ephemeral-recipient-v1",
        "run_id": run_id,
        "recipient_b64": base64.b64encode(public_raw).decode("ascii"),
        "recipient_key_id": "sha256:" + hashlib.sha256(public_raw).hexdigest(),
    }


def test_producer_roundtrip_matches_existing_consumer(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import ephemeral_x25519_chunked_v1 as transport
    import mnq_corpus_ephemeral_consumer_v1 as corpus
    import mnq_corpus_ephemeral_producer_v1 as producer

    private_raw, recipient = _recipient()
    result = producer.build_response(
        recipient=recipient,
        download_url="https://files.oaiusercontent.com/frozen-mnq.zip",
        artifact_archive_sha256=corpus.ARCHIVE_SHA256,
        chunk_chars=32,
    )
    assert result["run_id"] == recipient["run_id"]
    assert result["response_root"] == f"rendezvous/responses/{recipient['run_id']}"
    assert len(result["chunk_files"]) > 1

    ciphertext_b64 = "".join(text for _, text in result["chunk_files"])
    ciphertext = base64.b64decode(ciphertext_b64.encode("ascii"), validate=True)
    private_path = tmp_path / "recipient-private.b64"
    private_path.write_text(base64.b64encode(private_raw).decode("ascii"), encoding="ascii")

    plaintext = transport.decrypt_assembled_ciphertext(
        envelope=result["envelope"],
        ciphertext=ciphertext,
        private_key_path=private_path,
        expected_schema=corpus.SCHEMA,
        expected_run_id=recipient["run_id"],
        expected_harness=corpus.HARNESS,
        response_root=result["response_root"],
    )
    ticket = json.loads(plaintext)
    assert ticket == {
        "schema": corpus.TICKET_SCHEMA,
        "download_url": "https://files.oaiusercontent.com/frozen-mnq.zip",
        "artifact_archive_sha256": corpus.ARCHIVE_SHA256,
    }


def test_producer_writes_only_ciphertext_and_sanitized_envelope(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import mnq_corpus_ephemeral_consumer_v1 as corpus
    import mnq_corpus_ephemeral_producer_v1 as producer

    _, recipient = _recipient("36298260604")
    result = producer.build_response(
        recipient=recipient,
        download_url="https://files.oaiusercontent.com/frozen-mnq.zip",
        artifact_archive_sha256=corpus.ARCHIVE_SHA256,
    )
    receipt = producer.write_response(result, tmp_path)
    assert receipt["schema"] == "mnq-corpus-ephemeral-producer-receipt-v1"
    assert receipt["strategy_spec_write"] is False
    assert receipt["runtime_activation"] is False
    assert receipt["broker_submit"] is False
    assert receipt["promotion_mutation"] is False
    assert receipt["live_trading"] is False
    assert receipt["files"][-1].endswith("/mnq-corpus-envelope.json")
    for relative in receipt["files"]:
        assert (tmp_path / relative).is_file()


def test_producer_rejects_wrong_archive_identity(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import mnq_corpus_ephemeral_producer_v1 as producer

    _, recipient = _recipient()
    with pytest.raises(RuntimeError, match="mnq_corpus_archive_sha_rejected"):
        producer.build_response(
            recipient=recipient,
            download_url="https://files.oaiusercontent.com/frozen-mnq.zip",
            artifact_archive_sha256="0" * 64,
        )


def test_producer_rejects_unapproved_download_host(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import mnq_corpus_ephemeral_consumer_v1 as corpus
    import mnq_corpus_ephemeral_producer_v1 as producer

    _, recipient = _recipient()
    with pytest.raises(RuntimeError, match="mnq_corpus_download_url_rejected"):
        producer.build_response(
            recipient=recipient,
            download_url="https://example.com/frozen-mnq.zip",
            artifact_archive_sha256=corpus.ARCHIVE_SHA256,
        )


def test_producer_rejects_recipient_key_id_drift(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import mnq_corpus_ephemeral_consumer_v1 as corpus
    import mnq_corpus_ephemeral_producer_v1 as producer

    _, recipient = _recipient()
    recipient["recipient_key_id"] = "sha256:" + "0" * 64
    with pytest.raises(RuntimeError, match="mnq_corpus_recipient_key_id_rejected"):
        producer.build_response(
            recipient=recipient,
            download_url="https://files.oaiusercontent.com/frozen-mnq.zip",
            artifact_archive_sha256=corpus.ARCHIVE_SHA256,
        )
