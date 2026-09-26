import test from 'node:test';
import assert from 'node:assert/strict';
import {
  analyzeSurface,
  updateComponentProperty,
  moveComponent,
  removeComponent,
  addComponent,
  validateSample,
  createPreview,
  simulateAction,
} from '../src/a2ui-workbench.js';
import { inspectPublishedComponentCatalog } from '../src/component-catalog-state.js';

const surface = {
  surfaceKey: 'demo',
  rootId: 'root',
  inputSchema: {
    type: 'object',
    required: ['prompt', 'options'],
    properties: {
      prompt: { type: 'string' },
      options: { type: 'array' },
      selection: { type: 'array' },
    },
  },
  components: [
    { id: 'root', component: 'Column', children: ['prompt', 'choice', 'confirm'], extension: { keep: true } },
    { id: 'prompt', component: 'Text', text: { path: '/prompt' }, unknown: 1 },
    { id: 'choice', component: 'ChoicePicker', options: [{ label: 'One', value: 'one' }], value: { path: '/selection' }, variant: 'mutuallyExclusive' },
    { id: 'confirm', component: 'Button', label: 'Confirm', action: { event: { name: 'confirm', context: { selection: { path: '/selection' }, safe: { literal: true } } } } },
  ],
};

const sample = { prompt: 'Choose', options: [{ label: 'One', value: 'one' }], selection: ['one'] };

test('analyzes hierarchy and reports duplicate and dangling ids without rewriting data', () => {
  const malformed = structuredClone(surface);
  malformed.components.push({ id: 'prompt', component: 'FutureCard', payload: { keep: true } });
  malformed.components[0].children.push('missing');
  const result = analyzeSurface(malformed);
  assert.deepEqual(result.nodes[0].children, ['prompt', 'choice', 'confirm', 'missing']);
  assert.ok(result.issues.some((issue) => issue.code === 'DUPLICATE_COMPONENT_ID' && issue.path === '/components/4/id'));
  assert.ok(result.issues.some((issue) => issue.code === 'DANGLING_COMPONENT_REF' && issue.path === '/components/0/children/3'));
  assert.deepEqual(malformed.components[4].payload, { keep: true });
});

test('component edits preserve unknown fields and reject immutable ids', () => {
  const updated = updateComponentProperty(surface, 1, ['text', 'path'], '/title');
  assert.equal(updated.components[1].text.path, '/title');
  assert.equal(updated.components[1].unknown, 1);
  assert.equal(surface.components[1].text.path, '/prompt');
  assert.equal(updateComponentProperty(surface, 1, ['id'], 'changed'), surface);
});

test('component edits preserve malformed ancestors for full JSON repair', () => {
  for (const malformed of [null, 'retained', ['retained']]) {
    const document = structuredClone(surface);
    document.components[1].text = malformed;
    const updated = updateComponentProperty(document, 1, ['text', 'path'], '/title');
    assert.equal(updated, document);
    assert.deepEqual(updated.components[1].text, malformed);
  }
  for (const malformed of [null, 'retained', ['retained']]) {
    const document = structuredClone(surface);
    document.components[3].action = malformed;
    const updated = updateComponentProperty(document, 3, ['action', 'event', 'name'], 'changed');
    assert.equal(updated, document);
    assert.deepEqual(updated.components[3].action, malformed);
  }
});

test('add remove and reorder follow the flat component contract without reference repair', () => {
  const added = addComponent(surface, 'Text');
  assert.deepEqual(addComponent(surface, 'ChoicePicker').components.at(-1).options, []);
  assert.equal(added.components.at(-1).component, 'Text');
  assert.equal(new Set(added.components.map((item) => item.id)).size, added.components.length);
  const moved = moveComponent(added, added.components.length - 1, -1);
  assert.equal(moved.components.at(-2).component, 'Text');
  const removed = removeComponent(surface, 1);
  assert.deepEqual(removed.components[0].children, ['prompt', 'choice', 'confirm']);
  assert.equal(removed.components.some((item) => item.id === 'prompt'), false);
});

test('sample validation finds required and binding type errors with focusable paths', () => {
  const result = validateSample(surface, { options: 'wrong' });
  assert.ok(result.issues.some((issue) => issue.code === 'SAMPLE_REQUIRED' && issue.samplePath === '/prompt'));
  assert.ok(result.issues.some((issue) => issue.code === 'SAMPLE_TYPE' && issue.samplePath === '/options'));
  assert.ok(result.issues.some((issue) => issue.code === 'BINDING_MISSING' && issue.componentId === 'choice' && issue.samplePath === '/selection'));
});

test('safe preview renders supported components and bounds action simulation', () => {
  const preview = createPreview(surface, sample);
  assert.equal(preview.ok, true);
  assert.equal(preview.root.children[0].value, 'Choose');
  assert.equal(preview.root.children[1].options[0].label, 'One');
  const event = simulateAction(surface, 'confirm', sample);
  assert.deepEqual(event, { simulated: true, componentId: 'confirm', name: 'confirm', arguments: { selection: ['one'], safe: true } });
});

