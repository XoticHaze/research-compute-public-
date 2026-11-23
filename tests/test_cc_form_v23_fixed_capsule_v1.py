"""Portable product-adapter tests with invented tiny fixtures, NEVER private files.

No actual Blender is run by this test. No signed placement, CI job or production
result is claimed. The existing public P256/AES-GCM module is imported as-is.
"""
from __future__ import annotations
import io,hashlib,json,struct,tempfile,unittest,zipfile,zlib
from unittest.mock import patch

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import generate_keypair,seal,open_capsule
from scripts.creative import form_v23_fixed_payload_v1 as m
from scripts.creative.form_v23_fixed_result_v1 import FILES,seal_native_outputs,open_native_outputs
from scripts.creative import form_v23_fixed_sealed_worker_v1 as worker
from scripts.creative.form_v23_fixed_sealed_worker_v1 import execute_admitted_form_v23
from pathlib import Path


def sha(x):return hashlib.sha256(x).hexdigest()

def fake_png():
    # 768 x 768, legal empty-looking pixels, ONLY for validation unit fixtures.
    head=b'\x89PNG\r\n\x1a\n'
    def ck(tag,payload):return struct.pack('>I',len(payload))+tag+payload+struct.pack('>I',zlib.crc32(tag+payload)&0xffffffff)
    rgb=b''.join(b'\x00'+b'\x11\x22\x33'*768 for _ in range(768))
    ihdr=struct.pack('>IIBBBBB',768,768,8,2,0,0,0)
    return head+ck(b'IHDR',ihdr)+ck(b'IDAT',zlib.compress(rgb))+ck(b'IEND',b'')


