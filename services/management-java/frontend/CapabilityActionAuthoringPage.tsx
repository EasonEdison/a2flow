import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  assetReleaseApi,
  capabilityCenterApi,
  skillFactoryApi,
  SKILL_FACTORY_CHAT_BIZ_KEYS,
  type CapabilityActionDraft,
  type CapabilityActionDraftData,
  type CapabilityActionDryRunEnvironment,
  type CapabilityActionDryRunResult,
  type CapabilityActionAllowedValue,
  type CapabilityActionInputField,
  type CapabilityActionKeyOutputField,
  type CapabilityPresentationComponent,
  type CapabilityActionValidationResult,
  type SkillFactoryDomainOption,
  type SkillFactorySpecialistOption,
  type CapabilityClassificationSelection,
  type SkillFactoryCodingEvent,
} from './api';
import {
  capabilityAllowedValueFromText,
  normalizeCapabilityAllowedValuesForType,
  normalizeCapabilityInputField,
} from './capabilityInputFieldContract';
import CapabilityPresentationComponents from './CapabilityPresentationComponents';
import CapabilityExecutionBindingEditor from './CapabilityExecutionBindingEditor';
import CapabilityInputSchemaEditor from './CapabilityInputSchemaEditor';
import CapabilityClientVariantReview from './CapabilityClientVariantReview';
import CapabilityClientTechnicalNavigation from './CapabilityClientTechnicalNavigation';
import {
  CAPABILITY_CLIENT_MODE_OPTIONS,
  capabilityClientsForMode,
  type CapabilityClient,
  type CapabilityClientMode,
} from './capabilityClientVariantLayout';
import {
  applyCapabilityTechnicalVariant,
  buildCapabilityClientCanonicalDraft,
  capabilityTechnicalVariant,
  selectCapabilityClientTechnicalDraft,
  splitCapabilityClientCanonicalDraft,
  updateCapabilityClientTechnicalSection,
  type CapabilityTechnicalSection,
} from './capabilityClientTechnicalDraft';
import AssetReleaseTab from './shared/AssetReleaseTab';
import { useAssetAccess } from './shared/AssetAccessContext';
import { executeReleaseOperation } from './shared/releaseOperationFeedback';
import { useAssetReleaseEditability } from './shared/useAssetReleaseEditability';
import {
  SkillFactoryAuthoringChat,
  authoringChangeSetId,
  eventPayload,
  useSkillFactoryChatStream,
} from './shared/authoringChat';
import AuthoringWorkbenchLayout, {
  type AuthoringRailView,
} from './shared/AuthoringWorkbenchLayout';
import { createCapabilityCenterAuthoringAdapter } from './shared/authoringChat/adapters/capabilityCenterAdapter';
import {
  applyFormPatchReview,
  AuthoringFormAdapterRegistry,
  buildFormPatchReview,
  captureFormPatchBaseline,
  formPatchProposalOf,
  resolveFormPatchBaseline,
  type FormPatchBaseline,
  type FormPatchConflictChoice,
  type FormPatchReview,
} from './shared/authoringFormPatch';
import FormPatchReviewPanel from './shared/authoringFormPatch/FormPatchReview';
import type { ChangeReviewStatus } from './shared/authoringChangeReview';
import { createCapabilityFormPatchAdapter } from './capabilityFormPatchAdapter';
import { type CapabilityAuthoringStage } from './capabilityAuthoringDiff';
import {
  capabilityBasicInfoErrors,
  capabilityDraftWithSourceType,
  CAPABILITY_API_SOURCE_TYPE,
  createEmptyCapabilityDraft,
  formatCapabilityDryRunResult,
  formatCapabilityDemoJson,
  loadPersistedCapabilityDraft,
  normalizeCapabilitySourceType,
  persistCapabilityDraft,
  runCapabilityDryRun,
  stripUnusedCapabilityDraftFields,
  supportsCapabilityDirectDryRun,
  uniqueCapabilityValidationMessages,
  type CapabilityBasicInfoField,
} from './capabilityDraftLifecycle';
import {
  capabilityClassificationError,
  normalizeCapabilityClassification,
} from './capabilityClassification';
import { resolveCapabilityCreateChangeView } from './capabilityCreateChangeModel';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const PAYLOAD_DRAFT_SNAPSHOT = 'CAPABILITY_DRAFT_SNAPSHOT';
const PAYLOAD_DRAFT_PATCH = 'CAPABILITY_DRAFT_PATCH';
const PAYLOAD_FORM_PATCH_PROPOSED = 'FORM_PATCH_PROPOSED';
const PAYLOAD_VALIDATION_REPORT = 'CAPABILITY_VALIDATION_REPORT';
const RELEASE_ACTION_DEPLOY_PREPROD = 'DEPLOY_PREPROD';
const PUBLISH_READY_MESSAGE = '校验已通过，可以发布到预发。';
const PUBLISH_BLOCKED_MESSAGE = '当前不能发布：请先完成校验并通过 API 验证。';
const CAPABILITY_CENTER_AGENT_MISSING = `当前页面缺少能力中心 AI Authoring agentId 配置，请在 skillFactoryPageConfig 中配置 ${SKILL_FACTORY_CHAT_BIZ_KEYS.CAPABILITY_CENTER_AUTHORING} 场景的 agentId。`;

type CapabilityAuthoringConfig = {
  agentId: string;
  ownerId?: string;
  businessDomains: Array<{ value: string; label: string }>;
  capabilityDomains: Array<{ value: string; label: string }>;
  specialists: Array<{ value: string; label: string }>;
  disabledReason?: string;
};

type CapabilityEditableSection =
  | 'basicInfo'
  | 'apiSource'
  | 'modelContract'
  | 'executionBinding'
  | 'resultContract'
  | 'governance';

const capabilityAuthoringStages: Array<{ key: CapabilityAuthoringStage; label: string }> = [
  { key: 'basic', label: '基础信息' },
  { key: 'contract', label: '参数契约' },
  { key: 'binding', label: '执行绑定' },
  { key: 'components', label: '包装组件' },
  { key: 'validation', label: '校验' },
  { key: 'publish', label: '发布' },
];

function recordOf(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringOf(value: unknown): string {
  return value === undefined || value === null ? '' : String(value);
}

function parseClientValueMapping(value: string): Record<string, string> {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('client value mapping must be an object');
  }
  const mapping: Record<string, string> = {};
  Object.entries(parsed as Record<string, unknown>).forEach(([sourceValue, targetValue]) => {
    if (!sourceValue.trim() || typeof targetValue !== 'string' || !targetValue.trim()) {
      throw new Error('client value mapping must contain non-empty string pairs');
    }
    mapping[sourceValue.trim()] = targetValue.trim();
  });
  return mapping;
}

function normalizeDraft(
  value?: Partial<CapabilityActionDraftData> | null,
): CapabilityActionDraftData {
  const defaults = createEmptyCapabilityDraft();
  const basicInfo = { ...defaults.basicInfo, ...(value?.basicInfo || {}) } as Record<
    string,
    unknown
  >;
  delete basicInfo.toolName;
  delete basicInfo.releaseApprover;
  const sourceType = normalizeCapabilitySourceType(value?.apiSource?.sourceType);
  return stripUnusedCapabilityDraftFields(
    capabilityDraftWithSourceType(
      {
        ...defaults,
        ...value,
        payloadType: PAYLOAD_DRAFT_SNAPSHOT,
        basicInfo: basicInfo as CapabilityActionDraftData['basicInfo'],
        apiSource: {
          ...defaults.apiSource,
          ...(value?.apiSource || {}),
          sourceType,
        },
        modelContract: {
          ...defaults.modelContract,
          ...(value?.modelContract || {}),
          inputFields: (value?.modelContract?.inputFields || []).map(normalizeCapabilityInputField),
        },
        executionBinding: {
          ...defaults.executionBinding,
          ...(value?.executionBinding || {}),
          target: {
            ...(defaults.executionBinding?.target || {}),
            ...(value?.executionBinding?.target || {}),
          },
        },
        resultContract: {
          keyOutputFields: value?.resultContract?.keyOutputFields || [],
          responseDemoJson: value?.resultContract?.responseDemoJson || '',
          technicalOutputSchema: value?.resultContract?.technicalOutputSchema,
          errorMappings: value?.resultContract?.errorMappings,
          presentationComponents: value?.resultContract?.presentationComponents,
        },
        governance: { ...defaults.governance, ...(value?.governance || {}) },
      },
      sourceType,
    ),
  );
}

type NormalizedCapabilityClientDrafts = {
  canonicalDraft: CapabilityActionDraftData;
  appDraft: CapabilityActionDraftData;
  commonDraft: CapabilityActionDraftData;
  clientMode: CapabilityClientMode;
};

/** 新格式按精确模式恢复独立契约；旧平铺技术契约只进入 PC。 */
function normalizeCapabilityClientDrafts(
  value?: Partial<CapabilityActionDraftData> | null,
): NormalizedCapabilityClientDrafts {
  const splitDrafts = splitCapabilityClientCanonicalDraft(value, createEmptyCapabilityDraft());
  return {
    canonicalDraft: normalizeDraft(splitDrafts.canonicalDraft),
    appDraft: normalizeDraft(splitDrafts.appDraft),
    commonDraft: normalizeDraft(splitDrafts.commonDraft),
    clientMode: splitDrafts.clientMode,
  };
}

/** Patch 逐步应用时规范化各端技术段，但不丢弃尚未与 supportedClients 配对的中间 variant。 */
function normalizeCapabilityClientCanonicalPatchDraft(
  value: CapabilityActionDraftData,
): CapabilityActionDraftData {
  const normalizedRoot = normalizeDraft(value);
  const {
    apiSource: _apiSource,
    modelContract: _modelContract,
    executionBinding: _executionBinding,
    resultContract: _resultContract,
    supportedClients: _supportedClients,
    clientVariants: _clientVariants,
    ...commonFields
  } = normalizedRoot;
  const clientVariants: CapabilityActionDraftData['clientVariants'] = {};
  (['PC', 'APP', 'COMMON'] as CapabilityClient[])?.forEach((client) => {
    const variant = value.clientVariants?.[client];
    if (!variant) return;
    clientVariants[client] = capabilityTechnicalVariant(
      normalizeDraft(applyCapabilityTechnicalVariant(normalizedRoot, variant)),
    );
  });
  return {
    ...commonFields,
    supportedClients: [...(value.supportedClients || [])],
    clientVariants,
  } as CapabilityActionDraftData;
}

