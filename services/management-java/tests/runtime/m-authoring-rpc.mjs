// Real management HTTP authoring on a FRESH disposable local database only.
// Requires M_ORIGIN, M_SESSION_COOKIE, RPC_DESCRIPTOR_FILE (base64 text), B_WEB_DIR,
// RPC_TARGET_KEY, RPC_SERVICE_NAME, RPC_METHOD_NAME, OUTPUT_FILE, and M_FRESH_TEST_DB=1.
// M_REUSE_PUBLISHED_CATALOG=1 permits another isolated fixture run against this same
// disposable database; its published catalog schemas are compared before reuse.
// No SQL, release-state injection, credential output, or automatic publication retry.
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const env = name => { assert.ok(process.env[name], `${name} is required`); return process.env[name]; };
const requireWeb = createRequire(resolve(env('B_WEB_DIR'), 'package.json'));
const { basicCatalog } = await import(pathToFileURL(requireWeb.resolve('@a2ui/react/v0_9')));
const { zodToJsonSchema } = await import(pathToFileURL(requireWeb.resolve('zod-to-json-schema')));
const catalogId = 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';
assert.equal(basicCatalog.id, catalogId);
assert.equal(basicCatalog.components.size, 18);
const types = [...basicCatalog.components.keys()];
function sample(schema, depth = 0) {
  assert.ok(depth < 30, 'schema example recursion limit');
  if ('const' in schema) return schema.const;
  if (schema.enum) return schema.enum[0];
  if ('default' in schema) return schema.default;
  if (schema.anyOf || schema.oneOf) return sample((schema.anyOf || schema.oneOf)[0], depth + 1);
  if (schema.type === 'object') return Object.fromEntries((schema.required || []).map(key => [key, sample(schema.properties[key], depth + 1)]));
  if (schema.type === 'array') return Array.from({ length: schema.minItems || 0 }, () => sample(schema.items, depth + 1));
  if (schema.type === 'boolean') return false;
  if (schema.type === 'number' || schema.type === 'integer') return schema.minimum || 0;
  if (schema.type === 'null') return null;
  return 'example';
}
const atoms = [...basicCatalog.components.values()].map(component => {
  const propsSchema = zodToJsonSchema(component.schema, { $refStrategy: 'none' });
  const props = component.schema.parse(sample(propsSchema));
  const eventProperties = Object.fromEntries(Object.entries(propsSchema.properties).filter(([key]) => key === 'action' || key.endsWith('Action')));
  return { componentCode: component.name, type: component.name, nameCn: `基础组件 ${component.name}`,
    category: 'basic', compositionKind: 'ATOMIC', propsSchema,
    eventSchema: { type: 'object', properties: eventProperties, additionalProperties: false },
    // Official child/reference constraints are preserved in propsSchema; no invented extra limits.
    childrenConstraint: {},
    validMessageExample: { id: 'example', component: component.name, ...props },
    invalidMessageExample: { id: 'invalid', component: component.name, unsupportedProperty: true } };
});
if (process.argv.includes('--check-fixture')) {
  console.log(`PASS ${atoms.length} official renderer schemas and examples; no HTTP requests made`);
  process.exit(0);
}
assert.equal(env('M_FRESH_TEST_DB'), '1', 'launcher must provision a new disposable database');
const origin = env('M_ORIGIN');
const url = new URL(origin);
assert.equal(url.protocol, 'http:');
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname), 'only loopback hosts permitted');
const cookie = env('M_SESSION_COOKIE');
assert.match(cookie, /^a2flow_management_session=[A-Za-z0-9_-]+$/);
const descriptorSetBase64 = (await readFile(env('RPC_DESCRIPTOR_FILE'), 'utf8')).trim();
assert.match(descriptorSetBase64, /^[A-Za-z0-9+/]+={0,2}$/);
const run = randomUUID().replaceAll('-', '').slice(0, 12);
const actionCode = `integration.activity.confirm${run}`;
const appCode = `integration_activity_${run}`;
const skillCode = `integration-activity-${run}`;
const surfaceId = 'activity';
const componentId = 'confirm';
const actionName = 'confirmActivity';
const quantity = '2'; // ProtoJSON int64: never a JS number.
async function call(method, params = {}) {
  const response = await fetch(`${origin}/api/management/v2/handler`, {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(120_000),
    headers: { 'Content-Type': 'application/json', Origin: origin, Cookie: cookie },
    body: JSON.stringify({ method, params: Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)])) }),
  });
  const text = await response.text();
  assert.equal(response.status, 200, `${method}: HTTP ${response.status}: ${text}`);
  const frames = text.startsWith('data:') ? text.split(/\r?\n/).filter(line => line.startsWith('data:') && !line.includes('[DONE]')).map(line => JSON.parse(line.slice(5).trim())) : [JSON.parse(text)];
  const envelope = frames.findLast(frame => Object.hasOwn(frame, 'result'));
  assert.ok(envelope, `${method}: missing result envelope`);
  assert.equal(envelope.result, 1, `${method}: ${JSON.stringify(envelope)}`);
  const data = typeof envelope.data === 'string' ? JSON.parse(envelope.data) : envelope.data;
  console.log(`PASS HTTP ${method}`);
  return data;
}
async function publish(assetType, assetKey, extra = {}) {
  const identity = { assetType, assetKey, ...extra };
  await call('RELEASE_CHANGE_CREATE', { ...identity, changeName: '真实 HTTP 合成验收', requestId: randomUUID() });
  const overview = await call('RELEASE_OVERVIEW', identity);
  assert.ok(overview.currentSnapshot?.digest, `${assetType}: missing current digest`);
  const result = await call('RELEASE_PREPROD_DEPLOY', { ...identity, expectedDigest: overview.currentSnapshot.digest, requestId: randomUUID() });
  assert.equal(result.status, 'SUCCEEDED', `${assetType}: ${JSON.stringify(result)}`);
  const published = await call('RELEASE_OVERVIEW', identity);
  assert.ok(published.environments?.PRT?.sourceId, `${assetType}: missing real PRT pointer`);
  return published;
}

