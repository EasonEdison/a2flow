import {
  buildA2uiContractPreview,
  createEmptyA2uiApplicationDraft,
  deriveActionDeclarations,
  normalizeResultAdapters,
  parseA2uiApplicationForm,
  projectA2uiApplicationBlueprintOptions,
  projectA2uiApplicationActionScanResult,
  projectA2uiApplicationBlueprintWireSource,
  toA2uiApplicationAuthoringPayload,
  toA2uiApplicationFormValues,
  validateA2uiApplicationBuild,
  type A2uiApplicationDraft,
} from './a2uiApplicationContracts';
import type { A2uiCatalogComponentRecord } from './a2uiCatalogContracts';
import { buildDetailedA2uiContractPreview } from './a2uiApplicationPreview';
import { validateA2uiApplicationBuildIssues } from './a2uiApplicationValidationIssues';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertIncludes(values: string[], expected: string, description: string) {
  if (!values.includes(expected)) {
    throw new Error(`${description}: expected ${expected}, received ${values.join(',')}`);
  }
}

async function test(description: string, callback: () => void | Promise<void>) {
  await callback();
  console.log(`PASS ${description}`);
}

function assertThrows(callback: () => void, expectedMessage: string, description: string) {
  let message = '';
  try {
    callback();
  } catch (reason) {
    message = reason instanceof Error ? reason.message : String(reason);
  }
  if (!message.includes(expectedMessage)) {
    throw new Error(
      `${description}: expected ${expectedMessage}, received ${message || 'no error'}`,
    );
  }
}

const catalogRelease = {
  catalogId: 'a2flow.a2ui.basic',
  revision: '2026-08-17.1',
  digest: 'sha256:catalog-digest',
};

function componentRecord(type: string): A2uiCatalogComponentRecord {
  return {
    id: `component-${type}`,
    componentCode: `a2flow.basic.${type.toLowerCase()}`,
    type,
    nameCn: type,
    category: type === 'Button' ? 'ACTION' : 'LAYOUT',
    compositionKind: 'ATOMIC',
    propsSchema: { type: 'object', properties: {} },
    eventSchema: { type: 'object', properties: {} },
    childrenConstraint: { mode: type === 'Column' ? 'MULTIPLE' : 'NONE' },
    validMessageExample: { type },
    invalidMessageExample: {},
    catalogSourceType: 'PLATFORM_MANAGED',
    componentOriginType: 'PLATFORM_CUSTOM',
    release: {
      catalogId: catalogRelease.catalogId,
      revision: catalogRelease.revision,
      digest: catalogRelease.digest,
      enabled: true,
    },
  };
}

