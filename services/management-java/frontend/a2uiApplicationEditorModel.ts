import type {
  A2uiActionBinding,
  A2uiActionDeclarationStatus,
  A2uiMessage,
  A2uiResultAdapter,
  A2uiScannedActionDeclaration,
  A2uiShowTemplate,
} from './a2uiApplicationContracts';
import type { A2uiEnvironmentReleaseMap } from './a2uiCatalogContracts';

export type A2uiApplicationEditorStage = 'basic' | 'show' | 'actions' | 'validation' | 'release';
export type A2uiApplicationEditableStage = 'basic' | 'show' | 'actions';

export interface A2uiApplicationEditorStageDescriptor {
  id: A2uiApplicationEditorStage;
  label: string;
  saveable: boolean;
}

export const A2UI_APPLICATION_EDITOR_STAGES: A2uiApplicationEditorStageDescriptor[] = [
  { id: 'basic', label: '基础信息', saveable: true },
  { id: 'show', label: 'A2UI 展示编排', saveable: true },
  { id: 'actions', label: 'Action 与结果配置', saveable: true },
  { id: 'validation', label: '联调验证', saveable: false },
  { id: 'release', label: '发布', saveable: false },
];

const A2UI_APPLICATION_SAVEABLE_STAGE_IDS = A2UI_APPLICATION_EDITOR_STAGES?.filter(
  (stage) => stage.saveable,
)?.map?.((stage) => stage.id as A2uiApplicationEditableStage);

export interface A2uiApplicationEditorInput {
  mode: 'create' | 'edit';
  activeStage?: A2uiApplicationEditorStage;
  availableComponentCount: number;
  interactionGapCount: number;
  validationIssueCount: number;
}

export interface A2uiApplicationEditorHeader {
  applicationLabel: 'Application';
  draftStatus: '草稿';
  availableComponentCount: number;
  interactionClosure: string;
  validationSummary: string;
}

export interface A2uiApplicationEditorViewModel {
  mode: 'create' | 'edit';
  activeStage: A2uiApplicationEditorStage;
  visibleStageIds: A2uiApplicationEditorStage[];
  saveableStageIds: A2uiApplicationEditableStage[];
  authoringWorkbenchClassName: string;
  header: A2uiApplicationEditorHeader;
}

export interface A2uiApplicationEditorDraftSession<TDraft> {
  mode: 'create' | 'edit';
  applicationId?: string;
  activeStage: A2uiApplicationEditorStage;
  draft: TDraft;
}

export interface A2uiApplicationToolInvocation {
  toolName: 'render_a2ui_application';
  arguments: {
    appCode: string;
    params: Record<string, unknown>;
  };
}

export interface A2uiPublicEventEnvelope {
  type: 'CUSTOM';
  name: 'a2ui';
  value: A2uiMessage[];
}

export interface A2uiV091Action {
  name: string;
  surfaceId: string;
  sourceComponentId: string;
  timestamp: string;
  context: Record<string, unknown>;
}

export interface A2uiActionHttpRequest {
  conversationId: string;
  messageId: string;
  message: {
    version: 'v0.9.1';
    action: A2uiV091Action;
  };
}

export function buildA2uiPublicEventEnvelope(messages: A2uiMessage[]): A2uiPublicEventEnvelope {
  return {
    type: 'CUSTOM',
    name: 'a2ui',
    value: messages.map((message) => ({ ...message })),
  };
}

export function buildA2uiActionHttpRequest(
  conversationId: string,
  messageId: string,
  action: A2uiV091Action,
): A2uiActionHttpRequest {
  return {
    conversationId,
    messageId,
    message: {
      version: 'v0.9.1',
      action: {
        ...action,
        context: { ...action.context },
      },
    },
  };
}

export type A2uiActionClosureStatus = A2uiActionDeclarationStatus;

export interface A2uiActionClosureRow {
  stableKey: string;
  declaration: A2uiScannedActionDeclaration;
  binding?: A2uiActionBinding;
  status: A2uiActionClosureStatus;
  configurable: boolean;
  capabilityAction?: string;
  requestMappingCount: number;
  policySummary?: string;
  orderedAdapterIds: string[];
  gap?: string;
}

