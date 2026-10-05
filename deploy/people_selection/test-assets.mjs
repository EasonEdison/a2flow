import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { buildApplication, capabilitySpecs, skillSpec, validateAssets } from './assets.mjs';
import { createRequestId, publishCapabilityPrt, publishPrt } from './authoring-core.mjs';

assert.deepEqual(validateAssets(), { capabilities: 2, applications: 1, skills: 1 });
assert.deepEqual(capabilitySpecs.map(item => [item.actionCode, item.methodName]), [
  ['content.people.list', 'ListPeople'],
  ['content.people.resolve', 'ResolvePeople'],
]);
assert.deepEqual(capabilitySpecs[0].sample, { page: 1, pageSize: 5 });
assert.deepEqual(capabilitySpecs[1].sample, { personIds: ['demo-person-001', 'demo-person-002'] });
assert.equal(capabilitySpecs[0].outputs.find(([path]) => path === 'total')[2], 'string');
assert.match(capabilitySpecs[1].description, /保序去重.*未知 ID 整次失败/);

const application = buildApplication();
assert.equal(application.appCode, 'people-selector');
assert.equal(skillSpec.skillCode, 'people-selection');
assert.deepEqual(skillSpec.capabilities, ['content.people.list', 'content.people.resolve']);
assert.match(skillSpec.markdown, /不.*消息已发送/);
const components = application.showTemplate.messageTemplates[1].updateComponents.components;
const picker = components.find(item => item.id === 'people');
assert.equal(picker.variant, 'multipleSelection');
assert.equal(picker.displayStyle, 'checkbox');
assert.deepEqual(picker.options, []);
assert.deepEqual(picker.value, { path: '/selectedPersonIds' });
const load = application.loadBindings[0];
assert.deepEqual(load.requestMappings.map(item => item.constantValue), [1, 5]);
const optionsBinding = load.resultAdapters.find(item => item.adapterId === 'options').bindings[0];
assert.equal(optionsBinding.targetPath, '/updateComponents/components/0/options');
assert.deepEqual(load.resultAdapters.find(item => item.adapterId === 'options')
  .messageTemplate.updateComponents.components[0].value, { path: '/selectedPersonIds' });
assert.deepEqual(optionsBinding.transform, {
  type: 'ARRAY_OBJECT_TO_OPTIONS', valuePath: '/personId',
  labelColumns: [
    { label: '姓名', sourcePath: '/name' }, { label: '电话', sourcePath: '/phone' },
    { label: '性别', sourcePath: '/gender' }, { label: '年龄', sourcePath: '/age' },
    { label: '爱好', sourcePath: '/hobbies' },
  ],
  labelSeparator: '｜',
});

const projectOptions = (items, transform) => items.map(item => ({
  value: item[transform.valuePath.slice(1)],
  label: transform.labelColumns.map(column => {
    const value = item[column.sourcePath.slice(1)];
    return `${column.label}：${Array.isArray(value) ? value.join('、') : String(value)}`;
  }).join(transform.labelSeparator),
}));
assert.deepEqual(projectOptions([{
  personId: 'demo-person-001', name: '林晓', phone: '138****0001', gender: '女', age: 28,
  hobbies: ['阅读', '徒步'],
}], optionsBinding.transform), [{
  value: 'demo-person-001', label: '姓名：林晓｜电话：138****0001｜性别：女｜年龄：28｜爱好：阅读、徒步',
}]);

const pagination = (total, pageNum, pageSize = 5) => {
  const count = Number(total);
  const totalPages = count === 0 ? 0 : Math.ceil(count / pageSize);
  return {
    totalPages,
    prevDisabled: pageNum <= 1,
    nextDisabled: totalPages === 0 || pageNum >= totalPages,
  };
};
assert.deepEqual(pagination('0', 1), { totalPages: 0, prevDisabled: true, nextDisabled: true });
assert.deepEqual(pagination('12', 1), { totalPages: 3, prevDisabled: true, nextDisabled: false });
assert.deepEqual(pagination('12', 3), { totalPages: 3, prevDisabled: false, nextDisabled: true });

