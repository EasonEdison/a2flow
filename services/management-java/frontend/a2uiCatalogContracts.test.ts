import {
  A2UI_MANAGED_CATALOG_SOURCE_URL,
  A2UI_APPLICATION_ROUTE_PATHS,
  A2UI_COMPONENT_CENTER_ENTRIES,
  COMPONENT_CENTER_ASSET_VIEWS,
  COMPONENT_CENTER_HEADER_ACTIONS,
  LEGACY_BUSINESS_DSL_ENTRY,
  a2uiApplicationEditorRoute,
  a2uiApplicationIdFromSearchParams,
  a2uiApplicationListRoute,
  a2uiCatalogReleaseAssetBinding,
  a2uiRouteWithChangeId,
  collectPublishedA2uiCatalogOptions,
  componentCenterDataSourceFor,
  createEmptyA2uiCatalogComponent,
  filterA2uiCatalogComponents,
  filterA2uiCatalogs,
  isA2uiCatalogEditable,
  isA2uiCatalogComponentEditable,
  parseA2uiCatalogAuthoringJson,
  parseA2uiCatalogComponentForm,
  projectA2uiCatalogMembership,
  validateA2uiCatalogComponent,
  type A2uiCatalogComponentContract,
  type A2uiCatalogComponentRecord,
  type A2uiCatalogRecord,
} from './a2uiCatalogContracts';

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

const baseComponent: A2uiCatalogComponentContract = {
  componentCode: 'a2flow.basic.text',
  type: 'Text',
  nameCn: '文本',
  category: 'CONTENT',
  compositionKind: 'ATOMIC',
  propsSchema: { type: 'object', properties: { text: { type: 'string' } } },
  eventSchema: { type: 'object', properties: {} },
  childrenConstraint: { mode: 'NONE' },
  validMessageExample: { type: 'Text', text: '示例文本' },
  invalidMessageExample: { type: 'Text' },
};

function componentRecord(
  id: string,
  catalogSourceType: 'A2UI_OFFICIAL' | 'PLATFORM_MANAGED',
  componentOriginType: 'A2UI_OFFICIAL' | 'PLATFORM_CUSTOM',
  enabled = true,
): A2uiCatalogComponentRecord {
  return {
    ...baseComponent,
    id,
    componentCode: `${id}.text`,
    catalogSourceType,
    componentOriginType,
    release: {
      catalogId: `${id}.catalog`,
      revision: '2026-08-24.1',
      digest: `sha256:${id}`,
      enabled,
    },
  };
}

function catalogRecord(
  id: string,
  catalogSourceType: 'A2UI_OFFICIAL' | 'PLATFORM_MANAGED',
  enabled = true,
): A2uiCatalogRecord {
  const digest = `sha256:${id}`;
  return {
    id,
    catalogId: `${id}.catalog`,
    catalogSourceType,
    editable: catalogSourceType === 'PLATFORM_MANAGED',
    componentCodes: [`${id}.text`],
    releases: {
      PRT: {
        revision: '2026-08-24.1',
        digest,
        enabled,
      },
      ONLINE: {
        revision: '',
        digest: '',
        enabled: false,
      },
    },
    componentTypes: ['Text'],
    componentOrigins: {
      Text: catalogSourceType === 'A2UI_OFFICIAL' ? 'A2UI_OFFICIAL' : 'PLATFORM_CUSTOM',
    },
  };
}