function countSummary(count: number, noun: string, empty: string): string {
  return count > 0 ? `${count} ${noun}` : empty;
}

export function createA2uiApplicationEditorViewModel(
  input: A2uiApplicationEditorInput,
): A2uiApplicationEditorViewModel {
  const activeStage = input.activeStage || 'basic';
  return {
    mode: input.mode,
    activeStage,
    visibleStageIds: [activeStage],
    saveableStageIds: A2UI_APPLICATION_SAVEABLE_STAGE_IDS,
    authoringWorkbenchClassName: 'skill-authoring-workbench a2ui-application-authoring-workbench',
    header: {
      applicationLabel: 'Application',
      draftStatus: '草稿',
      availableComponentCount: input.availableComponentCount,
      interactionClosure: countSummary(input.interactionGapCount, '个缺口', '已闭合'),
      validationSummary: countSummary(input.validationIssueCount, '个校验问题', '已通过'),
    },
  };
}

export function resolveA2uiApplicationReleaseAssetKey(
  applicationId: string | undefined | null,
  appCode: string | undefined | null,
  _draftId: string,
): string {
  const persistedId = applicationId?.trim();
  const stableAppCode = appCode?.trim();
  return persistedId && stableAppCode ? stableAppCode : '';
}

export function selectA2uiApplicationStage(
  view: A2uiApplicationEditorViewModel,
  activeStage: A2uiApplicationEditorStage,
): A2uiApplicationEditorViewModel {
  return {
    ...view,
    activeStage,
    visibleStageIds: [activeStage],
  };
}

export function createA2uiApplicationEditorDraftSession<TDraft>(
  draft: TDraft,
  applicationId?: string,
): A2uiApplicationEditorDraftSession<TDraft> {
  return {
    mode: applicationId ? 'edit' : 'create',
    applicationId,
    activeStage: 'basic',
    draft,
  };
}

export function applySavedA2uiApplication<TDraft>(
  session: A2uiApplicationEditorDraftSession<TDraft>,
  saved: { id: string; draft: TDraft },
): A2uiApplicationEditorDraftSession<TDraft> {
  return {
    ...session,
    mode: 'edit',
    applicationId: saved.id,
    draft: saved.draft,
  };
}

export function selectA2uiApplicationDraftStage<TDraft>(
  session: A2uiApplicationEditorDraftSession<TDraft>,
  activeStage: A2uiApplicationEditorStage,
): A2uiApplicationEditorDraftSession<TDraft> {
  return {
    ...session,
    activeStage,
  };
}

export function buildA2uiApplicationToolInvocation(
  appCode: string,
  params: Record<string, unknown>,
): A2uiApplicationToolInvocation {
  return {
    toolName: 'render_a2ui_application',
    arguments: {
      appCode,
      params: { ...params },
    },
  };
}

export interface A2uiShowResolutionIssue {
  bindingIndex: number;
  code: 'SOURCE_NOT_FOUND' | 'TARGET_MESSAGE_NOT_FOUND' | 'TARGET_PATH_NOT_FOUND';
  path: string;
}

export interface A2uiShowResolutionResult {
  messages: A2uiMessage[];
  issues: A2uiShowResolutionIssue[];
}

export type A2uiParameterType = 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array';

export interface A2uiParameterDefinition {
  name: string;
  type: A2uiParameterType;
  required: boolean;
  description?: string;
  example?: unknown;
  /** Schema rules not exposed by the flat parameter form must survive edits. */
  schema?: Record<string, unknown>;
  schemaType?: A2uiParameterType;
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return value && !Array.isArray(value) && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : undefined;
}

export function buildA2uiParamsSchema(
  definitions: A2uiParameterDefinition[],
  originalSchema: Record<string, unknown> = {},
): Record<string, unknown> {
  const required = definitions?.filter((item) => item.required)?.map?.((item) => item.name);
  const schema: Record<string, unknown> = {
    type: 'object',
    additionalProperties: false,
    ...jsonClone(originalSchema),
    properties: Object.fromEntries(
      definitions.map((item) => [
        item.name,
        {
          type: item.type,
          ...(item.schemaType === item.type ? jsonClone(item.schema || {}) : {}),
          ...(item.description ? { description: item.description } : {}),
          ...(item.example !== undefined ? { examples: [jsonClone(item.example)] } : {}),
        },
      ]),
    ),
  };
  if (required.length) schema.required = required;
  else delete schema.required;
  return schema;
}

