import {
  SkillFactoryMethod,
  a2uiApplicationApi,
  a2uiApplicationWriteParams,
  a2uiCatalogApi,
  a2uiManagedCatalogImportParams,
} from './api';
import {
  createEmptyA2uiCatalogComponent,
  parseA2uiCatalogComponentForm,
} from './a2uiCatalogContracts';
import {
  createEmptyA2uiApplicationDraft,
  toA2uiApplicationAuthoringPayload,
} from './a2uiApplicationContracts';
import { toA2uiApplicationFormValues } from './a2uiApplicationForm';

function assert(condition: boolean, description: string): void {
  if (!condition) throw new Error(`RED expectation failed: ${description}`);
}

function assertNoKeys(value: Record<string, unknown>, keys: string[], description: string): void {
  keys.forEach((key) => assert(!(key in value), `${description} must not contain ${key}`));
}

async function main(): Promise<void> {
  const emptyAtom = (createEmptyA2uiCatalogComponent as unknown as () => Record<string, unknown>)();
  assertNoKeys(
    emptyAtom,
    ['catalogId', 'catalogRevision', 'catalogDigest', 'lifecycle', 'frontendSupport'],
    'A2UI atom editable source',
  );

  const parsed = parseA2uiCatalogComponentForm({
    ...emptyAtom,
    componentCode: 'a2flow.basic.button',
    type: 'Button',
    nameCn: '按钮',
    category: 'ACTION',
    compositionKind: 'ATOMIC',
    propsSchemaJson: '{"type":"object","properties":{}}',
    eventSchemaJson: '{"type":"object","properties":{}}',
    childrenConstraintJson: '{"mode":"NONE"}',
    validMessageExampleJson: '{"type":"Button"}',
    invalidMessageExampleJson: '{}',
  } as never);
  assert(parsed.ok, 'atom form should still parse without lifecycle/catalog authority');
  if (parsed.ok) {
    assertNoKeys(
      parsed.component as unknown as Record<string, unknown>,
      ['catalogId', 'catalogRevision', 'catalogDigest', 'lifecycle', 'frontendSupport'],
      'parsed A2UI atom payload',
    );
  }

  assert(
    !('transitionLifecycle' in a2uiCatalogApi),
    'catalog API must not expose lifecycle transition',
  );
  assert(
    !('A2UI_CATALOG_COMPONENT_LIFECYCLE_TRANSITION' in SkillFactoryMethod),
    'method enum must not expose lifecycle transition',
  );
  [
    'A2UI_CATALOG_LIST',
    'A2UI_CATALOG_DETAIL',
    'A2UI_CATALOG_CREATE',
    'A2UI_CATALOG_UPDATE',
    'A2UI_CATALOG_MANAGED_IMPORT',
    'A2UI_APPLICATION_BLUEPRINT_LIST',
    'A2UI_APPLICATION_BLUEPRINT_IMPORT',
    'A2UI_APPLICATION_ACTION_SCAN',
  ].forEach((method) =>
    assert(method in SkillFactoryMethod, `stable public method registered: ${method}`),
  );
  assert(
    !('A2UI_CATALOG_OFFICIAL_IMPORT' in SkillFactoryMethod),
    'active M contract removes Official Catalog import',
  );
  assert('importManaged' in a2uiCatalogApi, 'Catalog API exposes managed source URL import');
  assert(!('importOfficial' in a2uiCatalogApi), 'Catalog API removes Official import');
  assert('listBlueprints' in a2uiApplicationApi, 'Application API lists server-owned blueprints');
  assert(
    'importBlueprint' in a2uiApplicationApi,
    'Application API exposes non-persisting blueprint import',
  );
  assert('scanActions' in a2uiApplicationApi, 'Application API exposes non-persisting Action scan');
  const importParams = a2uiManagedCatalogImportParams('  https://example.invalid/REQUIRES_CONFIGURATION  ');
  assert(
    JSON.stringify(importParams) ===
      JSON.stringify({ sourceUrl: 'https://example.invalid/REQUIRES_CONFIGURATION' }),
    'managed Catalog import wire contains only trimmed sourceUrl',
  );
  let catalogAuthorityRejected = false;
  try {
    a2uiCatalogApi.create({
      catalogId: 'managed.catalog',
      catalogSourceType: 'A2UI_OFFICIAL',
    });
  } catch {
    catalogAuthorityRejected = true;
  }
  assert(catalogAuthorityRejected, 'Catalog API rejects caller-supplied source authority');
  [
    'A2UI_APPLICATION_BUILD_VALIDATE',
    'A2UI_APPLICATION_BUILD_CREATE',
    'A2UI_APPLICATION_BUILD_HISTORY',
    'A2UI_APPLICATION_BUILD_ROLLBACK',
    'A2UI_APPLICATION_BUILD_DISABLE',
  ].forEach((method) =>
    assert(!(method in SkillFactoryMethod), `private Build method removed: ${method}`),
  );
  assert(
    !('validateBuild' in a2uiApplicationApi),
    'Application API must use shared release instead of private Build validation',
  );
  assert(
    !('createBuild' in a2uiApplicationApi),
    'Application API must not expose private Build creation',
  );
  assert(
    !('buildHistory' in a2uiApplicationApi),
    'Application API must not expose private Build history',
  );
  assert(
    !('rollbackBuild' in a2uiApplicationApi),
    'Application API must not expose private Build rollback',
  );
  assert(
    !('disableBuild' in a2uiApplicationApi),
    'Application API must not expose private Build disable',
  );

  const formValues = toA2uiApplicationFormValues(createEmptyA2uiApplicationDraft());
  assert(
    Object.prototype.hasOwnProperty.call(formValues, 'catalogId'),
    'Application form selects catalogId',
  );
  assertNoKeys(
    formValues as unknown as Record<string, unknown>,
    [
      'catalogRefJson',
      'catalogRevision',
      'catalogDigest',
      'frontendSupportJson',
      'hostContractVersion',
      'hostProfileReleaseId',
      'rendererArtifactDigest',
    ],
    'Application editable form',
  );

  const legacyBinding = {
    bindingId: 'binding-1',
    surfaceId: 'main',
    sourceComponentId: 'submit',
    actionCode: 'order.confirm',
    allowedSourceComponentIds: ['submit'],
    contextSchema: { type: 'object' },
    capability: {
      actionCode: 'order.confirm.execute',
      version: 3,
      sourceDigest: 'sha256:legacy-capability-release',
    },
    policy: {
      sideEffect: 'WRITE',
      idempotencyRequired: true,
      approvalRequired: true,
    },
    requestMappings: [],
    successOutcome: 'NO_UI_MESSAGES',
    failureOutcome: 'NO_UI_MESSAGES',
    resultAdapters: [],
    failureResultAdapters: [],
  };
  const application = createEmptyA2uiApplicationDraft();
  application.catalog = {
    catalogId: 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json',
    revision: 'v0.9.1-420c6183',
    digest: 'sha256:official-basic',
  };
  application.actionBindings = [legacyBinding as never];
  const payload = toA2uiApplicationAuthoringPayload(application);
  assert(
    payload.catalogId === application.catalog?.catalogId,
    'Application authoring submits top-level catalogId',
  );
  assert(!('catalog' in payload), 'Application authoring omits nested catalog authority');
  const binding = payload.actionBindings?.[0] as unknown as Record<string, unknown>;
  assertNoKeys(
    binding,
    ['policy', 'idempotencyKey', 'actionInstanceToken', 'surfaceRevision'],
    'ActionBinding authoring payload',
  );
  assertNoKeys(
    binding.capability as Record<string, unknown>,
    ['version', 'sourceDigest'],
    'CapabilityAction authoring reference',
  );
  const scanParams = a2uiApplicationWriteParams(application);
  assert(
    Object.keys(scanParams).join(',') === 'applicationJson',
    'Action scan wire contains only the full authoring applicationJson',
  );
  const scanApplication = JSON.parse(scanParams.applicationJson || '{}') as Record<string, unknown>;
  assert(
    scanApplication.catalogId === application.catalog?.catalogId,
    'Action scan wire keeps flat catalogId',
  );
  assert(
    Boolean(scanApplication.showTemplate),
    'Action scan wire includes current unsaved ShowTemplate',
  );
  assert(
    Array.isArray(scanApplication.actionBindings) && scanApplication.actionBindings.length === 1,
    'Action scan wire includes current unsaved ActionBindings',
  );
  assert(!('catalog' in scanApplication), 'Action scan wire omits nested Catalog authority');
  console.log('RED PASS: M contract correction expectations are registered');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
