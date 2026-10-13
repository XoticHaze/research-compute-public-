"""Public synthetic general-job wire-contract regression, no private source."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("cc_public_synthetic",ROOT/"scripts/cc_general_public_synthetic_v1.py")
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
PACKET=json.loads((ROOT/"proof/fire/cc-general-public-synthetic-v1.json").read_text())

class GeneralWireContractTests(unittest.TestCase):
    def run_packet(self, packet=None, run_id="12345"):
        return worker.validate_and_run(PACKET if packet is None else packet,run_id,
            "XoticHaze/research-compute-public-/.github/workflows/cc-general-public-synthetic-v1.yml@refs/heads/main")

    def test_full_generic_job_three_different_operations(self):
        r=self.run_packet()
        self.assertEqual(r["state"],"PUBLIC_SYNTHETIC_TERMINAL")
        self.assertEqual(r["job_sha256"],PACKET["job_sha256"])
        self.assertEqual(r["results"][0],12)
        self.assertEqual(r["results"][1],[2,5,9])
        self.assertEqual(len(r["results"][2]),64)
        self.assertIs(r["private_authority_granted"],False)
        self.assertIs(r["encrypted_private_input"],False)

    def test_wrong_canonical_job_identity_rejected(self):
        p=deepcopy(PACKET);p["job_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"identity"):
            self.run_packet(p)

    def test_private_encrypted_mode_rejected_for_public_probe(self):
        p=deepcopy(PACKET);p["job"]["compute_requirements"]["trust_mode"]="public_encrypted"
        with self.assertRaisesRegex(ValueError,"synthetic_only"):
            self.run_packet(p)

    def test_private_inputs_not_admitted(self):
        p=deepcopy(PACKET);p["job"]["inputs"]={"source_ref":"secret"}
        with self.assertRaisesRegex(ValueError,"private_dependencies"):
            self.run_packet(p)

    def test_arbitrary_code_operation_not_admitted(self):
        p=deepcopy(PACKET);p["job"]["package"]["tasks"][0]["operation"]="EXEC"
        from hashlib import sha256
        p["job_sha256"]=sha256(worker.canonical_bytes(p["job"])).hexdigest()
        with self.assertRaisesRegex(ValueError,"unapproved"):
            self.run_packet(p)

    def test_wrong_schema_rejected(self):
        p=deepcopy(PACKET);p["schema"]="v2"
        with self.assertRaisesRegex(ValueError,"schema"):
            self.run_packet(p)

    def test_extra_public_field_rejected(self):
        p=deepcopy(PACKET);p["source"]="private"
        with self.assertRaisesRegex(ValueError,"shape"):
            self.run_packet(p)

    def test_wrong_run_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,"run_identity"):
            self.run_packet(run_id="caller-claimed-id")

    def test_oversized_values_rejected(self):
        p=deepcopy(PACKET);p["job"]["package"]["tasks"][0]["values"]=list(range(21))
        from hashlib import sha256
        p["job_sha256"]=sha256(worker.canonical_bytes(p["job"])).hexdigest()
        with self.assertRaisesRegex(ValueError,"values"):
            self.run_packet(p)

if __name__=="__main__":
    unittest.main()
