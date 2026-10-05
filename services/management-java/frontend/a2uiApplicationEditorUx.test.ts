import { readFileSync } from 'node:fs';

import {
  A2UI_APPLICATION_EDITOR_STAGES,
  createA2uiApplicationEditorViewModel,
} from './a2uiApplicationEditorModel';
import {
  createEmptyA2uiApplicationDraft,
  type A2uiApplicationDraft,
} from './a2uiApplicationContracts';
import {
  parseA2uiApplicationForm,
  toA2uiApplicationFormValues,
  type A2uiApplicationFormParseResult,
  type A2uiApplicationFormValues,
} from './a2uiApplicationForm';

interface StageParseOptions {
  baseApplication: A2uiApplicationDraft;
  stage: 'basic' | 'show' | 'actions';
}

type StageAwareParser = (
  values: A2uiApplicationFormValues,
  options: StageParseOptions,
) => A2uiApplicationFormParseResult;

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

const failures: string[] = [];

function test(description: string, callback: () => void) {
  try {
    callback();
    console.log(`PASS ${description}`);
  } catch (reason) {
    const detail = reason instanceof Error ? reason.message : String(reason);
    failures.push(`${description}: ${detail}`);
    console.error(`FAIL ${description}: ${detail}`);
  }
}

function savedApplication(): A2uiApplicationDraft {
  const application = createEmptyA2uiApplicationDraft();
  application.appCode = 'order.confirm.application';
  application.nameCn = '订单确认';
  application.description = '已保存说明';
  application.catalog = {
    catalogId: 'a2flow.a2ui.basic',
    revision: '2026-08-24.1',
    digest: 'sha256:saved-catalog',
  };
  application.showTemplate = {
    ...application.showTemplate,
    templateCode: 'saved-show',
  };
  application.loadBindings = [
    {
      bindingId: 'saved-load',
      capability: { actionCode: 'order.load' },
      requestMappings: [],
      successOutcome: 'NO_UI_MESSAGES',
      failureOutcome: 'NO_UI_MESSAGES',
      resultAdapters: [],
      failureResultAdapters: [],
    },
  ];
  application.actionBindings = [];
  return application;
}

test('editor exposes five ordered mutually exclusive tabs with Basic Information first', () => {
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
  const view = createA2uiApplicationEditorViewModel({
    mode: 'create',
    availableComponentCount: 0,
    interactionGapCount: 0,
    validationIssueCount: 0,
  }) as ReturnType<typeof createA2uiApplicationEditorViewModel> & {
    saveableStageIds?: string[];
    authoringWorkbenchClassName?: string;
  };
  assertEqual(view.activeStage, 'basic', 'default active stage');
  assertDeepEqual(view.saveableStageIds, ['basic', 'show', 'actions'], 'saveable stages');
  assertEqual(
    view.authoringWorkbenchClassName,
    'skill-authoring-workbench a2ui-application-authoring-workbench',
    'latest shared authoring layout class',
  );
});

test('Basic Information save ignores pending Show and Action values', () => {
  const baseApplication = savedApplication();
  const values = toA2uiApplicationFormValues(baseApplication);
  values.nameCn = '订单确认新版';
  values.showTemplateJson = JSON.stringify({
    ...baseApplication.showTemplate,
    templateCode: 'pending-show',
  });
  values.actionBindingsJson = '{invalid pending action json';
  const result = (parseA2uiApplicationForm as unknown as StageAwareParser)(values, {
    baseApplication,
    stage: 'basic',
  });
  assertEqual(result.ok, true, 'basic stage parse');
  if (result.ok === false) return;
  assertEqual(result.application?.nameCn, '订单确认新版', 'saved basic name');
  assertEqual(
    result.application?.showTemplate?.templateCode,
    'saved-show',
    'saved ShowTemplate retained',
  );
  assertDeepEqual(
    result.application?.loadBindings,
    baseApplication.loadBindings,
    'saved LoadBindings retained',
  );
});

test('Show and Action saves merge only their owned fields', () => {
  const baseApplication = savedApplication();
  const showValues = toA2uiApplicationFormValues(baseApplication);
  showValues.nameCn = 'pending basic name';
  showValues.showTemplateJson = JSON.stringify({
    ...baseApplication.showTemplate,
    templateCode: 'saved-new-show',
  });
  showValues.actionBindingsJson = '{invalid pending action json';
  const showResult = (parseA2uiApplicationForm as unknown as StageAwareParser)(showValues, {
    baseApplication,
    stage: 'show',
  });
  assertEqual(showResult.ok, true, 'show stage parse');
  if (showResult.ok === false) return;
  assertEqual(
    showResult.application?.nameCn,
    baseApplication.nameCn,
    'pending Basic Information ignored',
  );
  assertEqual(
    showResult.application?.showTemplate?.templateCode,
    'saved-new-show',
    'ShowTemplate saved',
  );
  assertDeepEqual(
    showResult.application?.loadBindings,
    baseApplication.loadBindings,
    'pending Action fields ignored',
  );

  const actionValues = toA2uiApplicationFormValues(baseApplication);
  actionValues.showTemplateJson = '{invalid pending show json';
  actionValues.loadBindingsJson = '[]';
  actionValues.actionBindingsJson = '[]';
  const actionResult = (parseA2uiApplicationForm as unknown as StageAwareParser)(actionValues, {
    baseApplication,
    stage: 'actions',
  });
  assertEqual(actionResult.ok, true, 'actions stage parse');
  if (actionResult.ok === false) return;
  assertEqual(
    actionResult.application?.showTemplate?.templateCode,
    'saved-show',
    'pending ShowTemplate ignored',
  );
  assertDeepEqual(actionResult.application?.loadBindings, [], 'LoadBindings saved');
  assertDeepEqual(actionResult.application?.actionBindings, [], 'ActionBindings saved');
});

