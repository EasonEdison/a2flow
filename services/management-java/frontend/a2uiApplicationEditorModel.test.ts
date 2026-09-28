import {
  A2UI_APPLICATION_EDITOR_STAGES,
  buildA2uiActionClosureRows,
  buildA2uiActionHttpRequest,
  buildA2uiBuildManifestPreview,
  applySavedA2uiApplication,
  buildA2uiApplicationToolInvocation,
  buildA2uiPublicEventEnvelope,
  buildA2uiParamsSchema,
  createA2uiBuildGateSummary,
  createA2uiApplicationEditorDraftSession,
  createA2uiApplicationEditorViewModel,
  createA2uiActionBindingFromDeclaration,
  createA2uiValidationPreviewViewModel,
  resolveA2uiShowMessages,
  resolveA2uiMessageTemplateAdapter,
  readA2uiParameterDefinitions,
  resolveA2uiApplicationReleaseAssetKey,
  selectA2uiApplicationDraftStage,
  selectA2uiApplicationStage,
  upsertA2uiActionBinding,
  type A2uiApplicationEditorStage,
} from './a2uiApplicationEditorModel';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertDeepEqual(actual: unknown, expected: unknown, description: string) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${description}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`,
    );
  }
}

function test(description: string, callback: () => void) {
  callback();
  console.log(`PASS ${description}`);
}

test('staged Application editor exposes the five phases in order', () => {
  assertDeepEqual(
    A2UI_APPLICATION_EDITOR_STAGES.map((stage) => stage.id),
    ['basic', 'show', 'actions', 'validation', 'release'],
    'stage order',
  );
  assertDeepEqual(
    A2UI_APPLICATION_EDITOR_STAGES.map((stage) => stage.label),
    ['基础信息', 'A2UI 展示编排', 'Action 与结果配置', '联调验证', '发布'],
    'stage labels',
  );
});

test('editor view model renders only the selected stage and a bounded header summary', () => {
  const view = createA2uiApplicationEditorViewModel({
    mode: 'create',
    activeStage: 'validation',
    availableComponentCount: 3,
    interactionGapCount: 1,
    validationIssueCount: 2,
  });

  assertEqual(view.mode, 'create', 'create mode');
  assertEqual(view.activeStage, 'validation', 'active stage');
  assertDeepEqual(view.visibleStageIds, ['validation'], 'visible stage ids');
  assertDeepEqual(
    Object.keys(view.header),
    [
      'applicationLabel',
      'draftStatus',
      'availableComponentCount',
      'interactionClosure',
      'validationSummary',
    ],
    'bounded header keys',
  );
  assertEqual(view.header?.applicationLabel, 'Application', 'application header label');
  assertEqual(view.header?.draftStatus, '草稿', 'draft header status');
  assertEqual(view.header?.availableComponentCount, 3, 'available component count');
  assertEqual(view.header?.interactionClosure, '1 个缺口', 'interaction closure summary');
  assertEqual(view.header?.validationSummary, '2 个校验问题', 'validation summary');
});

test('stage selection preserves edit mode and the canonical stage state', () => {
  const initial = createA2uiApplicationEditorViewModel({
    mode: 'edit',
    activeStage: 'show',
    availableComponentCount: 2,
    interactionGapCount: 0,
    validationIssueCount: 0,
  });

  const next = selectA2uiApplicationStage(initial, 'actions' as A2uiApplicationEditorStage);
  assertEqual(next.mode, 'edit', 'edit mode after stage selection');
  assertEqual(next.activeStage, 'actions', 'selected stage');
  assertDeepEqual(next.visibleStageIds, ['actions'], 'only selected stage after selection');
  assertEqual(
    next.header?.applicationLabel,
    'Application',
    'header remains build-free after selection',
  );
});

test('saving a create draft keeps the same editor and promotes it to edit mode', () => {
  const draft = { appCode: 'order.confirm.application', version: 1 };
  const created = createA2uiApplicationEditorDraftSession(draft);
  const savedDraft = { ...draft, version: 2 };
  const saved = applySavedA2uiApplication(created, {
    id: 'application-1',
    draft: savedDraft,
  });

  assertEqual(created.mode, 'create', 'new editor mode');
  assertEqual(saved.mode, 'edit', 'saved editor mode');
  assertEqual(saved.applicationId, 'application-1', 'saved application id');
  assertEqual(saved.draft, savedDraft, 'canonical saved draft');
  assertEqual(saved.activeStage, 'basic', 'saved active stage');
});

test('changing stages preserves the canonical draft value', () => {
  const draft = { appCode: 'order.confirm.application', version: 1 };
  const session = createA2uiApplicationEditorDraftSession(draft, 'application-1');
  const next = selectA2uiApplicationDraftStage(session, 'release');

  assertEqual(next.mode, 'edit', 'draft session edit mode');
  assertEqual(next.activeStage, 'release', 'draft session stage');
  assertEqual(next.draft, draft, 'draft identity after stage change');
});

test('dedicated A2UI Tool invocation contains only appCode and params', () => {
  const invocation = buildA2uiApplicationToolInvocation('order.confirm.application', {
    orderId: 'order-1',
  });

  assertDeepEqual(
    invocation,
    {
      toolName: 'render_a2ui_application',
      arguments: {
        appCode: 'order.confirm.application',
        params: { orderId: 'order-1' },
      },
    },
    'A2UI Tool invocation shape',
  );
  const serialized = JSON.stringify(invocation);
  [
    'render_component',
    'appBuildId',
    'messages',
    'capabilityEndpoint',
    'resultAdapter',
    'identity',
    'environment',
    'credential',
    'script',
  ].forEach((forbidden) => {
    assertEqual(serialized.includes(forbidden), false, `forbidden Tool field ${forbidden}`);
  });
});

test('sample APP_PARAMS resolve into updateComponents and updateDataModel messages', () => {
  const showTemplate = {
    templateCode: 'sample.params.preview',
    paramsSchema: {
      type: 'object',
      additionalProperties: false,
      required: ['submitText', 'status'],
      properties: {
        submitText: { type: 'string' },
        status: { type: 'string' },
      },
    },
    surfaceDeclarations: [{ surfaceId: 'main', rootComponentId: 'root' }],
    messageTemplates: [
      {
        version: 'v0.9.1' as const,
        updateComponents: {
          surfaceId: 'main',
          components: [
            { id: 'root', component: 'Column', children: ['submit'] },
            { id: 'submit', component: 'Button', label: '' },
          ],
        },
      },
      {
        version: 'v0.9.1' as const,
        updateDataModel: { surfaceId: 'main', path: '/status', value: null },
      },
    ],
    inputBindings: [
      {
        targetMessageIndex: 0,
        targetPath: '/updateComponents/components/1/label',
        source: 'APP_PARAMS' as const,
        sourcePath: '/submitText',
        required: true,
      },
      {
        targetMessageIndex: 1,
        targetPath: '/updateDataModel/value',
        source: 'APP_PARAMS' as const,
        sourcePath: '/status',
        required: true,
      },
    ],
  };

  const resolved = resolveA2uiShowMessages(showTemplate, {
    submitText: '立即提交',
    status: 'WAITING',
  });

  assertDeepEqual(resolved.issues, [], 'resolved binding issues');
  assertDeepEqual(
    resolved.messages,
    [
      {
        version: 'v0.9.1',
        updateComponents: {
          surfaceId: 'main',
          components: [
            { id: 'root', component: 'Column', children: ['submit'] },
            { id: 'submit', component: 'Button', label: '立即提交' },
          ],
        },
      },
      {
        version: 'v0.9.1',
        updateDataModel: { surfaceId: 'main', path: '/status', value: 'WAITING' },
      },
    ],
    'messages resolved from sample params',
  );
  assertEqual(
    (
      showTemplate.messageTemplates?.[0]?.updateComponents?.components?.[1] as
        | { label: string }
        | undefined
    )?.label,
    '',
    'message template remains immutable',
  );
});

test('structured parameter definitions round-trip through the Application params schema', () => {
  const definitions = [
    {
      name: 'submitText',
      type: 'string' as const,
      required: true,
      description: '提交按钮文案',
      example: '立即提交',
    },
    {
      name: 'retryCount',
      type: 'integer' as const,
      required: false,
      description: '允许重试次数',
      example: 2,
    },
  ];

  const schema = buildA2uiParamsSchema(definitions);
  assertDeepEqual(
    schema,
    {
      type: 'object',
      additionalProperties: false,
      properties: {
        submitText: {
          type: 'string',
          description: '提交按钮文案',
          examples: ['立即提交'],
        },
        retryCount: {
          type: 'integer',
          description: '允许重试次数',
          examples: [2],
        },
      },
      required: ['submitText'],
    },
    'closed params schema',
  );
  assertDeepEqual(
    readA2uiParameterDefinitions(schema).map(({ schema: _schema, schemaType: _type, ...item }) => item),
    definitions,
    'parameter definition round-trip',
  );
});

test('editing a flat parameter preserves nested schemas and unrelated constraints', () => {
  const original = {
    type: 'object', additionalProperties: false, description: '稿件参数',
    properties: {
      refs: {type: 'array', minItems: 1, items: {type: 'object', properties: {
        id: {type: 'string', minLength: 1},
      }, required: ['id'], additionalProperties: false}},
      title: {type: 'string', minLength: 1},
    }, required: ['refs'],
  };
  const rows = readA2uiParameterDefinitions(original);
  rows[1].description = '标题';
  const next = buildA2uiParamsSchema(rows, original);
  assertDeepEqual((next.properties as Record<string, unknown>).refs, original.properties.refs,
    'nested array contract survives unrelated edits');
  assertDeepEqual((next.properties as Record<string, unknown>).title,
    {type: 'string', minLength: 1, description: '标题'}, 'constraints survive description edit');
  assertDeepEqual(next.description, original.description, 'root annotations survive');
  rows[0].name = 'references';
  const renamed = buildA2uiParamsSchema(rows, original);
  assertDeepEqual((renamed.properties as Record<string, unknown>).references,
    original.properties.refs, 'rename retains nested contract');
  assertDeepEqual(original.properties.title, {type: 'string', minLength: 1}, 'no source mutation');
});

test('explicit capability data bindings resolve into Binding-owned update messages', () => {
  const dataAdapter = {
    adapterId: 'success-data',
    order: 1,
    type: 'MESSAGE_TEMPLATE' as const,
    messageTemplate: {
      version: 'v0.9.1' as const,
      updateDataModel: { surfaceId: 'main', path: '/status', value: null },
    },
    bindings: [
      {
        targetPath: '/updateDataModel/value',
        source: 'CAPABILITY_DATA' as const,
        sourcePath: '/status',
        required: true,
      },
    ],
  };
  const componentAdapter = {
    adapterId: 'success-components',
    order: 2,
    type: 'MESSAGE_TEMPLATE' as const,
    messageTemplate: {
      version: 'v0.9.1' as const,
      updateComponents: {
        surfaceId: 'main',
        components: [{ id: 'result', component: 'Text', text: '' }],
      },
    },
    bindings: [
      {
        targetPath: '/updateComponents/components/0/text',
        source: 'CAPABILITY_DATA' as const,
        sourcePath: '/message',
        required: true,
      },
    ],
  };
  const capabilityData = { status: 'SUCCEEDED', message: '提交成功' };

  const dataResult = resolveA2uiMessageTemplateAdapter(dataAdapter, capabilityData);
  const componentResult = resolveA2uiMessageTemplateAdapter(componentAdapter, capabilityData);

  assertDeepEqual(dataResult.issues, [], 'data adapter issues');
  assertDeepEqual(
    dataResult.message,
    {
      version: 'v0.9.1',
      updateDataModel: { surfaceId: 'main', path: '/status', value: 'SUCCEEDED' },
    },
    'resolved updateDataModel message',
  );
  assertDeepEqual(componentResult.issues, [], 'component adapter issues');
  assertDeepEqual(
    componentResult.message,
    {
      version: 'v0.9.1',
      updateComponents: {
        surfaceId: 'main',
        components: [{ id: 'result', component: 'Text', text: '提交成功' }],
      },
    },
    'resolved updateComponents message',
  );
  assertEqual(
    dataAdapter.messageTemplate?.updateDataModel?.value,
    null,
    'data adapter template remains immutable',
  );
});

test('per-Action authoring upserts only the exact stable binding', () => {
  const declaration = {
    actionCode: 'a2ui.smoke.submit',
    sourceComponentId: 'submit',
    surfaceId: 'main',
    contextTemplateDigest: 'sha256:submit-context',
    contextSchema: { type: 'object', properties: { source: { type: 'string' } } },
    discoveredFrom: [{ sourceType: 'SHOW_TEMPLATE' as const }],
    status: 'UNBOUND' as const,
  };
  const existing = {
    bindingId: 'other-binding',
    surfaceId: 'other',
    sourceComponentId: 'other-button',
    actionCode: 'other.action',
    allowedSourceComponentIds: ['other-button'],
    contextSchema: { type: 'object' },
    capability: { actionCode: 'other.capability' },
    requestMappings: [],
    successOutcome: 'NO_UI_MESSAGES' as const,
    failureOutcome: 'NO_UI_MESSAGES' as const,
    resultAdapters: [],
    failureResultAdapters: [],
    completeWorkflowInteractionOnSuccess: false,
  };

  const created = createA2uiActionBindingFromDeclaration(declaration);
  const bindings = upsertA2uiActionBinding([existing], {
    ...created,
    capability: { actionCode: 'a2ui.smoke.submit.execute' },
  });

  assertEqual(bindings?.[0], existing, 'unrelated binding identity is preserved');
  assertDeepEqual(
    bindings?.[1],
    {
      bindingId: 'main-submit-a2ui-smoke-submit',
      surfaceId: 'main',
      sourceComponentId: 'submit',
      actionCode: 'a2ui.smoke.submit',
      allowedSourceComponentIds: ['submit'],
      contextSchema: declaration.contextSchema,
      capability: { actionCode: 'a2ui.smoke.submit.execute' },
      requestMappings: [],
      successOutcome: 'ADAPTER_PIPELINE',
      failureOutcome: 'ADAPTER_PIPELINE',
      resultAdapters: [],
      failureResultAdapters: [],
      completeWorkflowInteractionOnSuccess: false,
    },
    'new exact binding',
  );
});

test('release management is directly addressable without exposing Build UI state', () => {
  assertEqual(
    resolveA2uiApplicationReleaseAssetKey('application-1', 'order.confirm.application', 'draft-1'),
    'order.confirm.application',
    'saved application release asset key',
  );
  assertEqual(
    resolveA2uiApplicationReleaseAssetKey(undefined, 'order.confirm.application', 'draft-1'),
    '',
    'unsaved application must not query release state',
  );
  assertEqual(
    resolveA2uiApplicationReleaseAssetKey(undefined, '', 'draft-1'),
    '',
    'temporary draft id must not become release asset key',
  );
});

test('Action scan projection preserves exact binding facts and server statuses', () => {
  const declaration = {
    eventName: 'order.confirm',
    actionCode: 'order.confirm',
    sourceComponentId: 'confirm-button',
    surfaceId: 'order-surface',
    contextTemplateDigest: 'sha256:context-v1',
    discoveredFrom: [{ sourceType: 'SHOW_TEMPLATE' as const, path: '/createSurface/components/0' }],
    status: 'BOUND' as const,
  };
  const binding = {
    bindingId: 'binding-1',
    surfaceId: declaration.surfaceId,
    sourceComponentId: declaration.sourceComponentId,
    actionCode: declaration.actionCode,
    allowedSourceComponentIds: [declaration.sourceComponentId],
    contextSchema: { type: 'object' },
    capability: { actionCode: 'order.confirm.capability' },
    requestMappings: [
      { source: 'ACTION_CONTEXT' as const, sourcePath: '/orderId', targetPath: '/orderId' },
    ],
    successOutcome: 'ADAPTER_PIPELINE' as const,
    failureOutcome: 'ADAPTER_PIPELINE' as const,
    resultAdapters: [
      { adapterId: 'adapter-2', order: 2, type: 'MESSAGE_TEMPLATE' as const },
      {
        adapterId: 'adapter-1',
        order: 1,
        type: 'A2UI_PASSTHROUGH' as const,
        source: 'CAPABILITY_DATA' as const,
      },
    ],
    failureResultAdapters: [
      { adapterId: 'failure-1', order: 1, type: 'MESSAGE_TEMPLATE' as const },
    ],
    completeWorkflowInteractionOnSuccess: false,
  };
  const rows = buildA2uiActionClosureRows([declaration], [binding]);
  assertEqual(rows.length, 1, 'closed action row count');
  assertEqual(rows?.[0]?.status, 'BOUND', 'server-owned bound status');
  assertEqual(
    rows?.[0]?.capabilityAction,
    'order.confirm.capability',
    'stable capability actionCode',
  );
  assertEqual(rows?.[0]?.requestMappingCount, 1, 'request mapping count');
  assertEqual(
    rows?.[0]?.policySummary,
    '运行时解析当前生效 CapabilityAction；A2UI 不配置权限/审批/幂等',
    'runtime resolution summary',
  );
  assertDeepEqual(rows?.[0]?.orderedAdapterIds, ['adapter-1', 'adapter-2'], 'ordered adapters');

  const gaps = buildA2uiActionClosureRows([{ ...declaration, status: 'UNBOUND' as const }], []);
  assertEqual(gaps?.[0]?.status, 'UNBOUND', 'server-owned unbound status');
  assertEqual(gaps?.[0]?.gap, '缺少 ActionBinding', 'missing binding gap');

  const unreferenced = buildA2uiActionClosureRows([], [binding]);
  assertEqual(unreferenced.length, 1, 'disappeared declaration keeps configured binding row');
  assertEqual(unreferenced?.[0]?.status, 'UNREFERENCED', 'disappeared declaration status');
  assertEqual(unreferenced?.[0]?.binding, binding, 'configured binding object is preserved');

  const revalidation = buildA2uiActionClosureRows(
    [
      {
        ...declaration,
        contextTemplateDigest: 'sha256:context-v2',
        status: 'NEEDS_REVALIDATION' as const,
      },
    ],
    [binding],
  );
  assertEqual(revalidation?.[0]?.status, 'NEEDS_REVALIDATION', 'digest change status');
  assertEqual(revalidation?.[0]?.binding, binding, 'digest change preserves configured binding');

  const reserved = buildA2uiActionClosureRows(
    [{ ...declaration, actionCode: 'WORKFLOW_SUBMIT', status: 'RESERVED' as const }],
    [],
  );
  assertEqual(reserved?.[0]?.status, 'RESERVED', 'reserved status');
  assertEqual(
    (reserved?.[0] as unknown as { configurable?: boolean })?.configurable,
    false,
    'reserved declaration is not configurable',
  );
});

test('public A2UI event uses a direct message list and Action HTTP exposes no internal fields', () => {
  const messages = [
    {
      version: 'v0.9.1' as const,
      updateDataModel: { surfaceId: 'main', path: '/status', value: 'DONE' },
    },
  ];
  const event = buildA2uiPublicEventEnvelope(messages);
  assertDeepEqual(event, { type: 'CUSTOM', name: 'a2ui', value: messages }, 'public A2UI event');
  assertEqual(Array.isArray(event.value), true, 'public value is a direct list');

  const request = buildA2uiActionHttpRequest('conversation-1', 'message-1', {
    name: 'order.confirm',
    surfaceId: 'main',
    sourceComponentId: 'confirm-button',
    timestamp: '2026-08-21T02:00:00Z',
    context: { orderId: 'order-1' },
  });
  assertDeepEqual(
    Object.keys(request),
    ['conversationId', 'messageId', 'message'],
    'Action HTTP top-level fields',
  );
  assertDeepEqual(
    Object.keys(request.message?.action),
    ['name', 'surfaceId', 'sourceComponentId', 'timestamp', 'context'],
    'official v0.9.1 Action fields',
  );
  const serialized = JSON.stringify(request);
  [
    'appBuildId',
    'runtimeSession',
    'surfaceRevision',
    'requestId',
    'correlationId',
    'idempotencyKey',
  ].forEach((field) => assertEqual(serialized.includes(field), false, `internal field ${field}`));
});

test('validation preview switches structure and visual modes without pretending to render B UI', () => {
  const visual = createA2uiValidationPreviewViewModel('visual');
  assertDeepEqual(visual.visibleModeIds, ['visual'], 'only visual preview is visible');
  assertDeepEqual(
    visual.structure?.sectionLabels,
    [
      'JSON',
      '组件树',
      '数据绑定',
      '脱敏 request',
      '显式业务 data / Tool 元数据 Demo',
      'ordered adapters',
      'canonical final Surface',
    ],
    'structure preview sections',
  );
  assertEqual(visual.visual?.status, 'WAITING_FRONTEND', 'visual renderer status');
  assertEqual(visual.visual?.message, 'B 端 Renderer 待接入', 'visual renderer placeholder');
  assertEqual(visual.visual?.rendersMock, false, 'visual preview does not render mock');
  assertEqual(visual.prtInput?.persistence, 'SESSION_ONLY', 'PRT input persistence');
  assertEqual(visual.destructiveActionPolicy, 'AUDITED_DEMO_ONLY', 'destructive demo policy');
});

test('release summary exposes exact environments and only server-owned blockers', () => {
  const blocked = createA2uiBuildGateSummary({
    catalogReleases: {
      PRT: { revision: '3', digest: 'sha256:prt', enabled: true },
      ONLINE: { revision: '', digest: '', enabled: false },
    },
    releaseBlockers: ['A2UI_APPLICATION_CATALOG_ONLINE_NOT_PUBLISHED'],
  });
  assertDeepEqual(
    blocked.gates?.map?.((gate) => gate.id),
    ['serverReleaseBlockers'],
    'release gates are only server-owned blockers',
  );
  assertEqual(blocked.status, 'BLOCKED', 'server blocker status');
  assertEqual(blocked.canSaveDraft, true, 'blocked release keeps draft save');
  assertEqual(blocked.canPublish, false, 'frontend never declares publish readiness');

  const manifest = buildA2uiBuildManifestPreview({
    appCode: 'order.confirm.application',
    protocolVersion: 'v0.9.1',
    catalog: {
      catalogId: 'a2flow.a2ui.basic',
      releases: blocked.catalogReleases,
    },
    sourceDigest: undefined,
    requiredComponentTypes: ['Button', 'Text'],
    availableComponentTypes: ['Button'],
    gates: blocked,
  });
  assertDeepEqual(
    manifest.immutableManifest,
    {
      appCode: 'order.confirm.application',
      protocolVersion: 'v0.9.1',
      catalog: {
        catalogId: 'a2flow.a2ui.basic',
        releases: {
          PRT: { revision: '3', digest: 'sha256:prt', enabled: true },
          ONLINE: { revision: '', digest: '', enabled: false },
        },
      },
    },
    'immutable manifest',
  );
  assertEqual(manifest.sourceDigest, '待 Build 生成', 'pending source digest');
  assertDeepEqual(manifest.dependencyDiff?.unavailableComponentTypes, ['Text'], 'dependency diff');
  assertEqual(manifest.canPublish, false, 'manifest publish gate');

  const serverClear = createA2uiBuildGateSummary({
    catalogReleases: blocked.catalogReleases,
    releaseBlockers: [],
  });
  assertEqual(serverClear.status, 'SERVER_CLEAR', 'server reports no blockers');
  assertEqual(serverClear.canPublish, false, 'shared release service still owns publish');
});
