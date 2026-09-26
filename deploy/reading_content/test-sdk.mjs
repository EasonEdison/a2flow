// Validate authored basic components with the same locked SDK used by the B UI.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { buildApplications } from './assets.mjs';

const requireWeb = createRequire(resolve(process.argv[2] || 'apps/digital-employee/web', 'package.json'));
const { basicCatalog } = await import(pathToFileURL(requireWeb.resolve('@a2ui/react/v0_9')));
const { MessageProcessor } = await import(pathToFileURL(requireWeb.resolve('@a2ui/web_core/v0_9')));
let checked = 0;
for (const app of buildApplications()) {
  for (const message of app.showTemplate.messageTemplates) {
    for (const { id, component, ...props } of message.updateComponents?.components || []) {
      const registered = basicCatalog.components.get(component);
      if (!registered) continue; // Project-specific components have their own contract tests.
      const result = registered.schema.safeParse(props);
      assert.ok(result.success, `${app.appCode}/${id}: ${result.error?.message}`);
      checked++;
    }
  }
}
const [reading, topic, manuscript] = buildApplications();
const selection = reading.showTemplate.messageTemplates[1].updateComponents.components[8];
const { id, component, ...props } = selection;
const schema = basicCatalog.components.get(component).schema;
assert.ok(schema.safeParse({ ...props, options: [{ label: '一个真实选项', value: 'point-1' }] }).success);
assert.equal(schema.safeParse({ ...props, options: { path: '/options' } }).success, false);
const pointerTokens = pointer => pointer.slice(1).split('/').map(token => token.replaceAll('~1', '/').replaceAll('~0', '~'));
const readPointer = (root, pointer) => pointerTokens(pointer).reduce((value, token) => value?.[token], root);
const writePointer = (root, pointer, value) => {
  const tokens = pointerTokens(pointer);
  let cursor = root;
  for (const token of tokens.slice(0, -1)) cursor = cursor[token];
  cursor[tokens.at(-1)] = structuredClone(value);
};
const renderAdapters = (action, capabilityData, actionContext = {}) => action.resultAdapters
  .toSorted((left, right) => left.order - right.order)
  .map(adapter => {
    const message = structuredClone(adapter.messageTemplate);
    for (const binding of adapter.bindings) {
      const source = binding.source === 'CAPABILITY_DATA' ? capabilityData
        : binding.source === 'ACTION_CONTEXT' ? actionContext : undefined;
      writePointer(message, binding.targetPath, readPointer(source, binding.sourcePath));
    }
    return message;
  });
const replay = initial => {
  const processor = new MessageProcessor([basicCatalog], undefined, { version: 'v0.9.1' });
  processor.processMessages([
    { version: 'v0.9.1', createSurface: { surfaceId: 'main', catalogId: basicCatalog.id } },
    { version: 'v0.9.1', updateDataModel: { surfaceId: 'main', path: '/', value: initial } },
  ]);
  return processor;
};
const model = processor => processor.model.getSurface('main').dataModel;
const apply = (processor, action, capabilityData, actionContext) =>
  processor.processMessages(renderAdapters(action, capabilityData, actionContext));

const readingReplay = replay({
  prompt: '保留', projectId: 'project-1', points: [{ id: 'point-1' }],
  selectedPointIds: [], userNotes: '', confirmationId: '', status: '',
});
apply(readingReplay, reading.actionBindings[0], {
  id: 'confirmation-reading', selectedPointIds: ['point-1'], userNotes: '浏览器里的补充',
});
assert.equal(model(readingReplay).get('/prompt'), '保留');
assert.deepEqual(model(readingReplay).get('/selectedPointIds'), ['point-1']);
assert.equal(model(readingReplay).get('/userNotes'), '浏览器里的补充');
readingReplay.model.dispose();

const topicReplay = replay({
  prompt: '保留', projectId: 'project-1', confirmationId: '', status: '',
  topics: [{ id: 'old', title: '旧标题' }, { id: 'other', title: '其他标题' }],
});
apply(topicReplay, topic.actionBindings[0], {
  id: 'confirmation-topic', topicId: 'chosen', editedTitle: '最终标题', editedAngle: '最终角度',
});
assert.equal(model(topicReplay).get('/projectId'), 'project-1');
assert.deepEqual(model(topicReplay).get('/topics').map(({ id, title, angle }) => ({ id, title, angle })),
  [{ id: 'chosen', title: '最终标题', angle: '最终角度' }]);
topicReplay.model.dispose();

const manuscriptActions = Object.fromEntries(manuscript.actionBindings.map(action => [action.actionCode, action]));
const manuscriptReplay = replay({
  projectId: 'project-1', projectRevision: 7, draftTitle: '旧草稿', draftMarkdown: '旧正文',
  savedTitle: '', savedMarkdown: '', savedArtifactId: '', savedArtifactRevision: 0,
  inputRefs: [{ kind: 'SOURCE', id: 'source-1', revision: 1 }], citations: [],
  status: '', confirmationId: '',
  export: { artifactId: 'stale', artifactRevision: 1, filename: 'stale.md', mediaType: 'text/markdown', content: 'stale' },
});
apply(manuscriptReplay, manuscriptActions.saveManuscriptDraft, {
  id: 'manuscript-2', revision: 2, body: { manuscript: { title: '浏览器编辑标题', bodyMarkdown: '# 浏览器编辑正文' } },
});
assert.equal(model(manuscriptReplay).get('/projectId'), 'project-1');
assert.equal(model(manuscriptReplay).get('/draftTitle'), '浏览器编辑标题');
assert.equal(model(manuscriptReplay).get('/savedTitle'), '浏览器编辑标题');
assert.equal(model(manuscriptReplay).get('/draftMarkdown'), '# 浏览器编辑正文');
assert.equal(model(manuscriptReplay).get('/savedMarkdown'), '# 浏览器编辑正文');
assert.deepEqual(model(manuscriptReplay).get('/export'),
  { artifactId: '', artifactRevision: 0, filename: '', mediaType: '', content: '' });
apply(manuscriptReplay, manuscriptActions.exportManuscript,
  { filename: 'draft.md', mediaType: 'text/markdown', content: '# 浏览器编辑正文' },
  { artifactId: 'manuscript-2', artifactRevision: 2 });
assert.equal(model(manuscriptReplay).get('/draftMarkdown'), '# 浏览器编辑正文');
assert.deepEqual(model(manuscriptReplay).get('/export'), {
  artifactId: 'manuscript-2', artifactRevision: 2,
  filename: 'draft.md', mediaType: 'text/markdown', content: '# 浏览器编辑正文',
});
apply(manuscriptReplay, manuscriptActions.confirmManuscript, { id: 'confirmation-manuscript' });
assert.equal(model(manuscriptReplay).get('/confirmationId'), 'confirmation-manuscript');
assert.equal(model(manuscriptReplay).get('/export/content'), '# 浏览器编辑正文');
manuscriptReplay.model.dispose();

console.log(`PASS ${checked} basic components match the locked B SDK; leaf result adapters preserve and refresh browser edits`);
