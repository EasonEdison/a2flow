import test from 'node:test';
import assert from 'node:assert/strict';
import { readChatStream } from '../src/chatStream.mjs';

const frame = (sequence, type, extra = {}) => `data: ${JSON.stringify({ sequence, type, messageId: '2', inputMessageId: '1', ...extra })}\r\n\r\n`;
test('UTF8 and CRLF split at every byte; duplicate event is not duplicated', async () => {
  const bytes = new TextEncoder().encode(frame(1, 'turn_started') + frame(2, 'text_delta', { text: '你好' }) + frame(2, 'text_delta', { text: '你好' }) + frame(3, 'done'));
  const stream = new ReadableStream({ start(c) { for (const byte of bytes) c.enqueue(Uint8Array.of(byte)); c.close(); } });
  const events = [];
  await readChatStream(new Response(stream), e => events.push(e));
  assert.deepEqual(events.map(e => e.sequence), [1, 2, 3]);
  assert.equal(events[1].text, '你好');
});
test('first delta arrives before response ends', async () => {
  let writer;
  const stream = new ReadableStream({ start(c) { writer = c; } });
  let saw;
  const first = new Promise(resolve => { saw = resolve; });
  const read = readChatStream(new Response(stream), saw);
  writer.enqueue(new TextEncoder().encode(frame(1, 'text_delta', { text: 'first' })));
  assert.equal((await first).text, 'first');
  writer.enqueue(new TextEncoder().encode(frame(2, 'done'))); writer.close();
  await read;
});
test('EOF without terminal, event gap, and mixed turn are rejected', async () => {
  await assert.rejects(readChatStream(new Response(frame(1, 'text_delta')), () => {}), /DISCONNECTED/);
  await assert.rejects(readChatStream(new Response(frame(2, 'done')), () => {}), /SEQUENCE/);
  await assert.rejects(readChatStream(new Response(frame(1, 'turn_started') + frame(2, 'done', { messageId: '3' })), () => {}), /ID_CHANGED/);
});
