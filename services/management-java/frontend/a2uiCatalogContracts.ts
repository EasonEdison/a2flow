const A2UI_APPLICATION_ROUTE_PATH = 'components/a2ui-applications';

export const A2UI_APPLICATION_ROUTE_PATHS = {
  list: A2UI_APPLICATION_ROUTE_PATH,
  create: `${A2UI_APPLICATION_ROUTE_PATH}/create`,
  edit: `${A2UI_APPLICATION_ROUTE_PATH}/edit`,
} as const;

export const A2UI_APPLICATION_ROUTES = {
  list: `/management/${A2UI_APPLICATION_ROUTE_PATHS.list}`,
  create: `/management/${A2UI_APPLICATION_ROUTE_PATHS.create}`,
  edit: `/management/${A2UI_APPLICATION_ROUTE_PATHS.edit}`,
} as const;

interface A2uiSearchParamsLike {
  get: (name: string) => string | null;
}

function preservedChangeId(searchParams?: A2uiSearchParamsLike): URLSearchParams {
  const nextSearchParams = new URLSearchParams();
  const changeId = searchParams?.get('changeId');
  if (changeId) nextSearchParams.set('changeId', changeId);
  return nextSearchParams;
}

function routeWithSearchParams(route: string, searchParams: URLSearchParams): string {
  const search = searchParams.toString();
  return search ? `${route}?${search}` : route;
}

export function a2uiRouteWithChangeId(route: string, searchParams?: A2uiSearchParamsLike): string {
  return routeWithSearchParams(route, preservedChangeId(searchParams));
}

export function a2uiApplicationListRoute(searchParams?: A2uiSearchParamsLike): string {
  return a2uiRouteWithChangeId(A2UI_APPLICATION_ROUTES.list, searchParams);
}

export function a2uiApplicationEditorRoute(
  id?: string,
  searchParams?: A2uiSearchParamsLike,
): string {
  const nextSearchParams = preservedChangeId(searchParams);
  if (id) nextSearchParams.set('id', id);
  const route = id ? A2UI_APPLICATION_ROUTES.edit : A2UI_APPLICATION_ROUTES.create;
  return routeWithSearchParams(route, nextSearchParams);
}

export function a2uiApplicationIdFromSearchParams(
  searchParams: A2uiSearchParamsLike,
): string | undefined {
  return searchParams.get('id') || undefined;
}

export type A2uiNavigationEntryId = 'catalog' | 'application' | 'legacyCard';
export type A2uiNavigationButtonType = 'default' | 'primary';

export interface A2uiNavigationEntry {
  id: A2uiNavigationEntryId;
  label: string;
  route: string;
  buttonType: A2uiNavigationButtonType;
}

export const A2UI_COMPONENT_CENTER_ENTRIES: A2uiNavigationEntry[] = [
  {
    id: 'catalog',
    label: '平台 A2UI 基础组件库',
    route: '/management/components/a2ui-catalog',
    buttonType: 'default',
  },
  {
    id: 'application',
    label: '创建 A2UI 编排',
    route: A2UI_APPLICATION_ROUTES.create,
    buttonType: 'primary',
  },
  {
    id: 'legacyCard',
    label: '注册渲染组件',
    route: '/management/components/register-render-component',
    buttonType: 'default',
  },
];

export type ComponentCenterAssetViewKey = 'A2UI_ATOM' | 'A2UI_APPLICATION' | 'CARD_COMPONENT';

export type ComponentCenterDataSourceMethod = 'COMPONENT_LIST' | 'A2UI_APPLICATION_LIST';

export interface ComponentCenterAssetView {
  value: ComponentCenterAssetViewKey;
  title: string;
  description: string;
  listTitle: string;
  dataSource: ComponentCenterDataSourceMethod;
}

export const COMPONENT_CENTER_ASSET_VIEWS: ComponentCenterAssetView[] = [
  {
    value: 'A2UI_ATOM',
    title: 'A2UI 原子',
    description: '可信 A2UI Catalog 原子能力',
    listTitle: 'A2UI 原子列表',
    dataSource: 'COMPONENT_LIST',
  },
  {
    value: 'A2UI_APPLICATION',
    title: 'A2UI 编排',
    description: '由原子组件组成的 Application',
    listTitle: 'A2UI 编排列表',
    dataSource: 'A2UI_APPLICATION_LIST',
  },
  {
    value: 'CARD_COMPONENT',
    title: '渲染组件',
    description: '已有 bundle / CARD_CONTAINER 组件',
    listTitle: '渲染组件列表',
    dataSource: 'COMPONENT_LIST',
  },
];

