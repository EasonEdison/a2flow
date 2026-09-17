import assert from 'node:assert/strict';
import test from 'node:test';
import {
  hasPendingJsonField,
  inspectDraftText,
  inspectPathEditability,
  isEditableRecord,
  jsonFieldConflict,
  parseJsonField,
  updatePath,
  updateRow,
  appendRow,
  removeRow,
  moveRow,
  skillFrontmatterMismatch,
  workflowTopologyWarning,
} from '../src/form-editor-state.js';

const drafts = {
  SKILL: {
    metadata: { name: 'plan', description: 'Plan safely', extra: { retained: true } },
    skillMd: '---\nname: plan\ndescription: Plan safely\n---\n\n# Plan',
    requiredToolNames: ['execute_ability'], abilityBindings: ['demo.lookup'],
    applicationBindings: ['demo.confirm'], resources: [{ logicalPath: 'guide.md', custom: 1 }],
    extension: { nested: { retained: true } },
  },
  ABILITY: {
    abilityKey: 'demo.lookup', adapterOperationRef: 'demo.lookup.read',
    credentialRequirements: [{ slotId: 'read', required: true, extension: 'keep' }],
    defaultSuccessPolicyRef: 'ok',
    inputBindings: [{ targetPath: '/query', source: 'MODEL_ARGUMENT', sourcePath: '/query', extension: 1 }],
    modelArgumentSchema: { type: 'object', extension: { keep: true } },
    outputSchema: { type: 'object' }, resolvedInputSchema: { type: 'object' },
    resultInterpretationPolicies: [{ policyRef: 'ok', operator: 'JSON_POINTER_EQUALS' }],
    extension: { keep: true },
  },
  APPLICATION: {
    definition: {
      asset: { kind: 'APPLICATION', applicationKey: 'demo.app', extra: 'keep' },
      renderPolicy: { tool: 'render_application', interactionMode: 'INTERACTIVE', requiresPause: true },
      actionPolicies: [{ actionName: 'confirm', sourceComponentId: 'button', abilityReleaseRef: 'demo.confirm@v1', successPolicyRef: 'ok', completeInteractionOnSuccess: true, controlRequestDedupeOnly: true, businessIdempotencyOwner: 'CALLED_API_BACKEND', extension: 1 }],
      surfaceTemplate: { inputSchema: { type: 'object' }, components: [], extension: { keep: true } },
      extension: { keep: true },
    },
    dependencies: [{ kind: 'ABILITY', key: 'demo.confirm', extension: true }],
    extension: { keep: true },
  },
  WORKFLOW: {
    definitionKey: 'demo.workflow', topology: 'SEQUENTIAL',
    nodes: [{ nodeId: 'one', skillKey: 'demo/one', extension: { keep: true } }, { nodeId: 'two', skillKey: 'demo/two' }],
    extension: { nested: true },
  },
};

for (const [kind, draft] of Object.entries(drafts)) {
  test(`${kind} mode inspection is lossless and does not mutate`, () => {
    const text = JSON.stringify(draft, null, 2);
    const before = structuredClone(draft);
    const result = inspectDraftText(text);
    assert.equal(result.ok, true);
    assert.deepEqual(result.document, draft);
    assert.deepEqual(draft, before);
    assert.equal(JSON.stringify(result.document, null, 2), text);
  });
}

test('invalid JSON and non-object roots remain blocked without replacement', () => {
  for (const text of ['{"partial":', '[]', 'null']) {
    const result = inspectDraftText(text);
    assert.equal(result.ok, false);
    assert.equal(result.text, text);
  }
});

test('path and partial JSON edits preserve unknown nested fields and input values', () => {
  const original = drafts.ABILITY;
  const changed = updatePath(original, ['modelArgumentSchema'], { type: 'array' });
  assert.deepEqual(changed.extension, original.extension);
  assert.equal(changed.credentialRequirements[0].extension, 'keep');
  assert.equal(original.modelArgumentSchema.type, 'object');
  assert.throws(() => updatePath(original, ['__proto__', 'polluted'], true), /UNSAFE_PATH/);
});

test('partial complex JSON edits fail without changing the draft', () => {
  const result = parseJsonField('{"type":', 'object');
  assert.equal(result.ok, false);
  assert.equal(result.text, '{"type":');
  assert.equal(hasPendingJsonField(drafts.ABILITY), false);
  assert.equal(hasPendingJsonField(updatePath(drafts.ABILITY, ['modelArgumentSchema'], '{"type":')), true);
  assert.deepEqual(drafts.ABILITY.modelArgumentSchema, { type: 'object', extension: { keep: true } });
});

