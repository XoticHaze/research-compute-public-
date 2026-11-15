import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { sealPrivateOverEmploy } from '../cloudflare/fleet-authority/src/private_web_source_seal.js';

globalThis.crypto = webcrypto;
const enc = new TextEncoder();
const b64 = bytes => Buffer.from(bytes).toString('base64');
const utf = text => enc.encode(text);
const hex = async bytes => Buffer.from(await crypto.subtle.digest('SHA-256', bytes)).toString('hex');
const sha = 'a'.repeat(40);

async function fixture() {
  const privateFiles = {
    'operator/candidate_action_board.html': utf('<!doctype html><title>Test</title><script src="./candidate_action_board.js"></script>'),
    'operator/candidate_action_board.js': utf("console.log('synthetic')"),
    'operator/private_qualification.html': utf('<!doctype html><title>Test</title><script src="./private_qualification.js"></script>'),
    'operator/private_qualification.js': utf("console.log('synthetic')"),
  };
  const entry = privateFiles['operator/candidate_action_board.html'];
  const hashes = {};
  for (const [p, raw] of Object.entries(privateFiles)) {
    hashes['/assets/overemploy/' + p.slice(9)] = await hex(raw);
  }
  hashes['/assets/overemploy/index.html'] = await hex(entry);
  const request = {
    schema: 'commandcenter.private_web_release_request.v1',
    project: 'overemploy',
    owning_repository: 'XoticHaze/OverEmploy',
    source_pin_sha: sha,
    source_spec: 'operator/web_surface.v1.json',
    expected_asset_sha256: hashes,
  };
  const spec = {
    schema: 'commandcenter.private_web_app_source.v1',
    slug: 'overemploy',
    entrypoint: 'candidate_action_board.html',
    files: ['candidate_action_board.html', 'private_qualification.html',
      'candidate_action_board.js', 'private_qualification.js'],
  };
  privateFiles['contracts/private_web_release_request.v1.json'] = utf(JSON.stringify(request));
  privateFiles['operator/web_surface.v1.json'] = utf(JSON.stringify(spec));
  const rsa = await crypto.subtle.generateKey({
    name: 'RSA-OAEP', modulusLength: 2048,
    publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256',
  }, true, ['encrypt','decrypt']);
  const public_jwk = await crypto.subtle.exportKey('jwk', rsa.publicKey);
  const publicKey = {
    schema: 'mmibkr-source-vault-public-key-v1', ok: true, algorithm: 'RSA-OAEP-256',
    private_key_exported: false, key_id: 'sha256:' + 'f'.repeat(64), public_jwk,
  };
  const env = {
    CC_PRIVATE_WEB_SOURCE_STAGE_ENABLED: '1',
    CC_PRIVATE_WEB_APPROVED_OWNER_SOURCE_SHA: sha,
    MMIBKR_PRIVATE_SOURCE_TOKEN: 'synthetic-credential-only',
  };
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({url, options});
    const parsed = new URL(url);
    const path = parsed.pathname.split('/contents/')[1];
    if (parsed.searchParams.get('ref') !== (path === 'contracts/private_web_release_request.v1.json' ? 'main' : sha))
      return { ok: false, status: 403 };
    const body = privateFiles[path];
    if (!body) return { ok: false, status: 404 };
    return {
      ok: true, json: async () => ({
        type: 'file', encoding: 'base64', content: b64(body), size: body.length,
      }),
    };
  };
  return { env, publicKey, rsa, calls, fetchImpl, privateFiles };
}