const registered = await call('CAPABILITY_DRAFT_CREATE', { draftJson: JSON.stringify({ payloadType: 'CAPABILITY_DRAFT_SNAPSHOT', mode: 'CREATE', basicInfo: { nameCn: '确认合成活动' } }) });
const draft = { payloadType: 'CAPABILITY_DRAFT_SNAPSHOT', mode: 'CREATE',
  basicInfo: { actionCode, nameCn: '确认合成活动', description: '根据用户手填数量确认隔离测试活动', technicalOwner: 'integration-test' },
  governance: { sideEffectLevel: 'READ' }, supportedClients: ['COMMON'], clientVariants: { COMMON: {
    apiSource: { sourceType: 'GRPC' },
    modelContract: { description: '用户填写需要确认的活动数量', inputFields: [{ toolField: 'quantity', type: 'string', source: 'MODEL_INPUT', businessMeaning: '活动数量（int64 十进制字符串）', required: true, examples: quantity }], inputExampleJson: JSON.stringify({ quantity }) },
    executionBinding: { bindingType: 'GRPC', target: { targetKey: env('RPC_TARGET_KEY'), serviceName: env('RPC_SERVICE_NAME'), methodName: env('RPC_METHOD_NAME'), descriptorSetBase64, contextField: 'context' }, requestMappingsJson: '{"quantity":"quantity"}', contextMappingsJson: '{}', timeoutMs: 3000, maxResponseBytes: 5242880, idempotency: 'NONE', responsePolicy: 'ORIGINAL' },
    resultContract: { keyOutputFields: [{ path: 'quantity', description: '确认数量', observedType: 'string' }, { path: 'message', description: '确认结果', observedType: 'string' }], responseDemoJson: JSON.stringify({ quantity, message: 'confirmed' }) },
  } } };