export function readA2uiParameterDefinitions(
  schema: Record<string, unknown>,
): A2uiParameterDefinition[] {
  const properties = recordValue(schema.properties) || {};
  const required = new Set(
    Array.isArray(schema.required)
      ? schema.required?.filter?.((item): item is string => typeof item === 'string')
      : [],
  );
  return Object.entries(properties).flatMap(([name, value]) => {
    const property = recordValue(value);
    const type = property?.type;
    if (
      !property ||
      !['string', 'number', 'integer', 'boolean', 'object', 'array'].includes(String(type))
    ) {
      return [];
    }
    return [
      {
        name,
        type: type as A2uiParameterType,
        required: required.has(name),
        ...(typeof property.description === 'string' ? { description: property.description } : {}),
        ...(Array.isArray(property.examples) && property.examples.length
          ? { example: jsonClone(property.examples[0]) } : {}),
        schema: jsonClone(Object.fromEntries(Object.entries(property).filter(
          ([key]) => !['type', 'description', 'examples'].includes(key),
        ))),
        schemaType: type as A2uiParameterType,
      },
    ];
  });
}

function jsonClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function jsonPointerSegments(path: string): string[] | undefined {
  if (!path.startsWith('/')) return undefined;
  if (path === '/') return [];
  return path
    ?.slice(1)
    ?.split?.('/')
    ?.map?.((segment) => segment?.replace(/~1/g, '/')?.replace?.(/~0/g, '~'));
}

function readJsonPointer(root: unknown, path: string): { found: boolean; value?: unknown } {
  const segments = jsonPointerSegments(path);
  if (!segments) return { found: false };
  let cursor = root;
  for (const segment of segments) {
    if (Array.isArray(cursor)) {
      const index = Number(segment);
      if (!Number.isInteger(index) || index < 0 || index >= cursor.length) return { found: false };
      cursor = cursor[index];
      continue;
    }
    if (!cursor || typeof cursor !== 'object' || !(segment in cursor)) return { found: false };
    cursor = (cursor as Record<string, unknown>)?.[segment];
  }
  return { found: true, value: cursor };
}

function writeJsonPointer(root: unknown, path: string, value: unknown): boolean {
  const segments = jsonPointerSegments(path);
  if (!segments?.length) return false;
  let cursor = root;
  for (const segment of segments.slice(0, -1)) {
    const next = readJsonPointer(
      cursor,
      `/${segment?.replace(/~/g, '~0')?.replace?.(/\//g, '~1')}`,
    );
    if (!next.found) return false;
    cursor = next.value;
  }
  const leaf = segments[segments.length - 1];
  if (Array.isArray(cursor)) {
    const index = Number(leaf);
    if (!Number.isInteger(index) || index < 0 || index >= cursor.length) return false;
    cursor[index] = jsonClone(value);
    return true;
  }
  if (!cursor || typeof cursor !== 'object' || !(leaf in cursor)) return false;
  (cursor as Record<string, unknown>)[leaf] = jsonClone(value);
  return true;
}

export function resolveA2uiShowMessages(
  showTemplate: A2uiShowTemplate,
  appParams: Record<string, unknown>,
  trustedContext: Record<string, unknown> = {},
): A2uiShowResolutionResult {
  const messages = jsonClone(showTemplate.messageTemplates);
  const issues: A2uiShowResolutionIssue[] = [];
  showTemplate.inputBindings?.forEach?.((binding, bindingIndex) => {
    const source =
      binding.source === 'APP_PARAMS'
        ? readJsonPointer(appParams, binding.sourcePath)
        : binding.source === 'TRUSTED_CONTEXT'
        ? readJsonPointer(trustedContext, binding.sourcePath)
        : { found: binding.constantValue !== undefined, value: binding.constantValue };
    if (!source.found) {
      if (binding.required)
        issues.push({
          bindingIndex,
          code: 'SOURCE_NOT_FOUND',
          path: binding.sourcePath,
        });
      return;
    }
    const targetMessage = messages[binding.targetMessageIndex];
    if (!targetMessage) {
      issues.push({
        bindingIndex,
        code: 'TARGET_MESSAGE_NOT_FOUND',
        path: String(binding.targetMessageIndex),
      });
      return;
    }
    if (!writeJsonPointer(targetMessage, binding.targetPath, source.value)) {
      issues.push({
        bindingIndex,
        code: 'TARGET_PATH_NOT_FOUND',
        path: binding.targetPath,
      });
    }
  });
  return { messages, issues };
}

