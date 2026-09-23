import type {
  CapabilityActionDraft,
  CapabilityActionDraftData,
  CapabilityActionDryRunEnvironment,
  CapabilityActionValidationResult,
  CapabilityClassificationSelection,
} from './api';
import type { AssetReleaseOverview } from './types';
import type { CapabilityClient } from './capabilityClientVariantLayout';

export const CAPABILITY_API_SOURCE_TYPE = 'GRPC';
export const CAPABILITY_SOURCE_TYPE_OPTIONS = [
  { value: CAPABILITY_API_SOURCE_TYPE, label: 'gRPC 服务' },
];
export const CAPABILITY_DRY_RUN_GATE_CODES: Record<
  CapabilityActionDryRunEnvironment,
  Record<CapabilityClient, string>
> = {
  PRT: {
    PC: 'CAPABILITY_DRY_RUN_PC',
    APP: 'CAPABILITY_DRY_RUN_APP',
    COMMON: 'CAPABILITY_DRY_RUN_COMMON',
  },
  ONLINE: {
    PC: 'CAPABILITY_DRY_RUN_ONLINE_PC',
    APP: 'CAPABILITY_DRY_RUN_ONLINE_APP',
    COMMON: 'CAPABILITY_DRY_RUN_ONLINE_COMMON',
  },
};

export type CapabilityBasicInfoField = 'actionCode' | 'nameCn' | 'technicalOwner' | 'description';

export type CapabilityValidationMessage = {
  kind: 'error' | 'warning' | 'blocker';
  message: string;
};

const basicInfoRequiredMessages: Record<CapabilityBasicInfoField, string> = {
  actionCode: '请填写 actionCode',
  nameCn: '请填写中文名',
  technicalOwner: '请填写技术负责人',
  description: '请填写业务描述',
};

type CapabilityDryRunFlowOptions<T> = {
  authMode?: string;
  save: () => Promise<T | undefined>;
  execute: (saved: T) => Promise<void>;
};

type RegisterCapabilityDraftOptions = {
  nameCn: string;
  create: (draft: CapabilityActionDraftData) => Promise<CapabilityActionDraft>;
  openEditor: (draftId: string) => void;
};

/** 只用中文名称建立稳定草稿身份，其他业务与技术字段留给进入编辑页后显式填写。 */
export async function registerCapabilityDraftWithName({
  nameCn,
  create,
  openEditor,
}: RegisterCapabilityDraftOptions): Promise<CapabilityActionDraft> {
  const normalizedName = nameCn.trim();
  if (!normalizedName) {
    throw new Error('请填写中文名称');
  }
  const draft = {
    payloadType: 'CAPABILITY_DRAFT_SNAPSHOT',
    mode: 'CREATE',
    basicInfo: { nameCn: normalizedName },
  } as CapabilityActionDraftData;
  const created = await create(draft);
  openEditor(created.draftId);
  return created;
}

/** 旧 Cookie 鉴权在保存和执行前明确拒绝；用户身份由可信 Host 提供。 */
export async function runCapabilityDryRun<T>({
  authMode,
  save,
  execute,
}: CapabilityDryRunFlowOptions<T>): Promise<void> {
  if (authMode && authMode !== 'NONE') {
    throw new Error('不支持旧 Cookie 鉴权，请重新登记能力；不会自动降级鉴权');
  }
  const saved = await save();
  if (saved) await execute(saved);
}

/** 仅供基础信息页保存前使用；其他阶段仍允许保存不完整草稿。 */
export function capabilityBasicInfoErrors(
  draft: CapabilityActionDraftData,
): Partial<Record<CapabilityBasicInfoField, string>> {
  const errors: Partial<Record<CapabilityBasicInfoField, string>> = {};
  (Object.keys(basicInfoRequiredMessages) as CapabilityBasicInfoField[])?.forEach((field) => {
    if (!String(draft.basicInfo?.[field] || '').trim()) {
      errors[field] = basicInfoRequiredMessages[field];
    }
  });
  return errors;
}

/** 同一文案只展示一次，静态错误优先于发布提示和一般提醒。 */
export function uniqueCapabilityValidationMessages(
  validation: CapabilityActionValidationResult,
): CapabilityValidationMessage[] {
  const messages = new Map<string, CapabilityValidationMessage>();
  const append = (kind: CapabilityValidationMessage['kind'], values?: string[]) => {
    values?.forEach((value) => {
      const message = value.trim();
      if (message && !messages.has(message)) messages.set(message, { kind, message });
    });
  };
  append('error', validation.errors);
  append('blocker', validation.publishBlockers);
  append('warning', validation.warnings);
  return Array.from(messages.values());
}

/** 发布总览已按当前摘要计算门禁，因此 PASSED 可直接复用，EXPIRED/FAILED 必须重跑。 */
export function hasPassedCapabilityDryRun(
  overview: AssetReleaseOverview | undefined,
  environment: CapabilityActionDryRunEnvironment,
  client: CapabilityClient,
): boolean {
  const gateCode = CAPABILITY_DRY_RUN_GATE_CODES[environment]?.[client];
  return (
    overview?.gates?.some((gate) => gate.code === gateCode && gate.status === 'PASSED') === true
  );
}

export function createEmptyCapabilityDraft(): CapabilityActionDraftData {
  return {
    payloadType: 'CAPABILITY_DRAFT_SNAPSHOT',
    mode: 'CREATE',
    basicInfo: {},
    apiSource: { sourceType: CAPABILITY_API_SOURCE_TYPE },
    modelContract: { inputFields: [], inputExampleJson: '' },
    executionBinding: {
      bindingType: 'GRPC',
      target: { contextField: 'context' },
      requestMappingsJson: '{}',
      contextMappingsJson: '{}',
      timeoutMs: 3000,
      maxResponseBytes: 5242880,
      idempotency: 'NONE',
      responsePolicy: 'ORIGINAL',
    },
    resultContract: { keyOutputFields: [], responseDemoJson: '' },
    governance: { sideEffectLevel: 'READ',  },
  };
}

