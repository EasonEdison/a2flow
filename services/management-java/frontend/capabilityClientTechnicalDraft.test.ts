import { createEmptyCapabilityDraft } from './capabilityDraftLifecycle';
import {
  applyCapabilityTechnicalVariant,
  buildCapabilityClientCanonicalDraft,
  selectCapabilityClientTechnicalDraft,
  splitCapabilityClientCanonicalDraft,
  updateCapabilityClientTechnicalSection,
} from './capabilityClientTechnicalDraft';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function test(description: string, callback: () => void) {
  callback();
  console.log(`PASS ${description}`);
}

test('APP uses its independent technical draft instead of copying the PC contract', () => {
  const canonicalDraft = createEmptyCapabilityDraft();
  canonicalDraft.modelContract.description = 'PC 参数契约';
  const appPreviewDraft = createEmptyCapabilityDraft();
  appPreviewDraft.modelContract.description = 'APP 参数契约';
  const commonPreviewDraft = createEmptyCapabilityDraft();
  commonPreviewDraft.modelContract.description = '通用参数契约';

  assertEqual(
    selectCapabilityClientTechnicalDraft(
      'APP',
      canonicalDraft,
      appPreviewDraft,
      commonPreviewDraft,
    ),
    appPreviewDraft,
    'APP selected draft',
  );
  assertEqual(
    selectCapabilityClientTechnicalDraft('PC', canonicalDraft, appPreviewDraft, commonPreviewDraft),
    canonicalDraft,
    'PC selected draft',
  );
  assertEqual(
    selectCapabilityClientTechnicalDraft(
      'COMMON',
      canonicalDraft,
      appPreviewDraft,
      commonPreviewDraft,
    ),
    commonPreviewDraft,
    'COMMON selected draft',
  );
});

test('APP technical edits do not mutate or replace the PC canonical contract', () => {
  const canonicalDraft = createEmptyCapabilityDraft();
  canonicalDraft.modelContract.description = 'PC 参数契约';
  const appPreviewDraft = createEmptyCapabilityDraft();
  const commonPreviewDraft = createEmptyCapabilityDraft();

  const result = updateCapabilityClientTechnicalSection(
    'APP',
    canonicalDraft,
    appPreviewDraft,
    commonPreviewDraft,
    'modelContract',
    { description: 'APP 参数契约' },
  );

  assertEqual(result.canonicalDraft, canonicalDraft, 'PC draft identity');
  assertEqual(result.canonicalDraft?.modelContract?.description, 'PC 参数契约', 'PC content');
  assertEqual(result.appPreviewDraft?.modelContract?.description, 'APP 参数契约', 'APP content');
  assertEqual(
    appPreviewDraft.modelContract?.description,
    undefined,
    'original APP preview remains immutable',
  );
});

test('PC technical edits leave the APP browser preview untouched', () => {
  const canonicalDraft = createEmptyCapabilityDraft();
  const appPreviewDraft = createEmptyCapabilityDraft();
  appPreviewDraft.executionBinding.target = { targetKey: 'app-orders', serviceName: 'a2flow.AppOrders' };
  const commonPreviewDraft = createEmptyCapabilityDraft();

  const result = updateCapabilityClientTechnicalSection(
    'PC',
    canonicalDraft,
    appPreviewDraft,
    commonPreviewDraft,
    'executionBinding',
    { timeoutMs: 5000 },
  );

  assertEqual(result.canonicalDraft?.executionBinding?.timeoutMs, 5000, 'PC timeout');
  assertEqual(result.appPreviewDraft, appPreviewDraft, 'APP preview identity');
  assertEqual(
    result.appPreviewDraft?.executionBinding?.target?.targetKey,
    'app-orders',
    'APP target',
  );
});