export interface A2uiAdapterResolutionIssue {
  bindingIndex: number;
  code: 'MESSAGE_TEMPLATE_REQUIRED' | 'SOURCE_NOT_FOUND' | 'TARGET_PATH_NOT_FOUND';
  path: string;
}

export interface A2uiAdapterResolutionResult {
  message?: A2uiMessage;
  issues: A2uiAdapterResolutionIssue[];
}

export function resolveA2uiMessageTemplateAdapter(
  adapter: A2uiResultAdapter,
  capabilityData: Record<string, unknown>,
  capabilityMeta: Record<string, unknown> = {},
  trustedContext: Record<string, unknown> = {},
): A2uiAdapterResolutionResult {
  if (adapter.type !== 'MESSAGE_TEMPLATE' || !adapter.messageTemplate) {
    return {
      issues: [{ bindingIndex: -1, code: 'MESSAGE_TEMPLATE_REQUIRED', path: '/messageTemplate' }],
    };
  }
  const resolvedMessage = jsonClone(adapter.messageTemplate);
  const issues: A2uiAdapterResolutionIssue[] = [];
  const { data: _businessData, ...safeCapabilityMeta } = capabilityMeta;
  (adapter.bindings || []).forEach((binding, bindingIndex) => {
    const source =
      binding.source === 'CAPABILITY_DATA'
        ? readJsonPointer(capabilityData, binding.sourcePath)
        : binding.source === 'CAPABILITY_META'
        ? readJsonPointer(safeCapabilityMeta, binding.sourcePath)
        : binding.source === 'TRUSTED_CONTEXT'
        ? readJsonPointer(trustedContext, binding.sourcePath)
        : { found: binding.constantValue !== undefined, value: binding.constantValue };
    if (!source.found) {
      if (binding.required)
        issues.push({
          bindingIndex,
          code: 'SOURCE_NOT_FOUND',
          path: binding.sourcePath,
        });
      return;
    }
    if (!writeJsonPointer(resolvedMessage, binding.targetPath, source.value)) {
      issues.push({
        bindingIndex,
        code: 'TARGET_PATH_NOT_FOUND',
        path: binding.targetPath,
      });
    }
  });
  return { message: resolvedMessage, issues };
}

export function buildA2uiActionStableKey(
  value: Pick<A2uiActionBinding, 'surfaceId' | 'sourceComponentId' | 'actionCode'>,
): string {
  return `${value.surfaceId}\u0000${value.sourceComponentId}\u0000${value.actionCode}`;
}

function bindingIdPart(value: string): string {
  return value
    ?.trim()
    ?.replace?.(/[^a-zA-Z0-9]+/g, '-')
    ?.replace?.(/^-|-$/g, '')
    ?.toLowerCase?.();
}

export function createA2uiActionBindingFromDeclaration(
  declaration: A2uiScannedActionDeclaration,
): A2uiActionBinding {
  return {
    bindingId: [declaration.surfaceId, declaration.sourceComponentId, declaration.actionCode]
      ?.map(bindingIdPart)
      ?.filter?.(Boolean)
      ?.join?.('-'),
    surfaceId: declaration.surfaceId,
    sourceComponentId: declaration.sourceComponentId,
    actionCode: declaration.actionCode,
    allowedSourceComponentIds: [declaration.sourceComponentId],
    contextSchema: declaration.contextSchema
      ? { ...declaration.contextSchema }
      : {
          type: 'object',
          properties: {},
        },
    capability: { actionCode: '' },
    requestMappings: [],
    successOutcome: 'ADAPTER_PIPELINE',
    failureOutcome: 'ADAPTER_PIPELINE',
    resultAdapters: [],
    failureResultAdapters: [],
    completeWorkflowInteractionOnSuccess: false,
  };
}