test('sample params are fillable session input and stay outside the canonical draft', () => {
  const baseApplication = savedApplication();
  const values = toA2uiApplicationFormValues(baseApplication) as A2uiApplicationFormValues & {
    sampleParamsJson?: string;
  };
  assertEqual(values.sampleParamsJson, '{}', 'default sample params input');
  values.sampleParamsJson = '{"orderId":"order-1"}';
  const result = (parseA2uiApplicationForm as unknown as StageAwareParser)(values, {
    baseApplication,
    stage: 'show',
  });
  assertEqual(result.ok, true, 'show stage save with sample params');
  if (result.ok === false) return;
  assertEqual(
    'sampleParams' in result.application,
    false,
    'sample params omitted from canonical draft',
  );
});

test('draft save does not require a published Catalog projection', () => {
  const pageSource = readFileSync(
    new URL('./A2uiApplicationEditorPage.tsx', import.meta.url),
    'utf8',
  );
  assertEqual(
    pageSource.includes('当前 Catalog 未满足发布、support 与 Host Profile 闭包，不能保存基础信息'),
    false,
    'draft save must not be gated by release closure',
  );
});

test('Action scan reads preserved values from every editor stage', () => {
  const pageSource = readFileSync(
    new URL('./A2uiApplicationEditorPage.tsx', import.meta.url),
    'utf8',
  );
  const readFormStart = pageSource.indexOf('const readFormApplication');
  const refreshPreviewStart = pageSource.indexOf('const handleRefreshPreview');
  const readFormSource = pageSource.slice(readFormStart, refreshPreviewStart);
  assertEqual(
    readFormSource.includes('form.getFieldsValue(true)'),
    true,
    'Action scan must retain unmounted Basic/Show values',
  );
});

test('ResultAdapter Catalog and CapabilityAction use server-projected searchable enums', () => {
  const pageSource = readFileSync(
    new URL('./A2uiApplicationEditorPage.tsx', import.meta.url),
    'utf8',
  );
  const actionEditorSource = readFileSync(
    new URL('./A2uiActionAuthoringEditor.tsx', import.meta.url),
    'utf8',
  );
  const createSurfaceStart = actionEditorSource.indexOf("{type === 'createSurface' ? (");
  const updateDataModelStart = actionEditorSource.indexOf(
    "type === 'updateDataModel'",
    createSurfaceStart,
  );
  const createSurfaceSource = actionEditorSource.slice(createSurfaceStart, updateDataModelStart);
  const capabilityValue = actionEditorSource.indexOf(
    'value={binding.capability?.actionCode || undefined}',
  );
  const capabilityStart = actionEditorSource.lastIndexOf('<Select', capabilityValue);
  const capabilityEnd = actionEditorSource.indexOf('<Paragraph type="secondary">', capabilityStart);
  const capabilitySource = actionEditorSource.slice(capabilityStart, capabilityEnd);

  assertEqual(
    /skillBindingCandidateApi\s*\.capabilityList\(\)/.test(pageSource),
    true,
    'reuse Skill candidate API',
  );
  assertEqual(
    pageSource.includes('catalogOptions={publishedCatalogSelectOptions}'),
    true,
    'pass published Catalog options',
  );
  assertEqual(
    pageSource.includes('capabilityActionOptions={capabilityActionSelectOptions}'),
    true,
    'pass CapabilityAction options',
  );
  assertEqual(createSurfaceSource.includes('<Select'), true, 'createSurface Catalog Select');
  assertEqual(
    createSurfaceSource.includes('<Input'),
    false,
    'createSurface Catalog is not free text',
  );
  assertEqual(capabilitySource.includes('<Select'), true, 'CapabilityAction Select');
  assertEqual(capabilitySource.includes('showSearch'), true, 'CapabilityAction fuzzy search');
  assertEqual(capabilitySource.includes('<Input'), false, 'CapabilityAction is not free text');
});

test('Action form exposes deterministic option projection and composer append effect', () => {
  const actionEditorSource = readFileSync(
    new URL('./A2uiActionAuthoringEditor.tsx', import.meta.url),
    'utf8',
  );
  assertEqual(
    actionEditorSource.includes('数组选项使用 ARRAY_OBJECT_TO_OPTIONS'),
    true,
    'result transform is visible and editable in structured Action form',
  );
  assertEqual(
    actionEditorSource.includes('聊天输入框回填（成功响应级）'),
    true,
    'composer effect has a structured editor',
  );
  assertEqual(
    actionEditorSource.includes("type: 'COMPOSER_DRAFT'") &&
      actionEditorSource.includes("mode: 'APPEND'") &&
      actionEditorSource.includes("source: 'CAPABILITY_DATA'"),
    true,
    'composer effect editor keeps the closed contract',
  );
  assertEqual(
    actionEditorSource.includes('不发送消息'),
    true,
    'composer effect copy states the no-send boundary',
  );
});

if (failures.length) {
  throw new Error(`A2UI editor UX contract failures:\n${failures.join('\n')}`);
}
