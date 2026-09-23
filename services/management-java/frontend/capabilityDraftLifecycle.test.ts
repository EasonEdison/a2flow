import {
  capabilityBasicInfoErrors,
  capabilityDraftWithSourceType,
  CAPABILITY_SOURCE_TYPE_OPTIONS,
  formatCapabilityDryRunResult,
  formatCapabilityDemoJson,
  createEmptyCapabilityDraft,
  hasPassedCapabilityDryRun,
  loadPersistedCapabilityDraft,
  persistCapabilityDraft,
  registerCapabilityDraftWithName,
  runCapabilityDryRun,
  supportsCapabilityDirectDryRun,
  stripUnusedCapabilityDraftFields,
  uniqueCapabilityValidationMessages,
  visibleCapabilityDrafts,
} from './capabilityDraftLifecycle';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const TEST_CLASSIFICATION = {
  businessDomain: '直播经营',
  capabilityDomain: '计划创建',
  specialistIds: ['100001'],
};

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

async function test(description: string, callback: () => void | Promise<void>) {
  await callback();
  console.log(`PASS ${description}`);
}

async function main() {
  await test('opening the registration route keeps a local draft and does not persist anything', async () => {
    let detailCalls = 0;
    const loaded = await loadPersistedCapabilityDraft('', async () => {
      detailCalls += 1;
      throw new Error('new registration must not request a persisted draft');
    });

    assertEqual(loaded, undefined, 'new registration persisted detail');
    assertEqual(detailCalls, 0, 'new registration detail calls');
    assertEqual(
      createEmptyCapabilityDraft()?.apiSource?.sourceType,
      'GRPC',
      'default API source',
    );
  });

  await test('RPC draft preserves service identity, protocol and mappings', async () => {
    const draft = createEmptyCapabilityDraft();
    draft.executionBinding.target = { targetKey: 'orders', serviceName: 'a2flow.Orders', methodName: 'Query', descriptorSetBase64: 'ZGVzY3JpcHRvcg==', contextField: 'context' };
    draft.executionBinding.requestMappingsJson = '{"id":"order_id"}';
    const rpc = capabilityDraftWithSourceType(draft, 'GRPC');
    assertEqual(rpc.executionBinding.bindingType, 'GRPC', 'binding');
    assertEqual(rpc.executionBinding.target?.serviceName, 'a2flow.Orders', 'service retained');
    assertEqual(rpc.executionBinding.target?.descriptorSetBase64, 'ZGVzY3JpcHRvcg==', 'descriptor retained');
    assertEqual(rpc.executionBinding.requestMappingsJson, '{"id":"order_id"}', 'mapping retained');
    assertEqual(supportsCapabilityDirectDryRun('GRPC'), true, 'RPC validation enabled');
    assertEqual(CAPABILITY_SOURCE_TYPE_OPTIONS.length, 1, 'only RPC source');
    assertEqual(CAPABILITY_SOURCE_TYPE_OPTIONS[0].value, 'GRPC', 'RPC option');
  });

  await test('legacy source, binding and credential configuration are rejected, never migrated', async () => {
    for (const source of ['HTTP_REQUEST', 'API_CENTER', 'LOCAL_METHOD', 'KRPC']) {
      let rejected = false;
      try { capabilityDraftWithSourceType(createEmptyCapabilityDraft(), source); } catch { rejected = true; }
      assertEqual(rejected, true, source + ' rejected');
    }
    for (const patch of [
      { bindingType: 'CONTROLLED_HTTP' },
      { authMode: 'NONE' as const },
      { target: { registeredUrl: 'https://example.invalid' } },
      { staticHeadersJson: '{}' },
      { environmentHeadersJson: '{}' },
    ]) {
      const draft = createEmptyCapabilityDraft();
      draft.executionBinding = { ...draft.executionBinding, ...patch } as unknown as typeof draft.executionBinding;
      let rejected = false;
      try { capabilityDraftWithSourceType(draft, 'GRPC'); } catch { rejected = true; }
      assertEqual(rejected, true, 'old transport field rejected');
    }
  });

  await test('registration confirmation persists one trimmed named draft before opening the editor', async () => {
    let createCalls = 0;
    let createdName = '';
    let openedDraftId = '';
    const created = await registerCapabilityDraftWithName({
      nameCn: '  查询直播计划关联商品  ',
      create: async (draft) => {
        createCalls += 1;
        createdName = draft.basicInfo?.nameCn || '';
        return {
          draftId: 'cap_draft_named',
          revision: 1,
          status: 'DRAFT',
          draft,
        };
      },
      openEditor: (draftId) => {
        openedDraftId = draftId;
      },
    });

    assertEqual(createCalls, 1, 'minimal create call count');
    assertEqual(createdName, '查询直播计划关联商品', 'trimmed Chinese name');
    assertEqual(created.draft?.basicInfo?.actionCode, undefined, 'unfabricated actionCode');
    assertEqual(openedDraftId, 'cap_draft_named', 'opened persisted draft id');
  });

  await test('blank registration name creates nothing and does not open the editor', async () => {
    let createCalls = 0;
    let openCalls = 0;
    let errorMessage = '';
    try {
      await registerCapabilityDraftWithName({
        nameCn: '   ',
        create: async (draft) => {
          createCalls += 1;
          return { draftId: 'unexpected', revision: 1, status: 'DRAFT', draft };
        },
        openEditor: () => {
          openCalls += 1;
        },
      });
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : String(error);
    }

    assertEqual(errorMessage, '请填写中文名称', 'required registration name');
    assertEqual(createCalls, 0, 'blank registration create calls');
    assertEqual(openCalls, 0, 'blank registration open calls');
  });

  await test('opening an edit route loads the requested persisted draft', async () => {
    const loaded = await loadPersistedCapabilityDraft('cap_draft_existing', async (draftId) => ({
      draftId,
      revision: 3,
      status: 'DRAFT',
      draft: createEmptyCapabilityDraft(),
    }));

    assertEqual(loaded?.draftId, 'cap_draft_existing', 'loaded draft id');
    assertEqual(loaded?.revision, 3, 'loaded revision');
  });

  await test('first valid save creates the capability with the completed form in one request', async () => {
    const draft = createEmptyCapabilityDraft();
    draft.basicInfo.actionCode = 'live.plan.create';
    let createdDraft: unknown;
    let saveCalls = 0;
    const created = await persistCapabilityDraft({
      draftId: '',
      revision: 0,
      draft,
      classification: TEST_CLASSIFICATION,
      create: async (payload) => {
        createdDraft = payload;
        return { draftId: 'cap_draft_created', revision: 1, status: 'DRAFT', draft: payload };
      },
      save: async () => {
        saveCalls += 1;
        throw new Error('new capability must use create with its form payload');
      },
    });

    assertEqual(created.draftId, 'cap_draft_created', 'created draft id');
    assertEqual(createdDraft, draft, 'created form payload');
    assertEqual(saveCalls, 0, 'save calls during first persistence');
  });

  await test('blank actionCode never creates an orphan draft', async () => {
    let createCalls = 0;
    let errorMessage = '';
    try {
      await persistCapabilityDraft({
        draftId: '',
        revision: 0,
        draft: createEmptyCapabilityDraft(),
        classification: TEST_CLASSIFICATION,
        create: async (payload) => {
          createCalls += 1;
          return { draftId: 'unexpected', revision: 1, status: 'DRAFT', draft: payload };
        },
        save: async () => {
          throw new Error('save must not run');
        },
      });
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : String(error);
    }

    assertEqual(errorMessage, '请先填写 actionCode', 'blank actionCode validation');
    assertEqual(createCalls, 0, 'blank actionCode create calls');
  });

  await test('basic stage reports all required fields before saving', () => {
    const errors = capabilityBasicInfoErrors(createEmptyCapabilityDraft());

    assertEqual(Object.keys(errors).length, 4, 'required basic field count');
    assertEqual(errors.actionCode, '请填写 actionCode', 'actionCode error');
    assertEqual(errors.nameCn, '请填写中文名', 'name error');
    assertEqual(errors.technicalOwner, '请填写技术负责人', 'technical owner error');
    assertEqual(errors.description, '请填写业务描述', 'description error');
  });

  await test('basic stage required fields accept trimmed values', () => {
    const draft = createEmptyCapabilityDraft();
    draft.basicInfo = {
      actionCode: ' home.overview.query ',
      nameCn: ' 首页概览查询 ',
      technicalOwner: ' owner ',
      description: ' 查询首页经营概览 ',
    };

    assertEqual(Object.keys(capabilityBasicInfoErrors(draft)).length, 0, 'complete basic fields');
  });

  await test('editing an existing capability saves against its current revision', async () => {
    const draft = createEmptyCapabilityDraft();
    draft.basicInfo.actionCode = 'live.plan.create';
    let saveArguments = '';
    await persistCapabilityDraft({
      draftId: 'cap_draft_existing',
      revision: 4,
      draft,
      classification: TEST_CLASSIFICATION,
      create: async () => {
        throw new Error('existing capability must not be created again');
      },
      save: async (draftId, revision, payload) => {
        saveArguments = `${draftId}:${revision}:${payload.basicInfo?.actionCode}`;
        return { draftId, revision: revision + 1, status: 'DRAFT', draft: payload };
      },
    });

    assertEqual(saveArguments, 'cap_draft_existing:4:live.plan.create', 'existing save arguments');
  });

  await test('capability list keeps named unfinished drafts and hides only unnamed historical orphans', () => {
    const validDraft = createEmptyCapabilityDraft();
    validDraft.basicInfo.actionCode = 'live.plan.create';
    const namedDraft = createEmptyCapabilityDraft();
    namedDraft.basicInfo.nameCn = '查询直播计划关联商品';
    const items = visibleCapabilityDrafts([
      { draftId: 'orphan_1', revision: 1, status: 'DRAFT', draft: createEmptyCapabilityDraft() },
      {
        draftId: 'orphan_2',
        revision: 1,
        status: 'DRAFT',
        draft: { ...createEmptyCapabilityDraft(), basicInfo: { actionCode: '   ' } },
      },
      { draftId: 'named', revision: 1, status: 'DRAFT', draft: namedDraft },
      { draftId: 'valid', revision: 1, status: 'DRAFT', draft: validDraft },
    ]);

    assertEqual(items.length, 2, 'visible capability count');
    assertEqual(items?.[0]?.draftId, 'named', 'named unfinished capability id');
    assertEqual(items?.[1]?.draftId, 'valid', 'identified capability id');
  });

  await test('canonical capability drafts omit unused owner and API Center identity fields', () => {
    const legacyDraft = createEmptyCapabilityDraft();
    (legacyDraft as unknown as Record<string, unknown>).schemaVersion = 'capabilityActionDraft.v1';
    (legacyDraft.basicInfo as Record<string, unknown>).businessOwner = 'legacy-product-owner';
    (legacyDraft.apiSource as Record<string, unknown>).serviceDefinitionId =
      'legacy-service-definition-id';
    (legacyDraft.apiSource as Record<string, unknown>).apiCenterId = 'legacy-api-center-id';
    (legacyDraft.resultContract as Record<string, unknown>).modelSummaryTemplate = 'legacy summary';
    (legacyDraft.resultContract as Record<string, unknown>).interaction = 'legacy interaction';
    (legacyDraft.governance as Record<string, unknown>).requiredReviews = 'legacy reviews';

    const canonicalDraft = stripUnusedCapabilityDraftFields(legacyDraft);
    assertEqual(
      Object.prototype.hasOwnProperty.call(canonicalDraft, 'schemaVersion'),
      false,
      'schemaVersion presence',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(canonicalDraft.basicInfo, 'businessOwner'),
      false,
      'businessOwner presence',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(canonicalDraft.apiSource, 'serviceDefinitionId'),
      false,
      'serviceDefinitionId presence',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(canonicalDraft.apiSource, 'apiCenterId'),
      false,
      'apiCenterId presence',
    );
    assertEqual(canonicalDraft.apiSource?.sourceType, 'GRPC', 'preserved API source');
    assertEqual(
      Object.prototype.hasOwnProperty.call(canonicalDraft.resultContract, 'modelSummaryTemplate'),
      false,
      'modelSummaryTemplate presence',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(canonicalDraft.resultContract, 'interaction'),
      false,
      'interaction presence',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(canonicalDraft.governance, 'requiredReviews'),
      false,
      'requiredReviews presence',
    );
  });

  await test('demo JSON can be expanded and collapsed without changing data', () => {
    const compact = '{"timeRange":"ONE_DAY","filters":{"active":true}}';
    const expanded = formatCapabilityDemoJson(compact, true);
    assertEqual(expanded.includes('\n  "timeRange"'), true, 'expanded indentation');
    assertEqual(formatCapabilityDemoJson(expanded, false), compact, 'collapsed JSON');
  });

  await test('dry-run result JSON preserves the complete Tool result wrapper', () => {
    const result = {
      success: true,
      actionCode: 'home.overview.query',
      capabilityVersion: 7,
      requestedEnvironment: 'PRT',
      resolvedEnvironment: 'PRT',
      httpStatus: 200,
      contentType: 'application/json',
      traceId: 'capability_dry_run_trace',
      data: { result: 1, data: [{ payAmt: 123 }] },
    };

    const expanded = formatCapabilityDryRunResult(result, true);
    assertEqual(expanded.includes('\n  "success": true'), true, 'expanded Tool result status');
    assertEqual(
      expanded.includes('"traceId": "capability_dry_run_trace"'),
      true,
      'Tool result trace',
    );
    assertEqual(expanded.includes('"payAmt": 123'), true, 'Tool result data');
    assertEqual(
      JSON.stringify(JSON.parse(formatCapabilityDryRunResult(result, false))),
      JSON.stringify(result),
      'collapsed Tool result wrapper',
    );
  });

  await test('direct dry-run consumption stays transient and never patches responseDemoJson', () => {
    const pageSource = readFileSync(
      resolve(process.cwd(), 'CapabilityActionAuthoringPage.tsx'),
      'utf8',
    );
    const handlerSource = pageSource.slice(
      pageSource.indexOf('  const executeDryRun = async'),
      pageSource.indexOf('  const applyPendingReview = () => {'),
    );

    assertEqual(
      handlerSource.includes('setDryRunResult(result)'),
      true,
      'transient Tool result state',
    );
    assertEqual(
      handlerSource.includes("updateSection('resultContract'"),
      false,
      'responseDemoJson mutation',
    );
    assertEqual(handlerSource.includes('响应已回填'), false, 'response backfill success message');
  });

  await test('legacy Cookie auth blocks save and API execution without downgrade', async () => {
    let saveCalls = 0;
    let executeCalls = 0;
    let errorMessage = '';
    try {
      await runCapabilityDryRun({
        authMode: 'TRUSTED_COOKIE',
        save: async () => {
          saveCalls += 1;
          return { draftId: 'should-not-save' };
        },
        execute: async () => {
          executeCalls += 1;
        },
      });
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : String(error);
    }

    assertEqual(errorMessage, '不支持旧 Cookie 鉴权，请重新登记能力；不会自动降级鉴权', 'unsupported auth message');
    assertEqual(saveCalls, 0, 'blank credential save calls');
    assertEqual(executeCalls, 0, 'blank credential API calls');
  });

  await test('validation messages are de-duplicated with errors taking priority', () => {
    const messages = uniqueCapabilityValidationMessages({
      draftId: 'cap_draft_validation',
      revision: 3,
      valid: false,
      status: 'INVALID',
      errors: ['技术负责人不能为空。', '关键字段不能为空。'],
      warnings: ['仅完成静态校验。', '技术负责人不能为空。'],
      publishBlockers: ['技术负责人不能为空。', '缺少验证 API 证据。'],
      validatedAt: 1,
    });

    assertEqual(messages.length, 4, 'unique message count');
    assertEqual(messages?.[0]?.kind, 'error', 'duplicate keeps error priority');
    assertEqual(messages?.[0]?.message, '技术负责人不能为空。', 'duplicate message');
  });

  await test('current digest client dry-run gate is the only reusable API validation signal', () => {
    assertEqual(
      hasPassedCapabilityDryRun(
        {
          currentSnapshot: {
            assetType: 'CAPABILITY_ACTION',
            assetKey: 'cap_draft',
            digest: 'digest',
            summary: {},
          },
          builds: [],
          versions: [],
          deployments: [],
          environments: {},
          gates: [
            {
              code: 'CAPABILITY_DRY_RUN_PC',
              label: '验证 PC API',
              status: 'PASSED',
              required: true,
              message: 'PRT API 验证通过',
            },
          ],
          allowedActions: [],
          blockedReasons: [],
        },
        'PRT',
        'PC',
      ),
      true,
      'passed PC PRT dry-run gate',
    );
    assertEqual(
      hasPassedCapabilityDryRun(
        {
          currentSnapshot: {
            assetType: 'CAPABILITY_ACTION',
            assetKey: 'cap_draft',
            digest: 'changed',
            summary: {},
          },
          builds: [],
          versions: [],
          deployments: [],
          environments: {},
          gates: [
            {
              code: 'CAPABILITY_DRY_RUN_ONLINE_APP',
              label: '验证 APP ONLINE API',
              status: 'EXPIRED',
              required: true,
              message: '摘要已变化',
            },
          ],
          allowedActions: [],
          blockedReasons: [],
        },
        'ONLINE',
        'APP',
      ),
      false,
      'expired APP ONLINE dry-run gate',
    );
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
