import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const compiled = await build({ entryPoints: [new URL('../src/productApi.ts', import.meta.url).pathname], bundle: true, write: false, platform: 'node', format: 'esm' });
const { productApi } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
test('POST keeps conversation in body and resends the identical request ID', async () => {
  const calls = []; const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => { calls.push({ url, body: JSON.parse(init.body) }); return new Response('data: '+JSON.stringify({ type: 'done', sequence: 1, messageId: '2', inputMessageId: '1', content: { delivery: 'completed' } })+'\n\n'); };
  try {
    for (let attempt=0; attempt<2; attempt++) await productApi.sendMessage('56', 'hello', () => {}, undefined, [{ activityId: 'a' }], undefined, 'request-stable');
    assert.deepEqual(calls[0], calls[1]);
    assert.equal(calls[0].url, '/api/conversations/messages');
    assert.deepEqual(calls[0].body, { conversationId: 56, text: 'hello', clientRequestId: 'request-stable', runReferences: [{ activityId: 'a' }] });
  } finally { globalThis.fetch = original; }
});
test('history query keeps conversation parameter and exposes saved request ID for reconciliation', async () => {
  const original = globalThis.fetch; let path;
  globalThis.fetch = async url => { path = url; return Response.json({ messages: [{ id: 1, role: 'user', content: { text: 'hello', clientRequestId: 'request-stable' } }] }); };
  try {
    const history = await productApi.messages('56');
    assert.equal(path, '/api/conversations/messages?conversationId=56');
    assert.equal(history.items[0].clientRequestId, 'request-stable');
  } finally { globalThis.fetch = original; }
});
