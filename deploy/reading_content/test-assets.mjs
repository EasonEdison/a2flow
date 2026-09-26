import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequestId, placeholderSample, sampleFactory } from './authoring-core.mjs';
import { buildApplications, capabilitySpecs, customAtoms, skillSpecs, validateAssets } from './assets.mjs';

assert.equal(validateAssets().capabilities, 12);
const known = new Set(capabilitySpecs.map(item => item.actionCode));
for (const skill of skillSpecs) for (const actionCode of skill.capabilities) assert.ok(known.has(actionCode), `${skill.skillCode}: ${actionCode}`);

const contract = [
  ['content.project.create', 'CreateProject', { title: 'title', audience: 'audience', outputFormat: 'outputFormat' }, ['id', 'revision']],
  ['content.project.list', 'ListProjects', { page: 'page', pageSize: 'pageSize' }, ['list', 'total']],
  ['content.project.get', 'GetProject', { projectId: 'projectId' }, ['id', 'revision']],
  ['content.source.save', 'SaveSource', { projectId: 'projectId', title: 'title', body: 'body', sourceUrl: 'sourceUrl', expectedProjectRevision: 'expectedProjectRevision' }, ['id', 'revision', 'digest']],
  ['content.source.get', 'GetSource', { sourceId: 'sourceId' }, ['id', 'body', 'revision']],
  ['content.artifact.save', 'SaveArtifact', {
    projectId: 'projectId', kind: 'kind', readingPoints: 'body.readingBrief.points', questions: 'body.readingBrief.questions',
    usableMaterials: 'body.readingBrief.usableMaterials', topics: 'body.topicPlan.topics', manuscriptTitle: 'body.manuscript.title',
    manuscriptMarkdown: 'body.manuscript.bodyMarkdown', citations: 'body.manuscript.citations', inputRefs: 'inputRefs', origin: 'origin',
  }, ['id', 'kind', 'revision', 'body', 'bodyMarkdown']],
  ['content.artifact.get', 'GetArtifact', { artifactId: 'artifactId' }, ['id', 'kind', 'revision', 'body']],
  ['content.confirmation.get', 'GetConfirmation', { confirmationId: 'confirmationId' }, ['id', 'decisionType', 'artifactId']],
  ['content.reading.confirm', 'ConfirmReading', { projectId: 'projectId', artifactId: 'artifactId', selectedPointIds: 'selectedPointIds', userNotes: 'userNotes', expectedProjectRevision: 'expectedProjectRevision' }, ['id', 'decisionType', 'selectedPointIds']],
  ['content.topic.confirm', 'ConfirmTopic', { projectId: 'projectId', artifactId: 'artifactId', topicId: 'topicId', editedTitle: 'editedTitle', editedAngle: 'editedAngle', expectedProjectRevision: 'expectedProjectRevision' }, ['id', 'decisionType', 'topicId']],
  ['content.manuscript.confirm', 'ConfirmManuscript', { projectId: 'projectId', artifactId: 'artifactId', expectedProjectRevision: 'expectedProjectRevision' }, ['id', 'decisionType', 'artifactId']],
  ['content.manuscript.export', 'ExportManuscript', { artifactId: 'artifactId', format: 'format' }, ['filename', 'mediaType', 'content']],
];
assert.deepEqual(
  capabilitySpecs.map(spec => [spec.actionCode, spec.methodName, spec.mappings, spec.outputs.map(([path]) => path)]),
  contract,
  '12 capability specs must match content.proto ProtoJSON request and response paths',
);
const createSpec = capabilitySpecs.find(spec => spec.actionCode === 'content.project.create');
assert.deepEqual(createSpec.fields.find(item => item.toolField === 'outputFormat').allowedValues.map(item => item.value), ['ARTICLE', 'SPOKEN_SCRIPT']);
const saveArtifactSpec = capabilitySpecs.find(spec => spec.actionCode === 'content.artifact.save');
assert.deepEqual(saveArtifactSpec.fields.find(item => item.toolField === 'kind').allowedValues.map(item => item.value), ['READING_BRIEF', 'TOPIC_PLAN', 'MANUSCRIPT']);
const exportSpec = capabilitySpecs.find(spec => spec.actionCode === 'content.manuscript.export');
assert.deepEqual(exportSpec.fields.find(item => item.toolField === 'format').allowedValues.map(item => item.value), ['MARKDOWN', 'TXT']);