test('path edits refuse malformed existing parents but create absent parents', () => {
  const malformedValues = ['{unfinished user text', [], null];
  for (const surfaceTemplate of malformedValues) {
    const original = { definition: { surfaceTemplate }, unrelated: { keep: true } };
    assert.equal(updatePath(original, ['definition', 'surfaceTemplate', 'inputSchema'], {}), original);
    assert.deepEqual(original.definition.surfaceTemplate, surfaceTemplate);
    const state = inspectPathEditability(original, ['definition', 'surfaceTemplate', 'inputSchema']);
    assert.equal(state.editable, false);
    assert.deepEqual(state.blockedPath, ['definition', 'surfaceTemplate']);
  }

  const missing = { definition: {}, unrelated: { keep: true } };
  assert.deepEqual(updatePath(missing, ['definition', 'surfaceTemplate', 'inputSchema'], {}), {
    definition: { surfaceTemplate: { inputSchema: {} } },
    unrelated: { keep: true },
  });
  assert.equal(inspectPathEditability(missing, ['definition', 'surfaceTemplate', 'inputSchema']).editable, true);
});

test('overlapping JSON fields report pending ownership conflicts in both directions', () => {
  const parentPending = { definition: { surfaceTemplate: '{unfinished user text' }, unrelated: 'keep' };
  assert.match(jsonFieldConflict(parentPending, ['definition', 'surfaceTemplate', 'inputSchema']), /Surface template/);
  assert.equal(jsonFieldConflict(parentPending, ['definition', 'surfaceTemplate']), null);
  assert.equal(updatePath(parentPending, ['unrelated'], 'changed').definition.surfaceTemplate, '{unfinished user text');

  const childPending = { definition: { surfaceTemplate: { inputSchema: '{unfinished schema', components: [] } } };
  assert.match(jsonFieldConflict(childPending, ['definition', 'surfaceTemplate']), /Parameter schema/);
  assert.equal(jsonFieldConflict(childPending, ['definition', 'surfaceTemplate', 'inputSchema']), null);
  assert.equal(updatePath(childPending, ['definition', 'surfaceTemplate'], '{parent edit'), childPending);
});

test('malformed known objects and rows stay represented and cannot be nested-edited', () => {
  const malformed = {
    metadata: [],
    definition: 'broken',
    inputBindings: [null, 'broken', { targetPath: '/safe' }],
    nodes: [[], { nodeId: 'safe' }],
  };
  assert.equal(isEditableRecord(malformed.metadata), false);
  assert.equal(isEditableRecord(malformed.definition), false);
  assert.equal(updatePath(malformed, ['metadata', 'name'], 'lost'), malformed);
  assert.equal(updateRow(malformed, ['inputBindings'], 0, 'targetPath', '/lost'), malformed);
  assert.equal(updateRow(malformed, ['inputBindings'], 1, 'targetPath', '/lost'), malformed);
  assert.equal(updateRow(malformed, ['nodes'], 0, 'nodeId', 'lost'), malformed);
  const changed = updateRow(malformed, ['inputBindings'], 2, 'targetPath', '/changed');
  assert.equal(changed.inputBindings[2].targetPath, '/changed');
  assert.equal(changed.inputBindings[0], null);
});

test('form and JSON roundtrip retain pending nested text through unrelated edits', () => {
  const pending = updatePath(drafts.APPLICATION, ['definition', 'surfaceTemplate', 'inputSchema'], '{"type":');
  const changed = updatePath(pending, ['dependencies'], [...pending.dependencies, { kind: 'COMPONENT', key: 'x' }]);
  const text = JSON.stringify(changed, null, 2);
  const inspected = inspectDraftText(text);
  assert.equal(inspected.ok, true);
  assert.equal(inspected.document.definition.surfaceTemplate.inputSchema, '{"type":');
  assert.equal(inspected.document.definition.surfaceTemplate.extension.keep, true);
});

test('row edits and reorder preserve row extensions and unrelated fields', () => {
  const changed = updateRow(drafts.WORKFLOW, ['nodes'], 0, 'nodeId', 'first');
  const appended = appendRow(changed, ['nodes'], { nodeId: '', skillKey: '' });
  const moved = moveRow(appended, ['nodes'], 0, 1);
  const removed = removeRow(moved, ['nodes'], 2);
  assert.equal(removed.nodes[1].extension.keep, true);
  assert.deepEqual(removed.extension, drafts.WORKFLOW.extension);
  assert.equal(drafts.WORKFLOW.nodes[0].nodeId, 'one');
});

test('skill metadata reports narrow frontmatter mismatch and unsupported headers', () => {
  assert.equal(skillFrontmatterMismatch(drafts.SKILL), null);
  assert.match(skillFrontmatterMismatch(updatePath(drafts.SKILL, ['metadata', 'name'], 'other')), /不一致/);
  assert.match(skillFrontmatterMismatch(updatePath(drafts.SKILL, ['skillMd'], '---\nname: plan\nextra: value\ndescription: Plan safely\n---\n')), /不受支持/);
});

test('unsupported workflow topology warns without conversion or mutation', () => {
  const draft = updatePath(drafts.WORKFLOW, ['topology'], 'PARALLEL');
  assert.match(workflowTopologyWarning(draft), /无法发布/);
  assert.equal(draft.topology, 'PARALLEL');
  assert.equal(drafts.WORKFLOW.topology, 'SEQUENTIAL');
});
