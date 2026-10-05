// @ts-check
import {
  CATALOG_ID, CONTENT_SERVICE, buildApplication, capabilitySpecs, skillSpec, validateAssets,
} from './assets.mjs';

const requiredText = (value, name) => {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${name} is required`);
  return value.trim();
};
const list = value => Array.isArray(value) ? value : Array.isArray(value?.list) ? value.list : [];
const actionCodeOf = item => item?.draft?.basicInfo?.actionCode || item?.basicInfo?.actionCode || item?.actionCode;
const capabilityNameOf = item => item?.draft?.basicInfo?.nameCn || item?.basicInfo?.nameCn || item?.nameCn;
const appCodeOf = item => item?.appCode || item?.componentCode || item?.runtimeConfig?.appCode;

export function createRequestId() {
  if (!globalThis.crypto?.getRandomValues) throw new Error('secure random generator is unavailable');
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class ManagementClient {
  constructor({ origin, cookie, signal, onProgress = () => {} }) {
    this.origin = new URL(requiredText(origin, 'origin'));
    this.cookie = cookie || '';
    this.signal = signal;
    this.onProgress = onProgress;
  }

  async call(method, params = {}, allowFailure = false) {
    const headers = { 'Content-Type': 'application/json' };
    if (this.cookie) { headers.Origin = this.origin.origin; headers.Cookie = this.cookie; }
    const response = await fetch(new URL('/api/management/v2/handler', this.origin), {
      method: 'POST', credentials: this.cookie ? 'omit' : 'same-origin', redirect: 'error',
      signal: this.signal, headers,
      body: JSON.stringify({ method, params: Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)])) }),
    });
    const text = await response.text();
    if (response.status !== 200) throw new Error(`${method}: HTTP ${response.status}`);
    let frames;
    try {
      frames = text.startsWith('data:')
        ? text.split(/\r?\n/).filter(line => line.startsWith('data:') && !line.includes('[DONE]')).map(line => JSON.parse(line.slice(5).trim()))
        : [JSON.parse(text)];
    } catch {
      throw new Error(`${method}: invalid management response`);
    }
    const envelope = frames.findLast(frame => Object.hasOwn(frame, 'result'));
    if (!envelope) throw new Error(`${method}: missing result envelope`);
    const data = typeof envelope.data === 'string' && envelope.data !== '' ? JSON.parse(envelope.data) : envelope.data;
    if (envelope.result !== 1 && !allowFailure) throw new Error(`${method}: ${data?.errorCode || data?.code || 'MANAGEMENT_OPERATION_FAILED'}`);
    if (envelope.result === 1) this.onProgress(`完成 ${method}`);
    return { ok: envelope.result === 1, data, envelope };
  }
}

function capabilityDraft(spec, descriptorSetBase64, targetKey) {
  const responseDemo = Object.fromEntries(spec.outputs.map(([path, _description, type]) => [
    path, type === 'integer' ? 1 : type === 'array' ? [] : 'example',
  ]));
  return {
    payloadType: 'CAPABILITY_DRAFT_SNAPSHOT', mode: 'CREATE',
    basicInfo: { actionCode: spec.actionCode, nameCn: spec.nameCn, description: spec.description, technicalOwner: 'people-selection' },
    governance: { sideEffectLevel: spec.sideEffect }, supportedClients: ['PC'], clientVariants: { PC: {
      apiSource: { sourceType: 'GRPC' },
      modelContract: { description: spec.description, inputFields: spec.fields, inputExampleJson: JSON.stringify(spec.sample) },
      executionBinding: {
        bindingType: 'GRPC', target: { targetKey, serviceName: CONTENT_SERVICE, methodName: spec.methodName, descriptorSetBase64, contextField: 'context' },
        requestMappingsJson: JSON.stringify(spec.mappings), contextMappingsJson: '{}', timeoutMs: 30_000,
        maxResponseBytes: 1_048_576, idempotency: 'NONE', responsePolicy: 'ORIGINAL',
      },
      resultContract: {
        keyOutputFields: spec.outputs.map(([path, description, observedType]) => ({ path, description, observedType })),
        responseDemoJson: JSON.stringify(responseDemo),
      },
    } },
  };
}

async function ensureCapability(client, spec, options) {
  const matches = list((await client.call('CAPABILITY_LIST', { keyword: spec.actionCode })).data)
    .filter(item => actionCodeOf(item) === spec.actionCode);
  if (matches.length > 1) throw new Error(`${spec.actionCode}: duplicate capability drafts`);
  let draftId;
  if (matches.length) {
    draftId = requiredText(matches[0]?.draftId, `${spec.actionCode}.draftId`);
  } else {
    const byName = list((await client.call('CAPABILITY_LIST', { keyword: spec.nameCn })).data)
      .filter(item => capabilityNameOf(item) === spec.nameCn && !actionCodeOf(item));
    if (byName.length > 1) throw new Error(`${spec.actionCode}: multiple initial drafts`);
    draftId = byName.length
      ? requiredText(byName[0]?.draftId, `${spec.actionCode}.draftId`)
      : requiredText((await client.call('CAPABILITY_DRAFT_CREATE', { draftJson: JSON.stringify({ payloadType: 'CAPABILITY_DRAFT_SNAPSHOT', mode: 'CREATE', basicInfo: { nameCn: spec.nameCn } }) })).data?.draftId, `${spec.actionCode}.draftId`);
  }
  const detail = (await client.call('CAPABILITY_DRAFT_DETAIL', { draftId })).data;
  await client.call('CAPABILITY_DRAFT_SAVE', {
    draftId, baseRevision: detail.revision,
    draftJson: JSON.stringify(capabilityDraft(spec, options.descriptorSetBase64, options.targetKey)),
    businessDomain: 'general', capabilityDomain: 'general', specialistIds: options.specialistIds,
  });
  const validation = (await client.call('CAPABILITY_VALIDATE', { draftId })).data;
  if (validation?.valid !== true) throw new Error(`${spec.actionCode}: ${JSON.stringify(validation?.errors || validation)}`);
  const validated = (await client.call('CAPABILITY_DRAFT_DETAIL', { draftId })).data;
  const dryRun = (await client.call('CAPABILITY_DRY_RUN', { draftId, revision: validated.revision, environment: 'PRT', clientType: 'PC' })).data;
  if (dryRun?.toolResult?.success !== true) throw new Error(`${spec.actionCode}: dry-run failed (${dryRun?.toolResult?.errorCode || 'UNKNOWN'})`);
  return { draftId, detail: validated };
}

export async function publishPrt(client, assetType, assetKey, extra = {}) {
  const identity = { assetType, assetKey, ...extra };
  let overview = (await client.call('RELEASE_OVERVIEW', identity)).data;
  const digest = requiredText(overview?.currentSnapshot?.digest, `${assetType}/${assetKey}.digest`);
  if (overview?.environments?.PRT?.digest === digest) return overview;
  if (overview?.activeChange?.status === 'ACTIVE') {
    if (!overview.allowedActions?.includes('DEPLOY_PREPROD')) throw new Error(`${assetType}/${assetKey}: current change cannot publish to PRT`);
  } else {
    await client.call('RELEASE_CHANGE_CREATE', { ...identity, changeName: '人员选择 PRT 发布', requestId: createRequestId() });
  }
  const deployed = (await client.call('RELEASE_PREPROD_DEPLOY', { ...identity, expectedDigest: digest, requestId: createRequestId() })).data;
  if (deployed?.status !== 'SUCCEEDED') throw new Error(`${assetType}/${assetKey}: PRT deploy ${deployed?.status || 'UNKNOWN'}`);
  overview = (await client.call('RELEASE_OVERVIEW', identity)).data;
  if (!overview?.environments?.PRT?.sourceId) throw new Error(`${assetType}/${assetKey}: missing PRT pointer`);
  return overview;
}

async function requirePublishedCatalog(client) {
  const rows = list((await client.call('A2UI_CATALOG_LIST', { keyword: CATALOG_ID })).data);
  const matches = rows.filter(item => (item?.catalogId || item?.componentCode) === CATALOG_ID);
  if (matches.length !== 1) throw new Error(`${CATALOG_ID}: expected exactly one existing catalog`);
  const release = (await client.call('RELEASE_OVERVIEW', { assetType: 'A2UI_CATALOG', assetKey: CATALOG_ID })).data;
  if (!release?.environments?.PRT?.sourceId) throw new Error(`${CATALOG_ID}: PRT catalog is not published`);
}

async function ensureApplication(client) {
  const application = buildApplication();
  const matches = list((await client.call('A2UI_APPLICATION_LIST', { keyword: application.appCode })).data)
    .filter(item => appCodeOf(item) === application.appCode);
  if (matches.length > 1) throw new Error(`${application.appCode}: duplicate applications`);
  const saved = matches.length
    ? (await client.call('A2UI_APPLICATION_UPDATE', { id: matches[0].id, applicationJson: JSON.stringify(application) })).data
    : (await client.call('A2UI_APPLICATION_CREATE', { applicationJson: JSON.stringify(application) })).data;
  const id = requiredText(String(saved?.id || matches[0]?.id || ''), `${application.appCode}.id`);
  await client.call('A2UI_APPLICATION_DETAIL', { id });
  await publishPrt(client, 'A2UI_APPLICATION', application.appCode);
  return id;
}

async function ensureSkill(client, capabilityIds, applicationId, specialistIds) {
  let detail = await client.call('SKILL_DETAIL', { skillCode: skillSpec.skillCode }, true);
  const workspaceId = detail.ok
    ? detail.data?.workspaceId || skillSpec.skillCode
    : (await client.call('WORKSPACE_CREATE', {
      skillCode: skillSpec.skillCode, skillNameCn: skillSpec.nameCn,
      skillDescription: '分页选择虚构演示人员并显式回填聊天输入框。', specialistIds,
      businessDomain: 'general', capabilityDomain: 'general',
    })).data?.workspaceId || skillSpec.skillCode;
  await client.call('WORKSPACE_FILE_SAVE', { workspaceId, skillCode: skillSpec.skillCode, filePath: 'SKILL.md', content: skillSpec.markdown });
  detail = await client.call('SKILL_DETAIL', { skillCode: skillSpec.skillCode });
  await client.call('SKILL_BINDINGS_REPLACE', {
    workspaceId, skillCode: skillSpec.skillCode, version: detail.data.version,
    capabilityBindings: JSON.stringify(skillSpec.capabilities.map(actionCode => ({ draftId: capabilityIds.get(actionCode), bindMode: 'EXECUTION_ONLY' }))),
    componentBindings: JSON.stringify([{ assetId: applicationId, componentCode: skillSpec.applicationCode }]),
  });
  await publishPrt(client, 'SKILL', skillSpec.skillCode, { workspaceId });
  return workspaceId;
}

/** 独立发布 people_selection；不创建、更新或重发 reading_content 资产。 */
export async function runPrtAuthoring(client, options) {
  validateAssets();
  const descriptorSetBase64 = requiredText(options.descriptorSetBase64, 'descriptorSetBase64');
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(descriptorSetBase64)) throw new Error('descriptorSetBase64 must be base64 text');
  const normalized = {
    descriptorSetBase64, targetKey: requiredText(options.targetKey, 'targetKey'),
    specialistIds: requiredText(options.specialistIds, 'specialistIds'),
  };
  const capabilities = new Map();
  for (const spec of capabilitySpecs) {
    const current = await ensureCapability(client, spec, normalized);
    capabilities.set(spec.actionCode, current.draftId);
    await publishPrt(client, 'CAPABILITY', current.draftId);
  }
  await requirePublishedCatalog(client);
  const applicationId = await ensureApplication(client);
  const workspaceId = await ensureSkill(client, capabilities, applicationId, normalized.specialistIds);
  return { capabilityDraftIds: Object.fromEntries(capabilities), applicationId, workspaceId };
}