const id = suffix => `00000000-0000-4000-8000-${suffix.padStart(12, '0')}`;
const sampleState = {
  project: { id: id('1') }, source: { id: id('2'), revision: 1 }, reading: { id: id('3'), revision: 1 },
  readingConfirmation: { id: id('4') }, topic: { id: id('5'), revision: 1 }, manuscript: { id: id('6'), revision: 1 },
};
const samples = sampleFactory(sampleState);
assert.equal(samples.create.outputFormat, 'ARTICLE');
assert.equal(placeholderSample(createSpec).outputFormat, 'ARTICLE');
const sampleCases = [
  ['content.project.create', samples.create], ['content.project.list', samples.list],
  ['content.project.get', samples.project()], ['content.source.save', samples.sourceSave()],
  ['content.source.get', samples.sourceGet()], ['content.artifact.save', samples.readingArtifact()],
  ['content.reading.confirm', samples.readingConfirm()], ['content.artifact.save', samples.topicArtifact()],
  ['content.topic.confirm', samples.topicConfirm()], ['content.artifact.save', samples.manuscriptArtifact()],
  ['content.manuscript.confirm', samples.manuscriptConfirm()], ['content.artifact.get', samples.artifactGet()],
  ['content.confirmation.get', samples.confirmationGet()], ['content.manuscript.export', samples.export()],
];
for (const [actionCode, sample] of sampleCases) {
  const spec = capabilitySpecs.find(item => item.actionCode === actionCode);
  const fields = new Map(spec.fields.map(item => [item.toolField, item]));
  assert.deepEqual(Object.keys(sample).filter(key => !fields.has(key)), [], `${actionCode}: sample has undeclared fields`);
  assert.deepEqual(spec.fields.filter(item => item.required && !Object.hasOwn(sample, item.toolField)).map(item => item.toolField), [], `${actionCode}: sample misses required fields`);
}
const put = (target, path, value) => {
  const parts = path.split('.');
  let cursor = target;
  for (const part of parts.slice(0, -1)) cursor = cursor[part] ||= {};
  cursor[parts.at(-1)] = value;
};
const mapped = sample => {
  const request = {};
  for (const [field, path] of Object.entries(saveArtifactSpec.mappings)) if (Object.hasOwn(sample, field)) put(request, path, sample[field]);
  return request;
};
assert.deepEqual(Object.keys(mapped(placeholderSample(saveArtifactSpec)).body), ['readingBrief']);
const readingRequest = mapped(samples.readingArtifact());
const topicRequest = mapped(samples.topicArtifact());
const manuscriptRequest = mapped(samples.manuscriptArtifact());
assert.deepEqual(Object.keys(readingRequest.body), ['readingBrief']);
assert.deepEqual(Object.keys(topicRequest.body), ['topicPlan']);
assert.deepEqual(Object.keys(manuscriptRequest.body), ['manuscript']);
assert.deepEqual(readingRequest.inputRefs.map(item => item.kind), ['SOURCE']);
assert.deepEqual(topicRequest.inputRefs.map(item => item.kind), ['ARTIFACT']);
assert.deepEqual(manuscriptRequest.inputRefs.map(item => item.kind), ['SOURCE', 'ARTIFACT']);
assert.equal(manuscriptRequest.body.manuscript.bodyMarkdown, '# 注意力不是意志力\n\n主动安排休息。');
assert.equal(samples.export().format, 'MARKDOWN');
assert.match(skillSpecs[0].markdown, /ARTICLE.*SPOKEN_SCRIPT.*不能填写 Markdown/s);
assert.match(skillSpecs[0].markdown, /body\.readingBrief\.points/);
assert.match(skillSpecs[1].markdown, /body\.topicPlan\.topics/);
assert.match(skillSpecs[2].markdown, /body\.manuscript\.title.*body\.manuscript\.bodyMarkdown/s);

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
assert.match(authoringCore, /supportedClients: \['PC'\], clientVariants: \{ PC:/);
assert.doesNotMatch(authoringCore, /supportedClients: \['COMMON'\]|clientVariants: \{ COMMON:/);
assert.match(authoringCore, /client\.call\('CAPABILITY_DRY_RUN', \{[^\n]+clientType: 'PC'/);
assert.match(authoringCore, /getRandomValues/);
assert.doesNotMatch(authoringCore, /randomUUID|Math\.random/);
assert.match(authoringCore, /businessDomain: 'general', capabilityDomain: 'general'/);
assert.match(authoringCore, /initialDrafts\.length > 1/);
assert.match(authoringCore, /!actionCodeOf\(item\)/);
console.log('PASS reading-content assets, stale-draft guards, inline export identity, and explicit browser trigger');