test('safe preview refuses unsupported, invalid, oversized and dangerous content', () => {
  const unsupported = structuredClone(surface);
  unsupported.components[1].component = 'Html';
  assert.equal(createPreview(unsupported, sample).ok, false);
  assert.equal(createPreview(surface, { ...sample, prompt: '<script>alert(1)</script>' }).root.children[0].value, '<script>alert(1)</script>');
  assert.equal(createPreview(surface, JSON.parse('{"__proto__":{"polluted":true}}')).ok, false);
  assert.equal(createPreview(surface, { ...sample, huge: 'x'.repeat(100001) }).ok, false);
});

test('preview reports malformed component bindings and actions without throwing', () => {
  const cases = [
    ['Text', 'text', null, 'INVALID_TEXT_BINDING'],
    ['Text', 'text', '/prompt', 'INVALID_TEXT_BINDING'],
    ['Text', 'text', [], 'INVALID_TEXT_BINDING'],
    ['Text', 'text', {}, 'INVALID_TEXT_BINDING'],
    ['ChoicePicker', 'options', null, 'INVALID_OPTIONS'],
    ['ChoicePicker', 'options', { path: '/options' }, 'INVALID_OPTIONS'],
    ['ChoicePicker', 'value', '/selection', 'INVALID_VALUE_BINDING'],
  ];
  for (const [componentType, field, malformed, code] of cases) {
    const document = structuredClone(surface);
    const component = document.components.find((item) => item.component === componentType);
    component[field] = malformed;
    const preview = createPreview(document, sample);
    assert.equal(preview.ok, false);
    assert.ok(preview.issues.some((item) => item.code === code));
  }
  for (const malformed of [null, 'event', [], {}, { event: null }, { event: { name: 'confirm', context: null } }]) {
    const document = structuredClone(surface);
    document.components[3].action = malformed;
    const preview = createPreview(document, sample);
    assert.equal(preview.ok, false);
    assert.ok(preview.issues.some((item) => item.code === 'INVALID_BUTTON_ACTION'));
  }
});

test('preview rejects high-fanout shared hierarchies before expanding output', () => {
  const shared = {
    rootId: 'root',
    inputSchema: { type: 'object' },
    components: [
      { id: 'root', component: 'Column', children: Array(64).fill('branch') },
      { id: 'branch', component: 'Column', children: Array(64).fill('leaf') },
      { id: 'leaf', component: 'Text', text: { path: '/value' } },
    ],
  };
  const preview = createPreview(shared, { value: 'safe' });
  assert.equal(preview.ok, false);
  assert.ok(preview.issues.some((item) => item.code === 'RENDER_VISIT_LIMIT'));
  assert.equal(Object.hasOwn(preview, 'root'), false);
});

test('schema issue paths escape JSON Pointer segments and disclose partial validation', () => {
  const document = structuredClone(surface);
  document.inputSchema = {
    type: 'object',
    required: ['a/b~c'],
    properties: { 'a/b~c': { type: 'string' }, nested: { type: 'object', required: ['child'] } },
  };
  const result = validateSample(document, { 'a/b~c': 1, nested: {} });
  assert.ok(result.issues.some((item) => item.code === 'SAMPLE_TYPE' && item.path === '/inputSchema/properties/a~1b~0c' && item.samplePath === '/a~1b~0c'));
  assert.ok(result.issues.some((item) => item.code === 'PARTIAL_SCHEMA_VALIDATION'));
});

test('reads members from the selected published component catalog definition', () => {
  assert.deepEqual(inspectPublishedComponentCatalog({
    definition: {
      catalogKey: 'catalog/v1',
      protocolProfileRef: 'a2ui/v1',
      components: ['Column', 'Text', 'ChoicePicker', 'Button'],
    },
    dependencies: [],
  }, 'catalog/v1'), {
    ok: true,
    catalogKey: 'catalog/v1',
    protocolProfileRef: 'a2ui/v1',
    components: ['Column', 'Text', 'ChoicePicker', 'Button'],
  });
});

test('fails closed for a missing, mismatched, malformed, or duplicate catalog', () => {
  assert.equal(inspectPublishedComponentCatalog(null, 'catalog/v1').ok, false);
  assert.equal(inspectPublishedComponentCatalog({ definition: { catalogKey: 'other', protocolProfileRef: 'a2ui/v1', components: [] } }, 'catalog/v1').ok, false);
  assert.equal(inspectPublishedComponentCatalog({ definition: { catalogKey: 'catalog/v1', protocolProfileRef: 'a2ui/v1', components: ['Text', 1] } }, 'catalog/v1').ok, false);
  assert.equal(inspectPublishedComponentCatalog({ definition: { catalogKey: 'catalog/v1', protocolProfileRef: 'a2ui/v1', components: ['Text', 'Text'] } }, 'catalog/v1').ok, false);
});
