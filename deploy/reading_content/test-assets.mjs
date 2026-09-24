import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequestId } from './authoring-core.mjs';
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
assert.match(html, /<button id="load-project-descriptor" type="button">加载本项目 Content RPC 契约<\/button>/);
assert.match(html, /<textarea id="descriptor-text"/);
assert.match(html, /<input id="descriptor-file" type="file" accept="text\/plain,\.txt">/);
assert.match(html, /<input id="target-key" value="content"/);
assert.match(html, /<input id="sync-official-basic" type="checkbox" checked>/);
assert.doesNotMatch(html, /<input[^>]+(?:name|id)="[^"]*(?:token|cookie|password)/i);
const browser = await readFile(new URL('./import.js', import.meta.url), 'utf8');
assert.match(browser, /form\.addEventListener\('submit'/);
assert.match(browser, /loadDescriptorButton\.addEventListener\('click'/);
assert.match(browser, /fetch\(new URL\('\.\/content-descriptor\.txt', import\.meta\.url\)/);
assert.match(browser, /validateDescriptorBase64\(await response\.text\(\)\)/);
assert.match(browser, /client\.call\('A2UI_CATALOG_OFFICIAL_IMPORT'\)/);
assert.match(browser, /catalogSourceType !== 'A2UI_OFFICIAL'/);
assert.match(browser, /digital-employee-functions\.json/);
assert.match(browser, /functionContract\?\.functions\?\.equals/);
assert.match(browser, /descriptorText \|\| \(descriptorFile \?/);
assert.match(browser, /if \(!descriptorText && !descriptorFile\)/);
assert.doesNotMatch(browser, /RELEASE_ONLINE|forcePublish|authorization/i);

const descriptorText = (await readFile(new URL('./content-descriptor.txt', import.meta.url), 'utf8')).trim();
assert.match(descriptorText, /^[A-Za-z0-9+/]+={0,2}$/);
assert.equal(descriptorText.length % 4, 0);
const descriptorBinary = Buffer.from(descriptorText, 'base64');
assert.ok(descriptorBinary.length > 0);
for (const method of ['CreateProject', 'ListProjects', 'GetProject', 'SaveSource', 'GetSource', 'SaveArtifact', 'GetArtifact', 'GetConfirmation', 'ConfirmReading', 'ConfirmTopic', 'ConfirmManuscript', 'ExportManuscript']) {
  assert.ok(descriptorBinary.includes(Buffer.from(method)), `content descriptor misses ${method}`);
}

const deployedFunctions = JSON.parse(await readFile(
  new URL('./digital-employee-functions.json', import.meta.url), 'utf8'));
const rendererFunctions = JSON.parse(await readFile(
  new URL('../../apps/digital-employee/web/src/catalogs/digital-employee-functions.json', import.meta.url), 'utf8'));
assert.deepEqual(deployedFunctions, rendererFunctions, 'authoring function contract must exactly match B renderer');
assert.equal(Object.keys(deployedFunctions.functions).length, 15);
assert.equal(deployedFunctions.functions.equals.properties.call.const, 'equals');

const requestIds = new Set(Array.from({ length: 32 }, createRequestId));
assert.equal(requestIds.size, 32);
for (const requestId of requestIds) assert.match(requestId, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
const authoringCore = await readFile(new URL('./authoring-core.mjs', import.meta.url), 'utf8');
assert.match(authoringCore, /clientType: 'PC'/);
assert.match(authoringCore, /getRandomValues/);
assert.doesNotMatch(authoringCore, /randomUUID|Math\.random/);
assert.match(authoringCore, /businessDomain: 'general', capabilityDomain: 'general'/);
assert.match(authoringCore, /initialDrafts\.length > 1/);
assert.match(authoringCore, /!actionCodeOf\(item\)/);
console.log('PASS reading-content assets, stale-draft guards, inline export identity, and explicit browser trigger');