const saved = await call('CAPABILITY_DRAFT_SAVE', { draftId: registered.draftId, baseRevision: registered.revision, draftJson: JSON.stringify(draft), businessDomain: 'integration', capabilityDomain: 'activity', specialistIds: process.env.M_SPECIALIST_IDS || '101' });
const reread = await call('CAPABILITY_DRAFT_DETAIL', { draftId: registered.draftId });
assert.equal(reread.draft.clientVariants.COMMON.executionBinding.target.serviceName, env('RPC_SERVICE_NAME'));
const validation = await call('CAPABILITY_VALIDATE', { draftId: registered.draftId });
assert.equal(validation.valid, true, JSON.stringify(validation));
const validatedDraft = await call('CAPABILITY_DRAFT_DETAIL', { draftId: registered.draftId });
const dryRun = await call('CAPABILITY_DRY_RUN', { draftId: registered.draftId, revision: validatedDraft.revision, environment: 'PRT', clientType: 'COMMON' });
assert.equal(dryRun.toolResult?.success, true, JSON.stringify(dryRun));
await publish('CAPABILITY_ACTION', registered.draftId);
if (process.env.M_REUSE_PUBLISHED_CATALOG === '1') {
  const existing = await call('RELEASE_OVERVIEW', { assetType: 'A2UI_CATALOG', assetKey: catalogId });
  assert.ok(existing.environments?.PRT?.sourceId, 'catalog reuse requires a published PRT pointer');
  assert.equal(existing.environments.PRT.digest, existing.currentSnapshot.digest, 'catalog source changed after publication');
  const snapshot = JSON.parse(existing.currentSnapshot.payloadJson);
  assert.equal(snapshot.components.length, atoms.length);
  for (const atom of atoms) assert.deepEqual(snapshot.components.find(item => item.type === atom.type)?.contract.propsSchema, atom.propsSchema, `${atom.type}: published schema differs from renderer`);
} else {
  for (const atom of atoms) await call('A2UI_CATALOG_COMPONENT_CREATE', { componentJson: JSON.stringify(atom) });
  await call('A2UI_CATALOG_CREATE', { catalogJson: JSON.stringify({ catalogId, nameCn: '开源基础组件集', protocolVersion: 'v0.9.1', componentCodes: types }) });
  await publish('A2UI_CATALOG', catalogId);
}
const contextSchema = { type: 'object', properties: { quantity: { type: 'string' } }, required: ['quantity'], additionalProperties: false };
const application = { appCode, nameCn: '活动选择与确认', description: '隔离测试的真实注册与发布流程', interactionMode: 'INTERACTIVE', catalogId,
  showTemplate: { templateCode: `${appCode}_show`, paramsSchema: contextSchema, surfaceDeclarations: [{ surfaceId, rootComponentId: 'root' }], messageTemplates: [
    { version: 'v0.9.1', createSurface: { surfaceId, catalogId } },
    { version: 'v0.9.1', updateComponents: { surfaceId, components: [
      { id: 'root', component: 'Column', children: ['title', 'quantity', 'result', componentId] },
      { id: 'title', component: 'Text', text: '请选择活动数量并确认' },
      { id: 'quantity', component: 'TextField', label: '活动数量', value: { path: '/quantity' }, variant: 'shortText' },
      { id: 'result', component: 'Text', text: { path: '/message' } },
      { id: componentId, component: 'Button', child: 'confirmText', action: { event: { name: actionName, context: { quantity: { path: '/quantity' } } } } },
      { id: 'confirmText', component: 'Text', text: '确认活动' },
    ] } },
    { version: 'v0.9.1', updateDataModel: { surfaceId, path: '/', value: { quantity, message: '等待用户确认' } } },
  ], inputBindings: [{ targetMessageIndex: 2, targetPath: '/updateDataModel/value/quantity', source: 'APP_PARAMS', sourcePath: '/quantity', required: true }] },
  loadBindings: [{ bindingId: 'load_activity', capability: { actionCode },
    requestMappings: [{ source: 'APP_PARAMS', sourcePath: '/quantity', targetPath: '/quantity' }],
    successOutcome: 'ADAPTER_PIPELINE', failureOutcome: 'NO_UI_MESSAGES',
    resultAdapters: [{ adapterId: 'load_result', order: 1, type: 'MESSAGE_TEMPLATE', messageTemplate: { version: 'v0.9.1', updateDataModel: { surfaceId, path: '/message', value: '' } }, bindings: [{ targetPath: '/updateDataModel/value', source: 'CAPABILITY_DATA', sourcePath: '/message', required: true }] }], failureResultAdapters: [],
  }], actionBindings: [{ bindingId: 'confirm_activity', surfaceId, sourceComponentId: componentId, actionCode: actionName, allowedSourceComponentIds: [componentId], contextSchema,
    capability: { actionCode }, requestMappings: [{ source: 'ACTION_CONTEXT', sourcePath: '/quantity', targetPath: '/quantity' }],
    successOutcome: 'ADAPTER_PIPELINE', failureOutcome: 'NO_UI_MESSAGES', completeWorkflowInteractionOnSuccess: true,
    businessSuccessPredicate: { version: 'JSON_POINTER_V1', allOf: [{ source: 'CAPABILITY_DATA', sourcePath: '/message', operator: 'EQUALS', expectedValue: 'RPC操作成功' }] },
    resultAdapters: [{ adapterId: 'show_result', order: 1, type: 'MESSAGE_TEMPLATE', messageTemplate: { version: 'v0.9.1', updateDataModel: { surfaceId, path: '/message', value: '' } }, bindings: [{ targetPath: '/updateDataModel/value', source: 'CAPABILITY_DATA', sourcePath: '/message', required: true }] }], failureResultAdapters: [] }],
};
const app = await call('A2UI_APPLICATION_CREATE', { applicationJson: JSON.stringify(application) });
assert.ok(app.id, 'application create must return registry identity');
await call('A2UI_APPLICATION_UPDATE', { id: app.id, applicationJson: JSON.stringify(application) });
const loadedApp = await call('A2UI_APPLICATION_DETAIL', { id: app.id });
assert.deepEqual(loadedApp.loadBindings, application.loadBindings, 'LoadBinding must survive real M save/read');
await publish('A2UI_APPLICATION', appCode);
const workspace = await call('WORKSPACE_CREATE', { skillCode, skillNameCn: `活动确认助手 ${run}`, skillDescription: '先展示活动输入卡，等待用户确认后调用已发布的业务能力。', specialistIds: process.env.M_SPECIALIST_IDS || '101', businessDomain: 'integration', capabilityDomain: 'activity' });
const workspaceId = workspace.workspaceId || skillCode;
await call('WORKSPACE_FILE_SAVE', { workspaceId, skillCode, filePath: 'SKILL.md', content: `---\nname: ${skillCode}\ndescription: 活动数量选择与用户确认\n---\n\n# 活动确认\n使用 ${appCode} 展示数量输入卡。由用户确认后调用 ${actionCode}，展示业务真实返回，不得编造成功。\n` });
await call('WORKSPACE_TREE', { workspaceId });
const skill = await call('SKILL_DETAIL', { skillCode });
assert.ok(skill.version, 'skill detail must expose the current draft version');
await call('SKILL_BINDINGS_REPLACE', { workspaceId, skillCode, version: skill.version, capabilityBindings: JSON.stringify([{ draftId: registered.draftId, bindMode: 'EXECUTION_ONLY' }]), componentBindings: JSON.stringify([{ assetId: app.id, componentCode: appCode }]) });
await publish('SKILL', skillCode, { workspaceId });
await writeFile(env('OUTPUT_FILE'), JSON.stringify({ skillKey: skillCode, applicationKey: appCode, abilityKey: actionCode, capabilityDraftId: registered.draftId, actionName, surfaceId, componentId, params: { quantity }, abilityArguments: { quantity }, actionContext: { quantity }, expectedBusinessData: { quantity, message: 'RPC操作成功' }, loadBindingId: 'load_activity', catalogId }, null, 2), { mode: 0o600, flag: 'wx' });
console.log('PASS real M HTTP authoring and PRT publication; runtime action execution is a separate check');