export const COMPONENT_CENTER_HEADER_ACTIONS: A2uiNavigationEntry[] = [
  ...A2UI_COMPONENT_CENTER_ENTRIES,
];

export function componentCenterDataSourceFor(
  view: ComponentCenterAssetViewKey,
): ComponentCenterDataSourceMethod {
  const matchedView = COMPONENT_CENTER_ASSET_VIEWS.find((item) => item.value === view);
  if (!matchedView) throw new Error(`未知组件中心资产视图: ${view}`);
  return matchedView.dataSource;
}

export const LEGACY_BUSINESS_DSL_ENTRY = {
  label: '创建业务编排',
  route: '/management/components/create-business-dsl',
} as const;

export type A2uiComponentCompositionKind = 'ATOMIC' | 'COMPOSED';

export interface A2uiChildrenConstraint {
  mode: 'NONE' | 'SINGLE' | 'MULTIPLE' | 'SLOTS';
  slots?: Array<{
    name: string;
    required?: boolean;
    allowedTypes?: string[];
  }>;
}

export interface A2uiCatalogComponentContract {
  componentCode: string;
  type: string;
  nameCn: string;
  category: string;
  compositionKind: A2uiComponentCompositionKind;
  propsSchema: Record<string, unknown>;
  eventSchema: Record<string, unknown>;
  childrenConstraint: A2uiChildrenConstraint;
  validMessageExample: Record<string, unknown>;
  invalidMessageExample: Record<string, unknown>;
}

export interface A2uiCatalogComponentFormValues {
  componentCode: string;
  type: string;
  nameCn: string;
  category: string;
  compositionKind: A2uiComponentCompositionKind;
  propsSchemaJson: string;
  eventSchemaJson: string;
  childrenConstraintJson: string;
  validMessageExampleJson: string;
  invalidMessageExampleJson: string;
}

export type A2uiCatalogComponentFormParseResult =
  | { ok: true; component: A2uiCatalogComponentContract }
  | { ok: false; errors: string[] };

export interface A2uiCatalogReleaseProjection {
  catalogId: string;
  revision: string;
  digest: string;
  enabled: boolean;
}

export type A2uiReleaseEnvironment = 'PRT' | 'ONLINE';

export interface A2uiEnvironmentReleaseProjection {
  revision: string;
  digest: string;
  enabled: boolean;
}

export type A2uiEnvironmentReleaseMap = Record<
  A2uiReleaseEnvironment,
  A2uiEnvironmentReleaseProjection
>;

export type A2uiCatalogSourceType = 'A2UI_OFFICIAL' | 'PLATFORM_MANAGED';
export type A2uiComponentOriginType = 'A2UI_OFFICIAL' | 'PLATFORM_CUSTOM';
export type A2uiCatalogSourceFilter = 'ALL' | A2uiCatalogSourceType;

export const A2UI_MANAGED_CATALOG_SOURCE_URL =
  'https://example.invalid/REQUIRES_CONFIGURATION';

export const A2UI_CATALOG_SOURCE_LABELS: Record<A2uiCatalogSourceType, string> = {
  A2UI_OFFICIAL: 'A2UI 官方',
  PLATFORM_MANAGED: '平台自研',
};

export const A2UI_COMPONENT_ORIGIN_LABELS: Record<A2uiComponentOriginType, string> = {
  A2UI_OFFICIAL: '官方组件',
  PLATFORM_CUSTOM: '平台组件',
};

export interface A2uiCatalogComponentRecord extends A2uiCatalogComponentContract {
  id: string;
  catalogSourceType: A2uiCatalogSourceType;
  componentOriginType: A2uiComponentOriginType;
  release?: A2uiCatalogReleaseProjection;
  createTime?: number;
  updateTime?: number;
}

export interface A2uiCatalogComponentQuery {
  keyword?: string;
}

