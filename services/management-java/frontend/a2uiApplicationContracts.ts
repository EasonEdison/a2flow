import type {
  A2uiCatalogComponentRecord,
  A2uiCatalogSourceType,
  A2uiComponentOriginType,
  A2uiEnvironmentReleaseMap,
  A2uiEnvironmentReleaseProjection,
} from './a2uiCatalogContracts';
import {
  extractShowActions,
  extractShowComponents,
  validateShowAst,
  type A2uiMessage,
  type A2uiShowTemplate,
} from './a2uiApplicationShowAst';
import { validateAdapterOutcome } from './a2uiApplicationAdapterValidation';

export type A2uiApplicationStatus = 'DRAFT' | 'VALIDATED' | 'PRT' | 'ONLINE';
export type A2uiInteractionMode = 'DISPLAY_ONLY' | 'INTERACTIVE';
export type A2uiMappingSource =
  | 'ACTION_CONTEXT'
  | 'APP_PARAMS'
  | 'TRUSTED_CONTEXT'
  | 'CONSTANT'
  | 'CAPABILITY_PREVIOUS_RESULT';
export type A2uiResultAdapterType = 'MESSAGE_TEMPLATE' | 'A2UI_PASSTHROUGH';
export type A2uiResultOutcome = 'ADAPTER_PIPELINE' | 'NO_UI_MESSAGES';
export type A2uiCapabilityResultSource = 'CAPABILITY_DATA' | 'CAPABILITY_META';
export type A2uiBusinessPredicateOperator = 'EQUALS' | 'GREATER_THAN';
export type A2uiAdapterBindingSource =
  | A2uiCapabilityResultSource
  | 'TRUSTED_CONTEXT'
  | 'ACTION_CONTEXT'
  | 'CONSTANT';

export type A2uiResultTransformType =
  | 'MINOR_UNIT_TO_DECIMAL_STRING'
  | 'ARRAY_TO_CHILDREN_PREFIX'
  | 'ARRAY_OBJECT_TO_OPTIONS'
  | 'BOOLEAN_ARRAY_TRUE_COUNT'
  | 'PAGINATION_STATE'
  | 'NUMBER_TO_STRING';

export interface A2uiOptionLabelColumn {
  label: string;
  sourcePath: string;
}

export interface A2uiResultTransform {
  type: A2uiResultTransformType;
  scale?: number;
  componentIds?: string[];
  pageSize?: number;
  pageNumber?: number;
  actionPagePath?: string;
  valuePath?: string;
  labelColumns?: A2uiOptionLabelColumn[];
  labelSeparator?: string;
}

export interface A2uiApplicationCatalogRef {
  catalogId: string;
  revision: string;
  digest: string;
  catalogSourceType?: A2uiCatalogSourceType;
  componentTypes?: string[];
  componentOrigins?: Record<string, A2uiComponentOriginType>;
  releases?: A2uiEnvironmentReleaseMap;
}

export type A2uiApplicationBlueprintCode = string;

export interface A2uiApplicationBlueprintOption {
  blueprintCode: string;
  name: string;
  description: string;
  catalogId: string;
}

export interface A2uiActionDeclaration {
  eventName: string;
  actionCode: string;
  sourceComponentId: string;
  surfaceId: string;
}

export type A2uiActionDeclarationStatus =
  | 'BOUND'
  | 'UNBOUND'
  | 'UNREFERENCED'
  | 'NEEDS_REVALIDATION'
  | 'RESERVED';

export interface A2uiActionDeclarationSource {
  sourceType: 'SHOW_TEMPLATE' | 'MESSAGE_TEMPLATE' | 'A2UI_PASSTHROUGH';
  path?: string;
  bindingId?: string;
  outcome?: 'SUCCESS' | 'FAILURE';
  adapterId?: string;
}

export interface A2uiScannedActionDeclaration {
  eventName?: string;
  actionCode: string;
  sourceComponentId: string;
  surfaceId: string;
  contextTemplateDigest: string;
  contextSchema?: Record<string, unknown>;
  discoveredFrom: A2uiActionDeclarationSource[];
  status: A2uiActionDeclarationStatus;
}

export interface A2uiEmittedActionDeclaration {
  surfaceId: string;
  sourceComponentId: string;
  actionCode: string;
  contextSchema: Record<string, unknown>;
}

