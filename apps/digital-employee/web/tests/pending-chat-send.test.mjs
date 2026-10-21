import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pendingChatSendKey, persistPendingChatSend, readPendingChatSend, acknowledgePendingChatSend } from '../src/pendingChatSend.mjs';
const storage = () => { const values = new Map(); return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }; };
test('lost acknowledgement reload keeps original request ID, references and processing payload', () => {
  const store = storage();
  const key = pendingChatSendKey('member-a:PRT', '56');
  const request = { clientRequestId: 'request-1', text: 'summarize', references: [{ activityId: 'run-1' }], processing: { taskId: 'task-1', requestId: 'processing-1' } };
  persistPendingChatSend(key, request, store);
  request.text = 'edited later';
  const reloaded = readPendingChatSend(key, store);
  assert.equal(reloaded.clientRequestId, 'request-1');
  assert.equal(reloaded.text, 'summarize');
  assert.deepEqual(reloaded.references, [{ activityId: 'run-1' }]);
  assert.equal(reloaded.processing.requestId, 'processing-1');
  persistPendingChatSend(key, reloaded, store);
  assert.deepEqual(readPendingChatSend(key, store), reloaded);
});
test('account and conversation scopes do not borrow uncertain sends', () => {
  const store = storage(); const key = pendingChatSendKey('member-a', '56');
  persistPendingChatSend(key, { clientRequestId: 'one', text: 'x', references: [] }, store);
  assert.equal(readPendingChatSend(pendingChatSendKey('member-b', '56'), store), null);
  assert.equal(readPendingChatSend(pendingChatSendKey('member-a', '57'), store), null);
  acknowledgePendingChatSend(key, 'different', store);
  assert.equal(readPendingChatSend(key, store).clientRequestId, 'one');
  acknowledgePendingChatSend(key, 'one', store);
  assert.equal(readPendingChatSend(key, store), null);
});
test('corrupted or unavailable storage fails closed rather than inventing a new request', () => {
  const store = storage(); store.setItem('key', '{');
  assert.throws(() => readPendingChatSend('key', store));
  assert.throws(() => persistPendingChatSend('key', {}, { setItem() { throw new Error('quota'); } }));
});