class FixedProductCrypto(unittest.TestCase):
    def setUp(self):
        self.w_priv,self.w_pub,_=generate_keypair()
        self.owner_priv,self.owner_pub,_=generate_keypair()
        self.run_id='cc-form-public-fixture-001'
        self.synthetic={
          dst:(src,("FIXTURE:"+dst).encode()*20) for dst,(src,_) in m.FIXED_MEMBERS.items()
        }
        members={dst:(src,sha(raw)) for dst,(src,raw) in self.synthetic.items()}
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for dst,(src,raw) in sorted(self.synthetic.items()):z.writestr(src,raw)
        self.release=archive.getvalue()
        self.mpatch=patch.object(m,'FIXED_MEMBERS',members)
        self.spatch=patch.object(m,'PINNED_RELEASE_SHA',sha(self.release))
        self.mpatch.start();self.spatch.start()
        self.addCleanup(self.mpatch.stop);self.addCleanup(self.spatch.stop)
        self.payload,self.info=m.construct_fixed_payload_from_release(self.release)
        self.job={"schema":m.SCHEMA,"job_id":"blender-form-v23-public-fixture-001",
          "recipe_id":m.RECIPE,"variant":"original",
          "classification":"private_encrypted_fixed_recipe",
          "private_bundle_sha256":sha(self.payload),
          "source":{"repository":"XoticHaze/research-compute-public-","commit":"a"*40},
          "revision":0,"parent_job_sha256":None}

    def request_cipher(self):
        return m.make_sealed_inputs(self.payload,job=self.job,run_id=self.run_id,
            recipient_public_b64=self.w_pub,seal_fn=seal)

    def result_fixture(self):
        blend=b'BLENDER'+b'SYNTHETIC_ONLY_NOT_AN_EDITABLE_BLEND'*2000
        png=fake_png()
        qa={"schema":"incomeengine.form_v23.paired_native_scene_readback.v1",
          "status":"PASS_NATIVE_SECOND_PROCESS_READBACK","scene_engine":"CYCLES",
          "product_mesh_count":3,"source_512px_molded_normal_map_connected_and_packed":True,
          "glass_transmission_weight":0.58}
        receipt={"schema":"incomeengine.form_v23.paired_fixed_jar_hero_cycles_review.v1",
          "status":"ONE_NATIVE_JAR_REVIEW_EXECUTED__NOT_MERCHANT_READY",
          "native_blender_executed":True,"selected_variant":"original",
          "selected_jar_sha256":"cb9fc92c5161e34b5a45aaf862038acad6544efb722db7636713b5241314f4e4",
          "output":{"blend":{"bytes":len(blend),"sha256":sha(blend)},
                    "hero_png":{"bytes":len(png),"sha256":sha(png),"dimensions":[768,768]}},
          "independent_second_blender_process":qa}
        return {FILES[0]:blend,FILES[1]:png,FILES[2]:json.dumps(qa).encode(),FILES[3]:json.dumps(receipt).encode()}

    def test_deterministic_canonical_input_5_members(self):
        again,meta=m.construct_fixed_payload_from_release(self.release)
        self.assertEqual(self.payload,again)
        self.assertEqual(len(meta['members']),5)

    def test_input_crypto_roundtrip_existing_A1(self):
        self.assertEqual(self.payload,m.open_sealed_inputs(self.request_cipher(),job=self.job,
           run_id=self.run_id,recipient_private_b64=self.w_priv,open_capsule_fn=open_capsule))

    def test_wrong_run_and_key_fail_closed(self):
        with self.assertRaises(Exception):m.open_sealed_inputs(self.request_cipher(),job=self.job,
          run_id='cc-form-other-run-001',recipient_private_b64=self.w_priv,open_capsule_fn=open_capsule)
        private,_,_=generate_keypair()
        with self.assertRaises(Exception):m.open_sealed_inputs(self.request_cipher(),job=self.job,
          run_id=self.run_id,recipient_private_b64=private,open_capsule_fn=open_capsule)

    def test_wrong_job_digest_fails(self):
        another={**self.job,'variant':'candidate'}
        with self.assertRaises(ValueError):m.open_sealed_inputs(self.request_cipher(),job=another,
          run_id=self.run_id,recipient_private_b64=self.w_priv,open_capsule_fn=open_capsule)

    def test_cipher_chunk_tamper_fails(self):
        sealed=self.request_cipher();n=sealed['manifest.json']['parts'][0]
        sealed[n]['ciphertext_sha256']='0'*64
        with self.assertRaises(Exception):m.open_sealed_inputs(sealed,job=self.job,
          run_id=self.run_id,recipient_private_b64=self.w_priv,open_capsule_fn=open_capsule)

    def test_unknown_payload_member_fails(self):
        malicious=io.BytesIO()
        with zipfile.ZipFile(malicious,'w') as z:
            for name in sorted(self.synthetic):z.writestr(name,self.synthetic[name][1])
            z.writestr('unexpected.sh',b'echo wrong')
        with self.assertRaises(ValueError):m.inspect_fixed_payload(malicious.getvalue())

    def test_user_supplied_script_shell_url_fields_rejected(self):
        for extra in ('script','command','shell','input_url','public_workflow','token'):
            with self.subTest(extra=extra),self.assertRaises(ValueError):m.fixed_job({**self.job,extra:'bad'})

    def test_wrong_classification_rejected(self):
        with self.assertRaises(ValueError):m.fixed_job({**self.job,'classification':'public_demo_no_private_inputs'})

    def test_synthetic_result_encrypted_roundtrip(self):
        files=self.result_fixture()
        sealed=seal_native_outputs(files,job=self.job,run_id=self.run_id,
                                    recipient_public_b64=self.owner_pub,seal_fn=seal)
        self.assertEqual(files,open_native_outputs(sealed,job=self.job,run_id=self.run_id,
                             recipient_private_b64=self.owner_priv,open_capsule_fn=open_capsule))

    def test_result_wrong_key_or_tamper_fails(self):
        sealed=seal_native_outputs(self.result_fixture(),job=self.job,run_id=self.run_id,
                                    recipient_public_b64=self.owner_pub,seal_fn=seal)
        bad,_,_=generate_keypair()
        with self.assertRaises(Exception):open_native_outputs(sealed,job=self.job,run_id=self.run_id,
                      recipient_private_b64=bad,open_capsule_fn=open_capsule)
        name=sealed['manifest.json']['parts'][0];sealed[name]['ciphertext_sha256']='0'*64
        with self.assertRaises(Exception):open_native_outputs(sealed,job=self.job,run_id=self.run_id,
                      recipient_private_b64=self.owner_priv,open_capsule_fn=open_capsule)

    def test_no_placement_callback_is_blocking(self):
        with self.assertRaises(PermissionError):execute_admitted_form_v23({}, {},run_id=self.run_id,
          worker_private_b64=self.w_priv,source_root='.',work_root='/tmp/work-not-used',
          ciphertext_root='/tmp/cipher-not-used',blender_binary='/bin/false',placement_validator=None)

    def test_sealed_worker_simulated_end_to_end_and_plaintext_cleanup(self):
        # Exact input staging, signed-placement callback and result ciphertext
        # are exercised; the Blender process is MOCKED, not claimed native.
        req={"schema":"commandcenter.blender_sealed_request.v1","job":self.job,
             "result_recipient_public_b64":self.owner_pub}
        envelope=seal(json.dumps(req).encode(),recipient_public_b64=self.w_pub,
                      run_id=self.run_id,direction='request')
        calls=[]
        def mock_native(stage,work,binary,variant):
            self.assertEqual(variant,'original')
            self.assertTrue((stage/'assets/jar_hero_yup.glb').exists())
            work.mkdir();(work/'jar').mkdir()
            data=self.result_fixture()
            (work/'jar'/FILES[0]).write_bytes(data[FILES[0]])
            (work/'jar'/FILES[1]).write_bytes(data[FILES[1]])
            (work/FILES[2]).write_bytes(data[FILES[2]])
            (work/FILES[3]).write_bytes(data[FILES[3]])
            return json.loads(data[FILES[3]])
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch.object(worker,'_approved_checkout',return_value=root),\
                 patch.object(worker,'_run_exact_pinned_form',side_effect=mock_native),\
                 patch.object(worker,'FIXED_MEMBERS',{dst:(src,sha(raw)) for dst,(src,raw) in self.synthetic.items()}):
                result=execute_admitted_form_v23(envelope,self.request_cipher(),run_id=self.run_id,
                    worker_private_b64=self.w_priv,source_root=root/'source',
                    work_root=root/'work',ciphertext_root=root/'ciphertext',blender_binary=root/'blender',
                    placement_validator=lambda **kw:calls.append(kw))
            self.assertEqual(result['status'],'CIPHERTEXT_READY')
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['job_digest'],m.fixed_job_digest(self.job))
            self.assertFalse((root/'work'/self.job['job_id']).exists())
            self.assertFalse((root/'work'/(self.job['job_id']+'.private_input')).exists())
            self.assertTrue((root/'ciphertext'/self.job['job_id']/'manifest.json').is_file())
            sealed={x.name:json.loads(x.read_text()) for x in (root/'ciphertext'/self.job['job_id']).iterdir()}
            self.assertEqual(self.result_fixture(),open_native_outputs(sealed,job=self.job,
                 run_id=self.run_id,recipient_private_b64=self.owner_priv,
                 open_capsule_fn=open_capsule))

    def test_protected_placement_denial_stops_before_private_payload_stage(self):
        req={"schema":"commandcenter.blender_sealed_request.v1","job":self.job,
             "result_recipient_public_b64":self.owner_pub}
        envelope=seal(json.dumps(req).encode(),recipient_public_b64=self.w_pub,
                      run_id=self.run_id,direction='request')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with self.assertRaises(PermissionError):execute_admitted_form_v23(
                envelope,self.request_cipher(),run_id=self.run_id,
                worker_private_b64=self.w_priv,source_root=root,work_root=root/'work',
                ciphertext_root=root/'ciphertext',blender_binary=root/'blender',
                placement_validator=lambda **kw:(_ for _ in ()).throw(PermissionError('issuer_missing')))
            self.assertFalse((root/'work').exists())

    def test_wrong_run_is_rejected_before_placement_callback(self):
        req={"schema":"commandcenter.blender_sealed_request.v1","job":self.job,
             "result_recipient_public_b64":self.owner_pub}
        envelope=seal(json.dumps(req).encode(),recipient_public_b64=self.w_pub,
                      run_id=self.run_id,direction='request')
        called=[]
        with self.assertRaises(Exception):execute_admitted_form_v23(envelope, {},run_id='wrong-run-id-001',
          worker_private_b64=self.w_priv,source_root='.',work_root='/tmp/work-not-used',
          ciphertext_root='/tmp/cipher-not-used',blender_binary='/bin/false',
          placement_validator=lambda **kw:called.append(kw))
        self.assertEqual(called,[])

if __name__=='__main__':unittest.main()