function applicationFixture(): A2uiApplicationDraft {
  const application = createEmptyA2uiApplicationDraft();
  application.appCode = 'order.confirm.application';
  application.nameCn = '订单确认编排';
  application.description = '确认订单并根据结果更新当前 Surface';
  application.catalog = {
    catalogId: catalogRelease.catalogId,
    revision: catalogRelease.revision,
    digest: catalogRelease.digest,
  };
  application.showTemplate = {
    templateCode: 'order.confirm.show',
    paramsSchema: { type: 'object', properties: {} },
    surfaceDeclarations: [
      {
        surfaceId: 'order-confirm-surface',
        rootComponentId: 'root',
      },
    ],
    messageTemplates: [
      {
        version: 'v0.9.1',
        createSurface: {
          surfaceId: 'order-confirm-surface',
          catalogId: catalogRelease.catalogId,
        },
      },
      {
        version: 'v0.9.1',
        updateComponents: {
          surfaceId: 'order-confirm-surface',
          components: [
            { id: 'root', component: 'Column', children: ['confirm-button'] },
            {
              id: 'confirm-button',
              component: 'Button',
              label: '确认订单',
              action: {
                event: {
                  name: 'order.confirm',
                  context: { orderId: { path: '/orderId' } },
                },
              },
            },
          ],
        },
      },
      {
        version: 'v0.9.1',
        updateDataModel: {
          surfaceId: 'order-confirm-surface',
          path: '/orderId',
          value: 'fixture-order',
        },
      },
    ],
    inputBindings: [
      {
        targetMessageIndex: 2,
        targetPath: '/updateDataModel/value',
        source: 'APP_PARAMS',
        sourcePath: '/orderId',
        required: true,
      },
    ],
  };
  application.loadBindings = [];
  application.actionBindings = [
    {
      bindingId: 'order-confirm-binding',
      surfaceId: 'order-confirm-surface',
      sourceComponentId: 'confirm-button',
      actionCode: 'order.confirm',
      allowedSourceComponentIds: ['confirm-button'],
      contextSchema: { type: 'object', properties: { orderId: { type: 'string' } } },
      capability: {
        actionCode: 'order.confirm.execute',
      },
      requestMappings: [
        {
          source: 'ACTION_CONTEXT',
          sourcePath: '$.form',
          targetPath: '$.request.form',
        },
      ],
      successOutcome: 'ADAPTER_PIPELINE',
      failureOutcome: 'ADAPTER_PIPELINE',
      resultAdapters: [
        {
          adapterId: 'passthrough',
          order: 2,
          type: 'A2UI_PASSTHROUGH',
          source: 'CAPABILITY_DATA',
          sourcePath: '$.a2uiMessages',
          cardinality: 'MANY',
          required: true,
          emittedActionDeclarations: [
            {
              surfaceId: 'order-confirm-result',
              sourceComponentId: 'retry-button',
              actionCode: 'order.retry',
              contextSchema: { type: 'object', properties: {} },
            },
          ],
        },
        {
          adapterId: 'success-template',
          order: 1,
          type: 'MESSAGE_TEMPLATE',
          templateCode: 'order.confirm.success',
          templateRevision: '1',
          templateDigest: 'sha256:success-template',
          messageTemplate: {
            version: 'v0.9.1',
            updateDataModel: {
              surfaceId: 'order-confirm-surface',
              path: '/result',
              value: '{{capabilityData}}',
            },
          },
          bindings: [
            {
              targetPath: '/updateDataModel/value',
              source: 'CAPABILITY_DATA',
              sourcePath: '/',
              required: true,
            },
          ],
        },
      ],
      failureResultAdapters: [
        {
          adapterId: 'failure-template',
          order: 1,
          type: 'MESSAGE_TEMPLATE',
          templateCode: 'order.confirm.failure',
          templateRevision: '1',
          templateDigest: 'sha256:failure-template',
          messageTemplate: {
            version: 'v0.9.1',
            updateDataModel: {
              surfaceId: 'order-confirm-surface',
              path: '/error',
              value: '{{capabilityMeta.error}}',
            },
          },
          bindings: [
            {
              targetPath: '/updateDataModel/value',
              source: 'CAPABILITY_META',
              sourcePath: '/error',
              required: true,
            },
          ],
        },
      ],
      completeWorkflowInteractionOnSuccess: false,
    },
  ];
  return application;
}