export function upsertA2uiActionBinding(
  bindings: A2uiActionBinding[],
  updated: A2uiActionBinding,
): A2uiActionBinding[] {
  const stableKey = buildA2uiActionStableKey(updated);
  const index = bindings.findIndex((binding) => buildA2uiActionStableKey(binding) === stableKey);
  if (index < 0) return [...bindings, updated];
  return bindings.map((binding, bindingIndex) => (bindingIndex === index ? updated : binding));
}

export function buildA2uiActionClosureRows(
  declarations: A2uiScannedActionDeclaration[],
  bindings: A2uiActionBinding[],
): A2uiActionClosureRow[] {
  const declarationKeys = new Set(declarations.map(buildA2uiActionStableKey));
  const declarationRows: A2uiActionClosureRow[] = declarations.flatMap(
    (declaration): A2uiActionClosureRow[] => {
      const stableKey = buildA2uiActionStableKey(declaration);
      const matches = bindings.filter((binding) => buildA2uiActionStableKey(binding) === stableKey);
      if (matches.length === 0) {
        return [
          {
            stableKey,
            declaration,
            status: declaration.status,
            configurable: declaration.status !== 'RESERVED',
            requestMappingCount: 0,
            orderedAdapterIds: [],
            gap:
              declaration.status === 'RESERVED'
                ? 'Workflow 保留 Action，不可配置'
                : '缺少 ActionBinding',
          },
        ];
      }
      return matches.map((binding) => ({
        stableKey,
        declaration,
        binding,
        status: declaration.status,
        configurable: declaration.status !== 'RESERVED',
        capabilityAction: binding.capability?.actionCode,
        requestMappingCount: binding.requestMappings?.length,
        policySummary: '运行时解析当前生效 CapabilityAction；A2UI 不配置权限/审批/幂等',
        orderedAdapterIds: [...binding.resultAdapters]
          ?.sort((left, right) => left.order - right.order)
          ?.map?.((adapter) => adapter.adapterId),
        gap: declaration.status === 'BOUND' ? undefined : declaration.status,
      }));
    },
  );
  const unreferencedRows = bindings
    ?.filter((binding) => !declarationKeys.has(buildA2uiActionStableKey(binding)))
    ?.map?.((binding): A2uiActionClosureRow => {
      const stableKey = buildA2uiActionStableKey(binding);
      return {
        stableKey,
        declaration: {
          eventName: binding.actionCode,
          actionCode: binding.actionCode,
          sourceComponentId: binding.sourceComponentId,
          surfaceId: binding.surfaceId,
          contextTemplateDigest: '',
          contextSchema: { ...binding.contextSchema },
          discoveredFrom: [],
          status: 'UNREFERENCED',
        },
        binding,
        status: 'UNREFERENCED',
        configurable: true,
        capabilityAction: binding.capability?.actionCode,
        requestMappingCount: binding.requestMappings?.length,
        policySummary: '运行时解析当前生效 CapabilityAction；A2UI 不配置权限/审批/幂等',
        orderedAdapterIds: [...binding.resultAdapters]
          ?.sort((left, right) => left.order - right.order)
          ?.map?.((adapter) => adapter.adapterId),
        gap: '声明已消失，保留既有配置',
      };
    });
  return [...declarationRows, ...unreferencedRows];
}

export type A2uiValidationPreviewMode = 'structure' | 'visual';

export interface A2uiValidationPreviewViewModel {
  activeMode: A2uiValidationPreviewMode;
  visibleModeIds: A2uiValidationPreviewMode[];
  structure: {
    contractKind: 'STRUCTURE_CONTRACT_PREVIEW';
    visualPreview: false;
    sectionLabels: string[];
  };
  visual: {
    status: 'LOCAL_RENDERER';
    message: '真实 A2UI renderer 本地预览';
    rendersMock: false;
  };
}

