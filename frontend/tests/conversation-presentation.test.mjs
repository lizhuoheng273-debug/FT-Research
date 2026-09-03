import assert from 'node:assert/strict';
import test from 'node:test';
import { shouldFollowOutput, canSaveAnswer } from '../src/lib/conversationPresentation.ts';

test('reader at bottom follows output but reading earlier text does not', () => {
  assert.equal(shouldFollowOutput({ scrollHeight: 1000, scrollTop: 590, clientHeight: 400 }), true);
  assert.equal(shouldFollowOutput({ scrollHeight: 1000, scrollTop: 100, clientHeight: 400 }), false);
});

test('incomplete or stopped output cannot be presented as a saved full answer', () => {
  assert.equal(canSaveAnswer({ role: 'assistant', content: '正文', status: 'partial' }), false);
  assert.equal(canSaveAnswer({ role: 'assistant', content: '正文', status: 'error' }), false);
  assert.equal(canSaveAnswer({ role: 'assistant', content: '正文', status: 'stopped' }), false);
  assert.equal(canSaveAnswer({ role: 'assistant', content: '正文', partial: true }), false);
  assert.equal(canSaveAnswer({ role: 'assistant', content: '正文', status: 'complete' }), true);
  assert.equal(canSaveAnswer({ role: 'assistant', content: '旧回答' }), true);
});