function normalizeDomainOptions(value: unknown): Array<{ value: string; label: string }> {
  if (!Array.isArray(value)) return [];
  return value
    ?.map((item) => recordOf(item) as SkillFactoryDomainOption | null)
    ?.map?.((item) => ({
      value: stringOf(item?.value || item?.code || item?.id)?.trim?.(),
      label: stringOf(item?.label || item?.name || item?.value || item?.code || item?.id)?.trim?.(),
    }))
    ?.filter?.((item) => item.value && item.label);
}

function configRecord(config: unknown): Record<string, unknown> | null {
  const root = recordOf(config);
  const bizConfigs = recordOf(root?.bizConfigs);
  return (
    recordOf(bizConfigs?.[SKILL_FACTORY_CHAT_BIZ_KEYS.CAPABILITY_CENTER_AUTHORING]) ||
    recordOf(root?.[SKILL_FACTORY_CHAT_BIZ_KEYS.CAPABILITY_CENTER_AUTHORING])
  );
}

function observedTypeOf(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number';
  if (typeof value === 'object') return 'object';
  return typeof value;
}

function resolveDemoPath(responseDemoJson: string | undefined, path: string | undefined): unknown {
  if (!responseDemoJson?.trim() || !path?.trim()) return undefined;
  try {
    let values: unknown[] = [JSON.parse(responseDemoJson)];
    for (const rawSegment of path.split('.')) {
      const segment = rawSegment.trim();
      if (!segment) return undefined;
      const arraySegment = segment.endsWith('[]');
      const key = arraySegment ? segment.slice(0, -2) : segment;
      const nextValues: unknown[] = [];
      values.forEach((value) => {
        const record = recordOf(value);
        if (!record || !Object.prototype.hasOwnProperty.call(record, key)) return;
        const nextValue = record[key];
        if (arraySegment) {
          if (Array.isArray(nextValue)) nextValues.push(...nextValue);
          return;
        }
        nextValues.push(nextValue);
      });
      if (!nextValues.length) return undefined;
      values = nextValues;
    }
    return values.find((value) => value !== null && value !== undefined) ?? values?.[0];
  } catch {
    return undefined;
  }
}

function resolveConfig(config: unknown): CapabilityAuthoringConfig {
  const root = recordOf(config);
  const record = configRecord(config);
  const agentId = stringOf(record?.agentId)?.trim?.();
  const businessDomains = normalizeDomainOptions(root?.businessDomains);
  const capabilityDomains = normalizeDomainOptions(root?.capabilityDomains);
  const specialists = (Array.isArray(root?.specialists) ? root.specialists : [])
    ?.map((item) => recordOf(item) as SkillFactorySpecialistOption | null)
    ?.map?.((item) => ({
      value: stringOf(item?.id || item?.specialistId || item?.value)?.trim?.(),
      label: stringOf(item?.name || item?.specialistName || item?.label)?.trim?.(),
    }))
    ?.filter?.((item) => item.value && item.label);
  if (!agentId)
    return {
      agentId: '',
      businessDomains,
      capabilityDomains,
      specialists,
      disabledReason: CAPABILITY_CENTER_AGENT_MISSING,
    };
  return {
    agentId,
    ownerId: stringOf(record?.ownerId)?.trim?.() || undefined,
    businessDomains,
    capabilityDomains,
    specialists,
  };
}

function payloadTypeOf(
  event: SkillFactoryCodingEvent,
  payload: Record<string, unknown> | null,
): string {
  return stringOf(
    event.payloadType ||
      payload?.payloadType ||
      payload?.type ||
      event.eventCode ||
      event.eventType,
  );
}

function contentOf(payload: Record<string, unknown> | null): Record<string, unknown> {
  return recordOf(payload?.content) || payload || {};
}

const fieldSourceOptions = [
  { value: 'MODEL_INPUT', label: '模型输入' },
  { value: 'CONSTANT', label: '常量' },
  { value: 'SYSTEM_VARIABLE', label: '系统变量' },
];

const systemVariableOptions = [
  { value: 'userId', label: 'userId' },
  { value: 'client', label: 'client' },
];

const fieldTypeOptions = [
  { value: 'string', label: '字符' },
  { value: 'integer', label: '整数' },
  { value: 'number', label: '数字（允许小数）' },
  { value: 'boolean', label: '布尔' },
  { value: 'array', label: '数组' },
];

const sideEffectOptions = [
  { value: 'READ', label: '只读' },
  { value: 'WRITE', label: '读写' },
];



const CapabilityActionAuthoringPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryDraftId = searchParams.get('draftId') || '';
  const [draftId, setDraftId] = useState(queryDraftId);
  const [draft, setDraft] = useState<CapabilityActionDraftData>(createEmptyCapabilityDraft());
  const [appPreviewDraft, setAppPreviewDraft] = useState<CapabilityActionDraftData>(
    createEmptyCapabilityDraft(),
  );
  const [commonPreviewDraft, setCommonPreviewDraft] = useState<CapabilityActionDraftData>(
    createEmptyCapabilityDraft(),
  );
  const draftRef = useRef<CapabilityActionDraftData>(draft);
  const [revision, setRevision] = useState(0);
  const [classification, setClassification] = useState<CapabilityClassificationSelection>({
    businessDomain: '',
    capabilityDomain: '',
    specialistIds: [],
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [initializationError, setInitializationError] = useState('');
  const [config, setConfig] = useState<CapabilityAuthoringConfig>({
    agentId: '',
    businessDomains: [],
    capabilityDomains: [],
    specialists: [],
    disabledReason: '能力中心 AI Authoring 配置加载中',
  });
  const [validation, setValidation] = useState<CapabilityActionValidationResult>();
  const [basicInfoErrors, setBasicInfoErrors] = useState<
    Partial<Record<CapabilityBasicInfoField, string>>
  >({});
  const [dryRunLoadingEnvironment, setDryRunLoadingEnvironment] = useState<
    CapabilityActionDryRunEnvironment | ''
  >('');
  const [dryRunResult, setDryRunResult] = useState<CapabilityActionDryRunResult>();
  const [dryRunResultExpanded, setDryRunResultExpanded] = useState(true);
  const proposalBaselinesRef = useRef<Map<string, FormPatchBaseline<CapabilityActionDraftData>>>(
    new Map(),
  );
  const [formPatchReviews, setFormPatchReviews] = useState<
    Record<string, FormPatchReview<CapabilityActionDraftData>>
  >({});
  const [pendingReviewChangeSetId, setPendingReviewChangeSetId] = useState('');
  const [changeReviewStatuses, setChangeReviewStatuses] = useState<
    Record<string, ChangeReviewStatus>
  >({});
  const [selectedChangeIds, setSelectedChangeIds] = useState<Set<string>>(new Set());
  const [conflictChoices, setConflictChoices] = useState<Record<string, FormPatchConflictChoice>>(
    {},
  );
  const [aiDrawerOpen, setAiDrawerOpen] = useState(true);
  const [aiDrawerView, setAiDrawerView] = useState<AuthoringRailView>('chat');
  const [activeStage, setActiveStage] = useState<CapabilityAuthoringStage>('basic');
  const [clientMode, setClientMode] = useState<CapabilityClientMode>('PC_APP_COMMON');
  const [activeClient, setActiveClient] = useState<CapabilityClient>('COMMON');
  const [changeBaseVersion, setChangeBaseVersion] = useState<number>();
  const [changeName, setChangeName] = useState('');
  const [creatingChange, setCreatingChange] = useState(false);
  const supportedClients = useMemo(() => capabilityClientsForMode(clientMode), [clientMode]);
  const canonicalFormDraft = useMemo(
    () =>
      buildCapabilityClientCanonicalDraft(
        draft,
        appPreviewDraft,
        commonPreviewDraft,
        supportedClients,
      ),
    [appPreviewDraft, commonPreviewDraft, draft, supportedClients],
  );
  const pendingReview = formPatchReviews[pendingReviewChangeSetId];
  const releaseEditability = useAssetReleaseEditability('CAPABILITY_ACTION', draftId || undefined);
  const assetAccess = useAssetAccess('CAPABILITY_ACTION', draftId || undefined);
  const releaseEditDisabledReason = draftId
    ? assetAccess.loading
      ? '正在加载当前业务能力的操作权限'
      : !assetAccess.permissions?.canEdit
      ? assetAccess.readonlyReason || '当前用户不是负责人，仅可查看'
      : releaseEditability.loading
      ? '正在加载当前业务能力的变更状态'
      : releaseEditability.editable
      ? ''
      : '当前业务能力没有可编辑变更，请先在基础信息右侧新建变更'
    : '';
  const createChangeView = resolveCapabilityCreateChangeView({
    canEdit: assetAccess.permissions?.canEdit,
    readonlyReason:
      assetAccess.loading || releaseEditability.loading
        ? '正在加载当前业务能力的变更状态'
        : assetAccess.readonlyReason ||
          releaseEditability.error ||
          '当前已有编辑中变更，无需重复创建',
    allowedActions: releaseEditability.overview?.allowedActions || [],
    versions: releaseEditability.overview?.versions || [],
    baseVersion: changeBaseVersion,
    changeName,
  });

  useEffect(() => {
    setChangeBaseVersion((current) => {
      if (
        current !== undefined &&
        createChangeView.versionOptions.some((item) => item.value === current)
      ) {
        return current;
      }
      return createChangeView.defaultBaseVersion;
    });
  }, [createChangeView.defaultBaseVersion, releaseEditability.overview?.versions]);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  const validationMessages = useMemo(
    () => (validation ? uniqueCapabilityValidationMessages(validation) : []),
    [validation],
  );
  const capabilityPublishReady =
    releaseEditability.overview?.allowedActions?.includes(RELEASE_ACTION_DEPLOY_PREPROD) === true;
  const activeTechnicalDraft = selectCapabilityClientTechnicalDraft(
    activeClient,
    draft,
    appPreviewDraft,
    commonPreviewDraft,
  );

  const updateClientMode = (mode: CapabilityClientMode) => {
    const nextClients = capabilityClientsForMode(mode);
    setClientMode(mode);
    setActiveClient((current) => (nextClients.includes(current) ? current : nextClients?.[0]));
  };

  const loadDraft = useCallback(async (id: string) => {
    setLoading(Boolean(id));
    setInitializationError('');
    setDryRunResult(undefined);
    try {
      const response = await loadPersistedCapabilityDraft(id, capabilityCenterApi.detail);
      if (!response) {
        setDraftId('');
        setRevision(0);
        setDraft(createEmptyCapabilityDraft());
        setAppPreviewDraft(createEmptyCapabilityDraft());
        setCommonPreviewDraft(createEmptyCapabilityDraft());
        setClientMode('PC_APP_COMMON');
        setActiveClient('COMMON');
        setClassification({ businessDomain: '', capabilityDomain: '', specialistIds: [] });
        return;
      }
      const clientDrafts = normalizeCapabilityClientDrafts(response.draft);
      setDraftId(response.draftId);
      setRevision(response.revision);
      setDraft(clientDrafts.canonicalDraft);
      setAppPreviewDraft(clientDrafts.appDraft);
      setCommonPreviewDraft(clientDrafts.commonDraft);
      setClientMode(clientDrafts.clientMode);
      setActiveClient(capabilityClientsForMode(clientDrafts.clientMode)?.[0]);
      setClassification(
        normalizeCapabilityClassification({
          businessDomain: response.businessDomain,
          capabilityDomain: response.capabilityDomain,
          specialistIds: String(response.specialistId || '').split(','),
        }),
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '能力草稿加载失败';
      setInitializationError(errorMessage);
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    skillFactoryApi
      .config()
      .then(resolveConfig)
      .then(setConfig)
      .catch(() => {
        setConfig({
          agentId: '',
          businessDomains: [],
          capabilityDomains: [],
          specialists: [],
          disabledReason: CAPABILITY_CENTER_AGENT_MISSING,
        });
      });
  }, []);

  useEffect(() => {
    loadDraft(queryDraftId);
  }, [loadDraft, queryDraftId]);

  const formAdapter = useMemo(
    () =>
      createCapabilityFormPatchAdapter({
        draft: canonicalFormDraft,
        draftId,
        revision: Math.max(1, revision),
        normalize: normalizeCapabilityClientCanonicalPatchDraft,
        apply: (next) => {
          const clientDrafts = normalizeCapabilityClientDrafts(next);
          const nextClients = capabilityClientsForMode(clientDrafts.clientMode);
          setDraft(clientDrafts.canonicalDraft);
          setAppPreviewDraft(clientDrafts.appDraft);
          setCommonPreviewDraft(clientDrafts.commonDraft);
          setClientMode(clientDrafts.clientMode);
          setActiveClient((current) =>
            nextClients.includes(current) ? current : nextClients?.[0],
          );
          setValidation(undefined);
        },
      }),
    [canonicalFormDraft, draftId, revision],
  );
  const formAdapterRegistry = useMemo(
    () => new AuthoringFormAdapterRegistry().register(formAdapter),
    [formAdapter],
  );

  const prepareFormPatchReview = useCallback(
    (event: SkillFactoryCodingEvent, options: { silent?: boolean } = {}) => {
      const payload = eventPayload(event);
      const type = payloadTypeOf(event, payload);
      const content = contentOf(payload);
      if (
        type === PAYLOAD_FORM_PATCH_PROPOSED ||
        type === PAYLOAD_DRAFT_SNAPSHOT ||
        type === PAYLOAD_DRAFT_PATCH
      ) {
        const proposal = formPatchProposalOf({
          ...content,
          formKey: content.formKey || formAdapter.formKey,
          entityId: content.entityId || formAdapter.entityId,
        });
        if (!proposal) {
          if (!options.silent) {
            message.warning(
              'AI 返回的表单修改建议缺少合法 identity、revision、fingerprint 或 operations。',
            );
          }
          return null;
        }
        try {
          const activeAdapter = formAdapterRegistry.resolve<CapabilityActionDraftData>(
            proposal.formKey,
          );
          const baseline = resolveFormPatchBaseline(
            activeAdapter,
            proposalBaselinesRef.current,
            proposal,
          );
          if (!baseline) {
            if (!options.silent) {
              message.warning('AI 修改建议无法匹配本次请求基线，已拒绝覆盖当前表单。');
            }
            return null;
          }
          const review = buildFormPatchReview(
            activeAdapter,
            baseline,
            activeAdapter.snapshot(),
            proposal,
          );
          const changeSetId = authoringChangeSetId(event);
          proposalBaselinesRef.current?.set?.(baseline.fingerprint, baseline);
          return { changeSetId, review };
        } catch (error) {
          if (!options.silent) {
            message.error(error instanceof Error ? error.message : 'AI 表单修改建议校验失败');
          }
          return null;
        }
      }
      return null;
    },
    [formAdapterRegistry],
  );

  const openFormPatchReview = useCallback(
    (changeSetId: string, review: FormPatchReview<CapabilityActionDraftData>) => {
      setPendingReviewChangeSetId(changeSetId);
      setChangeReviewStatuses((current) => ({
        ...current,
        [changeSetId]: current[changeSetId] || 'PENDING',
      }));
      setSelectedChangeIds(
        new Set(
          review?.changes
            ?.filter?.((change) => change.status === 'safe')
            ?.map?.((change) => change.id),
        ),
      );
      setConflictChoices({});
      setValidation(undefined);
      setAiDrawerOpen(true);
      setAiDrawerView('review');
    },
    [],
  );

  const handleAuthoringEvent = useCallback(
    (event: SkillFactoryCodingEvent) => {
      const payload = eventPayload(event);
      const type = payloadTypeOf(event, payload);
      const preparedReview = prepareFormPatchReview(event);
      if (preparedReview) {
        setFormPatchReviews((current) => ({
          ...current,
          [preparedReview.changeSetId]: preparedReview.review,
        }));
        openFormPatchReview(preparedReview.changeSetId, preparedReview.review);
        message.info('AI 已生成表单修改建议，请审阅后再应用。');
      }
      if (type === PAYLOAD_VALIDATION_REPORT) {
        const content = contentOf(payload);
        setValidation(content as unknown as CapabilityActionValidationResult);
      }
    },
    [openFormPatchReview, prepareFormPatchReview],
  );

  const actionCode = draft.basicInfo?.actionCode || '';
  const adapter = useMemo(() => {
    const baseAdapter = createCapabilityCenterAuthoringAdapter<CapabilityActionDraftData>({
      draftId,
      actionCode,
      revision,
      disabledReason:
        releaseEditDisabledReason ||
        config.disabledReason ||
        (!draftId ? '正在创建能力草稿' : undefined),
      agentId: config.agentId,
      ownerId: config.ownerId,
      onEvent: handleAuthoringEvent,
    });
    return {
      ...baseAdapter,
      buildRequest: (input: Parameters<typeof baseAdapter.buildRequest>[0]) => {
        const requestBaseline = captureFormPatchBaseline(formAdapter);
        proposalBaselinesRef.current?.set?.(requestBaseline.fingerprint, requestBaseline);
        return {
          ...baseAdapter.buildRequest(input),
          formKey: requestBaseline.formKey,
          entityId: requestBaseline.entityId,
          revision: requestBaseline.revision,
          baseFingerprint: requestBaseline.fingerprint,
        };
      },
    };
  }, [
    actionCode,
    config.agentId,
    config.disabledReason,
    config.ownerId,
    draftId,
    formAdapter,
    handleAuthoringEvent,
    releaseEditDisabledReason,
    revision,
  ]);
  const chat = useSkillFactoryChatStream<CapabilityActionDraftData>({
    adapter,
    workspaceId: 'capability-center',
    currentDraft: canonicalFormDraft,
  });

  useEffect(() => {
    const restoredReviews: Record<string, FormPatchReview<CapabilityActionDraftData>> = {};
    const restoredStatuses: Record<string, ChangeReviewStatus> = {};
    chat.messages?.forEach?.((chatMessage) => {
      chatMessage.businessEvents?.forEach?.((event) => {
        const preparedReview = prepareFormPatchReview(event, { silent: true });
        if (!preparedReview) return;
        restoredReviews[preparedReview.changeSetId] = preparedReview.review;
        restoredStatuses[preparedReview.changeSetId] = 'PENDING';
      });
    });
    if (Object.keys(restoredReviews).length) {
      setFormPatchReviews((current) => ({ ...restoredReviews, ...current }));
      setChangeReviewStatuses((current) => ({ ...restoredStatuses, ...current }));
    }
  }, [chat.messages, prepareFormPatchReview]);

  const updateSection = (section: CapabilityEditableSection, patch: Record<string, unknown>) => {
    setValidation(undefined);
    setDryRunResult(undefined);
    if (section === 'basicInfo') {
      setBasicInfoErrors((current) => {
        const next = { ...current };
        Object.keys(patch).forEach((field) => {
          delete next[field as CapabilityBasicInfoField];
        });
        return next;
      });
    }
    setDraft((current) => {
      const currentSection = current[section] as Record<string, unknown>;
      return normalizeDraft({
        ...current,
        [section]: { ...currentSection, ...patch },
      } as CapabilityActionDraftData);
    });
  };

  const clearTechnicalValidation = () => {
    setValidation(undefined);
    setDryRunResult(undefined);
  };

  const updateActiveTechnicalDraft = (
    updater: (current: CapabilityActionDraftData) => CapabilityActionDraftData,
  ) => {
    clearTechnicalValidation();
    if (activeClient === 'APP') {
      setAppPreviewDraft((current) => normalizeDraft(updater(current)));
      return;
    }
    if (activeClient === 'COMMON') {
      setCommonPreviewDraft((current) => normalizeDraft(updater(current)));
      return;
    }
    setDraft((current) => normalizeDraft(updater(current)));
  };

  const updateTechnicalSection = <Section extends CapabilityTechnicalSection>(
    section: Section,
    patch: Partial<CapabilityActionDraftData[Section]>,
  ) => {
    clearTechnicalValidation();
    if (activeClient === 'APP') {
      setAppPreviewDraft((current) =>
        normalizeDraft(
          updateCapabilityClientTechnicalSection(
            'APP',
            draftRef.current,
            current,
            commonPreviewDraft,
            section,
            patch,
          )?.appPreviewDraft,
        ),
      );
      return;
    }
    if (activeClient === 'COMMON') {
      setCommonPreviewDraft((current) =>
        normalizeDraft(
          updateCapabilityClientTechnicalSection(
            'COMMON',
            draftRef.current,
            appPreviewDraft,
            current,
            section,
            patch,
          )?.commonPreviewDraft,
        ),
      );
      return;
    }
    setDraft((current) =>
      normalizeDraft(
        updateCapabilityClientTechnicalSection(
          'PC',
          current,
          appPreviewDraft,
          commonPreviewDraft,
          section,
          patch,
        )?.canonicalDraft,
      ),
    );
  };


  const formatDemoJson = (
    section: 'modelContract' | 'resultContract',
    field: 'inputExampleJson' | 'responseDemoJson',
    value: string | undefined,
    expanded: boolean,
  ) => {
    try {
      updateTechnicalSection(section, { [field]: formatCapabilityDemoJson(value || '', expanded) });
    } catch {
      message.error('JSON 格式不合法，请修正后重试');
    }
  };
  const updateInputField = (index: number, patch: Partial<CapabilityActionInputField>) => {
    updateActiveTechnicalDraft((current) => {
      const inputFields = [...(current.modelContract?.inputFields || [])];
      inputFields[index] = { ...inputFields[index], ...patch };
      return {
        ...current,
        modelContract: { ...current.modelContract, inputFields },
      };
    });
  };
  const updateAllowedValue = (
    fieldIndex: number,
    valueIndex: number,
    patch: Partial<CapabilityActionAllowedValue>,
  ) => {
    const field = activeTechnicalDraft.modelContract?.inputFields?.[fieldIndex];
    if (!field) return;
    const allowedValues = [...(field.allowedValues || [])];
    allowedValues[valueIndex] = { ...allowedValues[valueIndex], ...patch };
    updateInputField(fieldIndex, { allowedValues });
  };
  const updateKeyOutputField = (index: number, patch: Partial<CapabilityActionKeyOutputField>) => {
    updateActiveTechnicalDraft((current) => {
      const keyOutputFields = [...(current.resultContract?.keyOutputFields || [])];
      keyOutputFields[index] = { ...keyOutputFields[index], ...patch };
      return {
        ...current,
        resultContract: { ...current.resultContract, keyOutputFields },
      };
    });
  };

  const updatePresentationComponents = (components: CapabilityPresentationComponent[]) => {
    updateSection('resultContract', { presentationComponents: components });
  };

  const settlePendingReview = (status: ChangeReviewStatus) => {
    if (pendingReviewChangeSetId) {
      setChangeReviewStatuses((current) => ({
        ...current,
        [pendingReviewChangeSetId]: status,
      }));
    }
    setSelectedChangeIds(new Set());
    setConflictChoices({});
  };

  const clearPendingReview = () => {
    if (
      pendingReviewChangeSetId &&
      (changeReviewStatuses[pendingReviewChangeSetId] || 'PENDING') === 'PENDING'
    ) {
      settlePendingReview('DISCARDED');
    }
  };

  const save = async (): Promise<CapabilityActionDraft | undefined> => {
    if (releaseEditDisabledReason) {
      message.warning(releaseEditDisabledReason || '当前业务能力没有可编辑变更');
      return undefined;
    }
    if (activeStage === 'basic') {
      const errors = capabilityBasicInfoErrors(draft);
      setBasicInfoErrors(errors);
      const firstError = Object.values(errors)?.[0];
      if (firstError) {
        message.warning(firstError);
        return undefined;
      }
      const classificationError = capabilityClassificationError(classification);
      if (classificationError) {
        message.warning(classificationError);
        return undefined;
      }
    }
    setSaving(true);
    try {
      const creating = !draftId;
      const canonicalDraft = buildCapabilityClientCanonicalDraft(
        draft,
        appPreviewDraft,
        commonPreviewDraft,
        supportedClients,
      );
      const saved = await persistCapabilityDraft({
        draftId,
        revision,
        draft: canonicalDraft,
        classification,
        create: capabilityCenterApi.create,
        save: capabilityCenterApi.save,
      });
      const savedClientDrafts = normalizeCapabilityClientDrafts(saved.draft);
      setDraftId(saved.draftId);
      setDraft(savedClientDrafts.canonicalDraft);
      setAppPreviewDraft(savedClientDrafts.appDraft);
      setCommonPreviewDraft(savedClientDrafts.commonDraft);
      setClientMode(savedClientDrafts.clientMode);
      const savedClients = capabilityClientsForMode(savedClientDrafts.clientMode);
      setActiveClient((current) => (savedClients.includes(current) ? current : savedClients?.[0]));
      setRevision(saved.revision);
      setBasicInfoErrors({});
      clearPendingReview();
      setValidation(undefined);
      message.success('草稿已保存');
      if (creating) {
        navigate(`/management/capabilities/edit?draftId=${saved.draftId}`, {
          replace: true,
        });
      }
      return saved;
    } catch (error) {
      message.error(error instanceof Error ? error.message : '草稿保存失败');
      await assetAccess.refresh();
      return undefined;
    } finally {
      setSaving(false);
    }
  };

  const executeDryRun = async (
    saved: CapabilityActionDraft,
    environment: CapabilityActionDryRunEnvironment,
  ) => {
    setDryRunLoadingEnvironment(environment);
    setDryRunResult(undefined);
    setDryRunResultExpanded(true);
    try {
      const result = await capabilityCenterApi.dryRun(
        saved.draftId,
        saved.revision,
        environment,
        activeClient,
      );
      setDryRunResult(result);
      try {
        const overview = await assetReleaseApi.overview('CAPABILITY_ACTION', saved.draftId);
        releaseEditability.acceptOverview(overview);
      } catch {
        message.warning('API 验证结果已保存，发布状态刷新失败，请稍后刷新');
      }
      const traceSummary = result.toolResult?.traceId
        ? `，traceId: ${result.toolResult?.traceId}`
        : '';
      if (result.toolResult?.success) {
        message.success(
          `${environment === 'ONLINE' ? '线上' : 'PRT'} Tool 执行成功${traceSummary}`,
        );
      } else {
        message.error(
          `Tool 执行失败：${
            result.toolResult?.message || result.toolResult?.errorCode || '未知错误'
          }${traceSummary}`,
        );
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Tool 执行失败');
    } finally {
      setDryRunLoadingEnvironment('');
    }
  };

  const runStaticValidation = async (
    saved: CapabilityActionDraft,
  ): Promise<CapabilityActionDraft | undefined> => {
    const result = await capabilityCenterApi.validate(saved.draftId);
    setValidation(result);
    setRevision(result.revision);
    if (!result.valid) {
      message.warning('静态校验未通过，请先修正字段缺口');
      return undefined;
    }
    return { ...saved, revision: result.revision };
  };

  const dryRun = async (environment: CapabilityActionDryRunEnvironment) => {
    if (!supportsCapabilityDirectDryRun(activeTechnicalDraft.apiSource?.sourceType)) {
      message.warning('仅支持 gRPC 能力验证，请检查执行绑定');
      return;
    }
    try {
      await runCapabilityDryRun({
        save,
        execute: (saved) => executeDryRun(saved, environment),
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'API 验证失败';
      message.warning(errorMessage);
    }
  };

  const validate = async () => {
    const saved = await save();
    if (!saved) return;
    try {
      const validated = await runStaticValidation(saved);
      if (!validated) return;
      const overview = await assetReleaseApi.overview('CAPABILITY_ACTION', saved.draftId);
      releaseEditability.acceptOverview(overview);
      message.success('静态校验已通过；发布前请分别完成对应环境的 API 验证');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '草稿校验失败');
    }
  };

  const createCapabilityChange = async () => {
    const normalizedName = changeName.trim();
    if (!draftId || !createChangeView.canCreateChange) return;
    if (!normalizedName) {
      message.warning('请输入变更名称');
      return;
    }
    setCreatingChange(true);
    try {
      const execution = await executeReleaseOperation(
        () =>
          assetReleaseApi.createChange(
            'CAPABILITY_ACTION',
            draftId,
            changeBaseVersion,
            normalizedName,
          ),
        () => assetReleaseApi.overview('CAPABILITY_ACTION', draftId),
      );
      if (execution.feedback?.kind === 'SUCCESS') {
        message.success(execution.feedback?.message);
      } else if (execution.feedback?.kind === 'PENDING') {
        message.info(execution.feedback?.message);
      } else {
        message.error(execution.feedback?.message);
      }
      if (execution.overview) {
        releaseEditability.acceptOverview(execution.overview);
      }
      if (execution.refreshError) {
        message.error('变更已创建，但状态刷新失败，请手动刷新');
      }
      if (execution.feedback?.kind !== 'FAILURE') {
        setChangeName('');
        setChangeBaseVersion(undefined);
        await assetAccess.refresh();
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '新建变更失败');
      await assetAccess.refresh();
    } finally {
      setCreatingChange(false);
    }
  };

  const applyPendingReview = () => {
    if (!pendingReview) return;
    if (draftId && !releaseEditability.editable) {
      message.warning(releaseEditDisabledReason || '当前业务能力没有可编辑变更');
      return;
    }
    if (pendingReview.proposal?.baseRevision !== revision) {
      message.warning(
        `AI 建议基于 r${pendingReview.proposal?.baseRevision}，当前草稿为 r${revision}，请让 AI 重新生成。`,
      );
      return;
    }
    const unresolvedConflicts = pendingReview.changes?.filter?.(
      (change) => change.status === 'conflict' && !conflictChoices[change.id],
    );
    if (unresolvedConflicts.length) {
      message.warning(`还有 ${unresolvedConflicts.length} 个冲突未选择，不能覆盖用户修改。`);
      return;
    }
    try {
      const activeAdapter = formAdapterRegistry.resolve<CapabilityActionDraftData>(
        pendingReview.proposal?.formKey,
      );
      const nextDraft = applyFormPatchReview(
        activeAdapter,
        pendingReview,
        selectedChangeIds,
        conflictChoices,
      );
      activeAdapter.apply(nextDraft);
      settlePendingReview('APPLIED');
      setValidation(undefined);
      message.success('已原子应用选中的 AI 修改，保存后才会写入草稿。');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'AI 修改未应用，当前表单保持不变');
    }
  };

  const retryInitialization = () => {
    setInitializationError('');
    loadDraft(queryDraftId);
  };

  const basicStageReady = Boolean(
    draft.basicInfo.actionCode &&
      draft.basicInfo.nameCn &&
      classification.businessDomain &&
      classification.capabilityDomain &&
      classification.specialistIds.length &&
      draft.basicInfo.technicalOwner &&
      draft.basicInfo.description,
  );
  const contractStageReady = Boolean(
    draft.modelContract.description &&
      (draft.modelContract.inputFields || []).length &&
      draft.modelContract.inputExampleJson &&
      (draft.resultContract.keyOutputFields || []).length &&
      draft.resultContract.responseDemoJson,
  );
  const bindingTarget = draft.executionBinding?.target || {};
  const bindingStageReady = Boolean(
    draft.executionBinding.bindingType === 'GRPC' &&
    bindingTarget.targetKey && bindingTarget.serviceName && bindingTarget.methodName &&
    bindingTarget.descriptorSetBase64 && bindingTarget.contextField,
  );
  const presentationComponentCount = draft.resultContract?.presentationComponents?.length || 0;
  const validationStageReady = capabilityPublishReady;
  const stageReady: Record<CapabilityAuthoringStage, boolean> = {
    basic: basicStageReady,
    contract: contractStageReady,
    binding: bindingStageReady,
    components: presentationComponentCount > 0,
    validation: validationStageReady,
    publish: false,
  };
  const activeStageLabel =
    capabilityAuthoringStages?.find((stage) => stage.key === activeStage)?.label || '能力草稿';
  const pendingStageCounts =
    pendingReview?.changes.reduce<Partial<Record<CapabilityAuthoringStage, number>>>(
      (result, change) => {
        const stage = change.path?.startsWith?.('/basicInfo')
          ? 'basic'
          : change.path?.includes?.('/presentationComponents')
          ? 'components'
          : change.path?.startsWith?.('/modelContract') ||
            change.path?.startsWith?.('/resultContract')
          ? 'contract'
          : change.path?.startsWith?.('/executionBinding') ||
            change.path?.startsWith?.('/apiSource')
          ? 'binding'
          : 'basic';
        result[stage] = (result[stage] || 0) + 1;
        return result;
      },
      {},
    ) || {};

  return (
    <div className="page-container capability-authoring-page">
      <div className="page-header capability-authoring-header">
        <div>
          <h1 className="page-title">{queryDraftId ? '编辑业务能力' : '注册业务能力'}</h1>
          <p className="page-subtitle">能力定义、模型契约、执行绑定与发布治理</p>
        </div>
        <Space>
          {activeStage !== 'publish' ? <Button type="primary" icon={<SaveOutlined />} loading={saving} disabled={loading || Boolean(initializationError) || Boolean(releaseEditDisabledReason)} title={releaseEditDisabledReason || undefined} onClick={() => save()}>保存草稿</Button> : null}
          {!aiDrawerOpen ? (
            null
          ) : null}
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/management/capabilities')}
          >
            返回能力中心
          </Button>
        </Space>
      </div>


      {initializationError ? (
        <Alert
          type="error"
          showIcon
          message="能力草稿初始化失败"
          description={initializationError}
          action={<Button onClick={retryInitialization}>重试</Button>}
        />
      ) : (
        <Spin spinning={loading}>
          {releaseEditDisabledReason && !releaseEditability.loading && !assetAccess.loading ? (
            <Alert
              type="warning"
              showIcon
              message={releaseEditDisabledReason}
              style={{ marginBottom: 12 }}
            />
          ) : null}
          {assetAccess.error ? (
            <Alert type="error" showIcon message={assetAccess.error} style={{ marginBottom: 12 }} />
          ) : null}
          <AuthoringWorkbenchLayout
            railOpen={aiDrawerOpen}
            railView={aiDrawerView}
            onRailOpenChange={setAiDrawerOpen}
            onRailViewChange={setAiDrawerView}
            railTitle="AI 能力设计"
            railSubtitle="提出修改，不直接覆盖表单"
            reviewCount={pendingReview?.changes?.length || 0}
            review={
              pendingReview ? (
                <FormPatchReviewPanel
                  review={pendingReview}
                  selectedChangeIds={selectedChangeIds}
                  conflictChoices={conflictChoices}
                  onToggleChange={(changeId, selected) =>
                    setSelectedChangeIds((current) => {
                      const next = new Set(current);
                      if (selected) next.add(changeId);
                      else next.delete(changeId);
                      return next;
                    })
                  }
                  onConflictChoice={(changeId, choice) =>
                    setConflictChoices((current) => ({
                      ...current,
                      [changeId]: choice,
                    }))
                  }
                  adapter={{
                    targetLabel: '当前业务能力表单草稿',
                    applyLabel: '应用到表单草稿',
                    appliedLabel: '已应用到表单草稿',
                    applyDescription: '只更新当前页面表单，保存和发布仍需单独确认。',
                    applyDisabled: Boolean(releaseEditDisabledReason),
                    status: pendingReviewChangeSetId
                      ? changeReviewStatuses[pendingReviewChangeSetId] || 'PENDING'
                      : 'PENDING',
                    onApply: applyPendingReview,
                    onDiscard: clearPendingReview,
                  }}
                />
              ) : undefined
            }
            chat={
              <SkillFactoryAuthoringChat
                title="对话生成"
                chat={chat}
                onOpenReview={(changeSetId, event) => {
                  let review = formPatchReviews[changeSetId];
                  if (!review && event) {
                    const preparedReview = prepareFormPatchReview(event);
                    if (preparedReview) {
                      review = preparedReview.review;
                      setFormPatchReviews((current) => ({
                        ...current,
                        [preparedReview.changeSetId]: preparedReview.review,
                      }));
                    }
                  }
                  if (!review) {
                    message.info('该表单修改建议不属于当前能力草稿。');
                    return;
                  }
                  openFormPatchReview(changeSetId, review);
                }}
                changeReviewStatuses={changeReviewStatuses}
                placeholder="M 端 AI 辅助暂缓，请手动填写 RPC 服务与方法。"
              />
            }
            className="skill-authoring-workbench"
          >
            <div className="capability-authoring-form-column">
              <div className="skill-factory-tabs capability-authoring-tabs" role="tablist">
                {capabilityAuthoringStages.map((stage) => (
                  <button
                    aria-selected={activeStage === stage.key}
                    className={activeStage === stage.key ? 'active' : ''}
                    key={stage.key}
                    onClick={() => setActiveStage(stage.key)}
                    role="tab"
                    type="button"
                  >
                    <span
                      className={`capability-stage-dot${stageReady[stage.key] ? ' ready' : ''}`}
                    />
                    {stage.label}
                    {pendingStageCounts[stage.key] ? (
                      <span className="capability-stage-ai-count">
                        AI {pendingStageCounts[stage.key]}
                      </span>
                    ) : null}
                    {stage.key === 'components' && presentationComponentCount ? (
                      <span className="capability-stage-count">{presentationComponentCount}</span>
                    ) : null}
                  </button>
                ))}
              </div>
              <Card
                title={activeStage === 'publish' ? undefined : activeStageLabel}
                className={
                  activeStage === 'publish' ? 'capability-authoring-publish-card' : undefined
                }
                extra={
                  activeStage === 'publish' ? undefined : (
                    <Space>
                      {activeStage === 'validation' ? (
                        <Button
                          danger={!capabilityPublishReady}
                          type={capabilityPublishReady ? 'default' : 'primary'}
                          disabled={Boolean(releaseEditDisabledReason)}
                          title={
                            capabilityPublishReady ? PUBLISH_READY_MESSAGE : PUBLISH_BLOCKED_MESSAGE
                          }
                          onClick={validate}
                        >
                          校验
                        </Button>
                      ) : null}
                    </Space>
                  )
                }
              >
                {activeStage === 'basic' ? (
                  <div className="capability-basic-layout">
                    <div className="capability-form-section capability-basic-information-panel">
                      <h3>基础信息</h3>
                      <div className="capability-form-grid">
                        <label
                          className={
                            basicInfoErrors.actionCode ? 'capability-form-field-error' : ''
                          }
                        >
                          actionCode
                          <Input
                            value={draft.basicInfo?.actionCode}
                            placeholder="live.plan.create"
                            onChange={(event) =>
                              updateSection('basicInfo', { actionCode: event.target.value })
                            }
                          />
                          {basicInfoErrors.actionCode ? (
                            <Text type="danger">{basicInfoErrors.actionCode}</Text>
                          ) : null}
                        </label>
                        <label
                          className={basicInfoErrors.nameCn ? 'capability-form-field-error' : ''}
                        >
                          中文名
                          <Input
                            value={draft.basicInfo?.nameCn}
                            placeholder="创建直播计划"
                            onChange={(event) =>
                              updateSection('basicInfo', { nameCn: event.target.value })
                            }
                          />
                          {basicInfoErrors.nameCn ? (
                            <Text type="danger">{basicInfoErrors.nameCn}</Text>
                          ) : null}
                        </label>
                        <label>
                          业务域
                          <Select
                            value={classification.businessDomain || undefined}
                            options={config.businessDomains}
                            placeholder="请选择业务域"
                            onChange={(value) =>
                              setClassification((current) => ({
                                ...current,
                                businessDomain: value,
                              }))
                            }
                          />
                        </label>
                        <label>
                          能力域
                          <Select
                            value={classification.capabilityDomain || undefined}
                            options={config.capabilityDomains}
                            placeholder="请选择能力域"
                            onChange={(value) =>
                              setClassification((current) => ({
                                ...current,
                                capabilityDomain: value,
                              }))
                            }
                          />
                        </label>
                        <label>
                          所属专员
                          <Select
                            mode="multiple"
                            value={classification.specialistIds}
                            options={config.specialists}
                            placeholder="请选择所属专员"
                            onChange={(value) =>
                              setClassification((current) => ({ ...current, specialistIds: value }))
                            }
                          />
                        </label>
                        <label
                          className={
                            basicInfoErrors.technicalOwner ? 'capability-form-field-error' : ''
                          }
                        >
                          技术负责人
                          <Input
                            value={draft.basicInfo?.technicalOwner}
                            onChange={(event) =>
                              updateSection('basicInfo', { technicalOwner: event.target.value })
                            }
                          />
                          {basicInfoErrors.technicalOwner ? (
                            <Text type="danger">{basicInfoErrors.technicalOwner}</Text>
                          ) : null}
                        </label>
                      </div>
                      <label
                        className={`capability-form-field-wide${
                          basicInfoErrors.description ? ' capability-form-field-error' : ''
                        }`}
                      >
                        业务描述
                        <TextArea
                          rows={3}
                          value={draft.basicInfo?.description}
                          onChange={(event) =>
                            updateSection('basicInfo', { description: event.target.value })
                          }
                        />
                        {basicInfoErrors.description ? (
                          <Text type="danger">{basicInfoErrors.description}</Text>
                        ) : null}
                      </label>
                      <div className="capability-client-support-field capability-form-field-wide">
                        <label>
                          支持端
                          <Select
                            value={clientMode}
                            options={CAPABILITY_CLIENT_MODE_OPTIONS}
                            placeholder="请选择支持端"
                            onChange={(value) => updateClientMode(value as CapabilityClientMode)}
                          />
                        </label>
                        <Text type="secondary">
                          四种模式互斥保存；只有“PC 与 APP 不同”会展示端侧切换。
                        </Text>
                      </div>
                    </div>
                    {draftId ? (
                      <aside className="capability-form-section capability-create-change-panel">
                        <div className="capability-create-change-heading">
                          <h3>创建变更</h3>
                          <Tag color={createChangeView.canCreateChange ? 'blue' : 'default'}>
                            {createChangeView.canCreateChange ? '可新建' : '当前不可新建'}
                          </Tag>
                        </div>
                        <Text type="secondary">
                          已上线内容需要先创建编辑中变更，才能修改左侧基础信息。
                        </Text>
                        <label>
                          来源版本
                          <Select
                            allowClear
                            disabled={!createChangeView.canCreateChange}
                            options={createChangeView.versionOptions}
                            placeholder="来源版本（选择后恢复）"
                            value={changeBaseVersion}
                            onChange={(value) => setChangeBaseVersion(value as number | undefined)}
                          />
                        </label>
                        <label>
                          变更名称
                          <Input
                            disabled={!createChangeView.canCreateChange}
                            maxLength={80}
                            placeholder="请输入变更名称"
                            value={changeName}
                            onChange={(event) => setChangeName(event.target.value)}
                            onPressEnter={() => createCapabilityChange()}
                          />
                        </label>
                        <Button
                          className="capability-create-change-button"
                          icon={<PlusOutlined />}
                          disabled={createChangeView.submitDisabled}
                          loading={creatingChange}
                          title={createChangeView.submitTitle}
                          onClick={createCapabilityChange}
                        >
                          {createChangeView.submitLabel}
                        </Button>
                        {!createChangeView.canCreateChange ? (
                          <Text type="secondary">{createChangeView.submitTitle}</Text>
                        ) : null}
                      </aside>
                    ) : null}
                  </div>
                ) : null}

                {activeStage === 'contract' ? (
                  <div className="capability-form-section">
                    <CapabilityClientTechnicalNavigation
                      activeClient={activeClient}
                      clientMode={clientMode}
                      onActiveClientChange={setActiveClient}
                      onClientModeChange={updateClientMode}
                    />
                    <div className="capability-stage-intro compact">
                      <div>
                        <h3>{activeClient} 参数契约</h3>
                        <Text type="secondary">
                          切换端后独立维护入参字段、入参 Demo、响应 Demo 和关键出参路径。
                        </Text>
                      </div>
                      <Tag color={activeClient === 'APP' ? 'orange' : 'green'}>
                        {activeClient} 端保存协议
                      </Tag>
                    </div>
                    <label className="capability-form-field-wide">
                      模型使用说明
                      <TextArea
                        rows={2}
                        value={activeTechnicalDraft.modelContract?.description}
                        onChange={(event) =>
                          updateTechnicalSection('modelContract', {
                            description: event.target.value,
                          })
                        }
                      />
                    </label>

                    <div className="capability-contract-subsection">
                      <div className="capability-section-title">
                        <h3>入参字段</h3>
                        <Button
                          size="small"
                          icon={<PlusOutlined />}
                          onClick={() =>
                            updateTechnicalSection('modelContract', {
                              inputFields: [
                                ...(activeTechnicalDraft.modelContract?.inputFields || []),
                                { source: 'MODEL_INPUT', type: 'string', required: false },
                              ],
                            })
                          }
                        >
                          添加入参
                        </Button>
                      </div>
                      <div className="capability-field-list">
                        {(activeTechnicalDraft.modelContract?.inputFields || []).map(
                          (field, index) => (
                            <div
                              className="capability-input-field"
                              key={`${field.toolField || 'field'}-${index}`}
                            >
                              <div className="capability-section-title">
                                <Text strong>字段 {index + 1}</Text>
                                <Button
                                  size="small"
                                  icon={<DeleteOutlined />}
                                  onClick={() =>
                                    updateTechnicalSection('modelContract', {
                                      inputFields: (
                                        activeTechnicalDraft.modelContract?.inputFields || []
                                      ).filter((_, itemIndex) => itemIndex !== index),
                                    })
                                  }
                                />
                              </div>
                              <div className="capability-form-grid compact">
                                <label>
                                  字段名
                                  <Input
                                    value={field.toolField}
                                    placeholder="英文 JSON 字段名，例如 liveTitle"
                                    onChange={(event) =>
                                      updateInputField(index, { toolField: event.target.value })
                                    }
                                  />
                                </label>
                                <label>
                                  类型
                                  <Select
                                    value={field.type}
                                    options={fieldTypeOptions}
                                    disabled={field.source === 'SYSTEM_VARIABLE'}
                                    placeholder="请选择"
                                    onChange={(value) => {
                                      const type = value as CapabilityActionInputField['type'];
                                      updateInputField(index, {
                                        type,
                                        items:
                                          type === 'array'
                                            ? field.items || { type: 'object', properties: {} }
                                            : undefined,
                                        allowedValues:
                                          type === 'string' || type === 'number' || type === 'integer'
                                            ? normalizeCapabilityAllowedValuesForType(
                                                type,
                                                field.allowedValues,
                                              )
                                            : undefined,
                                        ...(field.source === 'CONSTANT'
                                          ? {
                                              constantValue:
                                                type === 'boolean'
                                                  ? typeof field.constantValue === 'boolean'
                                                    ? field.constantValue
                                                    : false
                                                  : type === 'array'
                                                  ? Array.isArray(field.constantValue)
                                                    ? field.constantValue
                                                    : []
                                                  : undefined,
                                            }
                                          : {}),
                                      });
                                    }}
                                  />
                                </label>
                                <label>
                                  单位（可选）
                                  <Input
                                    value={field.unit}
                                    placeholder="例如：元、自然日、毫秒"
                                    onChange={(event) =>
                                      updateInputField(index, { unit: event.target.value })
                                    }
                                  />
                                </label>
                                <label>
                                  来源
                                  <Select
                                    value={field.source}
                                    options={fieldSourceOptions}
                                    placeholder="请选择"
                                    onChange={(value) => {
                                      const source = value as CapabilityActionInputField['source'];
                                      if (source === 'CONSTANT') {
                                        updateInputField(index, {
                                          source,
                                          constantValue:
                                            field.type === 'boolean'
                                              ? false
                                              : field.type === 'array'
                                              ? []
                                              : undefined,
                                          required: false,
                                          examples: undefined,
                                          allowedValues: undefined,
                                          systemVariable: undefined,
                                          valueMapping: undefined,
                                        });
                                      } else if (source === 'SYSTEM_VARIABLE') {
                                        updateInputField(index, {
                                          source,
                                          type: 'number',
                                          items: undefined,
                                          required: false,
                                          examples: undefined,
                                          allowedValues: undefined,
                                          constantValue: undefined,
                                          systemVariable: 'userId',
                                          valueMapping: undefined,
                                        });
                                      } else {
                                        updateInputField(index, {
                                          source,
                                          constantValue: undefined,
                                          systemVariable: undefined,
                                          valueMapping: undefined,
                                        });
                                      }
                                    }}
                                  />
                                </label>
                                {field.source === 'CONSTANT' ? (
                                  field.type === 'boolean' ? (
                                    <label>
                                      常量值
                                      <Select
                                        value={field.constantValue === true ? 'true' : 'false'}
                                        options={[
                                          { value: 'true', label: 'true' },
                                          { value: 'false', label: 'false' },
                                        ]}
                                        onChange={(value) =>
                                          updateInputField(index, {
                                            constantValue: value === 'true',
                                          })
                                        }
                                      />
                                    </label>
                                  ) : field.type === 'array' ? (
                                    <label className="capability-form-field-wide">
                                      常量数组 JSON
                                      <TextArea
                                        key={`constant-array-${index}-${JSON.stringify(
                                          field.constantValue || [],
                                        )}`}
                                        rows={5}
                                        defaultValue={JSON.stringify(
                                          field.constantValue || [],
                                          null,
                                          2,
                                        )}
                                        placeholder={'[\n  { "itemId": 1 }\n]'}
                                        onBlur={(event) => {
                                          try {
                                            const constantValue = JSON.parse(event.target.value);
                                            if (!Array.isArray(constantValue))
                                              throw new Error('not array');
                                            updateInputField(index, { constantValue });
                                          } catch {
                                            message.error('常量数组必须是合法的 JSON 数组');
                                          }
                                        }}
                                      />
                                    </label>
                                  ) : (
                                    <label>
                                      常量值
                                      <Input
                                        type={(field.type === 'number' || field.type === 'integer') ? 'number' : 'text'}
                                        value={field.constantValue as string | number | undefined}
                                        placeholder="请输入固定值"
                                        onChange={(event) =>
                                          updateInputField(index, {
                                            constantValue:
                                              (field.type === 'number' || field.type === 'integer')
                                                ? event.target.value === ''
                                                  ? undefined
                                                  : Number(event.target.value)
                                                : event.target.value,
                                          })
                                        }
                                      />
                                    </label>
                                  )
                                ) : field.source === 'SYSTEM_VARIABLE' ? (
                                  <label>
                                    系统变量
                                    <Select
                                      value={field.systemVariable}
                                      options={systemVariableOptions}
                                      placeholder="请选择"
                                      onChange={(value) => {
                                        const systemVariable =
                                          value as CapabilityActionInputField['systemVariable'];
                                        updateInputField(index, {
                                          systemVariable,
                                          type: 'string',
                                          items: undefined,
                                          valueMapping:
                                            systemVariable === 'client'
                                              ? field.valueMapping
                                              : undefined,
                                        });
                                      }}
                                    />
                                  </label>
                                ) : (
                                  <label>
                                    必填
                                    <Select
                                      value={field.required ? 'true' : 'false'}
                                      options={[
                                        { value: 'true', label: '必填' },
                                        { value: 'false', label: '选填' },
                                      ]}
                                      onChange={(value) =>
                                        updateInputField(index, { required: value === 'true' })
                                      }
                                    />
                                  </label>
                                )}
                                <label className="capability-form-field-wide">
                                  业务含义
                                  <Input
                                    value={field.businessMeaning}
                                    onChange={(event) =>
                                      updateInputField(index, {
                                        businessMeaning: event.target.value,
                                      })
                                    }
                                  />
                                </label>
                                {field.type === 'array' ? (
                                  <CapabilityInputSchemaEditor
                                    value={field.items}
                                    onChange={(items) => updateInputField(index, { items })}
                                  />
                                ) : null}
                                {field.source === 'MODEL_INPUT' &&
                                (field.type === 'string' || (field.type === 'number' || field.type === 'integer')) ? (
                                  <div className="capability-enum-editor capability-form-field-wide">
                                    <div className="capability-section-title">
                                      <div>
                                        <Text strong>可选值（枚举）</Text>
                                        <Text type="secondary">
                                          可选；配置后只允许使用这些值。单位不会参与参数执行。
                                        </Text>
                                      </div>
                                      <Button
                                        size="small"
                                        icon={<PlusOutlined />}
                                        onClick={() =>
                                          updateInputField(index, {
                                            allowedValues: [
                                              ...(field.allowedValues || []),
                                              { value: undefined, label: '', description: '' },
                                            ],
                                          })
                                        }
                                      >
                                        添加枚举值
                                      </Button>
                                    </div>
                                    {(field.allowedValues || []).map((allowedValue, valueIndex) => (
                                      <div
                                        className="capability-enum-row"
                                        key={`${index}-${valueIndex}`}
                                      >
                                        <Input
                                          type={(field.type === 'number' || field.type === 'integer') ? 'number' : 'text'}
                                          value={
                                            allowedValue.value === undefined
                                              ? ''
                                              : String(allowedValue.value)
                                          }
                                          placeholder="实际参数值"
                                          onChange={(event) =>
                                            updateAllowedValue(index, valueIndex, {
                                              value: capabilityAllowedValueFromText(
                                                field.type,
                                                event.target.value,
                                              ),
                                            })
                                          }
                                        />
                                        <Input
                                          value={allowedValue.label}
                                          placeholder="中文含义（必填）"
                                          onChange={(event) =>
                                            updateAllowedValue(index, valueIndex, {
                                              label: event.target.value,
                                            })
                                          }
                                        />
                                        <Input
                                          value={allowedValue.description}
                                          placeholder="补充说明（可选）"
                                          onChange={(event) =>
                                            updateAllowedValue(index, valueIndex, {
                                              description: event.target.value,
                                            })
                                          }
                                        />
                                        <Button
                                          size="small"
                                          icon={<DeleteOutlined />}
                                          onClick={() =>
                                            updateInputField(index, {
                                              allowedValues: field.allowedValues?.filter(
                                                (_, itemIndex) => itemIndex !== valueIndex,
                                              ),
                                            })
                                          }
                                        />
                                      </div>
                                    ))}
                                  </div>
                                ) : null}
                                {field.source === 'MODEL_INPUT' ? (
                                  <label className="capability-form-field-wide">
                                    示例
                                    <Input
                                      value={field.examples}
                                      placeholder="给模型看的合法业务示例"
                                      onChange={(event) =>
                                        updateInputField(index, { examples: event.target.value })
                                      }
                                    />
                                  </label>
                                ) : null}
                                {field.source === 'SYSTEM_VARIABLE' &&
                                field.systemVariable === 'client' ? (
                                  <label className="capability-form-field-wide">
                                    client 值映射（可选）
                                    <TextArea
                                      key={`client-value-mapping-${index}-${JSON.stringify(
                                        field.valueMapping || {},
                                      )}`}
                                      rows={3}
                                      defaultValue={
                                        Object.keys(field.valueMapping || {}).length
                                          ? JSON.stringify(field.valueMapping, null, 2)
                                          : ''
                                      }
                                      placeholder={'{\n  "app": "APP"\n}'}
                                      onBlur={(event) => {
                                        try {
                                          updateInputField(index, {
                                            valueMapping: parseClientValueMapping(
                                              event.target.value,
                                            ),
                                          });
                                        } catch {
                                          message.error(
                                            'client 值映射必须是字符串到字符串的 JSON 对象',
                                          );
                                        }
                                      }}
                                    />
                                  </label>
                                ) : null}
                              </div>
                            </div>
                          ),
                        )}
                      </div>
                      <label className="capability-form-field-wide">
                        <span className="capability-json-field-heading">
                          <span>入参 Demo JSON</span>
                          <Space size={4}>
                            <Button
                              size="small"
                              onClick={() =>
                                formatDemoJson(
                                  'modelContract',
                                  'inputExampleJson',
                                  activeTechnicalDraft.modelContract?.inputExampleJson,
                                  true,
                                )
                              }
                            >
                              展开 JSON
                            </Button>
                            <Button
                              size="small"
                              onClick={() =>
                                formatDemoJson(
                                  'modelContract',
                                  'inputExampleJson',
                                  activeTechnicalDraft.modelContract?.inputExampleJson,
                                  false,
                                )
                              }
                            >
                              折叠 JSON
                            </Button>
                          </Space>
                        </span>
                        <TextArea
                          rows={6}
                          value={activeTechnicalDraft.modelContract?.inputExampleJson}
                          placeholder={'{\n  "liveTitle": "夏季新品专场"\n}'}
                          onChange={(event) =>
                            updateTechnicalSection('modelContract', {
                              inputExampleJson: event.target.value,
                            })
                          }
                        />
                      </label>
                    </div>

                    <div className="capability-contract-subsection">
                      <div className="capability-stage-intro compact">
                        <div>
                          <h3>响应 Demo JSON</h3>
                          <Text type="secondary">
                            完整响应结构只维护这一份脱敏 Demo；技术 Schema
                            和关键字段类型由系统自动生成。
                          </Text>
                        </div>
                      </div>
                      <label className="capability-form-field-wide">
                        <span className="capability-json-field-heading">
                          <span>脱敏响应 Demo</span>
                          <Space size={4}>
                            <Button
                              size="small"
                              onClick={() =>
                                formatDemoJson(
                                  'resultContract',
                                  'responseDemoJson',
                                  activeTechnicalDraft.resultContract?.responseDemoJson,
                                  true,
                                )
                              }
                            >
                              展开 JSON
                            </Button>
                            <Button
                              size="small"
                              onClick={() =>
                                formatDemoJson(
                                  'resultContract',
                                  'responseDemoJson',
                                  activeTechnicalDraft.resultContract?.responseDemoJson,
                                  false,
                                )
                              }
                            >
                              折叠 JSON
                            </Button>
                          </Space>
                        </span>
                        <TextArea
                          rows={10}
                          value={activeTechnicalDraft.resultContract?.responseDemoJson}
                          placeholder={
                            '{\n  "data": {\n    "card": {\n      "url": "https://example.com/detail"\n    }\n  }\n}'
                          }
                          onChange={(event) =>
                            updateTechnicalSection('resultContract', {
                              responseDemoJson: event.target.value,
                            })
                          }
                        />
                      </label>
                      <div className="capability-section-title">
                        <h3>关键出参字段</h3>
                        <Button
                          size="small"
                          icon={<PlusOutlined />}
                          onClick={() =>
                            updateTechnicalSection('resultContract', {
                              keyOutputFields: [
                                ...(activeTechnicalDraft.resultContract?.keyOutputFields || []),
                                {},
                              ],
                            })
                          }
                        >
                          添加关键字段
                        </Button>
                      </div>
                      <Text type="secondary">
                        只填写会影响模型判断、后续动作或业务卡片展示的字段，例如{' '}
                        <code>data.card.url</code>、<code>data.cards[].url</code>。
                      </Text>
                      <div className="capability-field-list">
                        {(activeTechnicalDraft.resultContract?.keyOutputFields || []).map(
                          (field, index) => {
                            const resolvedValue = resolveDemoPath(
                              activeTechnicalDraft.resultContract?.responseDemoJson,
                              field.path,
                            );
                            const observedType =
                              resolvedValue === undefined ? '' : observedTypeOf(resolvedValue);
                            return (
                              <div
                                className="capability-input-field"
                                key={`${field.path || 'key-output'}-${index}`}
                              >
                                <div className="capability-section-title">
                                  <Text strong>关键字段 {index + 1}</Text>
                                  <Button
                                    size="small"
                                    icon={<DeleteOutlined />}
                                    onClick={() =>
                                      updateTechnicalSection('resultContract', {
                                        keyOutputFields: (
                                          activeTechnicalDraft.resultContract?.keyOutputFields || []
                                        ).filter((_, itemIndex) => itemIndex !== index),
                                      })
                                    }
                                  />
                                </div>
                                <div className="capability-form-grid">
                                  <label>
                                    响应字段路径
                                    <Input
                                      value={field.path}
                                      placeholder="data.card.url"
                                      onChange={(event) =>
                                        updateKeyOutputField(index, { path: event.target.value })
                                      }
                                    />
                                  </label>
                                  <label>
                                    识别类型
                                    <div>
                                      <Tag>{observedType || '等待有效 Demo 与路径'}</Tag>
                                    </div>
                                  </label>
                                  <label className="capability-form-field-wide">
                                    业务说明
                                    <Input
                                      value={field.description}
                                      placeholder="卡片点击后的跳转链接"
                                      onChange={(event) =>
                                        updateKeyOutputField(index, {
                                          description: event.target.value,
                                        })
                                      }
                                    />
                                  </label>
                                </div>
                              </div>
                            );
                          },
                        )}
                      </div>
                    </div>
                  </div>
                ) : null}

                {activeStage === 'binding' ? (
                  <div className="capability-form-section">
                    <CapabilityClientTechnicalNavigation
                      activeClient={activeClient}
                      clientMode={clientMode}
                      onActiveClientChange={setActiveClient}
                      onClientModeChange={updateClientMode}
                    />
                    <CapabilityClientVariantReview
                      activeClient={activeClient}
                      draft={activeTechnicalDraft}
                    />
                    <div className="capability-current-contract-editor">
                      <div className="capability-stage-intro compact">
                        <div>
                          <h3>{activeClient} API 来源与执行绑定</h3>
                          <Text type="secondary">
                            服务、方法、协议描述、请求映射和参数契约按当前端独立配置。
                          </Text>
                        </div>
                        <Tag color={activeClient === 'APP' ? 'orange' : 'green'}>
                          {activeClient} 端保存协议
                        </Tag>
                      </div>
                      <div className="capability-form-grid capability-client-api-source-editor">
                        <label>调用协议<Select value="GRPC" options={[{ value: 'GRPC', label: 'gRPC 服务（Unary）' }]} disabled /></label>
                      </div>
                      <CapabilityExecutionBindingEditor
                        value={activeTechnicalDraft.executionBinding}
                        inputFields={activeTechnicalDraft.modelContract?.inputFields || []}
                        sourceType="GRPC"
                        onChange={(patch) => updateTechnicalSection('executionBinding', patch)}
                      />
                    </div>
                  </div>
                ) : null}

                {activeStage === 'components' ? (
                  <CapabilityPresentationComponents
                    value={draft.resultContract?.presentationComponents}
                    onChange={updatePresentationComponents}
                  />
                ) : null}

                {activeStage === 'validation' ? (
                  <section className="capability-release-preflight">
                    <div className="asset-release-section-heading">
                      <div>
                        <h3>契约与治理校验</h3>
                        <Text type="secondary">
                          静态契约检查与 PRT / ONLINE RPC 验证分别形成发布门禁。
                        </Text>
                      </div>
                        <Space>
                          <Button
                            loading={dryRunLoadingEnvironment === 'PRT'}
                            disabled={Boolean(dryRunLoadingEnvironment)}
                            onClick={() => dryRun('PRT')}
                          >
                            验证 PRT
                          </Button>
                          <Button
                            loading={dryRunLoadingEnvironment === 'ONLINE'}
                            disabled={Boolean(dryRunLoadingEnvironment)}
                            onClick={() => dryRun('ONLINE')}
                          >
                            验证线上
                          </Button>
                        </Space>
                    </div>

                    <div className="capability-validation-panel">
                      <div className="capability-stage-intro compact">
                        <div>
                          <h3>校验结果</h3>
                          <Text type={capabilityPublishReady ? 'success' : 'danger'}>
                            {capabilityPublishReady
                              ? PUBLISH_READY_MESSAGE
                              : PUBLISH_BLOCKED_MESSAGE}
                          </Text>
                        </div>
                        <Tag color={capabilityPublishReady ? 'success' : 'error'}>
                          {capabilityPublishReady ? '可发布' : '不可发布'}
                        </Tag>
                      </div>
                      {validation ? (
                        validationMessages.map((item) => (
                          <Paragraph
                            className={`capability-validation-${item.kind}`}
                            key={item.message}
                          >
                            {item.message}
                          </Paragraph>
                        ))
                      ) : (
                        <Text type="danger">尚未完成校验。</Text>
                      )}
                    </div>

                    <div className="capability-form-section">
                      <h3>结果与治理</h3>
                      <div className="capability-form-grid">
                        <label>
                          副作用
                          <Select
                            value={draft.governance?.sideEffectLevel}
                            options={sideEffectOptions}
                            onChange={(value) =>
                              updateSection('governance', { sideEffectLevel: value })
                            }
                          />
                        </label>

                        <label>
                          技术输出 Schema
                          <div>
                            <Tag
                              color={
                                draft.resultContract?.technicalOutputSchema ? 'success' : 'default'
                              }
                            >
                              {draft.resultContract?.technicalOutputSchema
                                ? '已由响应 Demo 自动生成'
                                : '等待保存有效响应 Demo'}
                            </Tag>
                          </div>
                        </label>
                        <label className="capability-form-field-wide">
                          错误映射
                          <TextArea
                            rows={2}
                            value={draft.resultContract?.errorMappings}
                            placeholder="服务错误 -> 模型可理解的业务错误"
                            onChange={(event) =>
                              updateSection('resultContract', { errorMappings: event.target.value })
                            }
                          />
                        </label>
                      </div>
                    </div>

                    {dryRunResult ? (
                      <div className="capability-dry-run-result">
                        <div className="capability-section-title">
                          <div>
                            <h3>本次 Tool 验证结果</h3>
                            <Text type="secondary">
                              请求详情仅用于本次验证展示，用户身份由可信 Host 注入。
                            </Text>
                          </div>
                          <Space size={8}>
                            <Tag color={dryRunResult.toolResult?.success ? 'success' : 'error'}>
                              {dryRunResult.toolResult?.success ? '执行成功' : '执行失败'}
                            </Tag>
                            <Button size="small" onClick={() => setDryRunResultExpanded(true)}>
                              展开 JSON
                            </Button>
                            <Button size="small" onClick={() => setDryRunResultExpanded(false)}>
                              折叠 JSON
                            </Button>
                          </Space>
                        </div>
                        <div className="capability-dry-run-summary">
                          <span>
                            <Text type="secondary">验证环境</Text>
                            <Text>{dryRunResult.environment}</Text>
                          </span>
                          <span>
                            <Text type="secondary">服务配置键</Text>
                            <Text>{dryRunResult.targetKey || '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">调用协议</Text>
                            <Text>{dryRunResult.protocol || '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">RPC 方法</Text>
                            <Text>{dryRunResult.methodName || '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">服务名</Text>
                            <Text>{dryRunResult.serviceName || '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">actionCode</Text>
                            <Text>{dryRunResult.toolResult?.actionCode || '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">capabilityVersion</Text>
                            <Text>{dryRunResult.toolResult?.capabilityVersion ?? '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">requestedEnvironment</Text>
                            <Text>{dryRunResult.toolResult?.requestedEnvironment || '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">resolvedEnvironment</Text>
                            <Text>{dryRunResult.toolResult?.resolvedEnvironment || '-'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">调用状态</Text>
                            <Text>{dryRunResult.toolResult?.success ? '成功' : '失败'}</Text>
                          </span>
                          <span>
                            <Text type="secondary">响应映射</Text>
                            <Text>ProtoJSON</Text>
                          </span>
                          <span>
                            <Text type="secondary">traceId</Text>
                            <Text copyable={Boolean(dryRunResult.toolResult?.traceId)}>
                              {dryRunResult.toolResult?.traceId || '-'}
                            </Text>
                          </span>
                          <span>
                            <Text type="secondary">errorCode</Text>
                            <Text>{dryRunResult.toolResult?.errorCode || '-'}</Text>
                          </span>
                          <span className="capability-dry-run-summary-wide">
                            <Text type="secondary">message</Text>
                            <Text>{dryRunResult.toolResult?.message || '-'}</Text>
                          </span>
                        </div>
                        <div className="capability-dry-run-detail-grid">
                          <div>
                            <Text strong>有效入参</Text>
                            <pre className="capability-dry-run-json">
                              {formatCapabilityDryRunResult(
                                dryRunResult.effectiveArguments || {},
                                true,
                              )}
                            </pre>
                          </div>
                          <div>
                            <Text strong>有效请求 Body</Text>
                            <pre className="capability-dry-run-json">
                              {formatCapabilityDryRunResult(
                                dryRunResult.effectiveRequestBody || {},
                                true,
                              )}
                            </pre>
                          </div>
                        </div>
                        <Text strong>完整 ToolResult</Text>
                        <pre className="capability-dry-run-json">
                          {formatCapabilityDryRunResult(
                            dryRunResult.toolResult,
                            dryRunResultExpanded,
                          )}
                        </pre>
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {activeStage === 'publish' && draftId ? (
                  <section className="capability-release-management">
                    <AssetReleaseTab
                      assetKey={draftId}
                      assetType="CAPABILITY_ACTION"
                      title="业务能力发布管理"
                      showCreateChange={false}
                      onOverviewChange={releaseEditability.acceptOverview}
                    />
                  </section>
                ) : null}
              </Card>
            </div>
          </AuthoringWorkbenchLayout>
        </Spin>
      )}
    </div>
  );
};

export default CapabilityActionAuthoringPage;