const A2UI_STRUCTURE_PREVIEW_SECTIONS = [
  'JSON',
  '组件树',
  '数据绑定',
  '脱敏 request',
  '显式业务 data / Tool 元数据 Demo',
  'ordered adapters',
  'canonical final Surface',
];

export function createA2uiValidationPreviewViewModel(
  activeMode: A2uiValidationPreviewMode = 'structure',
): A2uiValidationPreviewViewModel {
  return {
    activeMode,
    visibleModeIds: [activeMode],
    structure: {
      contractKind: 'STRUCTURE_CONTRACT_PREVIEW',
      visualPreview: false,
      sectionLabels: [...A2UI_STRUCTURE_PREVIEW_SECTIONS],
    },
    visual: {
      status: 'LOCAL_RENDERER',
      message: '真实 A2UI renderer 本地预览',
      rendersMock: false,
    },
  };
}

export interface A2uiBuildGateSummaryInput {
  catalogReleases: A2uiEnvironmentReleaseMap;
  releaseBlockers: string[];
}

export interface A2uiBuildGate {
  id: 'serverReleaseBlockers';
  label: string;
  passed: boolean;
}

export interface A2uiBuildGateSummary {
  status: 'SERVER_CLEAR' | 'BLOCKED';
  canSaveDraft: true;
  canPublish: false;
  catalogReleases: A2uiEnvironmentReleaseMap;
  releaseBlockers: string[];
  gates: A2uiBuildGate[];
}

export function createA2uiBuildGateSummary(input: A2uiBuildGateSummaryInput): A2uiBuildGateSummary {
  const gates: A2uiBuildGate[] = [
    {
      id: 'serverReleaseBlockers',
      label: '服务端发布阻塞为空',
      passed: input.releaseBlockers?.length === 0,
    },
  ];
  return {
    status: input.releaseBlockers?.length ? 'BLOCKED' : 'SERVER_CLEAR',
    canSaveDraft: true,
    canPublish: false,
    catalogReleases: {
      PRT: { ...input.catalogReleases?.PRT },
      ONLINE: { ...input.catalogReleases?.ONLINE },
    },
    releaseBlockers: [...input.releaseBlockers],
    gates,
  };
}

export interface A2uiBuildManifestPreviewInput {
  appCode: string;
  protocolVersion: string;
  catalog: {
    catalogId: string;
    releases: A2uiEnvironmentReleaseMap;
  };
  sourceDigest?: string;
  requiredComponentTypes: string[];
  availableComponentTypes: string[];
  gates: A2uiBuildGateSummary;
}

export interface A2uiBuildManifestPreview {
  immutableManifest: {
    appCode: string;
    protocolVersion: string;
    catalog: A2uiBuildManifestPreviewInput['catalog'];
  };
  sourceDigest: string;
  dependencyDiff: {
    requiredComponentTypes: string[];
    availableComponentTypes: string[];
    unavailableComponentTypes: string[];
  };
  gates: A2uiBuildGate[];
  status: A2uiBuildGateSummary['status'];
  canPublish: boolean;
}

export function buildA2uiBuildManifestPreview(
  input: A2uiBuildManifestPreviewInput,
): A2uiBuildManifestPreview {
  const available = new Set(input.availableComponentTypes);
  return {
    immutableManifest: {
      appCode: input.appCode,
      protocolVersion: input.protocolVersion,
      catalog: {
        catalogId: input.catalog?.catalogId,
        releases: {
          PRT: { ...input.catalog?.releases?.PRT },
          ONLINE: { ...input.catalog?.releases?.ONLINE },
        },
      },
    },
    sourceDigest: input.sourceDigest || '待 Build 生成',
    dependencyDiff: {
      requiredComponentTypes: [...input.requiredComponentTypes],
      availableComponentTypes: [...input.availableComponentTypes],
      unavailableComponentTypes: input.requiredComponentTypes?.filter?.(
        (type) => !available.has(type),
      ),
    },
    gates: input.gates?.gates?.map?.((gate) => ({ ...gate })),
    status: input.gates?.status,
    canPublish: input.gates?.canPublish,
  };
}