export interface A2uiCatalogRecord {
  id: string;
  catalogId: string;
  nameCn?: string;
  description?: string;
  protocolVersion?: string;
  componentCodes?: string[];
  catalogSourceType: A2uiCatalogSourceType;
  editable: boolean;
  catalogJson?: Record<string, unknown>;
  releases?: A2uiEnvironmentReleaseMap;
  componentTypes?: string[];
  componentOrigins?: Record<string, A2uiComponentOriginType>;
  createTime?: number;
  updateTime?: number;
}

export interface A2uiCatalogMembershipProjection {
  importedComponentCodes: string[];
  importedCount?: number;
  releasedComponentOrigins: Array<{
    type: string;
    componentOriginType: A2uiComponentOriginType;
  }>;
  releasedCount: number;
}

export interface A2uiCatalogReleaseAssetBinding {
  assetType: 'A2UI_CATALOG';
  assetKey: string;
}

export interface A2uiCatalogQuery {
  keyword?: string;
  catalogSourceType?: A2uiCatalogSourceType;
}

export interface A2uiManagedCatalogImportResult {
  catalogId: string;
  protocolVersion: string;
  importedAtomCount: number;
  functionCount: number;
  rawDigest: string;
  errors?: string[];
}

export type A2uiCatalogAuthoringJson = Record<string, unknown>;

export type A2uiCatalogAuthoringParseResult =
  | { ok: true; catalog: A2uiCatalogAuthoringJson }
  | { ok: false; errors: string[] };

export interface A2uiPublishedCatalogOption {
  catalogId: string;
  revision: string;
  digest: string;
  environment: 'PRT';
  catalogSourceType: A2uiCatalogSourceType;
  componentTypes: string[];
  componentOrigins: Record<string, A2uiComponentOriginType>;
  releases: A2uiEnvironmentReleaseMap;
}

export function filterA2uiCatalogComponents(
  records: A2uiCatalogComponentRecord[],
  _filter: A2uiCatalogSourceFilter,
): A2uiCatalogComponentRecord[] {
  return records.filter(
    (record) =>
      record.catalogSourceType === 'PLATFORM_MANAGED' &&
      record.componentOriginType === 'PLATFORM_CUSTOM',
  );
}

export function filterA2uiCatalogs(
  records: A2uiCatalogRecord[],
  _filter: A2uiCatalogSourceFilter,
): A2uiCatalogRecord[] {
  return records.filter((record) => record.catalogSourceType === 'PLATFORM_MANAGED');
}

export function isA2uiCatalogEditable(record: A2uiCatalogRecord): boolean {
  return record.catalogSourceType === 'PLATFORM_MANAGED' && record.editable === true;
}

export function isA2uiCatalogComponentEditable(record: A2uiCatalogComponentRecord): boolean {
  return (
    record.catalogSourceType === 'PLATFORM_MANAGED' &&
    record.componentOriginType === 'PLATFORM_CUSTOM'
  );
}

export function projectA2uiCatalogMembership(
  record: A2uiCatalogRecord,
): A2uiCatalogMembershipProjection {
  const componentCodes = record.componentCodes || record.catalogJson?.componentCodes;
  const hasCanonicalComponentCodes =
    Array.isArray(componentCodes) &&
    componentCodes.every(
      (componentCode) => typeof componentCode === 'string' && Boolean(componentCode.trim()),
    );
  const importedComponentCodes = hasCanonicalComponentCodes
    ? (componentCodes as string[])?.map((componentCode) => componentCode.trim())
    : [];
  const releasedComponentOrigins = Object.entries(record.componentOrigins || {}).map(
    ([type, componentOriginType]) => ({ type, componentOriginType }),
  );
  return {
    importedComponentCodes,
    importedCount: hasCanonicalComponentCodes ? importedComponentCodes.length : undefined,
    releasedComponentOrigins,
    releasedCount: releasedComponentOrigins.length,
  };
}

export function a2uiCatalogReleaseAssetBinding(
  record: Pick<A2uiCatalogRecord, 'catalogId'>,
): A2uiCatalogReleaseAssetBinding {
  const assetKey = record.catalogId?.trim();
  if (!assetKey) {
    throw new Error('Catalog 详情缺少 catalogId，无法打开发布管理');
  }
  return {
    assetType: 'A2UI_CATALOG',
    assetKey,
  };
}

