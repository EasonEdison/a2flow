// @ts-check
import {
  CATALOG_ID, CONTENT_SERVICE, PROTOCOL_VERSION, buildApplications, buildWorkflow,
  capabilitySpecs, customAtoms, skillSpecs, validateAssets,
} from './assets.mjs';

const BASIC_COMPONENTS = ['Text', 'Row', 'Column', 'List', 'Card', 'Button', 'TextField', 'ChoicePicker'];
const UUID_ZERO = '00000000-0000-0000-0000-000000000000';

const requiredText = (value, name) => {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${name} is required`);
  return value.trim();
};
const list = value => Array.isArray(value) ? value : Array.isArray(value?.list) ? value.list : [];
const actionCodeOf = item => item?.draft?.basicInfo?.actionCode || item?.basicInfo?.actionCode || item?.actionCode;
const capabilityNameOf = item => item?.draft?.basicInfo?.nameCn || item?.basicInfo?.nameCn || item?.nameCn;
const appCodeOf = item => item?.appCode || item?.componentCode || item?.componentName || item?.runtimeConfig?.appCode;
const componentCodeOf = item => item?.componentCode || item?.type || item?.componentName;
const catalogIdOf = item => item?.catalogId || item?.componentCode || item?.componentName;

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
      method: 'POST', credentials: this.cookie ? 'omit' : 'same-origin', redirect: 'error', signal: this.signal,
      headers, body: JSON.stringify({ method, params: Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)])) }),
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
    if (envelope.result !== 1 && !allowFailure) {
      const code = data?.errorCode || data?.code || 'MANAGEMENT_OPERATION_FAILED';
      throw new Error(`${method}: ${code}`);
    }
    if (envelope.result === 1) this.onProgress(`完成 ${method}`);
    return { ok: envelope.result === 1, data, envelope };
  }
}

function capabilityDraft(spec, descriptorSetBase64, targetKey, sample) {
  const responseDemo = Object.fromEntries(spec.outputs.map(([path, _description, observedType]) => [
    path, observedType === 'integer' || observedType === 'number' ? 1
      : observedType === 'array' ? [] : observedType === 'object' ? {} : 'example',
  ]));
  return {
    payloadType: 'CAPABILITY_DRAFT_SNAPSHOT', mode: 'CREATE',
    basicInfo: { actionCode: spec.actionCode, nameCn: spec.nameCn, description: spec.description, technicalOwner: 'reading-content' },
    governance: { sideEffectLevel: spec.sideEffect }, supportedClients: ['COMMON'], clientVariants: { COMMON: {
      apiSource: { sourceType: 'GRPC' },
      modelContract: { description: spec.description, inputFields: spec.fields, inputExampleJson: JSON.stringify(sample) },
      executionBinding: { bindingType: 'GRPC', target: { targetKey, serviceName: CONTENT_SERVICE, methodName: spec.methodName, descriptorSetBase64, contextField: 'context' }, requestMappingsJson: JSON.stringify(spec.mappings), contextMappingsJson: '{}', timeoutMs: 30_000, maxResponseBytes: 5_242_880, idempotency: 'NONE', responsePolicy: 'ORIGINAL' },
      resultContract: { keyOutputFields: spec.outputs.map(([path, description, observedType]) => ({ path, description, observedType })), responseDemoJson: JSON.stringify(responseDemo) },
    } },
  };
}

function placeholderSample(spec) {
  const values = {
    title: '阅读到创作发布验收', audience: '希望把阅读转化为公开内容的创作者', outputFormat: 'Markdown',
    page: 1, pageSize: 20, projectId: UUID_ZERO, sourceId: UUID_ZERO, artifactId: UUID_ZERO,
    confirmationId: UUID_ZERO, sourceUrl: 'https://example.invalid/reading-content-fixture',
    body: '注意力不是无限资源。主动安排休息能保护注意力。', expectedProjectRevision: 1,
    kind: 'READING_BRIEF', readingPoints: [{ id: 'p1', claim: '注意力有限', evidenceQuote: '注意力不是无限资源', evidenceLocator: '第一句', explanation: '需要主动分配注意力', modelSuggestion: false }],
    questions: [], usableMaterials: ['注意力不是无限资源'], topics: [], manuscriptTitle: '注意力不是意志力', manuscriptMarkdown: '# 注意力不是意志力', citations: [],
    inputRefs: [{ kind: 'SOURCE', id: UUID_ZERO, revision: 1 }], origin: 'MODEL_GENERATED', selectedPointIds: ['p1'], userNotes: '',
    topicId: 't1', editedTitle: '注意力不是意志力', editedAngle: '从资源管理切入', format: 'MARKDOWN',
  };
  return Object.fromEntries(spec.fields.filter(item => item.required).map(item => [item.toolField, values[item.toolField]]));
}

async function ensureCapability(client, spec, options, sample) {
  const candidates = list((await client.call('CAPABILITY_LIST', { keyword: spec.actionCode })).data);
  const matches = candidates.filter(item => actionCodeOf(item) === spec.actionCode);
  if (matches.length > 1) throw new Error(`${spec.actionCode}: duplicate capability drafts`);
  let draftId;
  if (matches.length === 0) {
    const byName = list((await client.call('CAPABILITY_LIST', { keyword: spec.nameCn })).data);
    const initialDrafts = byName.filter(item => capabilityNameOf(item) === spec.nameCn && !actionCodeOf(item));
    if (initialDrafts.length > 1) throw new Error(`${spec.actionCode}: multiple initial drafts named ${spec.nameCn}`);
    if (initialDrafts.length === 1) {
      draftId = requiredText(initialDrafts[0]?.draftId, `${spec.actionCode}.draftId`);
    } else {
      const created = (await client.call('CAPABILITY_DRAFT_CREATE', { draftJson: JSON.stringify({ payloadType: 'CAPABILITY_DRAFT_SNAPSHOT', mode: 'CREATE', basicInfo: { nameCn: spec.nameCn } }) })).data;
      draftId = requiredText(created?.draftId, `${spec.actionCode}.draftId`);
    }
  } else {
    draftId = requiredText(matches[0]?.draftId, `${spec.actionCode}.draftId`);
  }
  const detail = (await client.call('CAPABILITY_DRAFT_DETAIL', { draftId })).data;
  await client.call('CAPABILITY_DRAFT_SAVE', {
    draftId, baseRevision: detail.revision,
    draftJson: JSON.stringify(capabilityDraft(spec, options.descriptorSetBase64, options.targetKey, sample)),
    businessDomain: 'general', capabilityDomain: 'general', specialistIds: options.specialistIds,
  });
  const validation = (await client.call('CAPABILITY_VALIDATE', { draftId })).data;
  if (validation?.valid !== true) throw new Error(`${spec.actionCode}: ${JSON.stringify(validation?.errors || validation)}`);
  return { draftId, detail: (await client.call('CAPABILITY_DRAFT_DETAIL', { draftId })).data };
}

async function dryRun(client, capability, environment = 'PRT') {
  const result = (await client.call('CAPABILITY_DRY_RUN', { draftId: capability.draftId, revision: capability.detail.revision, environment, clientType: 'PC' })).data;
  if (result?.toolResult?.success !== true) throw new Error(`${capability.detail?.draft?.basicInfo?.actionCode || capability.draftId}: dry-run failed (${result?.toolResult?.errorCode || 'UNKNOWN'})`);
  return result.toolResult.data;
}

async function publishPrt(client, assetType, assetKey, extra = {}) {
  const identity = { assetType, assetKey, ...extra };
  let overview = (await client.call('RELEASE_OVERVIEW', identity)).data;
  const digest = requiredText(overview?.currentSnapshot?.digest, `${assetType}/${assetKey}.digest`);
  if (overview?.environments?.PRT?.digest === digest) return overview;
  if (overview?.activeChange?.status === 'ACTIVE') {
    if (overview.activeChange.sourceDigest !== digest) throw new Error(`${assetType}/${assetKey}: another active change owns a different digest`);
  } else {
    await client.call('RELEASE_CHANGE_CREATE', { ...identity, changeName: '阅读到创作 PRT 发布', requestId: createRequestId() });
  }
  const deployed = (await client.call('RELEASE_PREPROD_DEPLOY', { ...identity, expectedDigest: digest, requestId: createRequestId() })).data;
  if (deployed?.status !== 'SUCCEEDED') throw new Error(`${assetType}/${assetKey}: PRT deploy ${deployed?.status || 'UNKNOWN'}`);
  overview = (await client.call('RELEASE_OVERVIEW', identity)).data;
  if (!overview?.environments?.PRT?.sourceId) throw new Error(`${assetType}/${assetKey}: missing PRT pointer`);
  return overview;
}

async function ensureAtom(client, atom) {
  const rows = list((await client.call('A2UI_CATALOG_COMPONENT_LIST', { keyword: atom.componentCode })).data);
  const matches = rows.filter(item => componentCodeOf(item) === atom.componentCode);
  if (matches.length > 1) throw new Error(`${atom.componentCode}: duplicate component atoms`);
  if (matches.length === 0) return (await client.call('A2UI_CATALOG_COMPONENT_CREATE', { componentJson: JSON.stringify(atom) })).data;
  const id = requiredText(String(matches[0].id || ''), `${atom.componentCode}.id`);
  return (await client.call('A2UI_CATALOG_COMPONENT_UPDATE', { id, componentJson: JSON.stringify(atom) })).data;
}

export async function bootstrapBasicAtoms(client, atoms) {
  for (const atom of atoms) await ensureAtom(client, atom);
}

async function ensureCatalog(client, officialComponentCodes = [], functionContract) {
  if (!functionContract || functionContract.catalogId !== CATALOG_ID || !functionContract.functions) {
    throw new Error('project function contract does not match catalog identity');
  }
  const importedOfficial = new Set(officialComponentCodes);
  const missing = [];
  for (const code of BASIC_COMPONENTS) {
    if (importedOfficial.has(code)) continue;
    const rows = list((await client.call('A2UI_CATALOG_COMPONENT_LIST', { keyword: code })).data);
    if (!rows.some(item => componentCodeOf(item) === code)) missing.push(code);
  }
  if (missing.length) throw new Error(`M 缺少已登记 basic atoms: ${missing.join(', ')}；先用隔离 CLI 的 --bootstrap-basic-catalog 导入官方 schema`);
  for (const atom of customAtoms) await ensureAtom(client, atom);
  const catalog = { catalogId: CATALOG_ID, nameCn: '数字员工阅读创作组件集', protocolVersion: PROTOCOL_VERSION, componentCodes: [...BASIC_COMPONENTS, ...customAtoms.map(item => item.componentCode)], functionContract };
  const catalogs = list((await client.call('A2UI_CATALOG_LIST', { keyword: CATALOG_ID })).data);
  const matches = catalogs.filter(item => catalogIdOf(item) === CATALOG_ID);
  if (matches.length > 1) throw new Error(`${CATALOG_ID}: duplicate catalogs`);
  if (matches.length === 0) await client.call('A2UI_CATALOG_CREATE', { catalogJson: JSON.stringify(catalog) });
  else await client.call('A2UI_CATALOG_UPDATE', { id: matches[0].id, catalogJson: JSON.stringify(catalog) });
  return publishPrt(client, 'A2UI_CATALOG', CATALOG_ID);
}

async function ensureApplication(client, application) {
  const rows = list((await client.call('A2UI_APPLICATION_LIST', { keyword: application.appCode })).data);
  const matches = rows.filter(item => appCodeOf(item) === application.appCode);
  if (matches.length > 1) throw new Error(`${application.appCode}: duplicate applications`);
  let saved;
  if (matches.length === 0) saved = (await client.call('A2UI_APPLICATION_CREATE', { applicationJson: JSON.stringify(application) })).data;
  else saved = (await client.call('A2UI_APPLICATION_UPDATE', { id: matches[0].id, applicationJson: JSON.stringify(application) })).data;
  const id = requiredText(String(saved?.id || matches[0]?.id || ''), `${application.appCode}.id`);
  await client.call('A2UI_APPLICATION_DETAIL', { id });
  const release = await publishPrt(client, 'A2UI_APPLICATION', application.appCode);
  return { id, release };
}

async function ensureSkill(client, skill, capabilityIds, applicationId, specialistIds) {
  let detailResult = await client.call('SKILL_DETAIL', { skillCode: skill.skillCode }, true);
  let workspaceId = skill.skillCode;
  if (!detailResult.ok) {
    const created = (await client.call('WORKSPACE_CREATE', { skillCode: skill.skillCode, skillNameCn: skill.nameCn, skillDescription: skill.markdown.split('\n')[2] || skill.nameCn, specialistIds, businessDomain: 'general', capabilityDomain: 'general' })).data;
    workspaceId = created?.workspaceId || skill.skillCode;
  } else {
    workspaceId = detailResult.data?.workspaceId || skill.skillCode;
  }
  await client.call('WORKSPACE_FILE_SAVE', { workspaceId, skillCode: skill.skillCode, filePath: 'SKILL.md', content: skill.markdown });
  detailResult = await client.call('SKILL_DETAIL', { skillCode: skill.skillCode });
  await client.call('SKILL_BINDINGS_REPLACE', {
    workspaceId, skillCode: skill.skillCode, version: detailResult.data.version,
    capabilityBindings: JSON.stringify(skill.capabilities.map(actionCode => ({ draftId: capabilityIds.get(actionCode), bindMode: 'EXECUTION_ONLY' }))),
    componentBindings: JSON.stringify([{ assetId: applicationId, componentCode: skill.applicationCode }]),
  });
  return { workspaceId, release: await publishPrt(client, 'SKILL', skill.skillCode, { workspaceId }) };
}

function sampleFactory(state) {
  const sourceRef = () => [{ kind: 'SOURCE', id: state.source.id, revision: state.source.revision }];
  const artifactRef = item => ({ kind: 'ARTIFACT', id: item.id, revision: item.revision });
  return {
    create: { title: '阅读到创作 PRT 发布验收', audience: '希望把阅读转化为公开内容的创作者', outputFormat: 'Markdown' },
    list: { page: 1, pageSize: 20 },
    project: () => ({ projectId: state.project.id }),
    sourceSave: () => ({ projectId: state.project.id, title: '注意力阅读摘录', body: '注意力不是无限资源。主动安排休息能保护注意力。', sourceUrl: 'https://example.invalid/reading-content-fixture', expectedProjectRevision: 1 }),
    sourceGet: () => ({ sourceId: state.source.id }),
    readingArtifact: () => ({ projectId: state.project.id, kind: 'READING_BRIEF', readingPoints: [{ id: 'p1', claim: '注意力有限', evidenceQuote: '注意力不是无限资源', evidenceLocator: '第一句', explanation: '需要有意识分配注意力', modelSuggestion: false }], questions: [], usableMaterials: ['注意力不是无限资源'], inputRefs: sourceRef(), origin: 'MODEL_GENERATED' }),
    readingConfirm: () => ({ projectId: state.project.id, artifactId: state.reading.id, selectedPointIds: ['p1'], userNotes: '保留原文证据', expectedProjectRevision: 2 }),
    topicArtifact: () => ({ projectId: state.project.id, kind: 'TOPIC_PLAN', topics: [{ id: 't1', title: '注意力不是意志力', angle: '从资源管理切入', audience: '职场新人', rationale: '连接工作节奏', sourcePointIds: ['p1'] }], inputRefs: [artifactRef(state.reading)], origin: 'MODEL_GENERATED' }),
    topicConfirm: () => ({ projectId: state.project.id, artifactId: state.topic.id, topicId: 't1', editedTitle: '注意力不是意志力', editedAngle: '从资源管理切入', expectedProjectRevision: 3 }),
    manuscriptArtifact: () => ({ projectId: state.project.id, kind: 'MANUSCRIPT', manuscriptTitle: '注意力不是意志力', manuscriptMarkdown: '# 注意力不是意志力\n\n主动安排休息。', citations: [{ referenceKind: 'SOURCE', referenceId: state.source.id, revision: state.source.revision, label: '注意力阅读摘录' }], inputRefs: [...sourceRef(), artifactRef(state.topic)], origin: 'USER_EDITED' }),
    manuscriptConfirm: () => ({ projectId: state.project.id, artifactId: state.manuscript.id, expectedProjectRevision: 4 }),
    artifactGet: () => ({ artifactId: state.manuscript.id }),
    confirmationGet: () => ({ confirmationId: state.readingConfirmation.id }),
    export: () => ({ artifactId: state.manuscript.id, format: 'MARKDOWN' }),
  };
}

/** Run the reviewed PRT-only authoring path. It never reads or accepts a token. */
export async function runPrtAuthoring(client, options) {
  validateAssets();
  const descriptorSetBase64 = requiredText(options.descriptorSetBase64, 'descriptorSetBase64');
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(descriptorSetBase64)) throw new Error('descriptorSetBase64 must be base64 text');
  const normalized = { descriptorSetBase64, targetKey: requiredText(options.targetKey, 'targetKey'), specialistIds: requiredText(options.specialistIds, 'specialistIds') };
  const byCode = new Map(capabilitySpecs.map(spec => [spec.actionCode, spec]));
  const capabilities = new Map();
  const apply = async (code, sample, execute = true) => {
    const spec = byCode.get(code);
    if (!spec) throw new Error(`unknown capability: ${code}`);
    const current = await ensureCapability(client, spec, normalized, sample);
    capabilities.set(code, current);
    return execute ? dryRun(client, current) : undefined;
  };
  if (options.resumeCheckpoint?.phase === 'DRY_RUNS_COMPLETE') {
    for (const item of options.resumeCheckpoint.capabilities || []) {
      if (!byCode.has(item.actionCode)) throw new Error(`checkpoint contains unknown capability: ${item.actionCode}`);
      const detail = (await client.call('CAPABILITY_DRAFT_DETAIL', { draftId: item.draftId })).data;
      if (detail.revision !== item.revision || actionCodeOf(detail) !== item.actionCode) throw new Error(`${item.actionCode}: checkpoint is stale`);
      capabilities.set(item.actionCode, { draftId: item.draftId, detail });
    }
    if (capabilities.size !== capabilitySpecs.length) throw new Error('checkpoint does not contain all 12 capabilities');
  } else {
    const state = {};
    const samples = sampleFactory(state);
    state.project = await apply('content.project.create', samples.create);
    state.source = await apply('content.source.save', samples.sourceSave());
    state.reading = await apply('content.artifact.save', samples.readingArtifact());
    state.readingConfirmation = await apply('content.reading.confirm', samples.readingConfirm());
    state.topic = await apply('content.artifact.save', samples.topicArtifact());
    state.topicConfirmation = await apply('content.topic.confirm', samples.topicConfirm());
    state.manuscript = await apply('content.artifact.save', samples.manuscriptArtifact());
    state.manuscriptConfirmation = await apply('content.manuscript.confirm', samples.manuscriptConfirm());
    await apply('content.project.list', samples.list);
    await apply('content.project.get', samples.project());
    await apply('content.source.get', samples.sourceGet());
    await apply('content.artifact.get', samples.artifactGet());
    await apply('content.confirmation.get', samples.confirmationGet());
    await apply('content.manuscript.export', samples.export());
    options.onCheckpoint?.({ phase: 'DRY_RUNS_COMPLETE', capabilities: capabilitySpecs.map(spec => ({ actionCode: spec.actionCode, draftId: capabilities.get(spec.actionCode).draftId, revision: capabilities.get(spec.actionCode).detail.revision })) });
  }
  // SaveArtifact was edited three times; only the final MANUSCRIPT dry-run belongs to its current digest.
  for (const spec of capabilitySpecs) {
    if (!capabilities.has(spec.actionCode)) capabilities.set(spec.actionCode, await ensureCapability(client, spec, normalized, placeholderSample(spec)));
    await publishPrt(client, 'CAPABILITY_ACTION', capabilities.get(spec.actionCode).draftId);
  }
  const catalogRelease = await ensureCatalog(client, options.officialComponentCodes, options.functionContract);
  const applicationRows = new Map();
  for (const application of buildApplications()) applicationRows.set(application.appCode, await ensureApplication(client, application));
  const skillRows = new Map();
  const capabilityIds = new Map([...capabilities].map(([code, item]) => [code, item.draftId]));
  for (const skill of skillSpecs) skillRows.set(skill.skillCode, await ensureSkill(client, skill, capabilityIds, applicationRows.get(skill.applicationCode).id, normalized.specialistIds));
  let workflow = null;
  if (options.includeWorkflow) {
    const specialistCode = requiredText(options.specialistCode, 'specialistCode');
    let workflowCode = options.workflowCode;
    let revision;
    if (!workflowCode) {
      const created = (await client.call('WORKFLOW_CREATE', { displayName: '阅读到创作', description: '阅读材料分析、选题规划、稿件创作与确认', specialistCode })).data;
      workflowCode = requiredText(created?.workflowCode, 'workflowCode'); revision = created.draftRevision;
    } else {
      revision = (await client.call('WORKFLOW_DRAFT_DETAIL', { workflowCode })).data?.draftRevision;
    }
    const payload = buildWorkflow(workflowCode);
    await client.call('WORKFLOW_COMPILED_PLAN_PREVIEW', { workflowCode, draftPayloadJson: JSON.stringify(payload) });
    const updated = (await client.call('WORKFLOW_DRAFT_UPDATE', { workflowCode, draftPayloadJson: JSON.stringify(payload), expectedDraftRevision: revision })).data;
    workflow = { workflowCode, draftRevision: updated?.draftRevision, release: await publishPrt(client, 'ORCHESTRATION_CONFIG', workflowCode) };
  }
  return {
    environment: 'PRT', catalog: { catalogId: CATALOG_ID, sourceId: catalogRelease.environments.PRT.sourceId },
    capabilities: capabilitySpecs.map(spec => ({ actionCode: spec.actionCode, draftId: capabilities.get(spec.actionCode).draftId })),
    applications: [...applicationRows].map(([appCode, item]) => ({ appCode, id: item.id, sourceId: item.release.environments.PRT.sourceId })),
    skills: [...skillRows].map(([skillCode, item]) => ({ skillCode, workspaceId: item.workspaceId, sourceId: item.release.environments.PRT.sourceId })),
    workflow,
  };
}
