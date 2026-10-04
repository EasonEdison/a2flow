import assert from 'node:assert/strict';
import test from 'node:test';
import { createEmptyA2uiApplicationDraft } from './a2uiApplicationContracts';
import {
  buildA2uiApplicationLocalPreview,
  buildA2uiLocalActionSummary,
  buildA2uiSampleParams,
} from './a2uiApplicationLocalPreview';

function application() {
  const draft = createEmptyA2uiApplicationDraft();
  draft.catalog.catalogId = 'a2flow.digital-employee.pc.v1';
  draft.showTemplate.paramsSchema = {
    type: 'object',
    required: ['title'],
    properties: { title: { type: 'string', examples: ['阅读要点'] } },
  };
  draft.showTemplate.messageTemplates = [
    { version: 'v0.9.1', createSurface: { surfaceId: 'main', catalogId: draft.catalog.catalogId } },
    { version: 'v0.9.1', updateComponents: { surfaceId: 'main', components: [
      { id: 'root', component: 'Column', children: ['title', 'button'] },
      { id: 'title', component: 'Markdown', content: '待替换' },
      { id: 'button', component: 'Button', child: 'button-label', action: { event: { name: 'save', context: { value: 'local' } } } },
      { id: 'button-label', component: 'Text', text: '保存' },
    ] } },
  ];
  draft.showTemplate.inputBindings = [
    { targetMessageIndex: 1, targetPath: '/updateComponents/components/1/content', source: 'APP_PARAMS', sourcePath: '/title', required: true },
  ];
  return draft;
}

test('sample params resolve through the authored ShowTemplate into the complete message batch', () => {
  const result = buildA2uiApplicationLocalPreview(application(), { title: '真实样例标题' });
  assert.deepEqual(result.errors, []);
  assert.equal(
    (result.messages[1].updateComponents as { components: Array<{ content?: string }> }).components[1].content,
    '真实样例标题',
  );
});

test('LoadBinding without an explicit fixture fails closed instead of rendering a partial tree', () => {
  const draft = application();
  draft.loadBindings = [{
    bindingId: 'load-reading-points', capability: { actionCode: 'reading.list' }, requestMappings: [],
    successOutcome: 'NO_UI_MESSAGES', failureOutcome: 'NO_UI_MESSAGES', resultAdapters: [], failureResultAdapters: [],
  }];
  const result = buildA2uiApplicationLocalPreview(draft, { title: '标题' });
  assert.deepEqual(result.messages, []);
  assert.deepEqual(result.requiredLoadFixtureIds, ['load-reading-points']);
  assert.match(result.errors[0], /不会调用 Capability，也不会伪造返回值/);
});

test('schema examples seed the local params entry and disclose missing required samples', () => {
  const seeded = buildA2uiSampleParams({
    type: 'object', required: ['title', 'content'], properties: {
      title: { type: 'string', examples: ['标题'] }, content: { type: 'string' },
    },
  });
  assert.deepEqual(seeded.params, { title: '标题', content: 'local-content-demo' });
  assert.deepEqual(seeded.generatedFields, ['content']);
  assert.deepEqual(seeded.missingRequired, []);
});

test('reading selector gets an explicit local contract fixture with related option values', () => {
  const seeded = buildA2uiSampleParams({
    type: 'object', required: ['projectId', 'artifactId', 'prompt', 'points', 'options'], properties: {
      projectId: { type: 'string' }, artifactId: { type: 'string' }, prompt: { type: 'string' },
      points: { type: 'array', items: { type: 'object', required: ['id', 'claim', 'evidenceQuote', 'explanation'], properties: {
        id: { type: 'string' }, claim: { type: 'string' }, evidenceQuote: { type: 'string' }, explanation: { type: 'string' },
      } } },
      options: { type: 'array', items: { type: 'object', required: ['label', 'value'], properties: {
        label: { type: 'string' }, value: { type: 'string' },
      } } },
    },
  });
  assert.deepEqual(seeded.params.options, [{ label: '保留这个阅读要点', value: 'point-demo-1' }]);
  assert.deepEqual((seeded.params.points as Array<Record<string, unknown>>)[0].id, 'point-demo-1');
  assert.deepEqual(seeded.missingRequired, []);
});

test('local Button action resolves authored mappings but never reports business success', () => {
  const draft = application();
  draft.actionBindings = [{
    bindingId: 'save', surfaceId: 'main', sourceComponentId: 'button', actionCode: 'save',
    allowedSourceComponentIds: ['button'], contextSchema: { type: 'object' },
    capability: { actionCode: 'content.save' },
    requestMappings: [
      { source: 'ACTION_CONTEXT', sourcePath: '/value', targetPath: '/selection' },
      { source: 'APP_PARAMS', sourcePath: '/title', targetPath: '/title' },
    ],
    successOutcome: 'NO_UI_MESSAGES', failureOutcome: 'NO_UI_MESSAGES', resultAdapters: [], failureResultAdapters: [],
    completeWorkflowInteractionOnSuccess: false,
  }];
  const result = buildA2uiLocalActionSummary(draft, { title: '标题' }, {
    name: 'save', surfaceId: 'main', sourceComponentId: 'button', context: { value: 'local' },
  });
  assert.equal(result.capabilityActionCode, 'content.save');
  assert.deepEqual(result.arguments, { selection: 'local', title: '标题' });
  assert.equal('success' in result, false);
});