export function a2uiPublishedCatalogOptionValue(
  option: Pick<A2uiPublishedCatalogOption, 'catalogId'>,
): string {
  return option.catalogId;
}

export function collectPublishedA2uiCatalogOptions(
  records: A2uiCatalogRecord[],
): A2uiPublishedCatalogOption[] {
  const options = new Map<string, A2uiPublishedCatalogOption>();
  const conflictedKeys = new Set<string>();
  records.forEach((record) => {
    const releases = record.releases;
    const release = releases?.PRT;
    const onlineRelease = releases?.ONLINE;
    const origins = record.componentOrigins || {};
    const originEntries = Object.entries(origins);
    if (
      release?.enabled !== true ||
      !record.catalogId?.trim() ||
      !release.revision?.trim() ||
      !release.digest?.trim() ||
      record.catalogSourceType !== 'PLATFORM_MANAGED' ||
      !record.componentTypes?.length ||
      !onlineRelease ||
      !originEntries.length ||
      originEntries.some(([type, origin]) => !type.trim() || origin !== 'PLATFORM_CUSTOM')
    )
      return;
    const key = record.catalogId;
    const current = options.get(key);
    if (
      current &&
      (current.catalogSourceType !== record.catalogSourceType ||
        current.revision !== release.revision ||
        current.digest !== release.digest)
    ) {
      conflictedKeys.add(key);
      options.delete(key);
      return;
    }
    options.set(key, {
      catalogId: record.catalogId,
      revision: release.revision,
      digest: release.digest,
      environment: 'PRT',
      catalogSourceType: record.catalogSourceType,
      componentTypes: [...new Set(record.componentTypes)].sort(),
      componentOrigins: { ...origins },
      releases: {
        PRT: { ...release },
        ONLINE: { ...onlineRelease },
      },
    });
  });
  conflictedKeys.forEach((key) => options.delete(key));
  return [...options.values()].sort(
    (left, right) =>
      left.catalogId?.localeCompare?.(right.catalogId) ||
      left.revision?.localeCompare?.(right.revision) ||
      left.digest?.localeCompare?.(right.digest),
  );
}

export function a2uiCatalogReleaseFor(
  record: Pick<A2uiCatalogRecord, 'releases'>,
  environment: A2uiReleaseEnvironment,
): A2uiEnvironmentReleaseProjection | undefined {
  return record.releases?.[environment];
}

/** 从服务端管理投影还原普通 Catalog 可写 source，不携带发布权威字段。 */
export function toA2uiCatalogAuthoringSource(record: A2uiCatalogRecord): A2uiCatalogAuthoringJson {
  return {
    catalogId: record.catalogId,
    nameCn: record.nameCn || '',
    description: record.description || '',
    protocolVersion: record.protocolVersion || 'v0.9.1',
    componentCodes: [...(record.componentCodes || [])],
  };
}

const A2UI_CATALOG_AUTHORITY_FIELDS = new Set([
  'catalogSourceType',
  'editable',
  'readOnly',
  'revision',
  'digest',
  'catalogDigest',
  'release',
  'frontendSupport',
  'catalogSupport',
  'hostProfile',
  'rendererArtifactDigest',
]);

function catalogAuthorityPath(value: unknown, path = '$'): string | undefined {
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      const nested = catalogAuthorityPath(value[index], `${path}[${index}]`);
      if (nested) return nested;
    }
    return undefined;
  }
  if (!value || typeof value !== 'object') return undefined;
  for (const [key, nestedValue] of Object.entries(value as Record<string, unknown>)) {
    if (A2UI_CATALOG_AUTHORITY_FIELDS.has(key)) return `${path}.${key}`;
    const nested = catalogAuthorityPath(nestedValue, `${path}.${key}`);
    if (nested) return nested;
  }
  return undefined;
}

export function parseA2uiCatalogAuthoringJson(text: string): A2uiCatalogAuthoringParseResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, errors: ['A2UI_CATALOG_JSON_INVALID'] };
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    return { ok: false, errors: ['A2UI_CATALOG_JSON_INVALID'] };
  }
  const authorityPath = catalogAuthorityPath(parsed);
  if (authorityPath) {
    return { ok: false, errors: [`A2UI_CATALOG_AUTHORITY_FORBIDDEN:${authorityPath}`] };
  }
  return { ok: true, catalog: parsed as A2uiCatalogAuthoringJson };
}

