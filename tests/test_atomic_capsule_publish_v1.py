import base64
import hashlib
import json
import unittest

from scripts.publish_chunked_envelope_atomic_v1 import build_publication


class AtomicCapsulePublicationTests(unittest.TestCase):
    def test_builds_chunks_and_envelope_as_one_publication_set(self):
        ciphertext = b"atomic-capsule-smoke" * 700
        payload_b64 = base64.b64encode(ciphertext).decode("ascii")
        envelope = {
            "schema": "example-envelope-v1",
            "run_id": "123",
            "authority": "research_only",
            "harness": "example",
            "recipient_key_id": "sha256:" + "1" * 64,
            "sender_public_b64": base64.b64encode(b"s" * 32).decode("ascii"),
            "nonce_b64": base64.b64encode(b"n" * 12).decode("ascii"),
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "plaintext_sha256": "2" * 64,
            "chunks": [],
        }
        files = build_publication(
            payload_b64,
            envelope,
            response_root="rendezvous/responses/123",
            stem="capsule",
            envelope_path="rendezvous/responses/123/envelope.json",
            chunk_chars=8000,
        )
        self.assertGreater(len(files), 2)
        paths = [path for path, _ in files]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(paths[-1], "rendezvous/responses/123/envelope.json")
        published_envelope = json.loads(files[-1][1])
        self.assertEqual(len(published_envelope["chunks"]), len(files) - 1)
        for descriptor, (path, raw) in zip(published_envelope["chunks"], files[:-1]):
            self.assertEqual(descriptor["path"], path)
            self.assertEqual(descriptor["chars"], len(raw))
            self.assertEqual(descriptor["sha256"], hashlib.sha256(raw).hexdigest())

    def test_rejects_ciphertext_digest_mismatch(self):
        payload_b64 = base64.b64encode(b"ciphertext").decode("ascii")
        with self.assertRaisesRegex(ValueError, "ciphertext digest"):
            build_publication(
                payload_b64,
                {"ciphertext_sha256": "0" * 64},
                response_root="rendezvous/responses/123",
                stem="capsule",
                envelope_path="rendezvous/responses/123/envelope.json",
            )

    def test_rejects_envelope_outside_response_root(self):
        ciphertext = b"ciphertext"
        payload_b64 = base64.b64encode(ciphertext).decode("ascii")
        with self.assertRaisesRegex(ValueError, "inside response root"):
            build_publication(
                payload_b64,
                {"ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest()},
                response_root="rendezvous/responses/123",
                stem="capsule",
                envelope_path="rendezvous/responses/other/envelope.json",
            )


if __name__ == "__main__":
    unittest.main()