export function normalizeCapabilitySourceType(sourceType?: string): string {
  if (sourceType && sourceType !== 'GRPC') throw new Error('仅支持新登记的 gRPC 能力，不支持旧来源或自动迁移');
  return 'GRPC';
}

/** 仅接受新的 RPC 合同；旧传输字段不做静默降级或迁移。 */
export function capabilityDraftWithSourceType(
  draft: CapabilityActionDraftData,
  sourceType: string,
): CapabilityActionDraftData {
  normalizeCapabilitySourceType(sourceType);
  const binding = draft.executionBinding || {};
  if (binding.bindingType && binding.bindingType !== 'GRPC') {
    throw new Error('仅支持 GRPC 执行绑定，请重新登记能力');
  }
  if ((binding.idempotency && binding.idempotency !== 'NONE') ||
      (binding.responsePolicy && binding.responsePolicy !== 'ORIGINAL')) {
    throw new Error('RPC 能力仅支持不自动重试与保留原始响应');
  }
  const forbidden = ['authMode', 'staticHeadersJson', 'environmentHeadersJson', 'successStatusCodes', 'contentType'];
  const targetForbidden = ['url', 'registeredUrl', 'preReleaseUrl', 'productionUrl', 'path', 'httpMethod', 'contentType'];
  if (forbidden.some((key) => key in binding) || targetForbidden.some((key) => key in (binding.target || {}))) {
    throw new Error('RPC 能力不接受旧 HTTP 或凭证配置，请重新登记能力');
  }
  return { ...draft, apiSource: { sourceType: 'GRPC' }, executionBinding: {
    ...binding, bindingType: 'GRPC', target: { contextField: 'context', ...binding.target },
    requestMappingsJson: binding.requestMappingsJson || '{}',
    contextMappingsJson: binding.contextMappingsJson || '{}',
    idempotency: 'NONE', responsePolicy: 'ORIGINAL',
  } };
}

export function supportsCapabilityDirectDryRun(sourceType?: string): boolean {
  return sourceType === 'GRPC';
}

export function stripUnusedCapabilityDraftFields(
  draft: CapabilityActionDraftData,
): CapabilityActionDraftData {
  const canonicalDraft = { ...draft } as Record<string, unknown>;
  delete canonicalDraft.schemaVersion;
  const basicInfo = { ...draft.basicInfo } as Record<string, unknown>;
  delete basicInfo.businessOwner;
  delete basicInfo.businessDomain;
  delete basicInfo.capabilityDomain;
  delete basicInfo.specialistIds;
  const apiSource = { ...draft.apiSource } as Record<string, unknown>;
  delete apiSource.serviceDefinitionId;
  delete apiSource.apiCenterId;
  const resultContract = { ...draft.resultContract } as Record<string, unknown>;
  delete resultContract.modelSummaryTemplate;
  delete resultContract.interaction;
  const governance = { ...draft.governance } as Record<string, unknown>;
  delete governance.requiredReviews;
  return {
    ...canonicalDraft,
    basicInfo: basicInfo as CapabilityActionDraftData['basicInfo'],
    apiSource: apiSource as CapabilityActionDraftData['apiSource'],
    resultContract: resultContract as CapabilityActionDraftData['resultContract'],
    governance: governance as CapabilityActionDraftData['governance'],
  } as CapabilityActionDraftData;
}

export function formatCapabilityDemoJson(value: string, expanded: boolean): string {
  const parsed = JSON.parse(value);
  return JSON.stringify(parsed, null, expanded ? 2 : undefined);
}

export function formatCapabilityDryRunResult(result: unknown, expanded: boolean): string {
  return JSON.stringify(result, null, expanded ? 2 : undefined);
}

export async function loadPersistedCapabilityDraft(
  queryDraftId: string,
  detail: (draftId: string) => Promise<CapabilityActionDraft>,
): Promise<CapabilityActionDraft | undefined> {
  const draftId = queryDraftId.trim();
  return draftId ? detail(draftId) : undefined;
}

type PersistCapabilityDraftOptions = {
  draftId: string;
  revision: number;
  draft: CapabilityActionDraftData;
  classification: CapabilityClassificationSelection;
  create: (
    draft: CapabilityActionDraftData,
    classification: CapabilityClassificationSelection,
  ) => Promise<CapabilityActionDraft>;
  save: (
    draftId: string,
    revision: number,
    draft: CapabilityActionDraftData,
    classification: CapabilityClassificationSelection,
  ) => Promise<CapabilityActionDraft>;
};

export async function persistCapabilityDraft({
  draftId,
  revision,
  draft,
  classification,
  create,
  save,
}: PersistCapabilityDraftOptions): Promise<CapabilityActionDraft> {
  if (!draftId) {
    if (!draft.basicInfo?.actionCode?.trim?.()) {
      throw new Error('请先填写 actionCode');
    }
    return create(draft, classification);
  }
  if (!revision) {
    throw new Error('能力草稿版本缺失，请刷新后重试');
  }
  return save(draftId, revision, draft, classification);
}

export function visibleCapabilityDrafts(items: CapabilityActionDraft[]): CapabilityActionDraft[] {
  return items.filter((item) =>
    Boolean(item.draft?.basicInfo?.actionCode?.trim() || item.draft?.basicInfo?.nameCn?.trim()),
  );
}
