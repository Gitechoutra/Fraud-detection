/**
 * Browser device identity for the customer app and the fraudster console.
 *
 * Each role gets a random device id kept in localStorage. localStorage
 * belongs to the browser profile, so a normal window keeps its id across
 * visits, while a private / incognito window starts with empty storage and
 * gets a new id — exactly how a bank sees "a new device". Customer and
 * fraudster use different keys, so the split-screen demo is two devices.
 *
 * The id and the chosen demo city are only claims sent to the server
 * (X-Device-Id, X-Demo-City); the server decides what they are worth.
 * Every storage access is guarded: when storage is blocked the id lives in
 * memory for this tab only (which, like incognito, means a new device).
 */

export const CITIES = [
  'Hyderabad', 'Bengaluru', 'Mumbai', 'Delhi', 'Chennai', 'Pune',
  'Kolkata', 'Ahmedabad', 'Jaipur', 'Lucknow', 'Kochi', 'Visakhapatnam',
];

const memory = new Map();

function read(storage, key) {
  try {
    return storage ? storage.getItem(key) : memory.get(key) ?? null;
  } catch {
    return memory.get(key) ?? null;
  }
}

function write(storage, key, value) {
  memory.set(key, value);
  try {
    storage?.setItem(key, value);
  } catch {
    /* storage unavailable: memory only */
  }
}

function defaultStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function randomId(prefix) {
  const bytes = new Uint8Array(12);
  globalThis.crypto.getRandomValues(bytes);
  return `${prefix}-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`.toUpperCase();
}

/** The device id for `role` ('customer' | 'attacker'), created on first use. */
export function getDeviceId(role, storage = defaultStorage()) {
  const key = `fs-device-${role}`;
  let id = read(storage, key);
  if (!id || !/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
    id = randomId(role === 'attacker' ? 'ATK' : 'WEB');
    write(storage, key, id);
  }
  return id;
}

/** Forget this browser's device id (as if it were a brand-new phone). */
export function resetDeviceId(role, storage = defaultStorage()) {
  const key = `fs-device-${role}`;
  memory.delete(key);
  try {
    storage?.removeItem(key);
  } catch {
    /* ignore */
  }
  return getDeviceId(role, storage);
}

export function getCity(role, fallback, storage = defaultStorage()) {
  const city = read(storage, `fs-city-${role}`);
  return CITIES.includes(city) ? city : fallback;
}

export function setCity(role, city, storage = defaultStorage()) {
  if (CITIES.includes(city)) write(storage, `fs-city-${role}`, city);
}

/** Alerts not seen before (by id), oldest first — used so that repeated
 *  polling never notifies twice. */
export function newAlerts(items, seenIds) {
  return items.filter((a) => !seenIds.has(a.id)).sort((a, b) => a.id - b.id);
}
