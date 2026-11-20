"""No Blender installation needed for contract/negative tests."""
import importlib.util
from pathlib import Path
import unittest
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("blender_fixed", ROOT / "scripts/creative/blender_fixed_worker_v1.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

BASE = {
    "schema": "commandcenter.blender_job.v1",
    "job_id": "blender-industrial-arm-r0",
    "recipe_id": "industrial_arm_v1",
    "source": {"repository": "XoticHaze/research-compute-public-", "commit": "a" * 40},
    "upstream_commit": worker.UPSTREAM,
    "revision": 0,
    "parent_job_sha256": None,
    "parameters": {"camera_azimuth_deg": 30, "preview_frame": 45, "preview_samples": 12},
    "classification": "public_demo_no_private_inputs",
}


class PublicFixedBlenderTests(unittest.TestCase):
    def test_job_digest_and_exact_recipe(self):
        self.assertEqual(len(worker.digest(BASE)), 64)
        self.assertEqual(worker.validate(BASE), BASE)

    def test_refuses_arbitrary_code_network_private_broker_or_bad_source(self):
        for extra in ("script", "shell", "url", "token", "broker", "credentials", "private_data"):
            sample = deepcopy(BASE)
            sample[extra] = "untrusted"
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                worker.validate(sample)
        sample = deepcopy(BASE)
        sample["classification"] = "private"
        with self.assertRaises(ValueError):
            worker.validate(sample)
        sample = deepcopy(BASE)
        sample["source"]["repository"] = "XoticHaze/CommandCenter"
        with self.assertRaises(ValueError):
            worker.validate(sample)

    def test_parameters_and_revisions_bounded(self):
        for key, value in (("preview_samples", 10000), ("preview_frame", 0),
                           ("camera_azimuth_deg", 180), ("preview_samples", True)):
            sample = deepcopy(BASE)
            sample["parameters"][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                worker.validate(sample)
        sample = deepcopy(BASE)
        sample["revision"] = 1
        with self.assertRaises(ValueError):
            worker.validate(sample)

    def test_same_canonical_job_hash_as_commandcenter_contract(self):
        self.assertEqual(worker.digest(BASE), __import__("hashlib").sha256(worker.canonical(BASE)).hexdigest())


if __name__ == "__main__":
    unittest.main()