async function main() {
  await test('keeps Host Profile support and renderer evidence out of the editor domain', () => {
    const application = createEmptyA2uiApplicationDraft();
    assertEqual(
      Object.prototype.hasOwnProperty.call(application, 'hostProfile'),
      false,
      'editor Host Profile field',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(application, 'frontendSupport'),
      false,
      'editor frontend support field',
    );
  });

  await test('derives action declarations from the canonical Show AST', () => {
    const application = applicationFixture();
    const declarations = deriveActionDeclarations(application.showTemplate);
    assertEqual(declarations.length, 1, 'derived declaration count');
    assertEqual(declarations?.[0]?.actionCode, 'order.confirm', 'derived actionCode');
    assertEqual(declarations?.[0]?.eventName, 'order.confirm', 'derived event name');
    assertEqual(declarations?.[0]?.sourceComponentId, 'confirm-button', 'source component');
    assertEqual(
      Object.prototype.hasOwnProperty.call(application, 'actionDeclarations'),
      false,
      'second action truth',
    );
  });

  await test('keeps MESSAGE_TEMPLATE and A2UI_PASSTHROUGH in configured order', () => {
    const adapters = normalizeResultAdapters(
      applicationFixture()?.actionBindings?.[0]?.resultAdapters || [],
    );
    assertEqual(adapters?.[0]?.type, 'MESSAGE_TEMPLATE', 'first adapter type');
    assertEqual(adapters?.[1]?.type, 'A2UI_PASSTHROUGH', 'second adapter type');
    assertEqual(
      adapters?.[1]?.emittedActionDeclarations?.[0]?.actionCode,
      'order.retry',
      'passthrough explicit emitted Action declaration',
    );
  });

  await test('rejects action mappings that let client payload overwrite trusted authority', () => {
    const application = applicationFixture();
    application.actionBindings?.[0]?.requestMappings?.push?.({
      source: 'ACTION_CONTEXT',
      sourcePath: '$.userId',
      targetPath: '$.request.userId',
    });
    assertIncludes(
      validateA2uiApplicationBuild(application, [
        componentRecord('Column'),
        componentRecord('Button'),
      ]),
      'A2UI_AUTHORITY_MAPPING_FORBIDDEN',
      'trusted authority mapping rejection',
    );
  });

  await test('validates authoring structure without client-owned release evidence', () => {
    const application = applicationFixture();
    assertEqual(
      validateA2uiApplicationBuild(application, [
        componentRecord('Column'),
        componentRecord('Button'),
      ])?.length,
      0,
      'valid build errors',
    );
    assertIncludes(
      validateA2uiApplicationBuild(application, [
        componentRecord('Column'),
        {
          ...componentRecord('Button'),
          componentOriginType: 'A2UI_OFFICIAL',
        },
      ]),
      'A2UI_COMPONENT_NOT_AVAILABLE',
      'wrong component origin rejection',
    );
  });

  await test('selects the exact AVAILABLE component when historical revisions share a type', () => {
    const historicalColumn = {
      ...componentRecord('Column'),
      id: 'component-column-historical',
      release: {
        catalogId: catalogRelease.catalogId,
        revision: '2026-08-01.1',
        digest: 'sha256:historical-catalog',
        enabled: false,
      },
    };
    assertEqual(
      validateA2uiApplicationBuild(applicationFixture(), [
        historicalColumn,
        componentRecord('Column'),
        componentRecord('Button'),
      ])?.length,
      0,
      'historical same-type record errors',
    );
  });

  await test('builds a renderer-free contract preview with one atomic message batch', () => {
    const preview = buildA2uiContractPreview(applicationFixture());
    assertEqual(preview.kind, 'STRUCTURE_CONTRACT_PREVIEW', 'preview kind');
    assertEqual(preview.visualPreview, false, 'visual preview flag');
    assertEqual(preview.actionDeclarations?.length, 1, 'preview action declarations');
    assertEqual(preview.messageBatch?.length, 3, 'initial message batch size');
    assertEqual(preview.messageBatch?.[0]?.version, 'v0.9.1', 'create message version');
    assertEqual(Boolean(preview.messageBatch?.[0]?.createSurface), true, 'createSurface message');
    assertEqual(
      Boolean(preview.messageBatch?.[1]?.updateComponents),
      true,
      'updateComponents message',
    );
    assertEqual(
      Boolean(preview.messageBatch?.[2]?.updateDataModel),
      true,
      'updateDataModel message',
    );
  });

  await test('round-trips editor sections without introducing a second Action truth', () => {
    const values = toA2uiApplicationFormValues(applicationFixture());
    assertEqual(
      Object.prototype.hasOwnProperty.call(values, 'actionDeclarationsJson'),
      false,
      'editable action declarations',
    );
    const parsed = parseA2uiApplicationForm(values);
    assertEqual(parsed.ok, true, 'round-trip parse');
    assertEqual(
      parsed.ok && deriveActionDeclarations(parsed.application.showTemplate)?.[0]?.actionCode,
      'order.confirm',
      'round-trip derived action',
    );
    assertEqual(
      parsed.ok && parsed.application.actionBindings?.[0]?.resultAdapters?.[0]?.type,
      'A2UI_PASSTHROUGH',
      'configured adapter order remains authoring truth',
    );
  });

  await test('selects a Catalog by id while keeping release authority out of authoring payload', () => {
    const baseApplication = applicationFixture();
    const values = toA2uiApplicationFormValues(baseApplication);
    values.catalogId = catalogRelease.catalogId;
    const parsed = parseA2uiApplicationForm(values, {
      stage: 'basic',
      baseApplication,
    });
    assertEqual(parsed.ok, true, 'basic stage Catalog parse');
    assertEqual(
      parsed.ok && parsed.application.catalog.catalogId,
      catalogRelease.catalogId,
      'selected catalogId',
    );
    assertEqual(
      parsed.ok && parsed.application.catalog.revision,
      catalogRelease.revision,
      'selected Catalog revision',
    );
    assertEqual(
      parsed.ok && parsed.application.catalog.digest,
      catalogRelease.digest,
      'selected Catalog digest',
    );
    const payload = toA2uiApplicationAuthoringPayload(
      parsed.ok ? parsed.application : baseApplication,
    );
    assertEqual(payload.catalogId, catalogRelease.catalogId, 'payload exact catalogId');
    assertEqual(
      Object.prototype.hasOwnProperty.call(payload, 'catalog'),
      false,
      'nested Catalog authority is not submitted',
    );
  });

  await test('projects the authority-free Blueprint wire into a safe fail-closed editor domain', () => {
    const source = toA2uiApplicationAuthoringPayload(applicationFixture());
    const projected = projectA2uiApplicationBlueprintWireSource(source);
    assertEqual(projected.catalog?.catalogId, catalogRelease.catalogId, 'projected catalogId');
    assertEqual(projected.catalog?.revision, '', 'Blueprint wire does not invent revision');
    assertEqual(projected.catalog?.digest, '', 'Blueprint wire does not invent digest');
    assertEqual(projected.protocolVersion, 'v0.9.1', 'editor protocol projection');
    assertEqual(
      projected.protocolStatus,
      'CURRENT_PRODUCTION',
      'editor protocol status projection',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(projected, 'hostProfile'),
      false,
      'no Host field',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(projected, 'frontendSupport'),
      false,
      'no support field',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(projected, 'catalogId'),
      false,
      'wire catalogId is consumed at the adapter boundary',
    );
    const buildErrors = validateA2uiApplicationBuild(projected, []);
    assertIncludes(buildErrors, 'A2UI_COMPONENT_NOT_AVAILABLE', 'missing component contracts');
  });

  await test('projects the server Blueprint list without a client-owned code list', () => {
    const options = projectA2uiApplicationBlueprintOptions([
      {
        blueprintCode: 'server_owned_example',
        name: '服务端样例',
        description: '由后端枚举',
        catalogId: 'a2flow.digital-employee.pc.v1',
      },
    ]);
    assertEqual(options.length, 1, 'server Blueprint option count');
    assertEqual(options?.[0]?.blueprintCode, 'server_owned_example', 'server Blueprint code');
    assertThrows(
      () =>
        projectA2uiApplicationBlueprintOptions([
          { blueprintCode: 'duplicate', name: 'A', description: '', catalogId: 'catalog-1' },
          { blueprintCode: 'duplicate', name: 'B', description: '', catalogId: 'catalog-1' },
        ]),
      '唯一 code/name/catalogId',
      'duplicate server Blueprint code',
    );
  });

  await test('accepts only explicit server Action scan declarations and blockers', () => {
    const scan = projectA2uiApplicationActionScanResult({
      actionDeclarations: [
        {
          surfaceId: 'main',
          sourceComponentId: 'submit',
          actionCode: 'order.submit',
          contextTemplateDigest: 'sha256:context',
          discoveredFrom: [{ sourceType: 'A2UI_PASSTHROUGH', adapterId: 'result-1' }],
          status: 'UNBOUND',
        },
      ],
      validationErrors: [],
      releaseBlockers: ['A2UI_ACTION_UNBOUND'],
    });
    assertEqual(scan.actionDeclarations?.[0]?.status, 'UNBOUND', 'server scan declaration status');
    assertEqual(scan.releaseBlockers?.[0], 'A2UI_ACTION_UNBOUND', 'server release blocker');
    assertThrows(
      () => projectA2uiApplicationActionScanResult({ actionDeclarations: [] }),
      '缺少声明或阻塞数组',
      'incomplete Action scan projection',
    );
  });

  await test('fails closed when the Blueprint wire source omits catalogId', () => {
    const { catalogId: _catalogId, ...source } = toA2uiApplicationAuthoringPayload(
      applicationFixture(),
    );
    assertThrows(
      () => projectA2uiApplicationBlueprintWireSource(source as never),
      'Catalog ID',
      'missing Blueprint catalogId',
    );
    assertThrows(
      () => projectA2uiApplicationBlueprintWireSource({ ...source, catalogId: '  ' }),
      'Catalog ID',
      'blank Blueprint catalogId',
    );
  });

  await test('rejects Workflow-reserved events and bindings in ordinary Applications', () => {
    [
      'WORKFLOW_START',
      'WORKFLOW_SUBMIT',
      'WORKFLOW_RETRY',
      'WORKFLOW_SKIP',
      'WORKFLOW_STOP',
    ].forEach((actionCode) => {
      const application = applicationFixture();
      const message = application.showTemplate?.messageTemplates?.[1] as unknown as {
        updateComponents: { components: Array<{ action?: { event?: { name?: string } } }> };
      };
      const binding = application.actionBindings?.[0];
      if (!binding) throw new Error('missing reserved action binding fixture');
      message.updateComponents!.components![1]!.action!.event!.name = actionCode;
      binding.actionCode = actionCode;
      assertIncludes(
        validateA2uiApplicationBuild(application, [
          componentRecord('Column'),
          componentRecord('Button'),
        ]),
        'A2UI_WORKFLOW_ACTION_RESERVED',
        `${actionCode} rejection`,
      );
    });
  });

  await test('fails editor projection on malformed structured JSON', () => {
    const values = toA2uiApplicationFormValues(applicationFixture());
    values.showTemplateJson = '{invalid';
    values.actionBindingsJson = '{}';
    const parsed = parseA2uiApplicationForm(values);
    assertEqual(parsed.ok, false, 'invalid editor parse');
    assertIncludes(
      parsed.ok === false ? parsed.errors : [],
      'A2UI_SHOW_TEMPLATE_JSON_INVALID',
      'invalid show template JSON',
    );
    assertIncludes(
      parsed.ok === false ? parsed.errors : [],
      'A2UI_ACTION_BINDINGS_JSON_INVALID',
      'non-array action bindings JSON',
    );
  });

  await test('requires explicit NO_UI_MESSAGES or a closed adapter pipeline', () => {
    const noUiApplication = applicationFixture();
    const noUiBinding = noUiApplication.actionBindings?.[0];
    if (!noUiBinding) throw new Error('missing no-ui binding fixture');
    noUiBinding.successOutcome = 'NO_UI_MESSAGES';
    noUiBinding.resultAdapters = [];
    assertEqual(
      validateA2uiApplicationBuild(noUiApplication, [
        componentRecord('Column'),
        componentRecord('Button'),
      ])?.length,
      0,
      'explicit no-ui outcome errors',
    );

    const implicitEmpty = applicationFixture();
    const implicitBinding = implicitEmpty.actionBindings?.[0];
    if (!implicitBinding) throw new Error('missing implicit-empty binding fixture');
    implicitBinding.successOutcome = undefined;
    implicitBinding.resultAdapters = [];
    assertIncludes(
      validateA2uiApplicationBuild(implicitEmpty, [
        componentRecord('Column'),
        componentRecord('Button'),
      ]),
      'A2UI_RESULT_OUTCOME_REQUIRED',
      'implicit empty outcome rejection',
    );
  });

  await test('requires MESSAGE_TEMPLATE revision closure and rejects executable mapping fields', () => {
    const application = applicationFixture();
    const binding = application.actionBindings?.[0];
    if (!binding) throw new Error('missing closure binding fixture');
    const template = binding.resultAdapters?.find?.(
      (adapter) => adapter.type === 'MESSAGE_TEMPLATE',
    );
    if (!template) throw new Error('missing message template fixture');
    template.templateDigest = '';
    (binding.requestMappings?.[0] as unknown as Record<string, unknown>).script = 'return payload';
    const errors = validateA2uiApplicationBuild(application, [
      componentRecord('Column'),
      componentRecord('Button'),
    ]);
    assertIncludes(errors, 'A2UI_MESSAGE_TEMPLATE_CLOSURE_REQUIRED', 'template closure rejection');
    assertIncludes(errors, 'A2UI_MAPPING_FIELD_FORBIDDEN', 'mapping script rejection');
  });

  await test('locates validation errors at the authored JSON field', () => {
    const application = applicationFixture();
    application.actionBindings?.[0]?.requestMappings?.push?.({
      source: 'ACTION_CONTEXT',
      sourcePath: '$.userId',
      targetPath: '$.request.userId',
    });
    const issue = validateA2uiApplicationBuildIssues(application, [
      componentRecord('Column'),
      componentRecord('Button'),
    ])?.find?.((item) => item.code === 'A2UI_AUTHORITY_MAPPING_FORBIDDEN');
    assertEqual(
      issue?.path,
      '$.actionBindings[0].requestMappings[1].targetPath',
      'authority issue path',
    );
  });

  await test('expands the renderer-free preview through the expected Surface contract', () => {
    const preview = buildDetailedA2uiContractPreview(applicationFixture());
    assertEqual(preview.showInputBindings?.length, 1, 'show input binding count');
    assertEqual(preview.actionContexts?.[0]?.actionCode, 'order.confirm', 'action context code');
    assertEqual(
      preview.redactedMappedRequests?.[0]?.mappings?.[0]?.previewValue,
      '<action-payload>',
      'redacted action payload',
    );
    assertEqual(
      preview.capabilityMetaFixtures?.[0]?.status,
      'SUCCEEDED',
      'sanitized capability status',
    );
    assertEqual(
      preview.actionBindings?.[0]?.resultAdapters?.[0]?.type,
      'MESSAGE_TEMPLATE',
      'ordered preview adapters',
    );
    assertEqual(preview.expectedFinalSurface?.surfaceId, 'order-confirm-surface', 'final surface');
    assertEqual(preview.expectedFinalSurface?.componentCount, 2, 'final component count');
    assertEqual(
      preview.expectedFinalSurface?.dataModel?.orderId,
      'fixture-order',
      'final data model',
    );
  });

  await test('accepts only canonical mapping sources', () => {
    const application = applicationFixture();
    (
      application.actionBindings?.[0]?.requestMappings?.[0] as unknown as Record<string, unknown>
    ).source = 'ACTION_PAYLOAD';
    assertIncludes(
      validateA2uiApplicationBuild(application, [
        componentRecord('Column'),
        componentRecord('Button'),
      ]),
      'A2UI_MAPPING_SOURCE_INVALID',
      'legacy mapping source rejection',
    );
  });

  await test('accepts invocation APP_PARAMS for load and action request mappings', () => {
    const application = applicationFixture();
    application.showTemplate.paramsSchema = {
      type: 'object',
      properties: {
        dayZeroHourTimestamp: { type: 'integer' },
      },
      required: ['dayZeroHourTimestamp'],
    };
    application.loadBindings = [
      {
        bindingId: 'load-live-plan-config',
        capability: { actionCode: 'live.assistant.plan.config.get' },
        requestMappings: [
          {
            source: 'APP_PARAMS' as never,
            sourcePath: '/dayZeroHourTimestamp',
            targetPath: '/dayZeroHourTimestamp',
          },
        ],
        successOutcome: 'NO_UI_MESSAGES',
        failureOutcome: 'NO_UI_MESSAGES',
        resultAdapters: [],
        failureResultAdapters: [],
      },
    ];

    const loadErrors = validateA2uiApplicationBuild(application, [
      componentRecord('Column'),
      componentRecord('Button'),
    ]);
    assertEqual(
      loadErrors.includes('A2UI_LOAD_MAPPING_SOURCE_INVALID'),
      false,
      'APP_PARAMS load mapping source',
    );

    (
      application.actionBindings?.[0]?.requestMappings?.[0] as unknown as Record<string, unknown>
    ).source = 'APP_PARAMS';
    assertEqual(
      validateA2uiApplicationBuild(application, [
        componentRecord('Column'),
        componentRecord('Button'),
      ])?.includes?.('A2UI_MAPPING_SOURCE_INVALID'),
      false,
      'APP_PARAMS action mapping source',
    );

    (
      application.loadBindings?.[0]?.requestMappings?.[0] as unknown as Record<string, unknown>
    ).source = 'UNDECLARED_SOURCE';
    assertIncludes(
      validateA2uiApplicationBuild(application, [
        componentRecord('Column'),
        componentRecord('Button'),
      ]),
      'A2UI_LOAD_MAPPING_SOURCE_INVALID',
      'unknown load mapping source rejection',
    );
  });

  await test('does not author an A2UI side-effect or idempotency policy in ActionBinding', () => {
    const application = applicationFixture();
    const binding = application.actionBindings?.[0];
    if (!binding) throw new Error('missing action binding fixture');
    binding.failureOutcome = 'NO_UI_MESSAGES';
    binding.failureResultAdapters = [];
    const errors = validateA2uiApplicationBuild(application, [
      componentRecord('Column'),
      componentRecord('Button'),
    ]);
    assertEqual(errors.length, 0, 'ActionBinding without A2UI policy remains valid');
  });

  await test('requires a stable CapabilityAction actionCode and structured ResultAdapter contracts', () => {
    const application = applicationFixture();
    const binding = application.actionBindings?.[0];
    if (!binding) throw new Error('missing stable capability fixture');
    binding.capability.actionCode = '';
    const template = binding.resultAdapters?.find?.(
      (adapter) => adapter.type === 'MESSAGE_TEMPLATE',
    );
    if (!template) throw new Error('missing structured template fixture');
    (template as unknown as Record<string, unknown>).messages = [template.messageTemplate];
    template.messageTemplate = undefined;
    const passthrough = binding.resultAdapters?.find?.(
      (adapter) => adapter.type === 'A2UI_PASSTHROUGH',
    );
    if (!passthrough) throw new Error('missing passthrough fixture');
    passthrough.cardinality = undefined;
    const errors = validateA2uiApplicationBuild(application, [
      componentRecord('Column'),
      componentRecord('Button'),
    ]);
    assertIncludes(errors, 'A2UI_CAPABILITY_ACTION_CODE_REQUIRED', 'capability actionCode closure');
    assertIncludes(errors, 'A2UI_MESSAGE_TEMPLATE_REQUIRED', 'legacy messages rejection');
    assertIncludes(errors, 'A2UI_PASSTHROUGH_CARDINALITY_REQUIRED', 'passthrough cardinality');
  });

  await test('rejects unknown top-level fields in a server message', () => {
    const application = applicationFixture();
    const message = application.showTemplate?.messageTemplates?.[1] as Record<string, unknown>;
    message.debugMetadata = { trace: true };
    assertIncludes(
      validateA2uiApplicationBuild(application, [
        componentRecord('Column'),
        componentRecord('Button'),
      ]),
      'A2UI_SHOW_MESSAGE_FIELD_INVALID',
      'unknown message field rejection',
    );
    const issue = validateA2uiApplicationBuildIssues(application, [
      componentRecord('Column'),
      componentRecord('Button'),
    ])?.find?.((item) => item.code === 'A2UI_SHOW_MESSAGE_FIELD_INVALID');
    assertEqual(
      issue?.path,
      '$.showTemplate.messageTemplates',
      'unknown message field authored path',
    );
  });

  await test('rejects malformed flat components and wrong component origins', () => {
    const application = applicationFixture();
    const update = application.showTemplate?.messageTemplates?.[1]?.updateComponents as {
      components: Array<Record<string, unknown>>;
    };
    update.components?.push?.({ id: 'malformed-component' });
    const mismatchedButton = componentRecord('Button');
    mismatchedButton.componentOriginType = 'A2UI_OFFICIAL';
    const errors = validateA2uiApplicationBuild(application, [
      componentRecord('Column'),
      mismatchedButton,
    ]);
    assertIncludes(errors, 'A2UI_SHOW_COMPONENT_INVALID', 'malformed component rejection');
    assertIncludes(errors, 'A2UI_COMPONENT_NOT_AVAILABLE', 'component origin closure');
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
