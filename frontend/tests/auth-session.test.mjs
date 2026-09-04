import assert from 'node:assert/strict';
import test from 'node:test';
import { clearAuthMemory, getGuestToken, hasGuestToken } from '../src/lib/authClient.ts';

test('guest identity starts in memory only and can be cleared', () => {
  clearAuthMemory();
  assert.equal(getGuestToken(), null);
  assert.equal(hasGuestToken(), false);
});
