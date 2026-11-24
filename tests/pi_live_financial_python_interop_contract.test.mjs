/** Public test-only Python-signed fixture. NO real broker money, keys, or account IDs. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { webcrypto } from 'node:crypto';
import {
  verifyPrivateFinancial, storePrivateFinancial, readPrivateFinancial,
} from '../cloudflare/operator-console/src/pi_live_financial_private.js';

globalThis.crypto ||= webcrypto;
const signed = JSON.parse(readFileSync(new URL('./fixtures/pi_live_financial_synthetic_python_v1.json', import.meta.url),'utf8'));
const env = {
  PI_LIVE_FINANCE_HMAC_KEY: 'ab'.repeat(32), // SYNTHETIC PUBLIC TEST KEY
  PI_LIVE_EXPECTED_ACCOUNT_SHA256: signed.source.account_sha256,
};
const now = Date.parse('2026-11-13T20:30:30.000Z');
class Storage {
  constructor(){ this.rows=new Map(); }
  async transaction(fn){ return fn(this); }
  async get(k){ return this.rows.get(k); }
  async put(k,v){ this.rows.set(k,v); }
}

test('Python projector canonical signed envelope authenticates in exact Worker consumer',async()=>{
  const verified = await verifyPrivateFinancial(signed,env,now);
  assert.equal(verified.cycleId,signed.source.cycle_id);
  const storage = new Storage();
  const stored = await storePrivateFinancial(storage,signed,env,now);
  assert.equal(stored.accepted,true);
  const browser = await readPrivateFinancial(storage,env,now);
  assert.equal(browser.status,'VERIFIED_FRESH');
  assert.equal(browser.account.net_liquidation.value,'12000.25');
  assert.equal(browser.account.available_funds.value,'5000.00');
  assert.equal(browser.account.cash.status,'UNVERIFIED');
  assert.equal(browser.positions.status,'UNVERIFIED');
  assert.equal(browser.risk.pending_order_reservations_verified,false);
  assert.equal(browser.broker_mutation_authority,false);
  assert.equal(Object.hasOwn(browser,'mac_hex'),false);
  assert.equal(Object.hasOwn(browser.source,'account_sha256'),false);
});

test('cross-language payload tamper and age boundary fail closed',async()=>{
  const forged=structuredClone(signed);
  forged.snapshot.account.net_liquidation.value='12001.25';
  await assert.rejects(verifyPrivateFinancial(forged,env,now),/mac_invalid/);
  await assert.rejects(verifyPrivateFinancial(signed,env,now+421000),/stale/);
});