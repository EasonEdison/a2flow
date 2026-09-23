import { readFileSync } from 'node:fs';

import {
  createEmptyA2uiApplicationDraft,
  toA2uiApplicationAuthoringPayload,
  validateA2uiApplicationBuild,
  type A2uiActionBinding,
  type A2uiApplicationDraft,
} from './a2uiApplicationContracts';
import {
  parseA2uiApplicationForm,
  toA2uiApplicationFormValues,
  type A2uiApplicationFormValues,
} from './a2uiApplicationForm';

type InteractionMode = 'DISPLAY_ONLY' | 'INTERACTIVE';
type InteractionDraft = A2uiApplicationDraft & { interactionMode?: InteractionMode };

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

function actionBinding(complete: boolean): A2uiActionBinding {
  const binding = {
    bindingId: 'save-binding',
    surfaceId: 'main',
    sourceComponentId: 'save-button',
    actionCode: 'live.assistant.plan.save',
    allowedSourceComponentIds: ['save-button'],
    contextSchema: { type: 'object', properties: {} },
    capability: { actionCode: 'live.assistant.plan.save' },
    requestMappings: [],
    successOutcome: 'NO_UI_MESSAGES',
    failureOutcome: 'NO_UI_MESSAGES',
    resultAdapters: [],
    failureResultAdapters: [],
    completeWorkflowInteractionOnSuccess: complete,
  } as A2uiActionBinding;
  if (complete) {
    (binding as unknown as Record<string, unknown>).businessSuccessPredicate = {
      version: 'JSON_POINTER_V1',
      allOf: [
        {
          source: 'CAPABILITY_DATA',
          sourcePath: '/result',
          operator: 'EQUALS',
          expectedValue: 1,
        },
        {
          source: 'CAPABILITY_DATA',
          sourcePath: '/planId',
          operator: 'GREATER_THAN',
          expectedValue: 0,
        },
      ],
    };
  }
  return binding;
}

function interactionDraft(mode: InteractionMode, complete: boolean): InteractionDraft {
  const draft = createEmptyA2uiApplicationDraft() as InteractionDraft;
  draft.appCode = 'a2ui_live_plan_creator';
  draft.nameCn = '创建直播计划';
  draft.catalog.catalogId = 'a2flow-managed-basic.catalog';
  draft.interactionMode = mode;
  draft.actionBindings = [actionBinding(complete)];
  return draft;
}

test('canonical empty draft and write payload freeze explicit interaction defaults', () => {
  const draft = createEmptyA2uiApplicationDraft() as InteractionDraft;
  draft.actionBindings = [actionBinding(false)];
  const payload = toA2uiApplicationAuthoringPayload(draft) as unknown as Record<string, unknown>;
  const binding = (payload.actionBindings as Array<Record<string, unknown>>)?.[0];

  assertEqual(draft.interactionMode, 'DISPLAY_ONLY', 'empty draft interactionMode');
  assertEqual(payload.interactionMode, 'DISPLAY_ONLY', 'wire interactionMode');
  assertEqual(binding?.completeWorkflowInteractionOnSuccess, false, 'wire completion flag');
});

test('Basic save owns interactionMode and ignores pending Action JSON', () => {
  const baseApplication = interactionDraft('DISPLAY_ONLY', false);
  const values = toA2uiApplicationFormValues(baseApplication);
  values.interactionMode = 'INTERACTIVE';
  values.actionBindingsJson = '{pending invalid action json';
  const result = parseA2uiApplicationForm(values, { baseApplication, stage: 'basic' });

  assertEqual(result.ok, true, 'Basic parse result');
  if (result.ok === false) return;
  assertEqual(
    (result.application as InteractionDraft)?.interactionMode,
    'INTERACTIVE',
    'saved Basic interactionMode',
  );
  assertEqual(
    (result.application?.actionBindings?.[0] as unknown as Record<string, unknown>)
      ?.completeWorkflowInteractionOnSuccess,
    false,
    'pending Action value ignored',
  );
});

