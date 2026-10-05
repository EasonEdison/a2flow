import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import ts from 'typescript';

const source = await readFile(new URL('../src/assistantChat.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { applyChatStreamEvent, toAssistantMessage } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
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
