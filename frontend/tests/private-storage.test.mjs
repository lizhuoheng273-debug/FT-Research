import assert from 'node:assert/strict';
import test from 'node:test';
import { createPrivateStorage } from '../src/lib/privateStorage.ts';

test('guest storage never reads or writes owner browser keys', () => {
  const storage = new Map([['vr-watchlist', '["600519"]']]);
  const disk = { getItem: (k) => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v), removeItem: (k) => storage.delete(k) };
  const guest = createPrivateStorage({ id: 'guest-a', kind: 'guest' }, disk);
  assert.equal(guest.get('watchlist'), null);
  guest.set('watchlist', '["000001"]');
  assert.equal(storage.has('ft:owner:watchlist'), false);
  assert.equal(createPrivateStorage({ id: 'guest-b', kind: 'guest' }, disk).get('watchlist'), null);
});

test('owner storage is namespaced', () => {
  const values = new Map();
  const disk = { getItem: (k) => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: (k) => values.delete(k) };
  const owner = createPrivateStorage({ id: 'owner', kind: 'owner' }, disk);
  owner.set('notes', 'private');
  assert.equal(values.get('ft:owner:notes'), 'private');
  assert.equal(owner.get('notes'), 'private');
});