export interface A2uiRequestMapping {
  source: A2uiMappingSource;
  sourcePath: string;
  targetPath: string;
  constantValue?: unknown;
}

export interface A2uiCapabilityActionRef {
  actionCode: string;
}

export interface A2uiMessageTemplateBinding {
  targetPath: string;
  source: A2uiAdapterBindingSource;
  sourcePath: string;
  required: boolean;
  constantValue?: unknown;
  transform?: A2uiResultTransform;
}

export interface A2uiComposerDraftColumn {
  label: string;
  sourcePath: string;
}

export interface A2uiComposerDraftEffect {
  type: 'COMPOSER_DRAFT';
  mode: 'APPEND';
  source: 'CAPABILITY_DATA';
  itemsPath: string;
  columns: A2uiComposerDraftColumn[];
}

export interface A2uiResultAdapter {
  adapterId: string;
  order: number;
  type: A2uiResultAdapterType;
  templateCode?: string;
  templateRevision?: string;
  templateDigest?: string;
  messageTemplate?: A2uiMessage;
  bindings?: A2uiMessageTemplateBinding[];
  source?: A2uiCapabilityResultSource;
  sourcePath?: string;
  cardinality?: 'ONE' | 'MANY';
  required?: boolean;
  emittedActionDeclarations?: A2uiEmittedActionDeclaration[];
}

export interface A2uiBusinessPredicateClause {
  source: 'CAPABILITY_DATA';
  sourcePath: string;
  operator: A2uiBusinessPredicateOperator;
  expectedValue: unknown;
}

export interface A2uiBusinessSuccessPredicate {
  version: 'JSON_POINTER_V1';
  allOf: A2uiBusinessPredicateClause[];
}

export interface A2uiActionBinding {
  bindingId: string;
  surfaceId: string;
  sourceComponentId: string;
  actionCode: string;
  allowedSourceComponentIds: string[];
  contextSchema: Record<string, unknown>;
  capability: A2uiCapabilityActionRef;
  requestMappings: A2uiRequestMapping[];
  successOutcome?: A2uiResultOutcome;
  failureOutcome?: A2uiResultOutcome;
  resultAdapters: A2uiResultAdapter[];
  failureResultAdapters: A2uiResultAdapter[];
  businessSuccessPredicate?: A2uiBusinessSuccessPredicate;
  completeWorkflowInteractionOnSuccess: boolean;
  composerDraftEffect?: A2uiComposerDraftEffect;
}

export interface A2uiLoadBinding {
  bindingId: string;
  capability: A2uiCapabilityActionRef;
  requestMappings: A2uiRequestMapping[];
  successOutcome?: A2uiResultOutcome;
  failureOutcome?: A2uiResultOutcome;
  resultAdapters: A2uiResultAdapter[];
  failureResultAdapters: A2uiResultAdapter[];
}

export interface A2uiApplicationDraft {
  appCode: string;
  nameCn: string;
  description: string;
  interactionMode: A2uiInteractionMode;
  protocolVersion: 'v0.9.1';
  protocolStatus: 'CURRENT_PRODUCTION';
  catalog: A2uiApplicationCatalogRef;
  showTemplate: A2uiShowTemplate;
  loadBindings: A2uiLoadBinding[];
  actionBindings: A2uiActionBinding[];
}

/** M 端唯一可写的 Application current-source payload；Catalog 发布状态由服务端投影补齐。 */
export interface A2uiApplicationAuthoringPayload {
  appCode: string;
  nameCn: string;
  description: string;
  interactionMode: A2uiInteractionMode;
  catalogId: string;
  showTemplate: A2uiShowTemplate;
  loadBindings: A2uiLoadBinding[];
  actionBindings: A2uiActionBinding[];
}

export type A2uiApplicationBlueprintWireSource = Omit<
  A2uiApplicationAuthoringPayload,
  'catalogId' | 'interactionMode'
> & {
  catalogId?: string;
  interactionMode?: A2uiInteractionMode;
};

function canonicalInteractionMode(value: unknown): A2uiInteractionMode {
  if (value === undefined || value === null || value === '') return 'DISPLAY_ONLY';
  if (value === 'DISPLAY_ONLY' || value === 'INTERACTIVE') return value;
  throw new Error('A2UI_APPLICATION_INTERACTION_MODE_INVALID');
}

