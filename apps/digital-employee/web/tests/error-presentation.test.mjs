import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(
  new URL('../src/errorPresentation.ts', import.meta.url),
  'utf8',
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { chatErrorPresentation, persistedChatErrorCode } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
);

test('maps only reviewed Chat error codes to user-facing reasons', () => {
  assert.equal(chatErrorPresentation('ARGUMENT_INVALID'), '工具执行被拒：参数无效');
  assert.equal(
    chatErrorPresentation('TRANSPORT_ERROR'),
    '能力调用失败，请查看已保存状态；未自动重试',
  );
  assert.equal(chatErrorPresentation('DUPLICATE_TOOL_ARGUMENT'), '模型返回协议异常');
});

test('reads only a string errorCode from persisted message content', () => {
  assert.equal(persistedChatErrorCode({ errorCode: 'ARGUMENT_INVALID' }), 'ARGUMENT_INVALID');
  assert.equal(persistedChatErrorCode({ errorCode: 42 }), undefined);
  assert.equal(persistedChatErrorCode('MODEL_STREAM_FAILED'), undefined);
  assert.equal(persistedChatErrorCode(null), undefined);
});

test('unknown or missing codes stay generic and never echo their value', () => {
  const secretCode = 'PRIVATE_secret-prompt';
  assert.equal(chatErrorPresentation(secretCode), '其他失败');
  assert.equal(chatErrorPresentation(undefined), '其他失败');
  assert.doesNotMatch(chatErrorPresentation(secretCode), /PRIVATE|secret|prompt/u);
});