test('unknown interactionMode fails closed in the Basic form', () => {
  const baseApplication = interactionDraft('DISPLAY_ONLY', false);
  const values = toA2uiApplicationFormValues(baseApplication);
  (values as unknown as { interactionMode: string }).interactionMode = 'AUTO';
  const result = parseA2uiApplicationForm(values, { baseApplication, stage: 'basic' });

  assertEqual(result.ok, false, 'unknown interactionMode parse result');
  if (result.ok === true) return;
  assertIncludes(
    result.errors,
    'A2UI_APPLICATION_INTERACTION_MODE_INVALID',
    'unknown interactionMode error',
  );
});

test('local validation explains both invalid Workflow interaction combinations', () => {
  const interactiveErrors = validateA2uiApplicationBuild(
    interactionDraft('INTERACTIVE', false),
    [],
  );
  const displayOnlyErrors = validateA2uiApplicationBuild(
    interactionDraft('DISPLAY_ONLY', true),
    [],
  );
  const validInteractiveErrors = validateA2uiApplicationBuild(
    interactionDraft('INTERACTIVE', true),
    [],
  );

  assertIncludes(
    interactiveErrors,
    'A2UI_INTERACTIVE_COMPLETION_ACTION_REQUIRED',
    'INTERACTIVE completion requirement',
  );
  assertIncludes(
    displayOnlyErrors,
    'A2UI_DISPLAY_ONLY_COMPLETION_ACTION_FORBIDDEN',
    'DISPLAY_ONLY completion prohibition',
  );
  assertEqual(
    validInteractiveErrors.includes('A2UI_INTERACTIVE_COMPLETION_ACTION_REQUIRED'),
    false,
    'valid INTERACTIVE combination',
  );
});

test('authoring wire preserves the versioned business success predicate', () => {
  const payload = toA2uiApplicationAuthoringPayload(
    interactionDraft('INTERACTIVE', true),
  ) as unknown as Record<string, unknown>;
  const binding = (payload.actionBindings as Array<Record<string, unknown>>)?.[0];
  const predicate = binding?.businessSuccessPredicate as Record<string, unknown> | undefined;

  assertEqual(predicate?.version, 'JSON_POINTER_V1', 'wire predicate version');
  assertEqual(
    (predicate?.allOf as unknown[] | undefined)?.length,
    2,
    'wire predicate clause count',
  );
});

test('completing Binding requires a valid closed business success predicate', () => {
  const missing = interactionDraft('INTERACTIVE', true);
  delete (missing.actionBindings?.[0] as unknown as Record<string, unknown>)
    ?.businessSuccessPredicate;
  assertIncludes(
    validateA2uiApplicationBuild(missing, []),
    'A2UI_BUSINESS_SUCCESS_PREDICATE_REQUIRED',
    'missing predicate error',
  );

  const invalid = interactionDraft('INTERACTIVE', true);
  const predicate = (invalid.actionBindings?.[0] as unknown as Record<string, unknown>)
    ?.businessSuccessPredicate as Record<string, unknown>;
  predicate.version = 'SCRIPT_V1';
  assertIncludes(
    validateA2uiApplicationBuild(invalid, []),
    'A2UI_BUSINESS_SUCCESS_PREDICATE_INVALID',
    'invalid predicate error',
  );
});

test('editor exposes Application mode and per-Binding completion controls', () => {
  const pageSource = readFileSync(
    new URL('./A2uiApplicationEditorPage.tsx', import.meta.url),
    'utf8',
  );
  const actionSource = readFileSync(
    new URL('./A2uiActionAuthoringEditor.tsx', import.meta.url),
    'utf8',
  );

  assertEqual(pageSource.includes('name="interactionMode"'), true, 'Application mode control');
  assertEqual(
    actionSource.includes('completeWorkflowInteractionOnSuccess'),
    true,
    'Binding completion control',
  );
  assertEqual(actionSource.includes('成功后完成 Workflow 交互'), true, 'Binding completion label');
  assertEqual(
    actionSource.includes('businessSuccessPredicate'),
    true,
    'Binding business predicate control',
  );
  assertEqual(actionSource.includes('业务成功判定'), true, 'Binding business predicate label');
  assertEqual(
    /\[\s*'ACTION_CONTEXT',\s*'APP_PARAMS'/.test(actionSource),
    true,
    'Action mapping APP_PARAMS option',
  );
});

if (failures.length) {
  throw new Error(`A2UI Workflow interaction contract failures:\n${failures.join('\n')}`);
}