function canonicalCompletionFlag(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === 'boolean') return value;
  throw new Error('A2UI_ACTION_BINDING_COMPLETION_FLAG_INVALID');
}

function cloneJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneJsonValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, cloneJsonValue(child)]),
    );
  }
  return value;
}

function normalizeBusinessSuccessPredicate(
  predicate: A2uiBusinessSuccessPredicate | undefined,
): A2uiBusinessSuccessPredicate | undefined {
  if (!predicate) return undefined;
  return {
    version: predicate.version,
    allOf: Array.isArray(predicate.allOf)
      ? predicate.allOf?.map?.((clause) => ({
          ...clause,
          expectedValue: cloneJsonValue(clause.expectedValue),
        }))
      : [],
  };
}

/** 将服务端/历史缺省值收敛为唯一显式作者态，不接受未知交互语义。 */
export function normalizeA2uiApplicationDraft<TApplication extends A2uiApplicationDraft>(
  application: TApplication,
): TApplication {
  return {
    ...application,
    interactionMode: canonicalInteractionMode(
      (application as unknown as Record<string, unknown>)?.interactionMode,
    ),
    actionBindings: application.actionBindings?.map?.((binding) => ({
      ...binding,
      businessSuccessPredicate: normalizeBusinessSuccessPredicate(binding.businessSuccessPredicate),
      completeWorkflowInteractionOnSuccess: canonicalCompletionFlag(
        (binding as unknown as Record<string, unknown>)?.completeWorkflowInteractionOnSuccess,
      ),
    })),
  } as TApplication;
}

export function projectA2uiApplicationBlueprintOptions(
  source: unknown,
): A2uiApplicationBlueprintOption[] {
  if (!Array.isArray(source)) {
    throw new Error('平台示例模板列表不是数组，已阻止展示');
  }
  const codes = new Set<string>();
  return source.map((item) => {
    if (!item || Array.isArray(item) || typeof item !== 'object') {
      throw new Error('平台示例模板列表包含非法条目，已阻止展示');
    }
    const value = item as Record<string, unknown>;
    const blueprintCode =
      typeof value.blueprintCode === 'string' ? value.blueprintCode?.trim?.() : '';
    const name = typeof value.name === 'string' ? value.name?.trim?.() : '';
    const description = typeof value.description === 'string' ? value.description?.trim?.() : '';
    const catalogId = typeof value.catalogId === 'string' ? value.catalogId?.trim?.() : '';
    if (!blueprintCode || !name || !catalogId || codes.has(blueprintCode)) {
      throw new Error('平台示例模板列表缺少唯一 code/name/catalogId，已阻止展示');
    }
    codes.add(blueprintCode);
    return { blueprintCode, name, description, catalogId };
  });
}

export function projectA2uiApplicationBlueprintWireSource(
  source: A2uiApplicationBlueprintWireSource,
): A2uiApplicationDraft {
  const catalogId = source.catalogId?.trim();
  if (!catalogId) {
    throw new Error('平台示例模板缺少服务端权威 Catalog ID，已阻止载入');
  }
  const { catalogId: _catalogId, ...application } = source;
  return normalizeA2uiApplicationDraft({
    ...createEmptyA2uiApplicationDraft(),
    ...application,
    catalog: {
      catalogId,
      revision: '',
      digest: '',
    },
  });
}

export function toA2uiApplicationAuthoringPayload(
  application: A2uiApplicationDraft,
): A2uiApplicationAuthoringPayload {
  const canonicalApplication = normalizeA2uiApplicationDraft(application);
  return {
    appCode: canonicalApplication.appCode,
    nameCn: canonicalApplication.nameCn,
    description: canonicalApplication.description,
    interactionMode: canonicalApplication.interactionMode,
    catalogId: canonicalApplication.catalog?.catalogId,
    showTemplate: canonicalApplication.showTemplate,
    loadBindings: canonicalApplication.loadBindings?.map?.(toAuthoringLoadBinding),
    actionBindings: canonicalApplication.actionBindings?.map?.(toAuthoringActionBinding),
  };
}

function toAuthoringLoadBinding(binding: A2uiLoadBinding): A2uiLoadBinding {
  return {
    bindingId: binding.bindingId,
    capability: { actionCode: binding.capability?.actionCode },
    requestMappings: binding.requestMappings?.map?.((mapping) => ({ ...mapping })),
    successOutcome: binding.successOutcome,
    failureOutcome: binding.failureOutcome,
    resultAdapters: normalizeResultAdapters(binding.resultAdapters),
    failureResultAdapters: normalizeResultAdapters(binding.failureResultAdapters),
  };
}