async function main() {
  await test('uses the reviewed public managed Catalog source URL', () => {
    assertEqual(
      A2UI_MANAGED_CATALOG_SOURCE_URL,
      'https://example.invalid/REQUIRES_CONFIGURATION',
      'managed Catalog source URL',
    );
  });

  await test('exposes the three peer entries without repurposing legacy routes', () => {
    assertEqual(A2UI_COMPONENT_CENTER_ENTRIES.length, 3, 'peer entry count');
    assertEqual(A2UI_COMPONENT_CENTER_ENTRIES?.[0]?.label, '平台 A2UI 基础组件库', 'catalog label');
    assertEqual(
      A2UI_COMPONENT_CENTER_ENTRIES?.[0]?.route,
      '/management/components/a2ui-catalog',
      'catalog route',
    );
    assertEqual(A2UI_COMPONENT_CENTER_ENTRIES?.[1]?.label, '创建 A2UI 编排', 'application label');
    assertEqual(
      A2UI_COMPONENT_CENTER_ENTRIES?.[1]?.route,
      '/management/components/a2ui-applications/create',
      'application route',
    );
    assertEqual(A2UI_COMPONENT_CENTER_ENTRIES?.[2]?.label, '注册渲染组件', 'legacy card label');
    assertEqual(
      A2UI_COMPONENT_CENTER_ENTRIES?.[2]?.route,
      '/management/components/register-render-component',
      'legacy card route',
    );
    assertEqual(
      A2UI_COMPONENT_CENTER_ENTRIES?.[2]?.buttonType,
      'default',
      'legacy card white button',
    );
    assertEqual(LEGACY_BUSINESS_DSL_ENTRY.label, '创建业务编排', 'legacy business label');
    assertEqual(
      LEGACY_BUSINESS_DSL_ENTRY.route,
      '/management/components/create-business-dsl',
      'legacy business route',
    );
  });

  await test('uses typed Component Center views and the Application list contract', () => {
    assertEqual(
      COMPONENT_CENTER_ASSET_VIEWS?.map((item) => item.value)?.join?.(','),
      'A2UI_ATOM,A2UI_APPLICATION,CARD_COMPONENT',
      'ordered asset views',
    );
    assertEqual(
      COMPONENT_CENTER_ASSET_VIEWS?.map((item) => item.title)?.join?.(','),
      'A2UI 原子,A2UI 编排,渲染组件',
      'asset view labels',
    );
    assertEqual(
      typeof componentCenterDataSourceFor === 'function'
        ? componentCenterDataSourceFor('A2UI_APPLICATION')
        : undefined,
      'A2UI_APPLICATION_LIST',
      'Application list data source',
    );
    assertEqual(
      COMPONENT_CENTER_HEADER_ACTIONS?.map((item) => item.id)?.join?.(','),
      'catalog,application,legacyCard',
      'header action ids',
    );
  });

  await test('keeps the application id in the edit query string', () => {
    assertEqual(
      A2UI_APPLICATION_ROUTE_PATHS.edit,
      'components/a2ui-applications/edit',
      'nested edit route',
    );
    assertEqual(
      a2uiApplicationEditorRoute('application/1'),
      '/management/components/a2ui-applications/edit?id=application%2F1',
      'encoded edit route',
    );
    assertEqual(
      a2uiApplicationEditorRoute(),
      '/management/components/a2ui-applications/create',
      'create route',
    );
    assertEqual(
      a2uiApplicationIdFromSearchParams(new URLSearchParams('?id=application%2F1')),
      'application/1',
      'query application id',
    );
    assertEqual(
      a2uiApplicationIdFromSearchParams(new URLSearchParams()),
      undefined,
      'missing query application id',
    );
  });

  await test('preserves the current iteration changeId across application routes', () => {
    const currentSearchParams = new URLSearchParams('?changeId=1275140&tab=ignored');
    assertEqual(
      a2uiApplicationEditorRoute('application/1', currentSearchParams),
      '/management/components/a2ui-applications/edit?changeId=1275140&id=application%2F1',
      'edit route with change id',
    );
    assertEqual(
      a2uiApplicationEditorRoute(undefined, currentSearchParams),
      '/management/components/a2ui-applications/create?changeId=1275140',
      'create route with change id',
    );
    assertEqual(
      a2uiApplicationListRoute(currentSearchParams),
      '/management/components/a2ui-applications?changeId=1275140',
      'list route with change id',
    );
    assertEqual(
      a2uiRouteWithChangeId(
        '/management/components/a2ui-catalog',
        currentSearchParams,
      ),
      '/management/components/a2ui-catalog?changeId=1275140',
      'component-center route with change id',
    );
  });

  await test('accepts atomic component contracts and rejects composed widgets', () => {
    assertEqual(validateA2uiCatalogComponent(baseComponent)?.length, 0, 'valid atomic errors');
    assertIncludes(
      validateA2uiCatalogComponent({ ...baseComponent, compositionKind: 'COMPOSED' }),
      'A2UI_CATALOG_COMPONENT_MUST_BE_ATOMIC',
      'composed component rejection',
    );
  });

  await test('creates fail-closed atomic drafts and parses strict JSON form fields', () => {
    const empty = createEmptyA2uiCatalogComponent();
    assertEqual(empty.compositionKind, 'ATOMIC', 'default composition kind');
    assertEqual(
      Object.prototype.hasOwnProperty.call(empty, 'catalogId'),
      false,
      'no editable catalog id',
    );
    assertEqual(
      Object.prototype.hasOwnProperty.call(empty, 'lifecycle'),
      false,
      'no editable lifecycle',
    );

    const parsed = parseA2uiCatalogComponentForm({
      ...empty,
      componentCode: 'a2flow.basic.button',
      type: 'Button',
      nameCn: '按钮',
      category: 'ACTION',
      propsSchemaJson: '{"type":"object","properties":{"label":{"type":"string"}}}',
      eventSchemaJson: '{"type":"object","properties":{"press":{"type":"object"}}}',
      childrenConstraintJson: '{"mode":"NONE"}',
      validMessageExampleJson: '{"type":"Button","label":"确认"}',
      invalidMessageExampleJson: '{"type":"Button"}',
    });
    assertEqual(parsed.ok, true, 'valid form result');
    assertEqual(parsed.ok && parsed.component.type, 'Button', 'parsed type');

    const invalid = parseA2uiCatalogComponentForm({
      ...empty,
      propsSchemaJson: '{invalid',
      eventSchemaJson: '{}',
      childrenConstraintJson: '{}',
      validMessageExampleJson: '{}',
      invalidMessageExampleJson: '{}',
    });
    assertEqual(invalid.ok, false, 'invalid form result');
    assertIncludes(
      invalid.ok === false ? invalid.errors : [],
      'A2UI_PROPS_SCHEMA_JSON_INVALID',
      'invalid props schema json',
    );
  });

  await test('active Catalog projections expose only managed/custom rows', () => {
    const official = componentRecord('a2ui-official-basic', 'A2UI_OFFICIAL', 'A2UI_OFFICIAL');
    const managed = componentRecord(
      'a2flow-managed-basic',
      'PLATFORM_MANAGED',
      'PLATFORM_CUSTOM',
    );
    const mismatched = componentRecord(
      'a2flow-managed-official-origin',
      'PLATFORM_MANAGED',
      'A2UI_OFFICIAL',
    );
    assertEqual(
      filterA2uiCatalogComponents([official, managed, mismatched], 'ALL')?.[0]?.id,
      managed.id,
      'managed/custom Catalog projection',
    );
    assertEqual(
      filterA2uiCatalogComponents([official, managed, mismatched], 'ALL')?.length,
      1,
      'active atom count',
    );
    assertEqual(isA2uiCatalogComponentEditable(official), false, 'official editability');
    assertEqual(isA2uiCatalogComponentEditable(managed), true, 'managed editability');
  });

  await test('collects only exact enabled managed/custom Catalog release options', () => {
    const official = catalogRecord('a2ui-official-basic', 'A2UI_OFFICIAL');
    const managed = catalogRecord('a2flow-managed-basic', 'PLATFORM_MANAGED');
    const disabled = catalogRecord('a2flow-managed-disabled', 'PLATFORM_MANAGED', false);
    const options = collectPublishedA2uiCatalogOptions([official, managed, disabled]);
    assertEqual(options.length, 1, 'published Catalog option count');
    assertEqual(options?.[0]?.catalogId, 'a2flow-managed-basic.catalog', 'exact catalogId');
    assertEqual(options?.[0]?.revision, '2026-08-24.1', 'exact Catalog revision');
    assertEqual(options?.[0]?.digest, 'sha256:a2flow-managed-basic', 'exact Catalog digest');
    assertEqual(options?.[0]?.catalogSourceType, 'PLATFORM_MANAGED', 'typed Catalog source');
    assertEqual(options?.[0]?.componentTypes?.join?.(','), 'Text', 'Catalog membership projection');
  });

  await test('collects a PRT Catalog option without support Profile or renderer evidence', () => {
    const managed = {
      id: 'managed-simple',
      catalogId: 'managed.simple.catalog',
      catalogSourceType: 'PLATFORM_MANAGED',
      editable: true,
      componentCodes: ['managed.simple.text'],
      componentTypes: ['Text'],
      componentOrigins: { Text: 'PLATFORM_CUSTOM' },
      releases: {
        PRT: { revision: '3', digest: 'sha256:prt', enabled: true },
        ONLINE: { revision: '', digest: '', enabled: false },
      },
    } as unknown as A2uiCatalogRecord;
    const options = collectPublishedA2uiCatalogOptions([managed]);
    assertEqual(options.length, 1, 'PRT Catalog option count');
    assertEqual(options?.[0]?.revision, '3', 'PRT revision');
    assertEqual(options?.[0]?.digest, 'sha256:prt', 'PRT digest');
    assertEqual(
      Object.prototype.hasOwnProperty.call(options?.[0] || {}, 'hostProfileReleaseId'),
      false,
      'option excludes Host Profile',
    );
  });

  await test('filters Catalog assets by typed source and trusts server editability only for managed rows', () => {
    const official = catalogRecord('official', 'A2UI_OFFICIAL');
    const managed = catalogRecord('managed', 'PLATFORM_MANAGED');
    assertEqual(
      filterA2uiCatalogs([official, managed], 'ALL')?.[0]?.id,
      managed.id,
      'managed assets',
    );
    assertEqual(
      filterA2uiCatalogs([official, managed], 'ALL')?.length,
      1,
      'active managed asset count',
    );
    assertEqual(isA2uiCatalogEditable(official), false, 'official Catalog read-only');
    assertEqual(isA2uiCatalogEditable(managed), true, 'managed Catalog editable');
    assertEqual(
      isA2uiCatalogEditable({ ...managed, editable: false }),
      false,
      'server editability fail closed',
    );
  });

  await test('separates imported canonical membership from released closure membership', () => {
    const catalog = catalogRecord('official', 'A2UI_OFFICIAL');
    catalog.componentCodes = ['official.text', 'official.button'];
    catalog.componentOrigins = { Text: 'A2UI_OFFICIAL' };
    const membership = projectA2uiCatalogMembership(catalog);
    assertEqual(
      membership.importedComponentCodes?.join?.(','),
      'official.text,official.button',
      'imported members',
    );
    assertEqual(membership.importedCount, 2, 'imported member count');
    assertEqual(membership.releasedComponentOrigins?.length, 1, 'released closure members');
    assertEqual(membership.releasedCount, 1, 'released closure count');

    const unpublished = projectA2uiCatalogMembership({
      ...catalog,
      releases: undefined,
      componentOrigins: undefined,
    });
    assertEqual(unpublished.importedCount, 2, 'unpublished imported member count');
    assertEqual(unpublished.releasedCount, 0, 'unpublished released closure count');
  });

  await test('binds Catalog detail to the shared release surface by exact catalogId', () => {
    const catalog = catalogRecord('official', 'A2UI_OFFICIAL');
    const binding = a2uiCatalogReleaseAssetBinding(catalog);
    assertEqual(binding.assetType, 'A2UI_CATALOG', 'release asset type');
    assertEqual(binding.assetKey, catalog.catalogId, 'release asset key');
  });

  await test('rejects Catalog authoring JSON that self-reports release authority', () => {
    assertEqual(
      parseA2uiCatalogAuthoringJson('{"catalogId":"managed","members":[]}')?.ok,
      true,
      'ordinary Catalog JSON',
    );
    const spoofed = parseA2uiCatalogAuthoringJson(
      '{"catalogId":"managed","release":{"digest":"spoofed"}}',
    );
    assertEqual(spoofed.ok, false, 'authority-bearing Catalog JSON');
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
