import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../src/index.js', import.meta.url), 'utf8');
const page = source.match(/const page=`([\s\S]*?)`;/)?.[1] ?? '';
const client = source.match(/const client=`([\s\S]*?)`;/)?.[1] ?? '';

test('bot recovery is the first primary action, before advanced administration', () => {
  assert.ok(page.length > 0);
  assert.ok(page.indexOf('id="bot-rejoin"') < page.indexOf('class="advanced"'));
  assert.ok(page.indexOf('id="load-rejoin"') < page.indexOf('id="load-proposal"'));
});

test('mobile controls have viewport, safe-area padding and large touch targets', () => {
  assert.match(page, /name="viewport"/);
  assert.match(page, /env\(safe-area-inset-bottom\)/);
  assert.match(page, /min-height:48px/);
  assert.match(page, /@media\(min-width:640px\)/);
});

test('exact request JSON is inspectable but not editable and approval starts disabled', () => {
  assert.match(page, /id="rejoin-details" hidden/);
  assert.match(page, /id="rejoin-request"[^>]*readonly/);
  assert.match(page, /id="rejoin-approved" type="checkbox" disabled/);
  assert.match(page, /id="approve-rejoin" class="primary" disabled/);
});

test('signing re-fetches and compares the exact current proposal before dispatch', () => {
  assert.match(client, /const current=await api\('rejoin-proposal'\)/);
  assert.match(client, /JSON\.stringify\(current\.request\)!==JSON\.stringify\(loadedRejoin\)/);
  assert.match(client, /approve_exact_bot_rejoin/);
  assert.match(client, /loadedRejoin=null;rejoinControls\(false\)/);
});

test('advanced root and one-time owner actions remain collapsed by default', () => {
  assert.match(page, /<details class="advanced">/);
  for (const id of ['initialize','enroll','approve']) {
    assert.ok(page.includes('id="'+id+'"'), 'missing existing owner action '+id);
  }
});

test('receipt check remains a distinct read-only action', () => {
  assert.match(page, /id="rejoin-receipt"/);
  assert.match(client, /api\('rejoin-receipt\?request_id='/);
});
