// Run with: npm test  (Node's built-in test runner, no extra packages)
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getCity, getDeviceId, newAlerts, resetDeviceId, setCity } from './device.js';

/** A minimal Web Storage stand-in: one per "browser context". */
function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
  };
}

test('the same browser keeps its device id', () => {
  const normal = fakeStorage();
  assert.equal(getDeviceId('customer', normal), getDeviceId('customer', normal));
});

test('a normal window and an incognito window get different device ids', () => {
  const normal = fakeStorage();
  const incognito = fakeStorage(); // private windows start with empty storage
  assert.notEqual(getDeviceId('customer', normal), getDeviceId('customer', incognito));
});

test('customer and fraudster are different devices in the same browser', () => {
  const s = fakeStorage();
  const customer = getDeviceId('customer', s);
  const attacker = getDeviceId('attacker', s);
  assert.notEqual(customer, attacker);
  assert.match(customer, /^WEB-[0-9A-F]{24}$/);
  assert.match(attacker, /^ATK-[0-9A-F]{24}$/);
});

test('the id matches what the server accepts, even if storage was tampered with', () => {
  const s = fakeStorage();
  s.setItem('fs-device-customer', 'bad id with spaces');
  assert.match(getDeviceId('customer', s), /^[A-Za-z0-9_-]{8,64}$/);
});

test('blocked storage still yields a usable id', () => {
  const blocked = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); }, removeItem() {} };
  assert.match(getDeviceId('customer', blocked), /^WEB-/);
});

test('resetting gives a new device', () => {
  const s = fakeStorage();
  const first = getDeviceId('attacker', s);
  assert.notEqual(resetDeviceId('attacker', s), first);
});

test('only known demo cities are remembered', () => {
  const s = fakeStorage();
  setCity('attacker', 'Atlantis', s);
  assert.equal(getCity('attacker', 'Delhi', s), 'Delhi');
  setCity('attacker', 'Mumbai', s);
  assert.equal(getCity('attacker', 'Delhi', s), 'Mumbai');
});

test('polling the same alerts twice notifies only once', () => {
  const seen = new Set();
  const first = newAlerts([{ id: 2 }, { id: 1 }], seen);
  assert.deepEqual(first.map((a) => a.id), [1, 2]);
  first.forEach((a) => seen.add(a.id));
  assert.deepEqual(newAlerts([{ id: 3 }, { id: 2 }, { id: 1 }], seen).map((a) => a.id), [3]);
  assert.deepEqual(newAlerts([{ id: 2 }, { id: 1 }], seen), []);
});
