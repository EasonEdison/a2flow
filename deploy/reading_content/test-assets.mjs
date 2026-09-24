import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { buildApplications, capabilitySpecs, customAtoms, skillSpecs, validateAssets } from './assets.mjs';

assert.equal(validateAssets().capabilities, 12);
const known = new Set(capabilitySpecs.map(item => item.actionCode));
for (const skill of skillSpecs) for (const actionCode of skill.capabilities) assert.ok(known.has(actionCode), `${skill.skillCode}: ${actionCode}`);

const [reading, topic, manuscript] = buildApplications();
assert.equal(reading.actionBindings[0].actionCode, 'confirmReading');
assert.equal(reading.actionBindings[0].completeWorkflowInteractionOnSuccess, true);
assert.equal(topic.actionBindings[0].actionCode, 'confirmTopic');
const topicButton = topic.showTemplate.messageTemplates[1].updateComponents.components.find(item => item.id === 'confirmTopic');
assert.equal(topicButton.action.event.context.topicId.path, 'id', 'repeated topic button must submit one scalar topic id');

const actions = Object.fromEntries(manuscript.actionBindings.map(item => [item.actionCode, item]));
assert.deepEqual(Object.keys(actions), ['saveManuscriptDraft', 'exportManuscript', 'confirmManuscript']);
const saveValue = actions.saveManuscriptDraft.resultAdapters[0].messageTemplate.updateDataModel.value;
assert.deepEqual(saveValue.export, { artifactId: '', artifactRevision: 0, filename: '', mediaType: '', content: '' });
for (const field of ['savedTitle', 'savedMarkdown', 'savedArtifactId', 'savedArtifactRevision']) {
  assert.ok(actions.saveManuscriptDraft.resultAdapters[0].bindings.some(item => item.targetPath.endsWith(`/${field}`)), `save adapter misses ${field}`);
}
assert.ok(actions.exportManuscript.resultAdapters[0].bindings.some(item => item.source === 'ACTION_CONTEXT' && item.sourcePath === '/artifactId'));
assert.ok(actions.exportManuscript.resultAdapters[0].bindings.some(item => item.source === 'ACTION_CONTEXT' && item.sourcePath === '/artifactRevision'));
const confirmButton = manuscript.showTemplate.messageTemplates[1].updateComponents.components.find(item => item.id === 'confirm');
assert.equal(confirmButton.action.event.context.artifactId.path, '/savedArtifactId');
assert.equal(confirmButton.checks.length, 3);
const downloadAtom = customAtoms.find(item => item.componentCode === 'TextDownload');
assert.ok(downloadAtom);
assert.equal(Object.hasOwn(downloadAtom.propsSchema.properties, 'url'), false);
assert.deepEqual(downloadAtom.propsSchema.required, ['label', 'filename', 'mediaType', 'content']);
assert.deepEqual(
  Object.keys(downloadAtom.propsSchema.properties),
  ['label', 'filename', 'mediaType', 'content', 'checks', 'isValid', 'validationErrors'],
);
assert.deepEqual(confirmButton.checks[0].condition, {
  call: 'equals',
  args: { a: { path: '/draftTitle' }, b: { path: '/savedTitle' } },
  returnType: 'boolean',
});
assert.deepEqual(confirmButton.checks[2].condition, {
  call: 'required',
  args: { value: { path: '/savedArtifactId' } },
  returnType: 'boolean',
});

const html = await readFile(new URL('./import.html', import.meta.url), 'utf8');
assert.match(html, /创建并发布阅读创作示例到 PRT/);
assert.match(html, /type="submit"/);
assert.doesNotMatch(html, /<input[^>]+(?:name|id)="[^"]*(?:token|cookie|password)/i);
const browser = await readFile(new URL('./import.js', import.meta.url), 'utf8');
assert.match(browser, /form\.addEventListener\('submit'/);
assert.doesNotMatch(browser, /RELEASE_ONLINE|forcePublish|authorization/i);
console.log('PASS reading-content assets, stale-draft guards, inline export identity, and explicit browser trigger');
