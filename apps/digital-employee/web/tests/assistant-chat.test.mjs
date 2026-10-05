import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import ts from 'typescript';

const source = await readFile(new URL('../src/assistantChat.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { applyChatStreamEvent, preserveUpdatedCards, toAssistantMessage } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
);
const productApiSource = `${await readFile(new URL('../src/productApi.ts', import.meta.url), 'utf8')}
export { chatCardOf };`;
const productApiCompiled = ts.transpileModule(productApiSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText.replace(/^import .*;\n/gm, '');
const { chatCardOf } = await import(
  `data:text/javascript;base64,${Buffer.from(productApiCompiled).toString('base64')}`
);

const base = {
  id: 'assistant-1',
  role: 'assistant',
  text: '',
  delivery: 'running',
  createdAt: '2026-10-05T10:00:00+08:00',
  execution: {
    schemaVersion: 'v1',
    turnId: 'turn-1',
    inputMessageId: 'input-1',
    assistantMessageId: 'assistant-1',
    modelMessages: [],
    toolCalls: [],
  },
};

const card = (cardId, status = 'WAITING_ACTION') => ({
  cardId,
  conversationId: 'conversation-1',
  turnId: 'turn-1',
  status,
  display: {
    applicationKey: 'demo.application',
    protocolProfile: 'a2ui.v0_9',
    snapshotMessages: [],
    catalog: {
      protocolVersion: '0.9',
      catalogId: 'demo',
      catalogRevision: '1',
      catalogDigest: 'digest',
    },
    actions: [],
  },
});

test('tool completion updates by toolCallId without reordering parallel calls', () => {
  const startedA = applyChatStreamEvent(base, {
    type: 'tool_call_started', sequence: 2, messageId: 'assistant-1', inputMessageId: 'input-1',
    toolCallId: 'call-a', name: 'first_tool', arguments: { query: 'A' },
    startedAt: '2026-10-05T10:00:01+08:00',
  });
  const startedB = applyChatStreamEvent(startedA, {
    type: 'tool_call_started', sequence: 3, messageId: 'assistant-1', inputMessageId: 'input-1',
    toolCallId: 'call-b', name: 'second_tool', arguments: { query: 'B' },
    startedAt: '2026-10-05T10:00:02+08:00',
  });
  const finishedA = applyChatStreamEvent(startedB, {
    type: 'tool_call_finished', sequence: 4, messageId: 'assistant-1', inputMessageId: 'input-1',
    toolCallId: 'call-a', name: 'first_tool', lifecycleStatus: 'returned',
    toolMessageStatus: 'success', finishedAt: '2026-10-05T10:00:03+08:00',
    durationMs: 2000, result: { count: 1 },
  });

  assert.deepEqual(finishedA.execution.toolCalls.map((item) => item.toolCallId), ['call-a', 'call-b']);
  assert.equal(finishedA.execution.toolCalls[0].sequence, 2);
  assert.equal(finishedA.execution.toolCalls[0].lifecycleStatus, 'returned');
  assert.equal(finishedA.execution.toolCalls[0].businessSuccess, undefined);
});

test('missing provider message id is not fabricated', () => {
  const next = applyChatStreamEvent(base, {
    type: 'reasoning_delta', sequence: 2, messageId: 'assistant-1', inputMessageId: 'input-1',
    modelMessageId: null, text: 'provider reasoning',
  });
  assert.deepEqual(next.execution.modelMessages, []);
  assert.equal(next.reasoning, 'provider reasoning');
});

test('final model reasoning remains a reasoning part while final text stays the answer', () => {
  const converted = toAssistantMessage({
    ...base,
    delivery: 'completed',
    text: '最终回答',
    execution: {
      ...base.execution,
      modelMessages: [{
        sequence: 5,
        messageId: 'provider-final',
        text: '最终回答',
        reasoning: '真实 provider reasoning',
        phase: 'final',
      }],
    },
  });
  assert.deepEqual(converted.content, [
    { type: 'reasoning', text: '真实 provider reasoning' },
    { type: 'text', text: '最终回答' },
  ]);
});

test('an explicit empty parts array does not hide compatible top-level text', () => {
  const converted = toAssistantMessage({
    ...base,
    delivery: 'completed',
    text: '兼容正文',
    parts: [],
  });
  assert.deepEqual(converted.content.at(-1), { type: 'text', text: '兼容正文' });
});

test('text and applications retain SSE order while repeated cards update in place', () => {
  const events = [
    { type: 'text_delta', sequence: 2, partId: 'text:assistant-1:1', modelMessageId: 'model-1', text: '文字 A' },
    { type: 'application_rendered', sequence: 3, partId: 'application:card-1', turnId: 'turn-1', assistantMessageId: 'assistant-1', card: card('card-1') },
    { type: 'text_delta', sequence: 4, partId: 'text:assistant-1:2', modelMessageId: 'model-1', text: '文字 B' },
    { type: 'application_rendered', sequence: 5, partId: 'application:duplicate-card-1', turnId: 'turn-1', assistantMessageId: 'assistant-1', card: card('card-1', 'COMPLETED') },
    { type: 'application_rendered', sequence: 6, partId: 'application:card-2', turnId: 'turn-1', assistantMessageId: 'assistant-1', card: card('card-2') },
    { type: 'text_delta', sequence: 7, partId: 'text:assistant-1:3', modelMessageId: 'model-1', text: '文字 C' },
  ].map(event => ({ ...event, messageId: 'assistant-1', inputMessageId: 'input-1' }));
  const result = events.reduce(applyChatStreamEvent, base);

  assert.deepEqual(result.parts.map(part => [part.type, part.id]), [
    ['text', 'text:assistant-1:1'],
    ['application', 'application:card-1'],
    ['text', 'text:assistant-1:2'],
    ['application', 'application:card-2'],
    ['text', 'text:assistant-1:3'],
  ]);
  assert.equal(result.parts[1].card.status, 'COMPLETED');

  const waiting = applyChatStreamEvent(result, {
    type: 'waiting_action', sequence: 8, messageId: 'assistant-1', inputMessageId: 'input-1',
    turnId: 'turn-1', assistantMessageId: 'assistant-1',
    partId: 'application:card-1', cardId: 'card-1',
  });
  assert.equal(waiting.parts.length, result.parts.length);
  assert.equal(waiting.delivery, 'waiting_action');
});

test('done projection keeps only snapshots updated by a completed Action', () => {
  const rendered = {
    ...base,
    parts: [
      { type: 'application', id: 'application:card-1', cardId: 'card-1', card: card('card-1') },
      { type: 'application', id: 'application:card-2', cardId: 'card-2', card: card('card-2') },
    ],
  };
  const merged = preserveUpdatedCards(rendered, new Map([
    ['card-1', card('card-1', 'COMPLETED')],
  ]));
  assert.equal(merged.parts[0].card.status, 'COMPLETED');
  assert.equal(merged.parts[1].card.status, 'WAITING_ACTION');
});

test('an unassigned historical card may omit turnId without failing history parsing', () => {
  const orphan = { ...card('orphan-card') };
  delete orphan.turnId;
  assert.equal(chatCardOf(orphan).turnId, '');
});