const actions = Object.fromEntries(application.actionBindings.map(item => [item.actionCode, item]));
for (const actionCode of ['previousPage', 'nextPage']) {
  assert.equal(actions[actionCode].capability.actionCode, 'content.people.list');
  assert.ok(actions[actionCode].resultAdapters.some(adapter =>
    adapter.bindings?.some(binding => binding.source === 'ACTION_CONTEXT' && binding.sourcePath === '/selectedPersonIds')),
  `${actionCode} must echo the complete cross-page selection`);
}
assert.equal(actions.fillComposer.capability.actionCode, 'content.people.resolve');
assert.deepEqual(actions.fillComposer.contextSchema.properties.selectedPersonIds, {
  type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 15, uniqueItems: true,
});
assert.ok(actions.fillComposer.resultAdapters.some(adapter =>
  adapter.bindings?.some(binding => binding.source === 'ACTION_CONTEXT' && binding.sourcePath === '/selectedPersonIds')),
'fillComposer must echo the final selection before response-triggered rebuild');
assert.deepEqual(actions.fillComposer.composerDraftEffect, {
  type: 'COMPOSER_DRAFT', mode: 'APPEND', source: 'CAPABILITY_DATA', itemsPath: '/items',
  columns: [{ label: '姓名', sourcePath: '/name' }, { label: '电话', sourcePath: '/phone' }],
});
assert.ok(components.find(item => item.id === 'fillComposer').checks.length, 'empty selection must disable fill');
assert.ok(components.find(item => item.id === 'previous').checks.length, 'first page must disable previous');
assert.ok(components.find(item => item.id === 'next').checks.length, 'last page must disable next');

let published = false;
await publishPrt({ call: async method => {
  if (method === 'RELEASE_OVERVIEW') return { data: {
    currentSnapshot: { digest: 'people-digest' }, activeChange: { status: 'ACTIVE' },
    allowedActions: ['DEPLOY_PREPROD'], environments: { PRT: published ? { digest: 'people-digest', sourceId: 'build-1' } : {} },
  } };
  assert.equal(method, 'RELEASE_PREPROD_DEPLOY'); published = true; return { data: { status: 'SUCCEEDED' } };
} }, 'A2UI_APPLICATION', 'people-selector');

const capabilityReleaseCalls = [];
await publishCapabilityPrt({ call: async (method, params) => {
  capabilityReleaseCalls.push([method, params]);
  return { data: {
    currentSnapshot: { digest: 'capability-digest' },
    environments: { PRT: { digest: 'capability-digest', sourceId: 'capability-build-1' } },
  } };
} }, 'capability-draft-1');
assert.deepEqual(capabilityReleaseCalls, [[
  'RELEASE_OVERVIEW',
  { assetType: 'CAPABILITY_ACTION', assetKey: 'capability-draft-1' },
]]);

const descriptorText = (await readFile(new URL('./content-descriptor.txt', import.meta.url), 'utf8')).trim();
assert.match(descriptorText, /^[A-Za-z0-9+/]+={0,2}$/);
const descriptor = Buffer.from(descriptorText, 'base64');
for (const method of ['ListPeople', 'ResolvePeople']) assert.ok(descriptor.includes(Buffer.from(method)), `descriptor misses ${method}`);
const authoring = await readFile(new URL('./authoring-core.mjs', import.meta.url), 'utf8');
assert.doesNotMatch(authoring, /reading-point-selector|content-topic-selector|content-manuscript-editor/);
assert.doesNotMatch(authoring, /A2UI_CATALOG_(CREATE|UPDATE)|RELEASE_ONLINE|forcePublish/);
assert.match(authoring,
  /CAPABILITY_VALIDATE[\s\S]+CAPABILITY_DRAFT_DETAIL[\s\S]+CAPABILITY_DRY_RUN[\s\S]+revision: validated\.revision/,
  'dry-run must use the authoritative revision read after validation');
const html = await readFile(new URL('./import.html', import.meta.url), 'utf8');
assert.match(html, /创建并发布人员选择示例到 PRT/);
assert.doesNotMatch(html, /token|cookie|password/i);
const requestIds = new Set(Array.from({ length: 16 }, createRequestId));
assert.equal(requestIds.size, 16);
console.log('PASS people-selection capability, pagination, projection, composer and isolated PRT authoring contracts');