function toAuthoringActionBinding(binding: A2uiActionBinding): A2uiActionBinding {
  return {
    bindingId: binding.bindingId,
    surfaceId: binding.surfaceId,
    sourceComponentId: binding.sourceComponentId,
    actionCode: binding.actionCode,
    allowedSourceComponentIds: [...binding.allowedSourceComponentIds],
    contextSchema: { ...binding.contextSchema },
    capability: { actionCode: binding.capability?.actionCode },
    requestMappings: binding.requestMappings?.map?.((mapping) => ({ ...mapping })),
    successOutcome: binding.successOutcome,
    failureOutcome: binding.failureOutcome,
    resultAdapters: normalizeResultAdapters(binding.resultAdapters),
    failureResultAdapters: normalizeResultAdapters(binding.failureResultAdapters),
    businessSuccessPredicate: normalizeBusinessSuccessPredicate(binding.businessSuccessPredicate),
    completeWorkflowInteractionOnSuccess: binding.completeWorkflowInteractionOnSuccess === true,
    composerDraftEffect: binding.composerDraftEffect
      ? {
          ...binding.composerDraftEffect,
          columns: binding.composerDraftEffect.columns?.map?.((column) => ({ ...column })) || [],
        }
      : undefined,
  };
}

export interface A2uiApplicationReleaseProjection extends A2uiEnvironmentReleaseProjection {
  version: number | null;
  matchesCurrentSource: boolean | null;
}

export interface A2uiApplicationRecord extends A2uiApplicationDraft {
  id: string;
  status: A2uiApplicationStatus;
  releases?: Record<'PRT' | 'ONLINE', A2uiApplicationReleaseProjection>;
  hasUnpublishedChanges?: boolean | null;
  sourceDigest?: string;
  actionScan?: A2uiApplicationActionScanResult;
  createTime?: number;
  updateTime?: number;
}

export interface A2uiApplicationActionScanResult {
  actionDeclarations: A2uiScannedActionDeclaration[];
  validationErrors: string[];
  releaseBlockers: string[];
  sourceDigest?: string;
}

const A2UI_ACTION_DECLARATION_STATUSES = new Set<A2uiActionDeclarationStatus>([
  'BOUND',
  'UNBOUND',
  'UNREFERENCED',
  'NEEDS_REVALIDATION',
  'RESERVED',
]);

export function projectA2uiApplicationActionScanResult(
  source: unknown,
): A2uiApplicationActionScanResult {
  if (!source || Array.isArray(source) || typeof source !== 'object') {
    throw new Error('服务端 Action 扫描投影不是对象，已阻止展示');
  }
  const value = source as Record<string, unknown>;
  if (
    !Array.isArray(value.actionDeclarations) ||
    !Array.isArray(value.validationErrors) ||
    !value.validationErrors?.every?.((error) => typeof error === 'string') ||
    !Array.isArray(value.releaseBlockers) ||
    !value.releaseBlockers?.every?.((error) => typeof error === 'string')
  ) {
    throw new Error('服务端 Action 扫描投影缺少声明或阻塞数组，已阻止展示');
  }
  const actionDeclarations = value.actionDeclarations?.map?.((item) => {
    if (!item || Array.isArray(item) || typeof item !== 'object') {
      throw new Error('服务端 Action 扫描声明格式非法，已阻止展示');
    }
    const declaration = item as Record<string, unknown>;
    const status = declaration.status as A2uiActionDeclarationStatus;
    const discoveredFrom = declaration.discoveredFrom;
    if (
      typeof declaration.surfaceId !== 'string' ||
      !declaration.surfaceId?.trim?.() ||
      typeof declaration.sourceComponentId !== 'string' ||
      !declaration.sourceComponentId?.trim?.() ||
      typeof declaration.actionCode !== 'string' ||
      !declaration.actionCode?.trim?.() ||
      typeof declaration.contextTemplateDigest !== 'string' ||
      !Array.isArray(discoveredFrom) ||
      !discoveredFrom.every(
        (sourceItem) =>
          Boolean(sourceItem) &&
          !Array.isArray(sourceItem) &&
          typeof sourceItem === 'object' &&
          ['SHOW_TEMPLATE', 'MESSAGE_TEMPLATE', 'A2UI_PASSTHROUGH'].includes(
            (sourceItem as Record<string, unknown>)?.sourceType as string,
          ),
      ) ||
      !A2UI_ACTION_DECLARATION_STATUSES.has(status)
    ) {
      throw new Error('服务端 Action 扫描声明缺少稳定键、digest、来源或状态，已阻止展示');
    }
    return {
      ...declaration,
      eventName: typeof declaration.eventName === 'string' ? declaration.eventName : undefined,
      surfaceId: declaration.surfaceId,
      sourceComponentId: declaration.sourceComponentId,
      actionCode: declaration.actionCode,
      contextTemplateDigest: declaration.contextTemplateDigest,
      contextSchema:
        declaration.contextSchema &&
        typeof declaration.contextSchema === 'object' &&
        !Array.isArray(declaration.contextSchema)
          ? { ...(declaration.contextSchema as Record<string, unknown>) }
          : undefined,
      discoveredFrom: discoveredFrom.map((sourceItem) => ({
        ...(sourceItem as A2uiActionDeclarationSource),
      })),
      status,
    } as A2uiScannedActionDeclaration;
  });
  return {
    actionDeclarations,
    validationErrors: [...value.validationErrors] as string[],
    releaseBlockers: [...value.releaseBlockers] as string[],
    sourceDigest: typeof value.sourceDigest === 'string' ? value.sourceDigest : undefined,
  };
}