function hasText(value: string | undefined): boolean {
  return Boolean(value?.trim());
}

function isObjectSchema(value: Record<string, unknown> | undefined): boolean {
  return value?.type === 'object';
}

export function createEmptyA2uiCatalogComponent(): A2uiCatalogComponentContract {
  return {
    componentCode: '',
    type: '',
    nameCn: '',
    category: '',
    compositionKind: 'ATOMIC',
    propsSchema: { type: 'object', properties: {} },
    eventSchema: { type: 'object', properties: {} },
    childrenConstraint: { mode: 'NONE' },
    validMessageExample: {},
    invalidMessageExample: {},
  };
}

function parseJsonObject(
  text: string,
  errorCode: string,
  errors: string[],
): Record<string, unknown> | undefined {
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      errors.push(errorCode);
      return undefined;
    }
    return parsed as Record<string, unknown>;
  } catch {
    errors.push(errorCode);
    return undefined;
  }
}

export function parseA2uiCatalogComponentForm(
  values: A2uiCatalogComponentFormValues,
): A2uiCatalogComponentFormParseResult {
  const errors: string[] = [];
  const propsSchema = parseJsonObject(
    values.propsSchemaJson,
    'A2UI_PROPS_SCHEMA_JSON_INVALID',
    errors,
  );
  const eventSchema = parseJsonObject(
    values.eventSchemaJson,
    'A2UI_EVENT_SCHEMA_JSON_INVALID',
    errors,
  );
  const childrenConstraint = parseJsonObject(
    values.childrenConstraintJson,
    'A2UI_CHILDREN_CONSTRAINT_JSON_INVALID',
    errors,
  );
  const validMessageExample = parseJsonObject(
    values.validMessageExampleJson,
    'A2UI_VALID_MESSAGE_EXAMPLE_JSON_INVALID',
    errors,
  );
  const invalidMessageExample = parseJsonObject(
    values.invalidMessageExampleJson,
    'A2UI_INVALID_MESSAGE_EXAMPLE_JSON_INVALID',
    errors,
  );
  if (
    !propsSchema ||
    !eventSchema ||
    !childrenConstraint ||
    !validMessageExample ||
    !invalidMessageExample
  ) {
    return { ok: false, errors };
  }
  const component: A2uiCatalogComponentContract = {
    componentCode: values.componentCode,
    type: values.type,
    nameCn: values.nameCn,
    category: values.category,
    compositionKind: values.compositionKind,
    propsSchema,
    eventSchema,
    childrenConstraint: childrenConstraint as unknown as A2uiChildrenConstraint,
    validMessageExample,
    invalidMessageExample,
  };
  const contractErrors = validateA2uiCatalogComponent(component);
  return contractErrors.length ? { ok: false, errors: contractErrors } : { ok: true, component };
}

export function validateA2uiCatalogComponent(component: A2uiCatalogComponentContract): string[] {
  const errors: string[] = [];
  if (!hasText(component.componentCode)) errors.push('A2UI_COMPONENT_CODE_REQUIRED');
  if (!hasText(component.type)) errors.push('A2UI_COMPONENT_TYPE_REQUIRED');
  if (!hasText(component.nameCn)) errors.push('A2UI_COMPONENT_NAME_REQUIRED');
  if (!hasText(component.category)) errors.push('A2UI_COMPONENT_CATEGORY_REQUIRED');
  if (component.compositionKind !== 'ATOMIC') {
    errors.push('A2UI_CATALOG_COMPONENT_MUST_BE_ATOMIC');
  }
  if (!isObjectSchema(component.propsSchema)) errors.push('A2UI_PROPS_SCHEMA_INVALID');
  if (!isObjectSchema(component.eventSchema)) errors.push('A2UI_EVENT_SCHEMA_INVALID');
  if (!component.childrenConstraint?.mode) errors.push('A2UI_CHILDREN_CONSTRAINT_REQUIRED');
  if (!component.validMessageExample || !component.invalidMessageExample) {
    errors.push('A2UI_COMPONENT_EXAMPLES_REQUIRED');
  }
  return errors;
}