test('sealed capsule contains ciphertext only, exact five assets and decodes privately', async () => {
  const a = await fixture();
  const c = await sealPrivateOverEmploy(a.env, a.publicKey, { fetchImpl: a.fetchImpl });
  assert.deepEqual(Object.keys(c).sort(), [
    'aad_b64','capsule_id','cipher','ciphertext_b64','ciphertext_sha256',
    'key_id','nonce_b64','schema','sealed_key_b64',
  ].sort());
  const key = await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, a.rsa.privateKey,
    Buffer.from(c.sealed_key_b64, 'base64'));
  const aes = await crypto.subtle.importKey('raw', key, { name: 'AES-GCM' }, false, ['decrypt']);
  const plaintext = await crypto.subtle.decrypt({
    name: 'AES-GCM', iv: Buffer.from(c.nonce_b64, 'base64'),
    additionalData: Buffer.from(c.aad_b64, 'base64'),
  }, aes, Buffer.from(c.ciphertext_b64, 'base64'));
  const obj = JSON.parse(new TextDecoder().decode(plaintext));
  assert.equal(obj.source_sha, sha);
  assert.equal(Object.keys(obj.files).length, 5);
  for (const [path, file] of Object.entries(obj.files)) {
    const raw = Buffer.from(file.data_b64, 'base64');
    assert.equal(await hex(raw), file.sha256);
    assert.match(path, /^assets\/overemploy\//);
  }
  assert.ok(a.calls.length >= 6);
  assert.equal(a.calls[0].options.redirect, 'manual');
  assert.equal(a.calls[0].options.headers.Authorization, 'Bearer synthetic-credential-only');
  assert.ok(!JSON.stringify(c).includes('synthetic-credential-only'));
  assert.ok(!JSON.stringify(c).includes(sha));
});

test('missing separately approved private source pin fails before any fetch', async () => {
  const a = await fixture();
  a.env.CC_PRIVATE_WEB_SOURCE_STAGE_ENABLED = '0';
  await assert.rejects(sealPrivateOverEmploy(a.env, a.publicKey, {
    fetchImpl: a.fetchImpl,
  }), /owner_approval_missing/);
  assert.equal(a.calls.length, 0);
});

test('mismatched owner pin refuses the private source', async () => {
  const a = await fixture();
  a.env.CC_PRIVATE_WEB_APPROVED_OWNER_SOURCE_SHA = 'b'.repeat(40);
  await assert.rejects(sealPrivateOverEmploy(a.env, a.publicKey, {
    fetchImpl: a.fetchImpl,
  }), /release_authority_not_admitted/);
});

test('tampered owner asset fails before public ciphertext', async () => {
  const a = await fixture();
  a.privateFiles['operator/candidate_action_board.js'] = utf('tampered');
  await assert.rejects(sealPrivateOverEmploy(a.env, a.publicKey, {
    fetchImpl: a.fetchImpl,
  }), /source_digest_mismatch/);
});

test('inline JavaScript is rejected without leaking source', async () => {
  const a = await fixture();
  a.privateFiles['operator/candidate_action_board.html'] = utf('<script>alert("x")</script>');
  const req = JSON.parse(new TextDecoder().decode(a.privateFiles['contracts/private_web_release_request.v1.json']));
  req.expected_asset_sha256['/assets/overemploy/candidate_action_board.html'] =
    await hex(a.privateFiles['operator/candidate_action_board.html']);
  req.expected_asset_sha256['/assets/overemploy/index.html'] =
    req.expected_asset_sha256['/assets/overemploy/candidate_action_board.html'];
  a.privateFiles['contracts/private_web_release_request.v1.json'] = utf(JSON.stringify(req));
  await assert.rejects(sealPrivateOverEmploy(a.env, a.publicKey, {
    fetchImpl: a.fetchImpl,
  }), /inline_script_rejected/);
});

test('private source spec includes exactly four scoped files', async () => {
  const a = await fixture();
  const spec = JSON.parse(new TextDecoder().decode(a.privateFiles['operator/web_surface.v1.json']));
  spec.files.push('more.js');
  a.privateFiles['operator/web_surface.v1.json'] = utf(JSON.stringify(spec));
  await assert.rejects(sealPrivateOverEmploy(a.env, a.publicKey, {
    fetchImpl: a.fetchImpl,
  }), /asset_spec_mismatch/);
});