export interface A2uiApplicationQuery {
  keyword?: string;
  status?: A2uiApplicationStatus | 'ALL';
}

export interface A2uiApplicationBuildValidationResult {
  valid: boolean;
  errors: string[];
  sourceDigest?: string;
  preview?: A2uiContractPreview;
}

export interface A2uiApplicationBuildResult {
  buildId: string;
  sourceDigest: string;
  status: 'BUILT' | 'BLOCKED';
  errors: string[];
}

export interface A2uiApplicationBuildHistoryItem {
  buildId: string;
  sourceDigest: string;
  protocolVersion: 'v0.9.1';
  catalog: A2uiApplicationCatalogRef;
  status: 'BUILT' | 'ACTIVE' | 'ROLLED_BACK' | 'DISABLED';
  active: boolean;
  createTime?: number;
}

export interface A2uiApplicationBuildOperationResult {
  success: boolean;
  currentBuildId?: string;
  errors: string[];
}

export interface A2uiContractPreview {
  kind: 'STRUCTURE_CONTRACT_PREVIEW';
  visualPreview: false;
  protocolVersion: 'v0.9.1';
  interactionMode: A2uiInteractionMode;
  catalog: A2uiApplicationCatalogRef;
  showTemplate: A2uiShowTemplate;
  actionDeclarations: A2uiActionDeclaration[];
  actionBindings: A2uiActionBinding[];
  messageBatch: A2uiMessage[];
}

const WORKFLOW_RESERVED_ACTION_CODES = new Set([
  'WORKFLOW_START',
  'WORKFLOW_SUBMIT',
  'WORKFLOW_RETRY',
  'WORKFLOW_SKIP',
  'WORKFLOW_STOP',
]);

export function createEmptyA2uiApplicationDraft(): A2uiApplicationDraft {
  return {
    appCode: '',
    nameCn: '',
    description: '',
    interactionMode: 'DISPLAY_ONLY',
    protocolVersion: 'v0.9.1',
    protocolStatus: 'CURRENT_PRODUCTION',
    catalog: {
      catalogId: '',
      revision: '',
      digest: '',
    },
    showTemplate: {
      templateCode: '',
      paramsSchema: { type: 'object', properties: {} },
      surfaceDeclarations: [],
      messageTemplates: [],
      inputBindings: [],
    },
    loadBindings: [],
    actionBindings: [],
  };
}

export function deriveActionDeclarations(showTemplate: A2uiShowTemplate): A2uiActionDeclaration[] {
  return extractShowActions(showTemplate)?.map?.(
    ({ contextTemplate: _context, ...action }) => action,
  );
}