test('save emits exact PC and APP variants without legacy root technical fields', () => {
  const pcDraft = createEmptyCapabilityDraft();
  pcDraft.modelContract.description = 'PC 参数契约';
  const appDraft = createEmptyCapabilityDraft();
  appDraft.modelContract.description = 'APP 参数契约';

  const commonDraft = createEmptyCapabilityDraft();
  const saved = buildCapabilityClientCanonicalDraft(pcDraft, appDraft, commonDraft, ['PC', 'APP']);
  const root = saved as unknown as Record<string, unknown>;

  assertEqual(saved.supportedClients?.join(','), 'PC,APP', 'supported client order');
  assertEqual(saved.clientVariants?.PC?.modelContract?.description, 'PC 参数契约', 'PC variant');
  assertEqual(saved.clientVariants?.APP?.modelContract?.description, 'APP 参数契约', 'APP variant');
  assertEqual(
    Object.prototype.hasOwnProperty.call(root, 'modelContract'),
    false,
    'no root model contract',
  );
  assertEqual(Object.prototype.hasOwnProperty.call(root, 'apiSource'), false, 'no root API source');
  assertEqual(
    Object.prototype.hasOwnProperty.call(root, 'executionBinding'),
    false,
    'no root binding',
  );
  assertEqual(
    Object.prototype.hasOwnProperty.call(root, 'resultContract'),
    false,
    'no root result contract',
  );
});

test('common mode saves only an independently authored COMMON variant', () => {
  const pcDraft = createEmptyCapabilityDraft();
  pcDraft.modelContract.description = 'PC 参数契约';
  const appDraft = createEmptyCapabilityDraft();
  appDraft.modelContract.description = 'APP 参数契约';
  const commonDraft = createEmptyCapabilityDraft();
  commonDraft.modelContract.description = '通用参数契约';

  const saved = buildCapabilityClientCanonicalDraft(pcDraft, appDraft, commonDraft, ['COMMON']);

  assertEqual(saved.supportedClients?.join(','), 'COMMON', 'COMMON supported shape');
  assertEqual(
    saved.clientVariants?.COMMON?.modelContract?.description,
    '通用参数契约',
    'COMMON variant',
  );
  assertEqual(saved.clientVariants?.PC, undefined, 'PC variant omitted');
  assertEqual(saved.clientVariants?.APP, undefined, 'APP variant omitted');
});

test('COMMON edits do not copy or mutate PC and APP contracts', () => {
  const pcDraft = createEmptyCapabilityDraft();
  pcDraft.modelContract.description = 'PC 参数契约';
  const appDraft = createEmptyCapabilityDraft();
  appDraft.modelContract.description = 'APP 参数契约';
  const commonDraft = createEmptyCapabilityDraft();

  const result = updateCapabilityClientTechnicalSection(
    'COMMON',
    pcDraft,
    appDraft,
    commonDraft,
    'modelContract',
    { description: '通用参数契约' },
  );

  assertEqual(result.canonicalDraft?.modelContract?.description, 'PC 参数契约', 'PC untouched');
  assertEqual(result.appPreviewDraft?.modelContract?.description, 'APP 参数契约', 'APP untouched');
  assertEqual(
    result.commonPreviewDraft?.modelContract?.description,
    '通用参数契约',
    'COMMON updated',
  );
});

test('missing APP variant initializes an empty technical contract instead of inheriting PC', () => {
  const commonDraft = createEmptyCapabilityDraft();
  commonDraft.modelContract.description = 'PC 参数契约';

  const appDraft = applyCapabilityTechnicalVariant(commonDraft);

  assertEqual(
    appDraft.modelContract?.description,
    undefined,
    'APP does not inherit PC model contract',
  );
  assertEqual(
    appDraft.executionBinding?.target?.targetKey,
    undefined,
    'APP does not inherit PC target',
  );
});

test('canonical reviewed patch restores independent PC and APP drafts', () => {
  const pcDraft = createEmptyCapabilityDraft();
  pcDraft.modelContract.description = 'AI 修改后的 PC 参数契约';
  const appDraft = createEmptyCapabilityDraft();
  appDraft.modelContract.description = 'AI 修改后的 APP 参数契约';
  const commonDraft = createEmptyCapabilityDraft();
  const reviewedCanonical = buildCapabilityClientCanonicalDraft(pcDraft, appDraft, commonDraft, [
    'PC',
    'APP',
  ]);

  const restored = splitCapabilityClientCanonicalDraft(
    reviewedCanonical,
    createEmptyCapabilityDraft(),
  );

  assertEqual(restored.clientMode, 'PC_APP_DIFFERENT', 'client mode');
  assertEqual(
    restored.canonicalDraft?.modelContract?.description,
    'AI 修改后的 PC 参数契约',
    'PC reviewed patch',
  );
  assertEqual(
    restored.appDraft?.modelContract?.description,
    'AI 修改后的 APP 参数契约',
    'APP reviewed patch',
  );
  assertEqual(
    restored.commonDraft?.modelContract?.description,
    undefined,
    'COMMON remains independent',
  );
});