export function normalizeResultAdapters(adapters: A2uiResultAdapter[]): A2uiResultAdapter[] {
  return adapters
    ?.map((adapter, index) => ({ adapter, index }))
    ?.sort?.(
      (left, right) => left.adapter?.order - right.adapter?.order || left.index - right.index,
    )
    ?.map?.(({ adapter }) => ({
      ...adapter,
      messageTemplate: adapter.messageTemplate ? { ...adapter.messageTemplate } : undefined,
      bindings: adapter.bindings?.map((binding) => ({
        ...binding,
        transform: binding.transform
          ? {
              ...binding.transform,
              componentIds: binding.transform.componentIds
                ? [...binding.transform.componentIds]
                : undefined,
              labelColumns: binding.transform.labelColumns?.map?.((column) => ({ ...column })),
            }
          : undefined,
      })),
      emittedActionDeclarations: adapter.emittedActionDeclarations?.map((declaration) => ({
        ...declaration,
        contextSchema: { ...declaration.contextSchema },
      })),
    }));
}

function hasText(value: string | undefined): boolean {
  return Boolean(value?.trim());
}

function validJsonPointer(pointer: unknown): pointer is string {
  if (typeof pointer !== 'string') return false;
  if (!pointer) return true;
  if (!pointer.startsWith('/')) return false;
  for (let index = 0; index < pointer.length; index += 1) {
    if (pointer[index] === '~' && !['0', '1'].includes(pointer[index + 1])) return false;
  }
  return true;
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function canonicalJsonValue(value: unknown): boolean {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(canonicalJsonValue);
  if (value && typeof value === 'object') {
    return Object.values(value).every(canonicalJsonValue);
  }
  return false;
}

function validateBusinessSuccessPredicate(binding: A2uiActionBinding, errors: string[]): void {
  const predicate = (binding as unknown as Record<string, unknown>)?.businessSuccessPredicate as
    | A2uiBusinessSuccessPredicate
    | undefined;
  if (!predicate) {
    if (binding.completeWorkflowInteractionOnSuccess === true) {
      errors.push('A2UI_BUSINESS_SUCCESS_PREDICATE_REQUIRED');
    }
    return;
  }
  const invalid =
    predicate.version !== 'JSON_POINTER_V1' ||
    !Array.isArray(predicate.allOf) ||
    !predicate.allOf?.length ||
    predicate.allOf?.some?.(
      (clause) =>
        !clause ||
        clause.source !== 'CAPABILITY_DATA' ||
        !validJsonPointer(clause.sourcePath) ||
        !['EQUALS', 'GREATER_THAN'].includes(clause.operator) ||
        (clause.operator === 'EQUALS' && !canonicalJsonValue(clause.expectedValue)) ||
        (clause.operator === 'GREATER_THAN' && !finiteNumber(clause.expectedValue)),
    );
  if (invalid) errors.push('A2UI_BUSINESS_SUCCESS_PREDICATE_INVALID');
}

function validateComposerDraftEffect(binding: A2uiActionBinding, errors: string[]): void {
  const effect = binding.composerDraftEffect;
  if (!effect) return;
  const raw = effect as unknown as Record<string, unknown>;
  const columns = effect.columns || [];
  const invalid =
    Object.keys(raw).some(
      (key) => !['type', 'mode', 'source', 'itemsPath', 'columns'].includes(key),
    ) ||
    effect.type !== 'COMPOSER_DRAFT' ||
    effect.mode !== 'APPEND' ||
    effect.source !== 'CAPABILITY_DATA' ||
    !hasText(effect.itemsPath) ||
    !validJsonPointer(effect.itemsPath) ||
    columns.length < 1 ||
    columns.length > 20 ||
    columns.some(
      (column) =>
        !column ||
        !hasText(column.label) ||
        !hasText(column.sourcePath) ||
        !validJsonPointer(column.sourcePath),
    );
  if (invalid) errors.push('A2UI_COMPOSER_DRAFT_EFFECT_INVALID');
}

function unique(errors: string[]): string[] {
  return [...new Set(errors)];
}

export function isProtectedAuthorityTarget(targetPath: string): boolean {
  const normalized = targetPath?.toLowerCase()?.replace?.(/[^a-z0-9]+/g, '.');
  const segments = normalized?.split('.')?.filter?.(Boolean);
  return segments.some((segment) =>
    [
      'userid',
      'client',
      'operator',
      'environment',
      'credential',
      'credentials',
      'transportauthority',
      'identity',
      'token',
      'cookie',
      'authorization',
      'host',
      'url',
      'target',
      'script',
      'appbuildid',
      'capabilityversion',
    ].includes(segment),
  );
}

export function hasForbiddenMappingField(mapping: A2uiRequestMapping): boolean {
  const raw = mapping as unknown as Record<string, unknown>;
  return [
    'script',
    'url',
    'credential',
    'credentials',
    'environment',
    'transportAuthority',
    'headers',
  ].some((key) => Object.prototype.hasOwnProperty.call(raw, key));
}

function componentMatchesBuild(component: A2uiCatalogComponentRecord | undefined): boolean {
  return Boolean(
    component &&
      component.catalogSourceType === 'PLATFORM_MANAGED' &&
      component.componentOriginType === 'PLATFORM_CUSTOM',
  );
}

function validateActionBindings(application: A2uiApplicationDraft, errors: string[]): void {
  const declarations = deriveActionDeclarations(application.showTemplate);
  const declarationKey = (
    item: Pick<A2uiActionDeclaration, 'surfaceId' | 'sourceComponentId' | 'actionCode'>,
  ) => `${item.surfaceId}:${item.sourceComponentId}:${item.actionCode}`;
  const declaredActions = new Set(declarations.map(declarationKey));
  if (declaredActions.size !== declarations.length) {
    errors.push('A2UI_ACTION_DECLARATION_DUPLICATE');
  }
  declarations.forEach((declaration) => {
    if (WORKFLOW_RESERVED_ACTION_CODES.has(declaration.actionCode)) {
      errors.push('A2UI_WORKFLOW_ACTION_RESERVED');
    }
    const matches = application.actionBindings?.filter?.(
      (binding) =>
        binding.actionCode === declaration.actionCode &&
        binding.surfaceId === declaration.surfaceId &&
        binding.sourceComponentId === declaration.sourceComponentId,
    );
    if (!matches.length) errors.push('A2UI_ACTION_BINDING_MISSING');
    if (matches.length > 1) errors.push('A2UI_ACTION_BINDING_DUPLICATE');
  });
  application.actionBindings?.forEach?.((binding) => {
    const rawCompletion = (binding as unknown as Record<string, unknown>)
      ?.completeWorkflowInteractionOnSuccess;
    if (rawCompletion !== undefined && typeof rawCompletion !== 'boolean') {
      errors.push('A2UI_ACTION_BINDING_COMPLETION_FLAG_INVALID');
    }
    if (WORKFLOW_RESERVED_ACTION_CODES.has(binding.actionCode)) {
      errors.push('A2UI_WORKFLOW_ACTION_RESERVED');
    }
    if (!declaredActions.has(declarationKey(binding))) errors.push('A2UI_ACTION_BINDING_ORPHAN');
    if (!hasText(binding.bindingId) || !hasText(binding.capability?.actionCode))
      errors.push('A2UI_CAPABILITY_ACTION_CODE_REQUIRED');
    if (
      !binding.allowedSourceComponentIds?.includes(binding.sourceComponentId) ||
      binding.contextSchema?.type !== 'object'
    )
      errors.push('A2UI_ACTION_BINDING_CLOSURE_INVALID');
    binding.requestMappings?.forEach?.((mapping) => {
      if (
        ![
          'ACTION_CONTEXT',
          'APP_PARAMS',
          'TRUSTED_CONTEXT',
          'CONSTANT',
          'CAPABILITY_PREVIOUS_RESULT',
        ].includes(mapping.source)
      )
        errors.push('A2UI_MAPPING_SOURCE_INVALID');
      if (mapping.source !== 'TRUSTED_CONTEXT' && isProtectedAuthorityTarget(mapping.targetPath)) {
        errors.push('A2UI_AUTHORITY_MAPPING_FORBIDDEN');
      }
      if (hasForbiddenMappingField(mapping)) errors.push('A2UI_MAPPING_FIELD_FORBIDDEN');
    });
    validateAdapterOutcome(binding.successOutcome, binding.resultAdapters, errors);
    validateAdapterOutcome(binding.failureOutcome, binding.failureResultAdapters, errors);
    validateBusinessSuccessPredicate(binding, errors);
    validateComposerDraftEffect(binding, errors);
  });
}

export function validateA2uiApplicationBuild(
  application: A2uiApplicationDraft,
  catalogComponents: A2uiCatalogComponentRecord[],
): string[] {
  const errors: string[] = [];
  if (!hasText(application.appCode) || !hasText(application.nameCn)) {
    errors.push('A2UI_APPLICATION_IDENTITY_REQUIRED');
  }
  if (application.protocolVersion !== 'v0.9.1') errors.push('A2UI_PROTOCOL_UNSUPPORTED');
  const interactionMode = (application as unknown as Record<string, unknown>)?.interactionMode;
  if (interactionMode !== 'DISPLAY_ONLY' && interactionMode !== 'INTERACTIVE') {
    errors.push('A2UI_APPLICATION_INTERACTION_MODE_INVALID');
  } else {
    const hasCompletingAction = application.actionBindings?.some?.(
      (binding) => binding.completeWorkflowInteractionOnSuccess === true,
    );
    if (interactionMode === 'INTERACTIVE' && !hasCompletingAction) {
      errors.push('A2UI_INTERACTIVE_COMPLETION_ACTION_REQUIRED');
    }
    if (interactionMode === 'DISPLAY_ONLY' && hasCompletingAction) {
      errors.push('A2UI_DISPLAY_ONLY_COMPLETION_ACTION_FORBIDDEN');
    }
  }
  if (!hasText(application.catalog?.catalogId)) {
    errors.push('A2UI_CATALOG_REF_INVALID');
  }
  errors.push(...validateShowAst(application.showTemplate, application.catalog?.catalogId));
  extractShowComponents(application.showTemplate)?.forEach?.(({ definition }) => {
    const hasExactComponent = catalogComponents.some(
      (candidate) => candidate.type === definition.component && componentMatchesBuild(candidate),
    );
    if (!hasExactComponent) {
      errors.push('A2UI_COMPONENT_NOT_AVAILABLE');
    }
  });
  application.loadBindings?.forEach?.((binding) => {
    if (!hasText(binding.bindingId) || !hasText(binding.capability?.actionCode)) {
      errors.push('A2UI_LOAD_BINDING_INVALID');
    }
    binding.requestMappings?.forEach?.((mapping) => {
      if (
        !['APP_PARAMS', 'TRUSTED_CONTEXT', 'CONSTANT', 'CAPABILITY_PREVIOUS_RESULT'].includes(
          mapping.source,
        )
      ) {
        errors.push('A2UI_LOAD_MAPPING_SOURCE_INVALID');
      }
      if (mapping.source !== 'TRUSTED_CONTEXT' && isProtectedAuthorityTarget(mapping.targetPath)) {
        errors.push('A2UI_AUTHORITY_MAPPING_FORBIDDEN');
      }
      if (hasForbiddenMappingField(mapping)) errors.push('A2UI_MAPPING_FIELD_FORBIDDEN');
    });
    validateAdapterOutcome(binding.successOutcome, binding.resultAdapters, errors);
    validateAdapterOutcome(binding.failureOutcome, binding.failureResultAdapters, errors);
  });
  validateActionBindings(application, errors);
  return unique(errors);
}

export function buildA2uiContractPreview(application: A2uiApplicationDraft): A2uiContractPreview {
  const show = application.showTemplate;
  return {
    kind: 'STRUCTURE_CONTRACT_PREVIEW',
    visualPreview: false,
    protocolVersion: application.protocolVersion,
    interactionMode: application.interactionMode,
    catalog: { ...application.catalog },
    showTemplate: {
      ...show,
      surfaceDeclarations: show.surfaceDeclarations?.map?.((surface) => ({ ...surface })),
      messageTemplates: show.messageTemplates?.map?.((message) => ({ ...message })),
      inputBindings: show.inputBindings?.map?.((binding) => ({ ...binding })),
    },
    actionDeclarations: deriveActionDeclarations(show),
    actionBindings: application.actionBindings?.map?.(toAuthoringActionBinding),
    messageBatch: show.messageTemplates?.map?.((message) => ({ ...message })),
  };
}

export {
  parseA2uiApplicationForm,
  toA2uiApplicationFormValues,
  type A2uiApplicationFormParseResult,
  type A2uiApplicationFormValues,
} from './a2uiApplicationForm';

export type {
  A2uiMessage,
  A2uiShowInputBinding,
  A2uiShowInputSource,
  A2uiShowTemplate,
  A2uiSurfaceDeclaration,
} from './a2uiApplicationShowAst';
