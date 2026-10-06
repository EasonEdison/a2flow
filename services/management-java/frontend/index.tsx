import React, { useEffect, useMemo, useRef, useState } from 'react';
import { jsonParse, jsonStringify } from './shared/safeJson';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Pagination,
  Select,
  Space,
  Spin,
  Tag,
  Tree,
  Typography,
  message,
} from 'antd';
import {
  CodeOutlined,
  CheckOutlined,
  DeleteOutlined,
  DownOutlined,
  DownloadOutlined,
  EditOutlined,
  FileMarkdownOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SafetyOutlined,
  SearchOutlined,
  StopOutlined,
  ThunderboltOutlined,
  UnlockOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { listDigitalEmployeeDefinitions } from './employeesApi';
import {
  SKILL_FACTORY_CHAT_BIZ_KEYS,
  SkillFactoryMethod,
  assetReleaseApi,
  capabilityCenterApi,
  componentCenterApi,
  skillBindingCandidateApi,
  skillFactoryApi,
  type SkillListQuery,
} from './api';
import {
  AnswerLayer,
  SkillFactoryAuthoringChat,
  useSkillFactoryChatStream,
} from './shared/authoringChat';
import type { SkillFactoryAuthoringMessage } from './shared/authoringChat';
import { createSkillCodingAuthoringAdapter } from './shared/authoringChat/adapters/skillCodingAdapter';
import AuthoringWorkbenchLayout, {
  type AuthoringRailView,
} from './shared/AuthoringWorkbenchLayout';
import AuthoringChangeReviewFrame from './shared/authoringChangeReview';
import {
  type ChangeReviewStatus,
  isActionablePatchProposal,
  isPatchDomainEvent,
  isPatchReviewEvent,
  isPatchSettledEvent,
  patchReviewStatus,
} from './shared/authoringChangeReview/patchProjection';
import {
  domainResultToolCallIds,
  shouldDisplayGenericToolResult,
} from './shared/authoringChat/toolResultProjection';
import AssetReleaseTab from './shared/AssetReleaseTab';
import { executeReleaseOperation } from './shared/releaseOperationFeedback';
import AssetEnvironmentFacts from './shared/AssetEnvironmentFacts';
import { BINDING_TRACE_PAGE_URL, openBindingTracePage } from './bindingValidationNavigation';
import {
  buildSpecialistDebugOptions,
  buildSpecialistManagementUrl,
  resolveSpecialistDebugSelection,
  resolveSpecialistPrtAction,
  SKILL_FACTORY_TAB_ITEMS,
  type SpecialistDebugOption,
} from './specialistPrtDebug';
import {
  decodeWorkspaceZipBase64,
  resolveWorkspaceZipFileName,
  triggerWorkspaceZipDownload,
} from './workspaceZipDownload';
import {
  buildWorkspaceResetOptionGroups,
  defaultWorkspaceResetValue,
  findWorkspaceResetOption,
  parseWorkspaceResetValue,
  resetSourceDisplayName,
} from './workspaceResetSource';
import {
  capabilitySideEffectText,
  capabilitySourceText,
  capabilityStatusText,
} from './shared/capabilityDisplayText';
import { useAssetAccess } from './shared/AssetAccessContext';
import PatchDiffPreview from './shared/diff/PatchDiffPreview';
import {
  defaultSkillFactorySpecialists as defaultSpecialists,
  normalizeSkillFactorySpecialists as normalizeSpecialists,
  specialistOptionId,
  specialistOptionName,
} from './shared/specialistOptions';
import type {
  AuthoringSessionScopeParams,
  CapabilityActionDraft,
  ReleaseVersionOptions,
  SkillFactoryCodingEvent,
  SkillFactoryCapabilityBinding,
  SkillFactoryCapabilityBindMode,
  SkillFactoryComponentBinding,
  SkillFactoryDomainOption,
  SkillFactoryMethodCode,
  SkillFactoryPageConfig,
  SkillFactoryQuickPrompt,
  SkillFactoryReferenceAsset,
  SkillFactoryReferenceComponent,
  SkillFactorySpecialistOption,
  SkillInfoPayload,
  SpecialistPrtBindingState,
  SkillDraft,
  SkillTreeNode,
  WorkspaceFileContent,
  WorkspaceTreeResult,
  WorkspaceViewMode,
} from './api';
import type { ComponentRenderPreviewResult, SkillFactoryComponentAsset } from './types';

const { Text } = Typography;
const { TextArea } = Input;

type WorkbenchTab = 'overview' | 'capabilities' | 'components' | 'files' | 'binding' | 'release';

type SkillInfoMode = 'create' | 'edit';
type AssistantMessageStatus = 'streaming' | 'done' | 'cancelled' | 'error';

interface SkillInfoFormValues {
  skillCode: string;
  skillNameCn: string;
  skillDescription?: string;
  businessDomain?: string;
  capabilityDomain?: string;
  specialistIds: string[];
  owner?: string;
  version?: string;
}

const DEFAULT_B_END_DEBUG_PAGE_URL = '/employee/';




const ZIP_EXPORT_ACTION_KEY = SkillFactoryMethod.WORKSPACE_ZIP_EXPORT;
const DEFAULT_AI_CODING_CLIENT = 'pc';
const DEFAULT_SKILL_CODING_AGENT_ID = '244510';
const DEFAULT_SKILL_CODING_OWNER_ID = 'system';

const DEFAULT_VERSION_LABEL = '1';
const SPECIALIST_DEBUG_LIST_PAGE_SIZE = 200;
const WORKSPACE_VIEW_PREPROD_CURRENT: WorkspaceViewMode = 'PREPROD_CURRENT';
const WORKSPACE_VIEW_ONLINE_RELEASE: WorkspaceViewMode = 'ONLINE_RELEASE';
const STREAM_TEXT_EVENT_TYPES = new Set(['ANSWER_TEXT_DELTA']);
const STREAM_MODEL_CONTENT_EVENT_TYPE = 'MODEL_CONTENT_DELTA';
const MODEL_CONTENT_TYPE_TEXT = 'TEXT';
const MODEL_CONTENT_TYPE_THINKING = 'THINKING';
const STREAM_THINKING_EVENT_TYPE = 'THINK_TEXT_DELTA';
const STREAM_DEBUG_EVENT_TYPES = new Set(['TOOL_CALL', 'TOOL_RESULT', 'STDOUT', 'STDERR', 'USAGE']);
const AUTHORING_EVENT_A2UI_MESSAGE = 'A2UI_MESSAGE';
const AUTHORING_EVENT_BUSINESS_INTERACTION = 'BUSINESS_INTERACTION_CREATED';
const AUTHORING_EVENT_OBSERVATION = 'AUTHORING_OBSERVATION';
const AUTHORING_EVENT_OBSERVATION_CREATED = 'OBSERVATION_CREATED';
const AUTHORING_EVENT_AG_UI = 'AG_UI_EVENT';
const STREAM_EVENT_TOOL_CALL_STARTED = 'TOOL_CALL_STARTED';
const STREAM_EVENT_TOOL_CALL_FINISHED = 'TOOL_CALL_FINISHED';
const STREAM_EVENT_RUN_COMPLETED = 'RUN_COMPLETED';
const STREAM_EVENT_RUN_FAILED = 'RUN_FAILED';
const STREAM_EVENT_RUN_CANCELLED = 'RUN_CANCELLED';
const LEGACY_EVENT_COMPLETED = 'COMPLETED';
const LEGACY_EVENT_FAILED = 'FAILED';
const DIAGNOSTIC_EVENT_ERROR = 'ERROR';
const STREAM_EVENT_VALIDATION_TASK_STARTED = 'VALIDATION_TASK_STARTED';
const STREAM_EVENT_VALIDATION_REPORT_CREATED = 'VALIDATION_REPORT_CREATED';
const PAYLOAD_TYPE_VALIDATION_REPORT = 'VALIDATION_REPORT';
const TRACE_STAGE_COLLAPSED_COUNT = 3;
const TRACE_DETAIL_MAX_LENGTH = 120;
const TRACE_RAW_DETAIL_MAX_LENGTH = 220;
const PATCH_DISPLAY_NAME_MAX_LENGTH = 20;
const SKILL_DESCRIPTION_MAX_LENGTH = 500;
const SKILL_DESCRIPTION_MAX_LENGTH_ERROR = 'Skill 描述最多500字符（换行不计）';
const RUNTIME_STATUS_PASSED = 'PASSED';
const RUNTIME_STATUS_FAILED = 'FAILED';
const RUNTIME_STATUS_PARTIAL = 'PARTIAL';
const RUNTIME_STATUS_SKIPPED = 'SKIPPED';
const SKILL_STATUS_LABELS: Record<string, string> = {
  ACTIVE: '编辑中',
  EDITING: '编辑中',
  DEVELOPING: '开发中',
  DRAFT: '草稿',
  SEALED: '已封板',
  ONLINE: '已上线',
  PUBLISHED: '已发布',
  REGISTERED: '已注册',
  PUBLISHING: '发布中',
  SUCCEEDED: '成功',
  FAILED: '失败',
  ERROR: '异常',
};
const SKILL_STATUS_FILTER_EDITING = 'EDITING';
const SKILL_LIST_PAGE_SIZE = 9;
const SKILL_STATUS_FILTER_ONLINE = 'ONLINE';
const SKILL_STATUS_FILTER_OPTIONS = [
  { value: SKILL_STATUS_FILTER_EDITING, label: '编辑中' },
  { value: SKILL_STATUS_FILTER_ONLINE, label: '已上线' },
];
const DEFAULT_VALIDATION_TEST_INPUT =
  '请用当前 Skill 处理一个典型用户请求，并检查输出能否被平台 runtime 承接。';
const CAPABILITY_BIND_EXECUTION_ONLY: SkillFactoryCapabilityBindMode = 'EXECUTION_ONLY';
const CAPABILITY_BIND_EXECUTION_AND_RENDER: SkillFactoryCapabilityBindMode = 'EXECUTION_AND_RENDER';



interface A2uiCardAction {
  actionCode: string;
  label: string;
  sourceComponentId?: string;
  actionParams?: Record<string, unknown>;
}

interface A2uiSurfaceState {
  surfaceId: string;
  title: string;
  dataModel: Record<string, unknown>;
  actions: A2uiCardAction[];
  event: SkillFactoryCodingEvent;
}

interface AssistantMessageState {
  messageId: string;
  sessionId: string;
  runId?: string;
  timestamp: number;
  answerText: string;
  status: AssistantMessageStatus;
  businessCards: A2uiSurfaceState[];
  executionTrace: SkillFactoryCodingEvent[];
  validationReports: SkillFactoryCodingEvent[];
}

type ExecutionTraceStageStatus = 'running' | 'done' | 'error';

interface ExecutionTraceStage {
  key: string;
  label: string;
  title?: string;
  status: ExecutionTraceStageStatus;
  details: string[];
  rawDetail?: string;
  events: SkillFactoryCodingEvent[];
  timestamp?: number;
}

interface ExecutionTraceRenderBlock {
  key: string;
  type: 'progress' | 'patch';
  status?: ExecutionTraceStageStatus;
  event?: SkillFactoryCodingEvent;
  text?: string;
  stages?: ExecutionTraceStage[];
  timestamp?: number;
}



const defaultBusinessDomains: SkillFactoryDomainOption[] = [
  { value: '直播经营', label: '直播经营' },
  { value: '内容经营', label: '内容经营' },
  { value: '售后保障', label: '售后保障' },
];

const defaultCapabilityDomains: SkillFactoryDomainOption[] = [
  { value: '计划创建', label: '计划创建' },
  { value: '复盘诊断', label: '复盘诊断' },
  { value: '内容生成', label: '内容生成' },
  { value: '保障处理', label: '保障处理' },
];

const defaultQuickPrompts: SkillFactoryQuickPrompt[] = [
  {
    key: 'readiness',
    label: '是否达到准出标准',
    prompt:
      '请基于当前 workspace 文件、参考组件、绑定验证结果和发布前检查，判断当前 Skill 是否达到准出标准，并按“已满足 / 未满足 / 风险 / 下一步动作”输出。',
  },
  {
    key: 'todo',
    label: '待定事项清单',
    prompt:
      '请基于当前 Skill 草稿列出还待人工确认的信息，按业务逻辑、前端协议、参数来源、发布风险四类输出待定事项清单。',
  },
  {
    key: 'card-protocol',
    label: '生成 Tool 调用参数',
    prompt:
      '请根据已选参考组件的接入提示，给出 render_component 调用时机与 arguments 示例，只包含 dslType、componentName/agentUiDsl 和 params。',
  },
];

const defaultReferenceComponents: SkillFactoryReferenceComponent[] = [
  {
    code: 'LivePlanCreateCard',
    name: '直播计划创建结果卡',
    componentName: 'LivePlanCreateCard',
    renderProtocol: 'CARD_CONTAINER',
    scene: '直播计划',
    prompt:
      '引用组件中心「直播计划创建结果卡（LivePlanCreateCard）」作为前端承接组件。需要展示结果时调用 render_component，dslType=CARD_CONTAINER，componentName=LivePlanCreateCard，params 中提供 title、planTime、todoItems 和 action。',
  },
  {
    code: 'ChoicePicker',
    name: '直播复盘选择器',
    componentName: 'ChoicePicker',
    renderProtocol: 'A2UI',
    scene: '直播复盘',
    prompt:
      '引用 A2UI「直播复盘选择器（ChoicePicker）」作为交互组件。Skill 只输出 DigitalEmployeeComponentPayload，agentUiDsl=live_stream_selector，params 放业务参数，完整 A2UI envelope 由 adviser adapter 生成。',
  },
  {
    code: 'MarkdownConclusionCard',
    name: '通用结论卡',
    componentName: 'MarkdownConclusionCard',
    renderProtocol: 'CARD_CONTAINER',
    scene: '通用兜底',
    prompt:
      '引用通用结论卡 MarkdownConclusionCard，输出面向商家的 markdown 结论，并在 data 中提供 title、summary、suggestions 和可选跳转 action。',
  },
];

const defaultPageConfig: SkillFactoryPageConfig = {
  agentId: DEFAULT_SKILL_CODING_AGENT_ID,
  ownerId: DEFAULT_SKILL_CODING_OWNER_ID,
  scopeType: 'SKILL',
  bizConfigs: {
    [SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING]: {
      agentId: DEFAULT_SKILL_CODING_AGENT_ID,
      ownerId: DEFAULT_SKILL_CODING_OWNER_ID,
      scopeType: 'SKILL',
    },
  },
  specialists: defaultSpecialists,
  businessDomains: defaultBusinessDomains,
  capabilityDomains: defaultCapabilityDomains,
  quickPrompts: defaultQuickPrompts,
  referenceComponents: defaultReferenceComponents,
  referenceRenderAssets: [],
  links: {
    bEndDebugPageUrl: DEFAULT_B_END_DEBUG_PAGE_URL,
    tracePageUrl: BINDING_TRACE_PAGE_URL,
  },
};

const tabList: Array<{ key: WorkbenchTab; label: string }> = SKILL_FACTORY_TAB_ITEMS.map(
  (item) => ({ ...item }),
);

function getInitialTab(): WorkbenchTab {
  if (typeof window === 'undefined') return 'overview';
  const routeTab = new URLSearchParams(window.location.search).get('tab');
  const tab = (routeTab === 'chat' ? 'components' : routeTab) as WorkbenchTab | null;
  return tabList.some((item) => item.key === tab) ? tab || 'overview' : 'overview';
}

function formatTime(time?: number): string {
  if (!time) return '-';
  const date = new Date(time);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function capabilityActionCodeOf(item: CapabilityActionDraft): string {
  return item.draft?.basicInfo?.actionCode || '';
}

function capabilityNameOf(item: CapabilityActionDraft): string {
  return item.draft?.basicInfo?.nameCn || '未命名能力';
}

function capabilityStatusColor(item: CapabilityActionDraft): string {
  if (item.validationStatus === 'PASSED') return 'success';
  if (item.validationStatus === 'FAILED') return 'error';
  if (item.validationStatus === 'PARTIAL') return 'warning';
  return 'blue';
}

function formatJson(value: unknown): string {
  return jsonStringify(value, null, 2);
}

function iconForNode(node: SkillTreeNode): React.ReactNode {
  if (node.directory) return <FolderOpenOutlined />;
  if (node.fileType === 'PYTHON') return <CodeOutlined />;
  if (node.fileType === 'MARKDOWN') return <FileMarkdownOutlined />;
  return <FileTextOutlined />;
}

function decorateTreeNode(node: SkillTreeNode): SkillTreeNode {
  return {
    ...node,
    icon: iconForNode(node),
    children: node.children?.map(decorateTreeNode),
  } as SkillTreeNode;
}

function decorateTree(node?: SkillTreeNode): SkillTreeNode[] {
  if (!node) return [];
  const decoratedNode = decorateTreeNode(node);
  const filePath = String(node.filePath || node.key || '').replace(/^\/+|\/+$/g, '');
  const currentRoot =
    Boolean(node.directory) &&
    (filePath === 'current' ||
      filePath === 'preprod/current' ||
      (node.key === 'root' && String(node.title || '').trim() === 'current'));
  return currentRoot ? decoratedNode.children || [] : [decoratedNode];
}

function isProtectedWorkspaceTreeNode(node: SkillTreeNode): boolean {
  const filePath = String(node.filePath || node.key || '').replace(/^\/+|\/+$/g, '');
  return (
    node.key === 'root' ||
    (Boolean(node.directory) && (filePath === 'current' || filePath === 'preprod/current'))
  );
}

function renderCodeLines(content: string) {
  return (
    <div className="skill-factory-code-viewer">
      {content?.split('\n')?.map?.((line, index) => (
        <div className="skill-factory-code-line" key={`${index}-${line}`}>
          <span className="skill-factory-line-no">{index + 1}</span>
          <span className="skill-factory-line-content">{line || ' '}</span>
        </div>
      ))}
    </div>
  );
}

function parseSamplePayload(payload: unknown): Record<string, unknown> {
  if (!payload) return {};
  if (typeof payload === 'object' && !Array.isArray(payload)) {
    return payload as Record<string, unknown>;
  }
  if (typeof payload !== 'string') return {};
  return jsonParse(payload, {}) as Record<string, unknown>;
}

function referenceAssetKey(
  asset?: Partial<SkillFactoryReferenceAsset> & { componentCode?: string },
): string {
  return (
    asset?.code ||
    asset?.componentCode ||
    asset?.agentUiDsl ||
    asset?.dslCode ||
    asset?.componentName ||
    asset?.localMethod ||
    ''
  );
}

function referenceComponentToAsset(
  item: SkillFactoryReferenceComponent,
): SkillFactoryReferenceAsset {
  return {
    code: item.code || item.componentName,
    name: item.name,
    assetType: item.renderProtocol === 'A2UI' ? 'A2UI_ATOM' : 'CARD_CONTAINER',
    renderProtocol: item.renderProtocol || 'CARD_CONTAINER',
    componentName: item.componentName,
    scene: item.scene,
    lifecycleStatus: 'REGISTERED',
    enabled: true,
    integrationPrompt: item.prompt,
    officialDemoJson: '',
  };
}

function componentAssetToReferenceAsset(
  asset: SkillFactoryComponentAsset,
): SkillFactoryReferenceAsset {
  const isBusinessDsl = asset.assetType === 'BUSINESS_DSL';
  const code = isBusinessDsl ? asset.agentUiDsl || asset.componentName : asset.componentName;
  return {
    assetId: asset.id,
    code,
    name: asset.componentNameCn || asset.componentName,
    assetType: asset.assetType,
    renderProtocol: asset.dslType || asset.assetType,
    componentName: asset.componentName,
    dslCode: isBusinessDsl ? asset.agentUiDsl : undefined,
    dslType: asset.dslType,
    agentUiDsl: asset.agentUiDsl,
    scene: asset.scene,
    owner: asset.owner,
    enabled: asset.enabled,
    published: asset.published,
    publishedVersion: asset.publishedVersion,
    releaseEnvironmentFacts: asset.releaseEnvironmentFacts,
    protocolVersion: String(asset.protocolVersion),
    interactionMode: asset.interactionMode,
    componentVersion: asset.publishedVersion ? String(asset.publishedVersion) : undefined,
    integrationPrompt: asset.integrationPrompt,
    officialDemoJson: asset.officialDemoJson,
    schemaJson: asset.paramsSchemaJson,
    paramsSchemaJson: asset.paramsSchemaJson,
    source: 'component-center',
  };
}

function uniqueReferenceAssets(items: SkillFactoryReferenceAsset[]): SkillFactoryReferenceAsset[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = referenceAssetKey(item);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function referenceCodesOf(assets?: SkillFactoryReferenceAsset[]): string {
  return (assets || []).map(referenceAssetKey).filter(Boolean).join(',');
}

function referenceAssetPrompt(asset: SkillFactoryReferenceAsset): string {
  return asset.integrationPrompt || asset.schemaJson || asset.officialDemoJson || '';
}

function referenceAssetDemoPayload(asset: SkillFactoryReferenceAsset): unknown {
  if (!asset.officialDemoJson) return {};
  return jsonParse(asset.officialDemoJson, asset.officialDemoJson);
}

function renderReferenceAssetPreview(asset: SkillFactoryReferenceAsset): React.ReactNode {
  const payload = parseSamplePayload(referenceAssetDemoPayload(asset));
  if (asset.assetType === 'BUSINESS_DSL') {
    return (
      <div className="skill-factory-reference-preview dsl">
        <div>
          <Text type="secondary">agentUiDsl</Text>
          <strong>{String(asset.dslCode || payload.agentUiDsl || referenceAssetKey(asset))}</strong>
        </div>
        <div>
          <Text type="secondary">params</Text>
          <Text code>
            {Object.keys(parseSamplePayload(payload.params)).length ? 'schema/demo 已配置' : '-'}
          </Text>
        </div>
      </div>
    );
  }
  if (asset.assetType === 'CARD_CONTAINER' || asset.renderProtocol === 'CARD_CONTAINER') {
    return (
      <div className="skill-factory-reference-preview card">
        <Text type="secondary">CARD_CONTAINER</Text>
        <strong>
          {String(asset.componentName || payload.componentName || referenceAssetKey(asset))}
        </strong>
        <p>{String(payload.title || payload.planName || asset.scene || '组件承接预览')}</p>
      </div>
    );
  }
  if (asset.assetType === 'A2UI_ATOM') {
    return (
      <div className="skill-factory-reference-preview atom">
        <Text type="secondary">A2UI_ATOM</Text>
        <strong>{asset.componentName || referenceAssetKey(asset)}</strong>
        <div className="skill-factory-reference-preview-control">选择项 A / 选择项 B</div>
      </div>
    );
  }
  if (asset.assetType === 'localMethod') {
    return (
      <div className="skill-factory-reference-preview local">
        <Text type="secondary">localMethod</Text>
        <strong>{asset.localMethod || referenceAssetKey(asset)}</strong>
        <p>由前端既有 localMethod 链路承接。</p>
      </div>
    );
  }
  return (
    <div className="skill-factory-reference-preview">{renderCodeLines(formatJson(payload))}</div>
  );
}

function assetTypeText(assetType?: string): string {
  if (assetType === 'BUSINESS_DSL') return 'BUSINESS_DSL';
  if (assetType === 'CARD_COMPONENT' || assetType === 'CARD_CONTAINER') return 'CARD_CONTAINER';
  if (assetType === 'localMethod') return 'localMethod';
  if (assetType === 'A2UI_ATOM') return 'A2UI_ATOM';
  return assetType || '-';
}

function referenceAssetSearchText(asset: SkillFactoryReferenceAsset): string {
  return [
    asset.name,
    referenceAssetKey(asset),
    asset.componentName,
    asset.dslCode,
    asset.localMethod,
    asset.renderProtocol,
    asset.assetType,
  ]
    ?.filter(Boolean)
    ?.join?.(' ')
    ?.toLowerCase?.();
}

function runtimeStatusColor(status?: string): string {
  if (status === RUNTIME_STATUS_PASSED) return 'success';
  if (status === RUNTIME_STATUS_FAILED) return 'error';
  if (status === RUNTIME_STATUS_PARTIAL) return 'warning';
  if (status === RUNTIME_STATUS_SKIPPED) return 'default';
  return 'blue';
}

function eventText(event: SkillFactoryCodingEvent): string {
  const content = event.content || {};
  if (event.eventType === 'PATCH_APPLIED' || event.eventCode === 'PATCH_APPLIED') {
    const changedFiles = content.changedFiles as unknown[] | undefined;
    const count = changedFiles?.length || 0;
    return content.autoApplied
      ? `patch 已自动应用，变更文件 ${count} 个`
      : `patch 已应用，变更文件 ${count} 个`;
  }
  if (event.eventType === 'PATCH_DISCARDED' || event.eventCode === 'PATCH_DISCARDED') {
    return 'patch 已丢弃';
  }
  return String(
    content.text || content.content || content.errorMsg || event.errorMsg || event.title || '',
  );
}

function isTerminalFailureEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === LEGACY_EVENT_FAILED || event.eventType === STREAM_EVENT_RUN_FAILED;
}

function isCancelledEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === STREAM_EVENT_RUN_CANCELLED;
}

function isDiagnosticErrorEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === DIAGNOSTIC_EVENT_ERROR ||
    (event.eventType !== LEGACY_EVENT_FAILED &&
      event.eventCode === LEGACY_EVENT_FAILED &&
      event.success === false)
  );
}

function isOperationFailureEvent(event: SkillFactoryCodingEvent): boolean {
  return isTerminalFailureEvent(event) || isCancelledEvent(event) || isDiagnosticErrorEvent(event);
}

function textOf(value: unknown): string {
  if (value === undefined || value === null) return '';
  return String(value);
}

function modelBlockType(event: SkillFactoryCodingEvent): string {
  const nestedBlock = recordOf(event.content?.modelContentBlock);
  return textOf(event.modelContentBlock?.type || nestedBlock?.type);
}

function isModelContentType(event: SkillFactoryCodingEvent, blockType: string): boolean {
  return event.eventType === STREAM_MODEL_CONTENT_EVENT_TYPE && modelBlockType(event) === blockType;
}

function isThinkingEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === STREAM_THINKING_EVENT_TYPE ||
    isModelContentType(event, MODEL_CONTENT_TYPE_THINKING)
  );
}

function isToolCallStartedEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === 'TOOL_CALL' || event.eventType === STREAM_EVENT_TOOL_CALL_STARTED;
}

function isToolCallFinishedEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === 'TOOL_RESULT' || event.eventType === STREAM_EVENT_TOOL_CALL_FINISHED;
}

function isBusinessInteractionEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === AUTHORING_EVENT_A2UI_MESSAGE ||
    event.eventType === AUTHORING_EVENT_BUSINESS_INTERACTION
  );
}

function isObservationEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === AUTHORING_EVENT_OBSERVATION ||
    event.eventType === AUTHORING_EVENT_OBSERVATION_CREATED
  );
}

function isCompletedEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === LEGACY_EVENT_COMPLETED || event.eventType === STREAM_EVENT_RUN_COMPLETED
  );
}

function isTextDeltaEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    STREAM_TEXT_EVENT_TYPES.has(event.eventType) ||
    isModelContentType(event, MODEL_CONTENT_TYPE_TEXT)
  );
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value;
  const formatted = formatJson(value);
  return formatted || textOf(value);
}

function debugEventTitle(event: SkillFactoryCodingEvent): string {
  const content = event.content || {};
  if (isThinkingEvent(event)) {
    return '思考过程';
  }
  if (isToolCallStartedEvent(event)) {
    return `调用工具 ${textOf(content.toolName) || '-'}`;
  }
  if (isToolCallFinishedEvent(event)) {
    return `工具结果 ${textOf(content.toolName) || '-'}`;
  }
  if (isObservationEvent(event)) {
    return '业务动作 Observation';
  }
  if (event.eventType === 'USAGE') {
    return 'Token 用量';
  }
  if (isCompletedEvent(event)) {
    return '本轮完成';
  }
  if (isTerminalFailureEvent(event)) {
    return '执行失败';
  }
  if (isCancelledEvent(event)) {
    return '运行已停止';
  }
  if (isDiagnosticErrorEvent(event)) {
    return '执行异常';
  }
  return event.eventType === 'STDERR' ? 'stderr' : 'stdout';
}

function debugEventBody(event: SkillFactoryCodingEvent): string {
  const content = event.content || {};
  if (isThinkingEvent(event)) {
    return textOf(content.text || content.content || event.title);
  }
  if (isToolCallStartedEvent(event)) {
    return displayValue(content.toolArgs || content);
  }
  if (isToolCallFinishedEvent(event)) {
    return displayValue(content.result || content);
  }
  if (isObservationEvent(event)) {
    return textOf(event.observation?.summary || content.summary || content);
  }
  if (event.eventType === 'USAGE') {
    return displayValue(content);
  }
  if (isCompletedEvent(event)) {
    return '流式输出已结束';
  }
  return textOf(content.text || content.content || event.errorMsg || event.title);
}

function collapseWhitespace(value: string): string {
  return value?.replace(/\s+/g, ' ')?.trim?.();
}

function trimTraceText(value: string, maxLength = TRACE_DETAIL_MAX_LENGTH): string {
  const text = collapseWhitespace(value);
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function recordFromValue(value: unknown): Record<string, unknown> | null {
  if (!value) return null;
  if (typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  if (typeof value !== 'string') return null;
  const parsed = jsonParse(value, null);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
  return parsed as Record<string, unknown>;
}

function traceToolName(event: SkillFactoryCodingEvent): string {
  const content = event.content || {};
  return (
    textOf(
      event.toolName ||
        event.payload?.toolName ||
        content.toolName ||
        content.toolCallName ||
        content.name,
    ) || '工具'
  );
}

function traceToolCallId(event: SkillFactoryCodingEvent): string {
  const content = event.content || {};
  return textOf(event.toolCallId || event.payload?.toolCallId || content.toolCallId);
}

function traceToolArgsSummary(value: unknown): string {
  const record = recordFromValue(value);
  if (record) {
    const importantKeys = [
      'skillCode',
      'path',
      'filePath',
      'pattern',
      'query',
      'command',
      'maxDepth',
    ];
    const parts = importantKeys
      ?.filter((key) => record[key] !== undefined && record[key] !== null && record[key] !== '')
      ?.map?.((key) => `${key}=${trimTraceText(displayValue(record[key]), 72)}`);
    if (parts.length) return parts.join(', ');
  }
  return trimTraceText(displayValue(value));
}

function traceToolStageLabel(toolName: string): string {
  if (toolName === 'use_skill') {
    return '加载 Skill';
  }
  if (['diff', 'propose_patch', 'workspace_diff'].includes(toolName)) {
    return '处理文件变更';
  }
  if (toolName === 'python') {
    return '执行脚本';
  }
  return '调用工具';
}

function traceToolTitle(toolName: string): string {
  return toolName === 'use_skill' ? '加载 Skill' : `调用工具 ${toolName}`;
}

function traceToolFinishedDetail(event: SkillFactoryCodingEvent, toolName: string): string {
  if (toolName !== 'use_skill') {
    return trimTraceText(debugEventBody(event), TRACE_RAW_DETAIL_MAX_LENGTH);
  }
  const content = event.content || {};
  const result = recordFromValue(content.result || content.output || content);
  if (!result) return 'Skill 加载完成';
  const skillCode = textOf(result.skillCode) || 'Skill';
  const version = textOf(result.version);
  const fileCount = textOf(result.fileCount);
  return `已加载 ${skillCode}${version ? ` 正式版 ${version}` : ''}${
    fileCount ? `，共 ${fileCount} 个文件` : ''
  }`;
}

function traceStageTitle(stage: ExecutionTraceStage): string {
  if (stage.title) return stage.title;
  if (stage.status === 'error') return `${stage.label}失败`;
  if (stage.status === 'done') return `已${stage.label}`;
  return `正在${stage.label}`;
}

function traceStageStatusText(stage: ExecutionTraceStage): string {
  if (stage.status === 'error') return '异常';
  if (stage.status === 'done') return '完成';
  return '进行中';
}

function traceEventDetail(event: SkillFactoryCodingEvent): {
  key: string;
  label: string;
  title?: string;
  status: ExecutionTraceStageStatus;
  detail: string;
} {
  const content = event.content || {};
  if (event.eventType === AUTHORING_EVENT_AG_UI) {
    const status = textOf(content.status);
    const stageStatus =
      status === 'error' || event.success === false
        ? 'error'
        : status === 'done'
        ? 'done'
        : 'running';
    const title = textOf(event.title || content.title || content.summary || '执行过程');
    return {
      key: textOf(content.stageId) || textOf(content.toolCallId) || title || AUTHORING_EVENT_AG_UI,
      label: title,
      title,
      status: stageStatus,
      detail: trimTraceText(
        textOf(content.summary) ||
          textOf(content.toolName) ||
          textOf(content.type) ||
          debugEventBody(event),
      ),
    };
  }
  if (isToolCallStartedEvent(event)) {
    const toolName = traceToolName(event);
    const toolCallId = traceToolCallId(event);
    const argsSummary = traceToolArgsSummary(content.toolArgs || content);
    const title = traceToolTitle(toolName);
    return {
      key: toolCallId ? `tool:${toolCallId}` : `tool-${traceToolStageLabel(toolName)}`,
      label: title,
      title,
      status: 'running',
      detail: `${title}${argsSummary ? `：${argsSummary}` : ''}`,
    };
  }
  if (isToolCallFinishedEvent(event)) {
    const toolName = traceToolName(event);
    const toolCallId = traceToolCallId(event);
    const hasError =
      event.success === false ||
      content.toolSuccess === false ||
      Boolean(content.errorMsg || event.errorMsg);
    const title = traceToolTitle(toolName);
    return {
      key: toolCallId ? `tool:${toolCallId}` : `tool-${traceToolStageLabel(toolName)}`,
      label: title,
      title,
      status: hasError ? 'error' : 'done',
      detail: hasError
        ? `${title}失败：${trimTraceText(debugEventBody(event), TRACE_RAW_DETAIL_MAX_LENGTH)}`
        : traceToolFinishedDetail(event, toolName),
    };
  }
  if (event.eventType === 'STDOUT' || event.eventType === 'STDERR') {
    return {
      key: 'script-output',
      label: '查看输出',
      status: event.eventType === 'STDERR' ? 'error' : 'done',
      detail: `${event.eventType?.toLowerCase?.()}：${trimTraceText(debugEventBody(event))}`,
    };
  }
  if (isObservationEvent(event)) {
    return {
      key: 'authoring-observation',
      label: '记录业务确认',
      status: 'done',
      detail: trimTraceText(debugEventBody(event)),
    };
  }
  if (event.eventType === 'USAGE') {
    const tokenCount = textOf(
      content.tokenCount || content.enterTokenCount || content.outputTokenCount,
    );
    return {
      key: 'usage',
      label: '统计消耗',
      status: 'done',
      detail: tokenCount ? `token 用量：${tokenCount}` : trimTraceText(debugEventBody(event)),
    };
  }
  if (isCompletedEvent(event)) {
    return {
      key: 'completed',
      label: '回答完成',
      status: 'done',
      detail: '本轮流式输出已结束',
    };
  }
  if (isCancelledEvent(event)) {
    return {
      key: 'cancelled',
      label: '停止运行',
      title: '运行已停止',
      status: 'done',
      detail: trimTraceText(debugEventBody(event) || '本轮运行已停止'),
    };
  }
  if (isTerminalFailureEvent(event)) {
    return {
      key: 'failed',
      label: '执行过程',
      status: 'error',
      detail: trimTraceText(debugEventBody(event) || '执行失败'),
    };
  }
  if (isDiagnosticErrorEvent(event)) {
    const toolCallId = traceToolCallId(event);
    const toolName = traceToolName(event);
    const title = traceToolTitle(toolName);
    return {
      key: toolCallId ? `tool:${toolCallId}` : 'diagnostic-error',
      label: toolCallId ? title : '执行过程',
      title: toolCallId ? title : undefined,
      status: 'error',
      detail: trimTraceText(debugEventBody(event) || '执行过程出现异常'),
    };
  }
  return {
    key: `event-${event.eventType}`,
    label: '处理执行事件',
    status: 'done',
    detail: trimTraceText(debugEventBody(event)),
  };
}

function stringListOf(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value?.map((item) => textOf(item))?.filter?.(Boolean);
}







function recordOf(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function eventMessageId(event: SkillFactoryCodingEvent): string {
  return (
    event.messageId || event.runId || event.sessionId || `msg_${event.timestamp || Date.now()}`
  );
}

function isValidationReportEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === STREAM_EVENT_VALIDATION_REPORT_CREATED ||
    event.eventCode === STREAM_EVENT_VALIDATION_REPORT_CREATED ||
    event.payloadType === PAYLOAD_TYPE_VALIDATION_REPORT
  );
}

function recordArrayOf(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value?.map(recordOf)?.filter?.(Boolean) as Array<Record<string, unknown>>;
}

function validationReportOf(event: SkillFactoryCodingEvent): Record<string, unknown> {
  const nestedPayloadContent = recordOf(event.payload?.content);
  return (
    recordOf(event.content?.report) ||
    recordOf(nestedPayloadContent?.report) ||
    recordOf(event.content) ||
    {}
  );
}

function isPatchChangedFileDetailList(value: unknown): value is Array<Record<string, unknown>> {
  return Array.isArray(value) && value.some((item) => Boolean(item) && typeof item === 'object');
}

function patchChangedFiles(event: SkillFactoryCodingEvent): Array<Record<string, unknown>> {
  return ((event.content?.changedFiles || []) as unknown[])?.map((file) => {
    if (file && typeof file === 'object') {
      return file as Record<string, unknown>;
    }
    return {
      path: String(file || ''),
      changeType: 'MODIFY',
      diffPreview: '',
    };
  });
}

function patchConflictFiles(event: SkillFactoryCodingEvent): string[] {
  const conflictFiles = event.content?.conflictFiles;
  if (!Array.isArray(conflictFiles)) return [];
  return conflictFiles?.map((file) => String(file || ''))?.filter?.(Boolean);
}

function boundedPatchDisplayName(value: string): string {
  const normalized = value?.replace(/\s+/g, ' ')?.trim?.();
  const characters = Array.from(normalized);
  if (characters.length <= PATCH_DISPLAY_NAME_MAX_LENGTH) return normalized;
  return `${characters?.slice(0, PATCH_DISPLAY_NAME_MAX_LENGTH)?.join?.('')}…`;
}

function countSkillDescriptionCharacters(value?: string): number {
  return Array.from((value || '').replace(/[\r\n]/g, '')).length;
}

function patchDisplayName(event: SkillFactoryCodingEvent): string {
  const summary = boundedPatchDisplayName(textOf(event.content?.summary));
  if (summary) return summary;
  const changedFiles = patchChangedFiles(event);
  if (changedFiles.length) {
    const firstFile = changedFiles?.[0];
    const path = textOf(firstFile.path) || '文件';
    const changeType = textOf(firstFile.changeType)?.toUpperCase?.();
    const actionText = changeType === 'ADD' ? '新增' : changeType === 'DELETE' ? '删除' : '修改';
    const fileText = changedFiles.length > 1 ? `${path} 等 ${changedFiles.length} 个文件` : path;
    return boundedPatchDisplayName(`${actionText} ${fileText}`);
  }
  const title = boundedPatchDisplayName(textOf(event.title));
  return title || '文件变更';
}

function earliestPatchTimestamp(previous?: number, next?: number): number | undefined {
  const timestamps = [previous, next].filter(
    (timestamp): timestamp is number => typeof timestamp === 'number' && timestamp > 0,
  );
  return timestamps.length ? Math.min(...timestamps) : undefined;
}

function patchEventKey(event: SkillFactoryCodingEvent, fallback: string | number): string {
  return event.patchId || `${event.sessionId || 'patch'}-${fallback}`;
}

function mergePatchEvent(
  previous: SkillFactoryCodingEvent,
  next: SkillFactoryCodingEvent,
): SkillFactoryCodingEvent {
  const previousContent = previous.content || {};
  const nextContent = next.content || {};
  const mergedContent: Record<string, unknown> = {
    ...previousContent,
    ...nextContent,
  };
  if (
    isPatchChangedFileDetailList(previousContent.changedFiles) &&
    !isPatchChangedFileDetailList(nextContent.changedFiles)
  ) {
    mergedContent.changedFiles = previousContent.changedFiles;
    mergedContent.appliedFiles = nextContent.changedFiles;
  }
  return {
    ...previous,
    ...next,
    timestamp: earliestPatchTimestamp(previous.timestamp, next.timestamp),
    title: next.title || previous.title,
    content: mergedContent,

    observation: next.observation || previous.observation,
  };
}



function patchReviewStatusText(status?: ChangeReviewStatus): string {
  if (status === 'APPLIED') return '已应用';
  if (status === 'DISCARDED') return '已丢弃';
  if (status === 'CONFLICTED') return '存在冲突';
  return status === 'PENDING' ? '待审阅' : '不可审阅';
}

function patchReviewStatusColor(status: ChangeReviewStatus): string {
  if (status === 'APPLIED') return 'success';
  if (status === 'CONFLICTED') return 'error';
  if (status === 'PENDING') return 'warning';
  return 'default';
}



function isExecutionTraceEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    isThinkingEvent(event) ||
    STREAM_DEBUG_EVENT_TYPES.has(event.eventType) ||
    isToolCallStartedEvent(event) ||
    isToolCallFinishedEvent(event) ||
    isPatchDomainEvent(event) ||
    event.eventType === AUTHORING_EVENT_AG_UI ||
    event.eventType === STREAM_EVENT_VALIDATION_TASK_STARTED ||
    isObservationEvent(event) ||
    isCompletedEvent(event) ||
    isTerminalFailureEvent(event) ||
    isCancelledEvent(event) ||
    isDiagnosticErrorEvent(event)
  );
}

function isExecutionTraceFooterEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === 'USAGE';
}

function a2uiPayloadOf(event: SkillFactoryCodingEvent): Record<string, unknown> {
  const content = event.content || {};
  return recordOf(content.a2ui) || content;
}

function surfaceIdOf(event: SkillFactoryCodingEvent, payload: Record<string, unknown>): string {
  const createSurface = recordOf(payload.createSurface);
  const updateDataModel = recordOf(payload.updateDataModel);
  return (
    event.surfaceId ||
    textOf(createSurface?.surfaceId) ||
    textOf(updateDataModel?.surfaceId) ||
    `surface_${eventMessageId(event)}`
  );
}

function a2uiActionsOf(payload: Record<string, unknown>): A2uiCardAction[] {
  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  return actions
    ?.map((item) => {
      const action = recordOf(item);
      if (!action) return null;
      const actionCode = textOf(action.actionCode);
      if (!actionCode) return null;
      return {
        actionCode,
        label: textOf(action.label || actionCode),
        sourceComponentId: textOf(action.sourceComponentId) || undefined,
        actionParams: recordOf(action.actionParams) || {},
      };
    })
    ?.filter?.(Boolean) as A2uiCardAction[];
}

function buildA2uiSurface(event: SkillFactoryCodingEvent): A2uiSurfaceState {
  const payload = a2uiPayloadOf(event);
  const createSurface = recordOf(payload.createSurface);
  const updateDataModel = recordOf(payload.updateDataModel);
  const surfaceProperties = recordOf(createSurface?.surfaceProperties);
  const dataModel = recordOf(updateDataModel?.value) || recordOf(payload.dataModel) || {};
  const surfaceId = surfaceIdOf(event, payload);
  const actions = a2uiActionsOf(payload);
  return {
    surfaceId,
    title: textOf(surfaceProperties?.title || event.title || '业务确认'),
    dataModel,
    actions,
    event,
  };
}

function isDeprecatedSkillConfirmCard(card: A2uiSurfaceState): boolean {
  return (
    card.title?.includes?.('确认 Skill 基础信息') ||
    card.surfaceId?.startsWith?.('requirement_confirm_')
  );
}

function buildAssistantMessages(events: SkillFactoryCodingEvent[]): AssistantMessageState[] {
  const messageMap = new Map<string, AssistantMessageState>();
  const ensureMessage = (event: SkillFactoryCodingEvent): AssistantMessageState => {
    const messageId = eventMessageId(event);
    const existed = messageMap.get(messageId);
    if (existed) return existed;
    const nextMessage: AssistantMessageState = {
      messageId,
      sessionId: event.sessionId,
      runId: event.runId,
      timestamp: event.timestamp || Date.now(),
      answerText: '',
      status: 'streaming',
      businessCards: [],
      executionTrace: [],
      validationReports: [],
    };
    messageMap.set(messageId, nextMessage);
    return nextMessage;
  };

  events.forEach((event) => {
    const messageState = ensureMessage(event);
    messageState.timestamp = Math.min(
      messageState.timestamp,
      event.timestamp || messageState.timestamp,
    );
    if (isTextDeltaEvent(event)) {
      messageState.answerText += eventText(event);
    }
    if (isBusinessInteractionEvent(event)) {
      const card = buildA2uiSurface(event);
      if (isDeprecatedSkillConfirmCard(card)) {
        return;
      }
      const cardIndex = messageState.businessCards?.findIndex?.(
        (item) => item.surfaceId === card.surfaceId,
      );
      if (cardIndex >= 0) {
        messageState.businessCards[cardIndex] = card;
      } else {
        messageState.businessCards?.push?.(card);
      }
    }
    if (isValidationReportEvent(event)) {
      messageState.validationReports?.push?.(event);
    }
    if (
      isExecutionTraceEvent(event) &&
      !isValidationReportEvent(event) &&
      !isExecutionTraceFooterEvent(event)
    ) {
      messageState.executionTrace?.push?.(event);
    }
    if (isCancelledEvent(event)) {
      messageState.status = 'cancelled';
    } else if (isTerminalFailureEvent(event)) {
      messageState.status = 'error';
    } else if (isCompletedEvent(event)) {
      messageState.status = 'done';
    }
  });
  return Array.from(messageMap.values()).sort((a, b) => a.timestamp - b.timestamp);
}

function buildExecutionTraceBlocks(
  events: SkillFactoryCodingEvent[],
  pendingFinalAnswer = false,
  pendingTimestamp?: number,
): ExecutionTraceRenderBlock[] {
  const blocks: ExecutionTraceRenderBlock[] = [];
  let progressBlock: ExecutionTraceRenderBlock | null = null;
  const stageMap = new Map<string, ExecutionTraceStage>();
  const patchBlockMap = new Map<string, ExecutionTraceRenderBlock>();
  const customResultIds = domainResultToolCallIds(events);
  let thinkingStageIndex = 0;
  let activeThinkingStageKey = '';
  let runSettled = false;

  const ensureProgressBlock = (timestamp?: number): ExecutionTraceRenderBlock => {
    if (progressBlock) return progressBlock;
    progressBlock = {
      key: 'progress',
      type: 'progress',
      status: 'running',
      text: '',
      stages: [],
      timestamp,
    };
    blocks.push(progressBlock);
    return progressBlock;
  };

  const closeRunningStagesExcept = (activeKey: string) => {
    stageMap.forEach((stage, key) => {
      if (key !== activeKey && stage.status === 'running') {
        stage.status = 'done';
      }
    });
  };

  const ensureStage = (
    key: string,
    label: string,
    status: ExecutionTraceStageStatus,
    timestamp?: number,
    title?: string,
  ): ExecutionTraceStage => {
    if (status === 'running') {
      closeRunningStagesExcept(key);
    }
    const existed = stageMap.get(key);
    if (existed) {
      existed.status = status === 'error' ? 'error' : status;
      existed.label = label || existed.label;
      existed.title = title || existed.title;
      existed.timestamp = timestamp || existed.timestamp;
      return existed;
    }
    const stage: ExecutionTraceStage = {
      key,
      label,
      title,
      status,
      details: [],
      events: [],
      timestamp,
    };
    stageMap.set(key, stage);
    return stage;
  };

  const closeActiveThinkingStage = () => {
    if (!activeThinkingStageKey) return;
    const stage = stageMap.get(activeThinkingStageKey);
    if (stage?.status === 'running') {
      stage.status = 'done';
    }
    activeThinkingStageKey = '';
  };

  const closePatchActionStage = (event: SkillFactoryCodingEvent) => {
    const settledCode = textOf(event.eventCode || event.eventType);
    const toolName = settledCode === 'PATCH_DISCARDED' ? 'discard_patch' : 'confirm_patch';
    stageMap.forEach((stage) => {
      if (stage.status !== 'running') {
        return;
      }
      const matched = stage.events?.some?.((stageEvent) => traceToolName(stageEvent) === toolName);
      if (!matched) {
        return;
      }
      stage.status = 'done';
      stage.details = [
        ...stage.details,
        settledCode === 'PATCH_DISCARDED' ? 'patch 已丢弃。' : 'patch 已应用。',
      ];
      stage.events?.push?.(event);
    });
  };

  events.forEach((event, index) => {
    if (isThinkingEvent(event)) {
      const block = ensureProgressBlock(event.timestamp);
      const thinkingDelta = debugEventBody(event);
      block.text = `${block.text || ''}${thinkingDelta}`;
      if (thinkingDelta) {
        if (!activeThinkingStageKey) {
          activeThinkingStageKey = `thinking-${thinkingStageIndex++}`;
        }
        const stage = ensureStage(
          activeThinkingStageKey,
          '思考您的请求',
          'running',
          event.timestamp,
        );
        stage.rawDetail = `${stage.rawDetail || ''}${thinkingDelta}`;
        const detailText = trimTraceText(stage.rawDetail, TRACE_RAW_DETAIL_MAX_LENGTH);
        stage.details = detailText ? [detailText] : [];
        stage.events?.push?.(event);
      }
      block.timestamp = event.timestamp || block.timestamp;
      return;
    }
    closeActiveThinkingStage();
    if (isCompletedEvent(event)) {
      runSettled = true;
      return;
    }
    if (isCancelledEvent(event)) {
      runSettled = true;
    }
    if (isPatchReviewEvent(event)) {
      if (isPatchSettledEvent(event)) {
        closePatchActionStage(event);
      }
      const key = `patch-${patchEventKey(event, event.timestamp || index)}`;
      const existingBlock = patchBlockMap.get(key);
      if (existingBlock) {
        existingBlock.event = existingBlock.event
          ? mergePatchEvent(existingBlock.event, event)
          : event;
        existingBlock.timestamp = event.timestamp || existingBlock.timestamp;
      } else {
        const block: ExecutionTraceRenderBlock = {
          key,
          type: 'patch',
          event,
          timestamp: event.timestamp,
        };
        patchBlockMap.set(key, block);
        blocks.push(block);
      }
      return;
    }
    const detail = traceEventDetail(event);
    const block = ensureProgressBlock(event.timestamp);
    const stage = ensureStage(
      detail.key,
      detail.label,
      detail.status,
      event.timestamp,
      detail.title,
    );
    if (detail.detail && shouldDisplayGenericToolResult(event, customResultIds)) {
      stage.details?.push?.(detail.detail);
    }
    stage.events?.push?.(event);
    block.timestamp = event.timestamp || block.timestamp;
  });
  if (pendingFinalAnswer && !progressBlock) {
    ensureProgressBlock(pendingTimestamp);
  }
  const finalProgressBlock = progressBlock as ExecutionTraceRenderBlock | null;
  if (finalProgressBlock) {
    if ((finalProgressBlock.text || '') && stageMap.size === 0) {
      ensureStage('analysis', '分析问题', 'running', finalProgressBlock.timestamp);
    }
    const stages = Array.from(stageMap.values());
    finalProgressBlock.stages = stages;
    let hasTerminalError = false;
    stages.forEach((stage) => {
      if (hasTerminalError || stage.status !== 'error') {
        return;
      }
      if (stage.key === 'run') {
        hasTerminalError = true;
        return;
      }
      const stageEvents = stage.events || [];
      for (let index = 0; index < stageEvents.length; index += 1) {
        if (isTerminalFailureEvent(stageEvents[index])) {
          hasTerminalError = true;
          break;
        }
      }
    });
    if (hasTerminalError) {
      finalProgressBlock.status = 'error';
    } else if (runSettled) {
      stages.forEach((stage) => {
        if (stage.status === 'running') {
          stage.status = 'done';
        }
      });
      finalProgressBlock.status = 'done';
    } else {
      if (pendingFinalAnswer && !stages.some((stage) => stage.status === 'running')) {
        ensureStage(
          'waiting-final-answer',
          '思考您的请求',
          'running',
          pendingTimestamp || finalProgressBlock.timestamp,
        );
        finalProgressBlock.stages = Array.from(stageMap.values());
      }
      finalProgressBlock.status = 'running';
    }
  }
  return blocks;
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const value = error as { name?: string; message?: string };
  return value.name === 'AbortError' || Boolean(value.message?.includes?.('aborted'));
}

function isPositiveIntegerText(value: string): boolean {
  const trimmed = value.trim();
  const numericValue = Number(trimmed);
  return Boolean(trimmed) && Number.isInteger(numericValue) && numericValue > 0;
}

function mergePageConfig(config?: SkillFactoryPageConfig | null): SkillFactoryPageConfig {
  const referenceComponents = config?.referenceComponents?.length
    ? config.referenceComponents
    : defaultReferenceComponents;
  const configSpecialists = normalizeSpecialists(config?.specialists);
  const defaultBizConfigs = defaultPageConfig.bizConfigs || {};
  const incomingBizConfigs = config?.bizConfigs || {};
  const skillCodingBizConfig = {
    ...(defaultBizConfigs[SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING] || {}),
    ...(incomingBizConfigs[SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING] || {}),
  };
  const bizConfigs = {
    ...defaultBizConfigs,
    ...incomingBizConfigs,
    [SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING]: skillCodingBizConfig,
  };
  return {
    agentId: config?.agentId || skillCodingBizConfig.agentId || defaultPageConfig.agentId,
    ownerId: config?.ownerId || skillCodingBizConfig.ownerId || defaultPageConfig.ownerId,
    scopeType: config?.scopeType || skillCodingBizConfig.scopeType || defaultPageConfig.scopeType,
    bizConfigs,
    specialists: configSpecialists.length ? configSpecialists : defaultSpecialists,
    businessDomains: config?.businessDomains?.length
      ? config.businessDomains
      : defaultBusinessDomains,
    capabilityDomains: config?.capabilityDomains?.length
      ? config.capabilityDomains
      : defaultCapabilityDomains,
    quickPrompts: config?.quickPrompts?.length ? config.quickPrompts : defaultQuickPrompts,
    referenceComponents,
    referenceRenderAssets: uniqueReferenceAssets(config?.referenceRenderAssets || []),
    links: {
      ...defaultPageConfig.links,
      ...(config?.links || {}),
    },
  };
}

function buildExternalUrl(
  baseUrl?: string,
  params: Record<string, string | undefined> = {},
): string {
  const rawUrl = baseUrl || '';
  if (!rawUrl) return '';
  try {
    const url = new URL(rawUrl, typeof window === 'undefined' ? undefined : window.location.origin);
    Object.entries(params).forEach(([key, value]) => {
      if (value) url.searchParams?.set?.(key, value);
    });
    return url.toString();
  } catch (error) {
    return rawUrl;
  }
}









function splitCsv(value?: string): string[] {
  return (value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function getCurrentUserName(): string {
  if (typeof document === 'undefined') return '';
  return document.querySelector<HTMLMetaElement>('meta[name="a2flow-user-id"]')?.content || '';
}

function buildCodingTurnId(prefix = 'coding'): string {
  return `${prefix}_${Date.now()}`;
}

function normalizeVersionText(value?: string): string {
  const text = (value || '').trim();
  return text.replace(/^v/i, '') || DEFAULT_VERSION_LABEL;
}

function skillSpecialistIds(
  skill: SkillDraft | null | undefined,
  specialists: SkillFactorySpecialistOption[],
): string[] {
  const ids = splitCsv(skill?.specialistId);
  if (ids.length) return ids;
  const names = splitCsv(skill?.specialistName);
  return specialists
    ?.filter((item) => names.includes(specialistOptionName(item)))
    ?.map?.((item) => specialistOptionId(item));
}

function domainOptionValue(option?: SkillFactoryDomainOption | null): string {
  return String(option?.value || option?.code || option?.id || option?.name || option?.label || '');
}

function domainOptionLabel(option?: SkillFactoryDomainOption | null): string {
  return String(option?.label || option?.name || option?.value || option?.code || option?.id || '');
}

function domainSelectOptions(options: SkillFactoryDomainOption[]) {
  return (options || [])
    .map((option) => ({
      label: domainOptionLabel(option),
      value: domainOptionValue(option),
    }))
    .filter((option) => option.value);
}

function domainDisplayText(options: SkillFactoryDomainOption[], value?: string): string {
  if (!value) return '-';
  const matched = (options || []).find((option) => domainOptionValue(option) === value);
  return matched ? domainOptionLabel(matched) : value;
}

function normalizeReleaseVersions(values?: Array<number | string>): number[] {
  const numbers =
    values
      ?.map((value) => Number(value))
      ?.filter((value) => Number.isInteger(value) && value > 0) || [];
  return Array.from(new Set(numbers)).sort((left, right) => left - right);
}

function releaseOptionsFromSkill(skill: SkillDraft | null): ReleaseVersionOptions | null {
  if (!skill) return null;
  return {
    workspaceId: skill.workspaceId,
    preprodBuildResetSources: skill.preprodBuildResetSources || [],
    releaseVersions: normalizeReleaseVersions(skill.releaseVersions),
    latestReleaseVersion: Number(skill.latestReleaseVersion || 0),
    nextReleaseVersion: Math.max(1, Number(skill.nextReleaseVersion || 1)),
    editable: skill.editable,
    draftStatus: skill.draftStatus,
    baseVersion: skill.baseVersion,
    sealedVersion: skill.sealedVersion,
  };
}

function buildWorkspaceViewParams(viewMode: WorkspaceViewMode, version?: string) {
  if (viewMode === WORKSPACE_VIEW_ONLINE_RELEASE) {
    return { viewMode, version };
  }
  return { viewMode: WORKSPACE_VIEW_PREPROD_CURRENT };
}

function buildSkillFactoryRoute(skillCode?: string, tab?: WorkbenchTab): string {
  const searchParams =
    typeof window === 'undefined'
      ? new URLSearchParams()
      : new URLSearchParams(window.location.search);
  if (skillCode) {
    searchParams.set('skillCode', skillCode);
  } else {
    searchParams.delete('skillCode');
  }
  if (tab) {
    searchParams.set('tab', tab);
  } else {
    searchParams.delete('tab');
  }
  const path = skillCode ? '/management/detail' : '/management';
  const searchText = searchParams.toString();
  return searchText ? `${path}?${searchText}` : path;
}

function buildCapabilityCenterRoute(draftId?: string): string {
  const searchParams =
    typeof window === 'undefined'
      ? new URLSearchParams()
      : new URLSearchParams(window.location.search);
  searchParams.delete('skillCode');
  searchParams.delete('tab');
  if (draftId) {
    searchParams.set('draftId', draftId);
  } else {
    searchParams.delete('draftId');
  }
  const path = draftId
    ? '/management/capabilities/edit'
    : '/management/capabilities';
  const searchText = searchParams.toString();
  return searchText ? `${path}?${searchText}` : path;
}

function skillStatusColor(status?: string): string {
  const normalizedStatus = status?.trim()?.toUpperCase?.();
  if (normalizedStatus === 'ONLINE') return 'success';
  if (normalizedStatus === 'SEALED') return 'warning';
  if (normalizedStatus === 'FAILED' || normalizedStatus === 'ERROR') return 'error';
  return 'blue';
}

function skillStatusLabel(status?: string): string {
  if (!status) return '-';
  const normalizedStatus = status?.trim()?.toUpperCase?.();
  return SKILL_STATUS_LABELS[normalizedStatus] || status;
}

function isSkillOnline(skill: SkillDraft): boolean {
  const onlineVersionId = String(skill.onlineVersionId || '').trim();
  return Boolean(onlineVersionId && onlineVersionId !== '0' && onlineVersionId !== '-');
}

const SkillFactoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const routeSkillCode = searchParams.get('skillCode') || '';
  const isDetailMode = Boolean(routeSkillCode);
  const [activeTab, setActiveTab] = useState<WorkbenchTab>(getInitialTab);
  const [skillInfoForm] = Form.useForm();
  const [keyword, setKeyword] = useState('');
  const [businessDomainFilter, setBusinessDomainFilter] = useState('');
  const [capabilityDomainFilter, setCapabilityDomainFilter] = useState('');
  const [specialistFilter, setSpecialistFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [skillList, setSkillList] = useState<SkillDraft[]>([]);
  const [skillPage, setSkillPage] = useState(1);
  const [skillTotal, setSkillTotal] = useState(0);
  const [skillCounts, setSkillCounts] = useState({ editingCount: 0, onlineCount: 0 });
  const listRequestId = useRef(0);
  const appliedListQuery = useRef<SkillListQuery>({ page: 1, pageSize: SKILL_LIST_PAGE_SIZE });
  const [selectedSkillCode, setSelectedSkillCode] = useState('');
  const [selectedSkill, setSelectedSkill] = useState<SkillDraft | null>(null);
  const [workspaceTree, setWorkspaceTree] = useState<WorkspaceTreeResult | null>(null);
  const [selectedFilePath, setSelectedFilePath] = useState('');
  const [fileContent, setFileContent] = useState<WorkspaceFileContent | null>(null);
  const [editorContent, setEditorContent] = useState('');
  const [isFileEditing, setIsFileEditing] = useState(false);
  const [createSkillFileOpen, setCreateSkillFileOpen] = useState(false);
  const [newSkillFileContent, setNewSkillFileContent] = useState('');

  const [workspaceNotice, setWorkspaceNotice] = useState('');
  const [workspaceViewMode, setWorkspaceViewMode] = useState<WorkspaceViewMode>(
    WORKSPACE_VIEW_PREPROD_CURRENT,
  );
  const [selectedReleaseVersion, setSelectedReleaseVersion] = useState('');
  const [releaseOptions, setReleaseOptions] = useState<ReleaseVersionOptions | null>(null);
  const [changeBaseVersion, setChangeBaseVersion] = useState('');
  const [changeName, setChangeName] = useState('');
  const [resetSourceValue, setResetSourceValue] = useState('');
  const [specialistPrtBindings, setSpecialistPrtBindings] = useState<
    Record<string, SpecialistPrtBindingState>
  >({});
  const [specialistPrtLoading, setSpecialistPrtLoading] = useState(false);
  const [debugSpecialistOptions, setDebugSpecialistOptions] = useState<SpecialistDebugOption[]>([]);
  const [debugSpecialistSelection, setDebugSpecialistSelection] = useState({
    skillCode: '',
    employeeId: '',
  });
  const [debugSpecialistOptionsLoading, setDebugSpecialistOptionsLoading] = useState(false);
  const [debugSpecialistOptionsError, setDebugSpecialistOptionsError] = useState('');
  const [pageConfig, setPageConfig] = useState<SkillFactoryPageConfig>(defaultPageConfig);
  const [configuredSpecialists, setConfiguredSpecialists] = useState<
    SkillFactorySpecialistOption[]
  >([]);
  const [, setConfigLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [errorText, setErrorText] = useState('');

  const [referenceComponentCodes, setReferenceComponentCodes] = useState('');
  const [componentNameKeyword, setComponentNameKeyword] = useState('');
  const [boundComponentRegistryAssets, setBoundComponentRegistryAssets] = useState<
    Record<number, SkillFactoryReferenceAsset | null>
  >({});
  const [capabilityKeyword, setCapabilityKeyword] = useState('');
  const [capabilityDrafts, setCapabilityDrafts] = useState<CapabilityActionDraft[]>([]);
  const [capabilityLoading, setCapabilityLoading] = useState(false);
  const [contextFillLoadingKey, setContextFillLoadingKey] = useState('');
  const [renderPreviewInput, setRenderPreviewInput] = useState('');
  const [renderPreviewResult, setRenderPreviewResult] = useState<ComponentRenderPreviewResult>();

  const [expandedTraceKeys, setExpandedTraceKeys] = useState<Record<string, boolean>>({});
  const [expandedBusinessCardKeys, setExpandedBusinessCardKeys] = useState<Record<string, boolean>>(
    {},
  );
  const [skillInfoDrawerOpen, setSkillInfoDrawerOpen] = useState(false);
  const [skillInfoMode, setSkillInfoMode] = useState<SkillInfoMode>('create');
  const [skillAuthoringRailOpen, setSkillAuthoringRailOpen] = useState(true);
  const [skillAuthoringRailView, setSkillAuthoringRailView] = useState<AuthoringRailView>('chat');
  const [selectedSkillPatchKey, setSelectedSkillPatchKey] = useState('');
  const [selectedSkillPatchFiles, setSelectedSkillPatchFiles] = useState<Record<string, string[]>>(
    {},
  );


  const treeData = useMemo(() => decorateTree(workspaceTree?.treeData), [workspaceTree]);
  const releaseVersionList = useMemo(
    () =>
      normalizeReleaseVersions(
        releaseOptions?.releaseVersions?.length
          ? releaseOptions.releaseVersions
          : selectedSkill?.releaseVersions || workspaceTree?.releaseVersions,
      ),
    [
      releaseOptions?.releaseVersions,
      selectedSkill?.releaseVersions,
      workspaceTree?.releaseVersions,
    ],
  );
  const resetSourceGroups = useMemo(
    () =>
      buildWorkspaceResetOptionGroups(
        releaseOptions?.preprodBuildResetSources ??
          selectedSkill?.preprodBuildResetSources ??
          workspaceTree?.preprodBuildResetSources,
        releaseVersionList,
      ),
    [
      releaseOptions?.preprodBuildResetSources,
      releaseVersionList,
      selectedSkill?.preprodBuildResetSources,
      workspaceTree?.preprodBuildResetSources,
    ],
  );
  const selectedResetSource = useMemo(
    () => parseWorkspaceResetValue(resetSourceValue),
    [resetSourceValue],
  );
  const selectedResetSourceOption = useMemo(
    () => findWorkspaceResetOption(resetSourceGroups, resetSourceValue),
    [resetSourceGroups, resetSourceValue],
  );
  const latestReleaseVersion = Number(
    releaseOptions?.latestReleaseVersion ||
      selectedSkill?.latestReleaseVersion ||
      workspaceTree?.latestReleaseVersion ||
      0,
  );
  const nextReleaseVersion = Math.max(
    1,
    Number(
      releaseOptions?.nextReleaseVersion ||
        selectedSkill?.nextReleaseVersion ||
        workspaceTree?.nextReleaseVersion ||
        1,
    ),
  );
  const resolvedPageConfig = useMemo(() => mergePageConfig(pageConfig), [pageConfig]);
  const specialists = resolvedPageConfig.specialists || defaultSpecialists;
  const businessDomains = resolvedPageConfig.businessDomains || defaultBusinessDomains;
  const capabilityDomains = resolvedPageConfig.capabilityDomains || defaultCapabilityDomains;
  const businessDomainSelectOptions = useMemo(
    () => domainSelectOptions(businessDomains),
    [businessDomains],
  );
  const capabilityDomainSelectOptions = useMemo(
    () => domainSelectOptions(capabilityDomains),
    [capabilityDomains],
  );
  const specialistFilterSelectOptions = useMemo(
    () =>
      configuredSpecialists.map((item) => ({
        label: specialistOptionName(item),
        value: specialistOptionId(item),
      })),
    [configuredSpecialists],
  );
  const quickPrompts = resolvedPageConfig.quickPrompts || defaultQuickPrompts;
  const referenceRenderAssets = useMemo(
    () => uniqueReferenceAssets(resolvedPageConfig.referenceRenderAssets || []),
    [resolvedPageConfig.referenceRenderAssets],
  );
  const capabilityBindings = useMemo<SkillFactoryCapabilityBinding[]>(() => {
    if (selectedSkill?.capabilityBindings !== undefined) {
      return selectedSkill.capabilityBindings || [];
    }
    return (selectedSkill?.referenceCapabilities || [])
      .map((item) => ({
        ...item,
        capabilityCode: item.actionCode || '',
        bindMode: CAPABILITY_BIND_EXECUTION_ONLY,
      }))
      .filter((item) => Boolean(item.capabilityCode));
  }, [selectedSkill?.capabilityBindings, selectedSkill?.referenceCapabilities]);
  const componentBindings = useMemo<SkillFactoryComponentBinding[]>(() => {
    if (selectedSkill?.componentBindings !== undefined) {
      return selectedSkill.componentBindings || [];
    }
    return (selectedSkill?.referenceRenderAssets || [])
      .filter((item) => Number(item.assetId || 0) > 0)
      .map((item) => ({
        ...item,
        assetId: Number(item.assetId),
        componentCode: referenceAssetKey(item),
      }));
  }, [selectedSkill?.componentBindings, selectedSkill?.referenceRenderAssets]);
  const activeReferenceRenderAssets = useMemo(() => componentBindings, [componentBindings]);
  useEffect(() => {
    let cancelled = false;
    const assetIds = Array.from(
      new Set(
        componentBindings
          ?.map((item) => Number(item.assetId || 0))
          ?.filter?.((assetId) => assetId > 0),
      ),
    );
    setBoundComponentRegistryAssets({});
    if (!assetIds.length) {
      return () => {
        cancelled = true;
      };
    }
    Promise.all(
      assetIds.map(async (assetId) => {
        try {
          const asset = await componentCenterApi.detail(assetId);
          return [assetId, componentAssetToReferenceAsset(asset)] as const;
        } catch {
          return [assetId, null] as const;
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      const nextRegistryAssets: Record<number, SkillFactoryReferenceAsset | null> = {};
      entries.forEach(([assetId, asset]) => {
        nextRegistryAssets[assetId] = asset;
      });
      setBoundComponentRegistryAssets(nextRegistryAssets);
    });
    return () => {
      cancelled = true;
    };
  }, [componentBindings]);
  const referenceCapabilityDraftIds = useMemo(
    () => capabilityBindings?.map((item) => item.draftId)?.filter?.(Boolean),
    [capabilityBindings],
  );
  const filteredReferenceRenderAssets = useMemo(() => {
    const searchText = componentNameKeyword?.trim()?.toLowerCase?.();
    if (!searchText) return referenceRenderAssets;
    return referenceRenderAssets.filter((asset) =>
      referenceAssetSearchText(asset)?.includes?.(searchText),
    );
  }, [componentNameKeyword, referenceRenderAssets]);
  const skillCodingBizConfig =
    resolvedPageConfig.bizConfigs?.[SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING];
  const skillCodingAgentId =
    skillCodingBizConfig?.agentId || resolvedPageConfig.agentId || DEFAULT_SKILL_CODING_AGENT_ID;
  const skillCodingOwnerId =
    skillCodingBizConfig?.ownerId || resolvedPageConfig.ownerId || DEFAULT_SKILL_CODING_OWNER_ID;
  const currentUserName = useMemo(getCurrentUserName, []);
  const skillAccess = useAssetAccess('SKILL', selectedSkill?.skillCode);
  const codingSessionScope = useMemo<AuthoringSessionScopeParams | null>(() => {
    if (!selectedSkill) return null;
    const scopeId = selectedSkill.workspaceId || selectedSkill.skillCode;
    return {
      bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING,
      scopeType: 'SKILL',
      scopeId,
      workspaceId: scopeId,
      skillCode: selectedSkill.skillCode,
    };
  }, [selectedSkill?.workspaceId, selectedSkill?.skillCode]);
  const canCurrentUserEditSkill = !selectedSkill || skillAccess.permissions?.canEdit;
  const currentSkillSpecialistIds = useMemo(
    () => skillSpecialistIds(selectedSkill, specialists),
    [selectedSkill?.specialistId, selectedSkill?.specialistName, specialists],
  );
  const selectedDebugSpecialistId =
    debugSpecialistSelection.skillCode === selectedSkill?.skillCode
      ? debugSpecialistSelection.employeeId
      : '';
  const debugSpecialists = useMemo(() => {
    if (!selectedDebugSpecialistId) return [];
    const selectedOption = debugSpecialistOptions.find(
      (option) => option.value === selectedDebugSpecialistId,
    );
    return [
      {
        employeeId: selectedDebugSpecialistId,
        employeeName: selectedOption?.employeeName || `专员 ${selectedDebugSpecialistId}`,
      },
    ];
  }, [debugSpecialistOptions, selectedDebugSpecialistId]);
  useEffect(() => {
    if (activeTab !== 'binding') return undefined;
    let cancelled = false;
    setDebugSpecialistOptionsLoading(true);
    setDebugSpecialistOptionsError('');
    listDigitalEmployeeDefinitions({
      pageNo: 1,
      pageSize: SPECIALIST_DEBUG_LIST_PAGE_SIZE,
    })
      .then((result) => {
        if (!cancelled) {
          setDebugSpecialistOptions(buildSpecialistDebugOptions(result.list));
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setDebugSpecialistOptions([]);
          setDebugSpecialistOptionsError(
            error instanceof Error ? error.message : '专员列表加载失败',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setDebugSpecialistOptionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab]);
  useEffect(() => {
    if (activeTab !== 'binding' || !selectedSkill?.skillCode) return;
    setDebugSpecialistSelection((current) => ({
      skillCode: selectedSkill.skillCode,
      employeeId: resolveSpecialistDebugSelection(
        current.skillCode === selectedSkill.skillCode ? current.employeeId : '',
        currentSkillSpecialistIds,
        debugSpecialistOptions,
      ),
    }));
  }, [activeTab, currentSkillSpecialistIds, debugSpecialistOptions, selectedSkill?.skillCode]);
  useEffect(() => {
    if (activeTab !== 'binding' || !selectedSkill?.skillCode || !debugSpecialists.length) {
      setSpecialistPrtBindings({});
      setSpecialistPrtLoading(false);
      return;
    }
    let cancelled = false;
    setSpecialistPrtLoading(true);
    Promise.all(
      debugSpecialists.map(async ({ employeeId, employeeName }) => {
        try {
          const state = await skillFactoryApi.querySpecialistPrtBinding(
            employeeId,
            selectedSkill.skillCode,
            currentUserName,
          );
          return [
            employeeId,
            { ...state, employeeName: state.employeeName || employeeName },
          ] as const;
        } catch (error) {
          return [
            employeeId,
            {
              employeeId,
              employeeCode: '',
              employeeName,
              skillCode: selectedSkill.skillCode,
              versionAction: 'BLOCKED' as const,
              versionId: '',
              versionLabel: '',
              versionStatus: '',
              containsSkill: false,
              prtEffective: false,
              blockedReason: error instanceof Error ? error.message : '查询 PRT 变更失败',
            },
          ] as const;
        }
      }),
    )
      .then((entries) => {
        if (!cancelled) {
          setSpecialistPrtBindings(Object.fromEntries(entries));
        }
      })
      .finally(() => {
        if (!cancelled) setSpecialistPrtLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, currentUserName, debugSpecialists, selectedSkill?.skillCode]);
  const hasFileDraftChange = editorContent !== (fileContent?.content || '');
  const currentDraftEditabilityKnown = [
    selectedSkill?.editable,
    releaseOptions?.editable,
    workspaceTree?.editable,
  ].some((editable) => typeof editable === 'boolean');
  const currentDraftEditable =
    Boolean(selectedSkill) &&
    currentDraftEditabilityKnown &&
    selectedSkill?.editable !== false &&
    releaseOptions?.editable !== false &&
    workspaceTree?.editable !== false;
  const skillInfoEditDisabledReason = !currentDraftEditable
    ? '当前 Skill 没有可编辑变更，请先新建变更'
    : !canCurrentUserEditSkill
    ? skillAccess.readonlyReason || '当前用户不是负责人，仅可查看'
    : '';
  const skillInfoFieldsDisabled = skillInfoMode === 'edit' && Boolean(skillInfoEditDisabledReason);
  const currentDraftStatus =
    workspaceTree?.draftStatus ||
    releaseOptions?.draftStatus ||
    selectedSkill?.draftStatus ||
    'EDITING';
  const currentSealedVersion =
    workspaceTree?.sealedVersion ||
    releaseOptions?.sealedVersion ||
    selectedSkill?.sealedVersion ||
    0;
  const sealedCurrentDraft = Boolean(selectedSkill) && !currentDraftEditable;
  const readonlyWorkspace =
    workspaceViewMode === WORKSPACE_VIEW_ONLINE_RELEASE ||
    Boolean(workspaceTree?.readonly || fileContent?.readonly) ||
    sealedCurrentDraft ||
    !canCurrentUserEditSkill;
  const workspaceReadonlyMessage = !canCurrentUserEditSkill
    ? skillAccess.readonlyReason || '当前用户不是负责人，仅可查看'
    : workspaceViewMode === WORKSPACE_VIEW_ONLINE_RELEASE
    ? '正式包历史只读，不能修改文件'
    : '当前变更已封板，请先从正式包新建变更';
  const canUseCodingChat =
    Boolean(selectedSkill) && currentDraftEditable && canCurrentUserEditSkill;
  const currentWorkspaceViewParams = useMemo(
    () => buildWorkspaceViewParams(workspaceViewMode, selectedReleaseVersion),
    [selectedReleaseVersion, workspaceViewMode],
  );
  const skillCodingAdapter = useMemo(
    () =>
      createSkillCodingAuthoringAdapter({
        sessionScope: {
          ...(codingSessionScope || {
            bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING,
            scopeType: 'SKILL',
            scopeId: '',
            workspaceId: '',
          }),
          disabledReason: !selectedSkill
            ? '请先选择 Skill'
            : !skillCodingAgentId
            ? '当前页面缺少 HADES_SKILL_FACTORY agentId 配置'
            : !canUseCodingChat
            ? !canCurrentUserEditSkill
              ? skillAccess.readonlyReason || '当前用户不是负责人，不能发起生成对话'
              : '当前变更已封板，请先新建变更后再发起对话'
            : undefined,
        },
        buildRequest: ({ message: messageText, sessionId, messageId, runId }) => ({
          bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING,
          agentId: skillCodingAgentId,
          specialistId: selectedSkill?.specialistId,
          ownerId: skillCodingOwnerId,
          skillCode: selectedSkill?.skillCode,
          workspaceId: selectedSkill?.workspaceId || selectedSkill?.skillCode,
          scopeType: 'SKILL',
          scopeId: selectedSkill?.workspaceId || selectedSkill?.skillCode,
          sessionId,
          conversationId: sessionId,
          messageId,
          runId,
          invokeId: messageId,
          message: messageText,

          referenceComponentCodes: referenceComponentCodes
            ?.split(',')
            ?.map?.((item) => item.trim())
            ?.filter?.(Boolean),
          referenceRenderAssets: activeReferenceRenderAssets.map((asset) => ({
            code: referenceAssetKey(asset),
            name: asset.name,
            assetType: assetTypeText(asset.assetType),
            renderProtocol: asset.renderProtocol,
            componentName: asset.componentName,
            dslCode: asset.dslCode,
            dslType: asset.dslType,
            agentUiDsl: asset.agentUiDsl,
            localMethod: asset.localMethod,
            scene: asset.scene,
            integrationPrompt: asset.integrationPrompt,
            schemaJson: asset.schemaJson,
            paramsSchemaJson: asset.paramsSchemaJson,
            officialDemoJson: asset.officialDemoJson,
          })),
          referenceCapabilities: selectedSkill?.referenceCapabilities || [],
          referenceCapabilityDraftIds,
          capabilityBindings,
          componentBindings,
          codingMode: 'PLAN_AND_PATCH',
          client: DEFAULT_AI_CODING_CLIENT,
          path: typeof window === 'undefined' ? '' : window.location.pathname,
        }),
      }),
    [
      activeReferenceRenderAssets,

      canUseCodingChat,
      canCurrentUserEditSkill,
      capabilityBindings,
      codingSessionScope,
      componentBindings,
      referenceCapabilityDraftIds,
      referenceComponentCodes,
      selectedSkill,
      skillCodingAgentId,
      skillCodingOwnerId,
      skillAccess.readonlyReason,
    ],
  );
  const skillAuthoringChat = useSkillFactoryChatStream({
    adapter: skillCodingAdapter,
    workspaceId: selectedSkill?.workspaceId || selectedSkill?.skillCode || '',
  });
  const currentCodingSessionId =
    skillAuthoringChat.selectedSessionId || skillAuthoringChat.activeSessionId;
  const skillPatchChangeSets = useMemo(() => {
    const patchMap = new Map<string, SkillFactoryCodingEvent>();
    skillAuthoringChat.events?.forEach?.((event, index) => {
      if (!isPatchReviewEvent(event)) return;
      const key = patchEventKey(event, event.timestamp || index);
      const previous = patchMap.get(key);
      patchMap.set(key, previous ? mergePatchEvent(previous, event) : event);
    });
    return Array.from(patchMap.entries())
      ?.map(([key, event]) => ({ key, event }))
      ?.sort?.(
        (left, right) => Number(right.event?.timestamp || 0) - Number(left.event?.timestamp || 0),
      );
  }, [skillAuthoringChat.events]);
  const selectedSkillPatch =
    skillPatchChangeSets.find(({ key }) => key === selectedSkillPatchKey) ||
    skillPatchChangeSets.find(({ event }) => patchReviewStatus(event) === 'PENDING') ||
    skillPatchChangeSets?.[0];
  const pendingSkillPatchCount = skillPatchChangeSets?.filter(
    ({ event }) => patchReviewStatus(event) === 'PENDING',
  )?.length;

  useEffect(() => {
    if (!skillPatchChangeSets.length) {
      setSelectedSkillPatchKey('');
      return;
    }
    if (!skillPatchChangeSets.some(({ key }) => key === selectedSkillPatchKey)) {
      setSelectedSkillPatchKey(selectedSkillPatch?.key || '');
    }
  }, [selectedSkillPatch?.key, selectedSkillPatchKey, skillPatchChangeSets]);

  const isPatchActionLoading =
    actionLoading.startsWith('confirm:') || actionLoading.startsWith('discard:');
  const isAuthoringActionLoading = actionLoading.startsWith('authoring:');
  const isValidationActionLoading =
    actionLoading === SkillFactoryMethod.CODING_VALIDATE ||
    actionLoading === SkillFactoryMethod.CODING_VALIDATION_REPAIR;
  const isCodingStreamLocked =
    skillAuthoringChat.loading ||
    isPatchActionLoading ||
    isAuthoringActionLoading ||
    isValidationActionLoading;

  const loadPageConfig = async () => {
    setConfigLoading(true);
    try {
      const config = await skillFactoryApi.config();
      setConfiguredSpecialists(normalizeSpecialists(config.specialists));
      const mergedConfig = mergePageConfig(config);
      try {
        const publishedAssets = await skillBindingCandidateApi.componentList({});
        setPageConfig({
          ...mergedConfig,
          referenceRenderAssets: uniqueReferenceAssets(
            publishedAssets.map(componentAssetToReferenceAsset),
          ),
        });
      } catch (componentError) {
        // eslint-disable-next-line no-console
        console.warn('Component center published assets load failed', componentError);
        setPageConfig({
          ...mergedConfig,
          referenceRenderAssets: [],
        });
      }
    } catch (error) {
      // 后端配置 method 热更完成前，页面保留默认结构，避免整页不可用。
      // eslint-disable-next-line no-console
      console.warn('SkillFactory config load failed', error);
      setConfiguredSpecialists([]);
      setPageConfig({
        ...defaultPageConfig,
        referenceRenderAssets: [],
      });
    } finally {
      setConfigLoading(false);
    }
  };

  const loadCapabilityDrafts = async (nextKeyword = capabilityKeyword) => {
    setCapabilityLoading(true);
    try {
      const publishedCapabilities = await skillBindingCandidateApi.capabilityList(nextKeyword);
      setCapabilityDrafts(publishedCapabilities);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '业务能力列表加载失败');
    } finally {
      setCapabilityLoading(false);
    }
  };

  const loadReleaseOptions = async (workspaceId: string, fallback?: SkillDraft | null) => {
    try {
      const options = await skillFactoryApi.releaseOptions(workspaceId);
      setReleaseOptions(options);
      const latestVersion = options.latestReleaseVersion
        ? String(options.latestReleaseVersion)
        : '';
      setSelectedReleaseVersion((prev) => prev || latestVersion);
      setChangeBaseVersion((prev) => prev || latestVersion);
      const nextResetGroups = buildWorkspaceResetOptionGroups(
        options.preprodBuildResetSources,
        options.releaseVersions,
      );
      setResetSourceValue((prev) =>
        findWorkspaceResetOption(nextResetGroups, prev)
          ? prev
          : defaultWorkspaceResetValue(nextResetGroups),
      );
      return options;
    } catch (error) {
      const fallbackOptions = releaseOptionsFromSkill(fallback || selectedSkill);
      setReleaseOptions(fallbackOptions);
      return fallbackOptions;
    }
  };

  const loadWorkspace = async (
    workspaceId: string,
    nextViewMode: WorkspaceViewMode = workspaceViewMode,
    nextReleaseVersion = selectedReleaseVersion,
  ) => {
    if (nextViewMode === WORKSPACE_VIEW_ONLINE_RELEASE && !nextReleaseVersion) {
      setWorkspaceTree(null);
      setSelectedFilePath('');
      setFileContent(null);
      setEditorContent('');
      setIsFileEditing(false);
      return;
    }
    const viewParams = buildWorkspaceViewParams(nextViewMode, nextReleaseVersion);
    const tree = await skillFactoryApi.workspaceTree(workspaceId, viewParams);
    setWorkspaceTree(tree);
    const firstFile = tree.files?.find((item) => item.filePath === 'SKILL.md') || tree.files?.[0];
    if (firstFile) {
      setSelectedFilePath(firstFile.filePath);
      const content = await skillFactoryApi.fileContent(
        workspaceId,
        firstFile.filePath,
        viewParams,
      );
      setFileContent(content);
      setEditorContent(content.content || '');
      setIsFileEditing(false);
      return;
    }
    setSelectedFilePath('');
    setFileContent(null);
    setEditorContent('');
    setIsFileEditing(false);
  };

  const loadDetail = async (skillCode: string) => {
    const detail = await skillFactoryApi.detail(skillCode);
    setSelectedSkill(detail);
    const detailReferenceCodes = referenceCodesOf(
      detail.componentBindings !== undefined
        ? detail.componentBindings
        : detail.referenceRenderAssets,
    );
    setReferenceComponentCodes(detailReferenceCodes);
    setSpecialistPrtBindings({});
    const detailReleaseOptions = releaseOptionsFromSkill(detail);
    setReleaseOptions(detailReleaseOptions);
    const latestVersion = detailReleaseOptions?.latestReleaseVersion
      ? String(detailReleaseOptions.latestReleaseVersion)
      : '';
    setSelectedReleaseVersion(latestVersion);
    setChangeBaseVersion(latestVersion);
    setResetSourceValue(
      defaultWorkspaceResetValue(
        buildWorkspaceResetOptionGroups(detail.preprodBuildResetSources, detail.releaseVersions),
      ),
    );
    setWorkspaceViewMode(WORKSPACE_VIEW_PREPROD_CURRENT);
    await loadReleaseOptions(detail.workspaceId, detail);
    await loadWorkspace(detail.workspaceId, WORKSPACE_VIEW_PREPROD_CURRENT, latestVersion);
  };

  const clearSkillSelection = () => {
    setSelectedSkillCode('');
    setSelectedSkill(null);
    setWorkspaceTree(null);
    setSelectedFilePath('');
    setFileContent(null);
    setEditorContent('');
    setIsFileEditing(false);
    setWorkspaceViewMode(WORKSPACE_VIEW_PREPROD_CURRENT);
    setSelectedReleaseVersion('');
    setReleaseOptions(null);
    setChangeBaseVersion('');
    setChangeName('');
    setResetSourceValue('');
    setSpecialistPrtBindings({});
  };

  const loadList = async (
    nextKeyword = keyword,
    preferredSkillCode = routeSkillCode,
    nextBusinessDomain = businessDomainFilter,
    nextCapabilityDomain = capabilityDomainFilter,
    nextPage = 1,
    nextSpecialist = specialistFilter,
    nextStatus = statusFilter,
  ) => {
    const requestId = ++listRequestId.current;
    setLoading(true);
    setErrorText('');
    try {
      const query: SkillListQuery = {
        keyword: nextKeyword,
        businessDomain: nextBusinessDomain,
        capabilityDomain: nextCapabilityDomain,
        specialistId: nextSpecialist,
        status: nextStatus,
        page: nextPage,
        pageSize: SKILL_LIST_PAGE_SIZE,
      };
      const result = await skillFactoryApi.list(query);
      if (requestId !== listRequestId.current) return;
      const lastPage = Math.max(1, Math.ceil(result.total / SKILL_LIST_PAGE_SIZE));
      if (nextPage > lastPage) {
        await loadList(nextKeyword, preferredSkillCode, nextBusinessDomain,
          nextCapabilityDomain, lastPage, nextSpecialist, nextStatus);
        return;
      }
      appliedListQuery.current = query;
      setSkillList(result.list);
      setSkillPage(result.page);
      setSkillTotal(result.total);
      setSkillCounts({ editingCount: result.editingCount, onlineCount: result.onlineCount });
      if (preferredSkillCode) {
        setSelectedSkillCode(preferredSkillCode);
        await loadDetail(preferredSkillCode);
      } else {
        clearSkillSelection();
      }
    } catch (error) {
      if (requestId !== listRequestId.current) return;
      const text = error instanceof Error ? error.message : 'SkillFactory 加载失败';
      setErrorText(text);
      message.error(text);
    } finally {
      if (requestId === listRequestId.current) setLoading(false);
    }
  };

  const handleResetListFilters = () => {
    setKeyword('');
    setBusinessDomainFilter('');
    setCapabilityDomainFilter('');
    setSpecialistFilter('');
    setStatusFilter('');
    loadList('', '', '', '', 1, '', '');
  };

  useEffect(() => {
    const init = async () => {
      await Promise.all([loadPageConfig(), loadList(keyword, routeSkillCode)]);
    };
    init();
    return () => { listRequestId.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeSkillCode]);

  useEffect(() => {
    if (activeTab === 'capabilities') {
      loadCapabilityDrafts();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);



  const handleSelectSkill = (skill: SkillDraft) => {
    if (isCodingStreamLocked) {
      message.warning('当前 AICoding 流式输出未结束，先停止或等待完成后再切换 Skill');
      return;
    }
    setActiveTab('overview');
    navigate(buildSkillFactoryRoute(skill.skillCode, 'overview'));
  };

  const handleBackToSkillList = () => {
    if (isCodingStreamLocked) {
      message.warning('当前 AICoding 流式输出未结束，先停止或等待完成后再返回列表');
      return;
    }
    navigate(buildSkillFactoryRoute());
    clearSkillSelection();
  };

  const handleTabChange = (tab: WorkbenchTab) => {
    setActiveTab(tab);
    if (selectedSkillCode || routeSkillCode) {
      navigate(buildSkillFactoryRoute(selectedSkillCode || routeSkillCode, tab), {
        replace: true,
      });
    }
  };

  const handleSelectFile = async (filePath: string) => {
    if (!selectedSkill || !filePath || filePath === 'root') return;
    if (isFileEditing && hasFileDraftChange) {
      message.warning('当前文件有未保存改动，请先保存或取消编辑后再切换文件');
      return;
    }
    setActionLoading(`file:${filePath}`);
    try {
      const content = await skillFactoryApi.fileContent(
        selectedSkill.workspaceId,
        filePath,
        currentWorkspaceViewParams,
      );
      setSelectedFilePath(filePath);
      setFileContent(content);
      setEditorContent(content.content || '');
      setIsFileEditing(false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '文件读取失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleSaveFile = async () => {
    if (!selectedSkill || !selectedFilePath) return;
    if (readonlyWorkspace) {
      message.warning(workspaceReadonlyMessage);
      return;
    }
    setActionLoading('saveFile');
    try {
      const saved = await skillFactoryApi.saveFile(
        selectedSkill.workspaceId,
        selectedSkill.skillCode,
        selectedFilePath,
        editorContent,
      );
      setFileContent(saved);
      setEditorContent(saved.content || editorContent);
      setIsFileEditing(false);
      message.success('文件已保存');
      await loadWorkspace(selectedSkill.workspaceId, WORKSPACE_VIEW_PREPROD_CURRENT);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '文件保存失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleCreateSkillFile = async () => {
    if (!selectedSkill || readonlyWorkspace || !workspaceTree || workspaceTree.fileCount !== 0
      || !newSkillFileContent.trim() || actionLoading) return;
    setActionLoading('createSkillFile');
    try {
      await skillFactoryApi.saveFile(
        selectedSkill.workspaceId, selectedSkill.skillCode, 'SKILL.md', newSkillFileContent,
      );
      setCreateSkillFileOpen(false);
      setNewSkillFileContent('');
      await loadWorkspace(selectedSkill.workspaceId, WORKSPACE_VIEW_PREPROD_CURRENT);
      message.success('SKILL.md 已创建');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建 SKILL.md 失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleSaveWorkspace = async () => {
    if (!selectedSkill) return;
    if (readonlyWorkspace) {
      message.warning(workspaceReadonlyMessage);
      return;
    }
    setActionLoading('saveWorkspace');
    try {
      const result = await skillFactoryApi.saveWorkspace(
        selectedSkill.workspaceId,
        selectedSkill.skillCode,
      );
      setWorkspaceTree(result);
      message.success('工作区摘要已保存');
      await loadDetail(selectedSkill.skillCode);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存工作区失败');
    } finally {
      setActionLoading('');
    }
  };

  const clearSelectedFile = () => {
    setSelectedFilePath('');
    setFileContent(null);
    setEditorContent('');
    setIsFileEditing(false);
  };

  const applyWorkspaceDeleteResult = (result: WorkspaceTreeResult, deletedPath?: string) => {
    setWorkspaceTree(result);
    setSelectedSkill((current) =>
      current ? { ...current, fileTreeDigest: result.fileTreeDigest } : current,
    );
    if (
      !deletedPath ||
      selectedFilePath === deletedPath ||
      selectedFilePath.startsWith(`${deletedPath}/`)
    ) {
      clearSelectedFile();
    }
  };

  const handleDeleteWorkspacePath = async (node: SkillTreeNode) => {
    if (!selectedSkill || isProtectedWorkspaceTreeNode(node)) return;
    if (readonlyWorkspace) {
      message.warning(workspaceReadonlyMessage);
      return;
    }
    const filePath = String(node.filePath || node.key || '');
    if (!filePath) return;
    const loadingKey = `deletePath:${filePath}`;
    setActionLoading(loadingKey);
    try {
      const result = await skillFactoryApi.deleteWorkspacePath(selectedSkill.workspaceId, filePath);
      applyWorkspaceDeleteResult(result, filePath);
      message.success(node.directory ? '目录已删除' : '文件已删除');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败');
    } finally {
      setActionLoading('');
    }
  };

  const confirmDeleteWorkspacePath = (node: SkillTreeNode) => {
    if (readonlyWorkspace) {
      message.warning(workspaceReadonlyMessage);
      return;
    }
    const filePath = String(node.filePath || node.key || '');
    Modal.confirm({
      title: `删除${node.directory ? '目录' : '文件'}`,
      content: node.directory
        ? `确认递归删除目录“${filePath}”及其中全部内容？该操作不可撤销。`
        : `确认删除文件“${filePath}”？该操作不可撤销。`,
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => handleDeleteWorkspacePath(node),
    });
  };

  const handleResetWorkspace = async () => {
    if (!selectedSkill) return;
    if (readonlyWorkspace) {
      message.warning(workspaceReadonlyMessage);
      return;
    }
    if (!selectedResetSource) {
      message.warning('请选择一个 PRT Build 或线上正式版本');
      return;
    }
    setActionLoading(SkillFactoryMethod.WORKSPACE_RESET_FROM_VERSION);
    try {
      const result = await skillFactoryApi.resetWorkspaceFromSource(
        selectedSkill.workspaceId,
        selectedResetSource,
      );
      applyWorkspaceDeleteResult(result);
      const sourceName =
        selectedResetSourceOption?.displayName || resetSourceDisplayName(selectedResetSource);
      setWorkspaceNotice(`当前变更已从${sourceName}重置，文件和全部绑定关系已同步。`);
      message.success(`已从${sourceName}重置当前变更`);
      await loadDetail(selectedSkill.skillCode);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '重置当前变更失败');
    } finally {
      setActionLoading('');
    }
  };

  const confirmResetWorkspace = () => {
    if (readonlyWorkspace) {
      message.warning(workspaceReadonlyMessage);
      return;
    }
    if (!selectedResetSource) {
      message.warning('请选择一个 PRT Build 或线上正式版本');
      return;
    }
    const sourceName =
      selectedResetSourceOption?.displayName || resetSourceDisplayName(selectedResetSource);
    Modal.confirm({
      title: `从${sourceName}重置当前变更`,
      content: `当前未发布的文件改动和绑定关系都会被丢弃，并完整恢复为${sourceName}的状态。当前 Skill 版本、workspaceId、线上版本和环境生效指针不变。`,
      okText: '确认重置',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: handleResetWorkspace,
    });
  };

  const handleEnsureSpecialistPrtBinding = async (employeeId: string) => {
    if (!selectedSkill) return;
    if (!canCurrentUserEditSkill) {
      message.warning(skillAccess.readonlyReason || '当前用户不是负责人，不能绑定调试专员');
      return;
    }
    if (!currentUserName) {
      message.error('未识别到当前登录用户，请重新登录后再试');
      return;
    }
    const loadingKey = `specialistPrt:${employeeId}`;
    setActionLoading(loadingKey);
    try {
      const result = await skillFactoryApi.ensureSpecialistPrtBinding(
        employeeId,
        selectedSkill.skillCode,
        currentUserName,
      );
      setSpecialistPrtBindings((prev) => ({ ...prev, [employeeId]: result }));
      if (result.publishStatus === 'PRT_EFFECTIVE') {
        message.success(`${result.employeeName || `专员 ${employeeId}`} 已绑定并发布到 PRT`);
      } else {
        message.error(
          result.message ||
            `PRT 发布未完全成功${result.failureStage ? `，失败阶段：${result.failureStage}` : ''}`,
        );
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '绑定并发布到 PRT 失败');
      try {
        const refreshed = await skillFactoryApi.querySpecialistPrtBinding(
          employeeId,
          selectedSkill.skillCode,
          currentUserName,
        );
        setSpecialistPrtBindings((prev) => ({ ...prev, [employeeId]: refreshed }));
      } catch {
        // 保留原查询结果，避免用二次查询错误覆盖更有价值的操作错误。
      }
    } finally {
      setActionLoading('');
    }
  };

  const handleWorkspaceViewModeChange = async (nextViewMode: WorkspaceViewMode) => {
    if (!selectedSkill) return;
    if (isFileEditing && hasFileDraftChange) {
      message.warning('当前文件有未保存改动，请先保存或取消编辑后再切换视图');
      return;
    }
    const nextVersion =
      nextViewMode === WORKSPACE_VIEW_ONLINE_RELEASE
        ? selectedReleaseVersion || (latestReleaseVersion ? String(latestReleaseVersion) : '')
        : '';
    if (nextViewMode === WORKSPACE_VIEW_ONLINE_RELEASE && !nextVersion) {
      message.warning('当前还没有正式包历史版本');
      return;
    }
    setWorkspaceViewMode(nextViewMode);
    setSelectedReleaseVersion(nextVersion);
    setIsFileEditing(false);
    setActionLoading('workspaceView');
    try {
      await loadWorkspace(selectedSkill.workspaceId, nextViewMode, nextVersion);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '工作区视图切换失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleReleaseVersionChange = async (version: string) => {
    if (!selectedSkill) return;
    if (isFileEditing && hasFileDraftChange) {
      message.warning('当前文件有未保存改动，请先保存或取消编辑后再切换版本');
      return;
    }
    setSelectedReleaseVersion(version);
    setIsFileEditing(false);
    setActionLoading('workspaceView');
    try {
      await loadWorkspace(selectedSkill.workspaceId, WORKSPACE_VIEW_ONLINE_RELEASE, version);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '正式包历史读取失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleCreateChange = async () => {
    if (!selectedSkill) return;
    if (!changeBaseVersion) {
      message.warning('请选择一个正式包版本作为变更起点');
      return;
    }
    const normalizedChangeName = changeName.trim();
    if (!normalizedChangeName) {
      message.warning('请输入变更名称');
      return;
    }
    if (isCodingStreamLocked) {
      message.warning('当前 AICoding 流式输出未结束，不能新建变更');
      return;
    }
    if (isFileEditing && hasFileDraftChange) {
      message.warning('当前文件有未保存改动，请先保存或取消编辑后再新建变更');
      return;
    }
    setActionLoading(SkillFactoryMethod.RELEASE_CHANGE_CREATE);
    try {
      const execution = await executeReleaseOperation(
        () =>
          assetReleaseApi.createChange(
            'SKILL',
            selectedSkill.skillCode,
            Number(changeBaseVersion),
            normalizedChangeName,
          ),
        () => assetReleaseApi.overview('SKILL', selectedSkill.skillCode),
      );
      const { feedback } = execution;
      if (feedback.kind === 'SUCCESS') {
        message.success(feedback.message);
      } else if (feedback.kind === 'PENDING') {
        message.info(feedback.message);
      } else {
        message.error(feedback.message);
      }
      setWorkspaceViewMode(WORKSPACE_VIEW_PREPROD_CURRENT);
      setSelectedReleaseVersion(changeBaseVersion);
      setChangeName('');
      if (execution.refreshError) {
        message.error('变更操作结果已返回，但发布状态刷新失败，请手动刷新');
      }
      try {
        await loadDetail(selectedSkill.skillCode);
      } catch {
        message.error('变更操作结果已返回，但 Skill 详情刷新失败，请手动刷新');
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '新建变更失败');
    } finally {
      setActionLoading('');
    }
  };

  const renderCreateChangeControl = () =>
    currentDraftEditable ? (
      <Tag color="success">当前已有可编辑变更</Tag>
    ) : (
      <Space className="skill-factory-change-action">
        <Input
          size="small"
          maxLength={80}
          value={changeName}
          placeholder="变更名称"
          style={{ width: 168 }}
          onChange={(event) => setChangeName(event.target.value)}
        />
        <Select
          size="small"
          value={changeBaseVersion || undefined}
          placeholder="版本"
          disabled={!releaseVersionList.length}
          style={{ width: 88 }}
          options={releaseVersionList.map((version) => ({
            label: String(version),
            value: String(version),
          }))}
          onChange={(value) => setChangeBaseVersion(String(value || ''))}
        />
        <Button
          size="small"
          icon={<PlusOutlined />}
          loading={actionLoading === SkillFactoryMethod.RELEASE_CHANGE_CREATE}
          disabled={
            !selectedSkill ||
            !changeBaseVersion ||
            !changeName.trim() ||
            !releaseVersionList.length ||
            isCodingStreamLocked
          }
          onClick={handleCreateChange}
        >
          新建变更
        </Button>
      </Space>
    );

  const handleCodingEvent = skillAuthoringChat.appendEvent;

  const buildCodingBaseParams = (
    sessionId: string,
    messageText: string,
    ids: { messageId?: string; runId?: string } = {},
  ): Record<string, unknown> | null => {
    if (!selectedSkill) return null;
    if (!skillCodingAgentId) {
      message.error('当前页面缺少 HADES_SKILL_FACTORY agentId 配置，无法发起 AI Coding');
      return null;
    }
    const messageId = ids.messageId || `msg_${sessionId}`;
    const runId = ids.runId || `run_${sessionId}`;
    return skillCodingAdapter.buildRequest({
      message: messageText,
      sessionId,
      messageId,
      runId,
    });
  };

  const handlePatchAction = async (
    action: 'confirm' | 'discard',
    patchEvent: SkillFactoryCodingEvent,
    selectedFilePaths?: string[],
  ) => {
    if (!selectedSkill || !patchEvent.patchId) return;
    if (!canUseCodingChat) {
      message.warning('当前变更已封板，请先新建变更后再应用 patch');
      return;
    }
    if (isCodingStreamLocked) {
      message.warning('当前 AICoding 流式输出未结束');
      return;
    }
    if (readonlyWorkspace) {
      message.warning(workspaceReadonlyMessage);
      return;
    }
    const loadingKey = `${action}:${patchEvent.patchId}`;
    const actionMethod =
      action === 'confirm'
        ? SkillFactoryMethod.CODING_PATCH_CONFIRM
        : SkillFactoryMethod.CODING_PATCH_DISCARD;
    const sessionId = patchEvent.sessionId || currentCodingSessionId || '';
    const messageId = eventMessageId(patchEvent);
    const runId = patchEvent.runId || `run_${sessionId}`;
    const workspaceId = selectedSkill.workspaceId || selectedSkill.skillCode;
    const idempotencyKey = `${action}-${patchEvent.patchId}-${Date.now()}`;
    if (action === 'confirm' && !selectedFilePaths?.length) {
      message.warning('请至少选择一个要应用的文件');
      return;
    }
    setActionLoading(loadingKey);
    try {
      const result = await skillFactoryApi.codingPatchAction(actionMethod, {
        bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.SKILL_CODING,
        agentId: String(skillCodingAgentId),
        ownerId: String(skillCodingOwnerId),
        skillCode: selectedSkill.skillCode,
        workspaceId,
        scopeType: 'SKILL',
        scopeId: workspaceId,
        sessionId,
        conversationId: sessionId,
        messageId,
        runId,
        invokeId: messageId,

        patchId: patchEvent.patchId,

        idempotencyKey,
        ...(action === 'confirm'
          ? { selectedFilePaths: jsonStringify(selectedFilePaths || []) || '[]' }
          : {}),
      });
      if (!result.success) {
        throw new Error(result.errorMsg || 'patch 操作失败');
      }
      message.success(
        action === 'confirm'
          ? `已应用 ${selectedFilePaths?.length || 0} 个文件，未选文件保持原状`
          : 'patch 已丢弃',
      );
      if (action === 'confirm') {
        await loadDetail(selectedSkill.skillCode);
      }
    } catch (error) {
      if (isAbortError(error)) return;
      message.error(error instanceof Error ? error.message : 'patch 操作失败');
    } finally {
      setActionLoading('');
      if (sessionId) {
        await skillAuthoringChat.reloadHistory(sessionId);
      }
    }
  };

  const handleAuthoringCardAction = async (
    assistantMessage: AssistantMessageState,
    card: A2uiSurfaceState,
    action: A2uiCardAction,
  ) => {
    if (!selectedSkill || !action.actionCode) return;
    if (!canUseCodingChat) {
      message.warning('当前变更已封板，请先新建变更后再处理业务卡片操作');
      return;
    }
    if (isCodingStreamLocked) {
      message.warning('当前 AICoding 流式输出未结束');
      return;
    }
    const sessionId = assistantMessage.sessionId || currentCodingSessionId || '';
    const requestParams = buildCodingBaseParams(sessionId, '处理业务卡片操作', {
      messageId: assistantMessage.messageId,
      runId: assistantMessage.runId,
    });
    if (!requestParams) return;
    const idempotencyKey = `${action.actionCode}-${assistantMessage.messageId}-${card.surfaceId}`;
    const loadingKey = `authoring:${idempotencyKey}`;
    const receivedEvents: SkillFactoryCodingEvent[] = [];
    setActionLoading(loadingKey);
    try {
      await skillFactoryApi.streamAuthoringAction(
        {
          ...requestParams,
          surfaceId: card.surfaceId,
          sourceComponentId: action.sourceComponentId,
          actionCode: action.actionCode,
          actionParams: action.actionParams || card.dataModel,
          idempotencyKey,
        },
        (event) => {
          receivedEvents.push(event);
          handleCodingEvent(event);
        },
      );
      const failureEvent = receivedEvents.find(isOperationFailureEvent);
      if (failureEvent) {
        throw new Error(eventText(failureEvent) || '业务卡片操作失败');
      }
      message.success('业务卡片操作已记录');
    } catch (error) {
      if (isAbortError(error)) return;
      message.error(error instanceof Error ? error.message : '业务卡片操作失败');
    } finally {
      setActionLoading('');
      const latestSessionId =
        receivedEvents?.find((event) => event.sessionId)?.sessionId || sessionId;
      if (latestSessionId) {
        await skillAuthoringChat.refreshSessionMetadata(latestSessionId);
      }
    }
  };

  const handleRunDynamicValidation = async () => {
    if (!selectedSkill) return;
    if (!canUseCodingChat) {
      message.warning('当前变更已封板，请先新建变更后再运行验证');
      return;
    }
    if (isCodingStreamLocked) {
      message.warning('当前 AICoding 流式输出未结束');
      return;
    }
    const testInput = skillAuthoringChat.input?.trim?.() || DEFAULT_VALIDATION_TEST_INPUT;
    const turnId = buildCodingTurnId('validation');
    const validationPrompt = [
      '请运行一次当前 Skill 的动态验证。',
      '请通过 invoke_agent 调用已配置的 checkAgent peer Agent，taskType=SKILL_RUNTIME_VALIDATION，expectedOutputType=ValidationReport。',
      '验证 Agent 必须先调用 simulate_skill_request 做只读 dry-run，再返回结构化 ValidationReport；如果 runtime adapter 未接入，只能返回 PARTIAL 或 FAILED，不要标记 PASSED。',
      `测试输入：${testInput}`,
    ].join('\n');
    setActionLoading(SkillFactoryMethod.CODING_VALIDATE);
    try {
      await skillAuthoringChat.send(validationPrompt, {
        displayText: `运行验证：${testInput}`,
        requestOverrides: {
          testInput,
          validationTaskId: turnId,
        },
      });
    } finally {
      setActionLoading('');
    }
  };

  const handleRenderStringPreview = async () => {
    if (!renderPreviewInput.trim()) {
      message.warning('请输入 render_component Tool arguments');
      return;
    }
    setActionLoading(SkillFactoryMethod.COMPONENT_RENDER_PREVIEW);
    try {
      const result = await componentCenterApi.bizRenderPreview({
        source: 'skill-workbench',
        clientType: 'PC',
        toolArgsJson: renderPreviewInput,
      });
      setRenderPreviewResult(result);
      if (result.valid) {
        message.success('渲染预览通过');
      } else {
        message.warning('渲染预览存在错误');
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '渲染预览失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleRepairValidationReport = async (validationEvent: SkillFactoryCodingEvent) => {
    if (!selectedSkill) return;
    if (!canUseCodingChat) {
      message.warning('当前变更已封板，请先新建变更后再修复');
      return;
    }
    if (isCodingStreamLocked) {
      message.warning('当前 AICoding 流式输出未结束');
      return;
    }
    const report = validationReportOf(validationEvent);
    const validationReportId = textOf(report.reportId || report.taskId);
    const messageText = [
      '请根据运行验证报告修复当前 Skill，只生成 patch 草稿，不直接写文件。',
      validationReportId
        ? `优先使用后端缓存的 validationReportId=${validationReportId} 对应报告。`
        : '如果没有后端 reportId，请谨慎使用请求里携带的 validationReport 作为上下文。',
      '修复时只允许通过 propose_patch 生成变更草稿，等待用户确认后才能落盘。',
    ].join('\n');
    setActionLoading(SkillFactoryMethod.CODING_VALIDATION_REPAIR);
    try {
      await skillAuthoringChat.send(messageText, {
        displayText: '让主 Agent 修复运行验证问题',
        requestOverrides: {
          validationReport: report,
          validationReportId,
        },
      });
    } finally {
      setActionLoading('');
    }
  };

  const injectPrompt = (prompt: string) => {
    const text = prompt.trim();
    if (!text) return;
    skillAuthoringChat.setInput((prev) => (prev.trim() ? `${prev.trim()}\n\n${text}` : text));
  };

  const appendToAuthoringChat = (prompt: string) => {
    injectPrompt(prompt);
    setSkillAuthoringRailOpen(true);
    setSkillAuthoringRailView('chat');
  };

  const handleFillCapabilityContext = async (capability: SkillFactoryCapabilityBinding) => {
    if (!selectedSkill) return;
    const revision = Number(capability.revision || 0);
    if (!capability.draftId || revision <= 0) {
      message.error('当前能力绑定缺少有效的草稿版本，无法生成对话上下文');
      return;
    }
    const loadingKey = `capability:${capability.draftId}:${revision}`;
    setContextFillLoadingKey(loadingKey);
    try {
      const context = await skillFactoryApi.capabilitySkillCreatorContext(
        selectedSkill.workspaceId || selectedSkill.skillCode,
        capability.draftId,
        revision,
      );
      appendToAuthoringChat(
        [
          '请基于以下已绑定业务能力完善当前 Skill 的 SKILL.md 和业务编排：',
          '<bound_business_capabilities>',
          JSON.stringify(context, null, 2),
          '</bound_business_capabilities>',
        ].join('\n'),
      );
      message.success('已填充到右侧对话框，请确认后发送');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取业务能力上下文失败');
    } finally {
      setContextFillLoadingKey('');
    }
  };

  const handleFillComponentContext = (
    asset: SkillFactoryReferenceAsset,
    componentAvailable = true,
  ) => {
    if (!componentAvailable) {
      message.warning('组件已禁用或不可用，仅可解除绑定');
      return;
    }
    const integrationPrompt = String(asset.integrationPrompt || '').trim();
    if (!integrationPrompt) {
      message.warning('当前组件尚未配置 Skill 使用提示词');
      return;
    }
    appendToAuthoringChat(
      ['<bound_component_reference>', integrationPrompt, '</bound_component_reference>'].join('\n'),
    );
    message.success('已填充到右侧对话框，请确认后发送');
  };

  const handleQuickPrompt = (item: SkillFactoryQuickPrompt) => {
    injectPrompt(item.prompt);
  };

  const replaceSkillBindings = async (
    nextCapabilityBindings: SkillFactoryCapabilityBinding[],
    nextComponentBindings: SkillFactoryComponentBinding[],
    successText: string,
  ) => {
    if (!selectedSkill) return;
    if (!canCurrentUserEditSkill) {
      message.warning(skillAccess.readonlyReason || '当前用户不是负责人，不能修改绑定');
      return;
    }
    setActionLoading(SkillFactoryMethod.SKILL_BINDINGS_REPLACE);
    try {
      const saved = await skillFactoryApi.replaceBindings(
        selectedSkill.workspaceId,
        selectedSkill.skillCode,
        Number(selectedSkill.version),
        nextCapabilityBindings,
        nextComponentBindings,
      );
      setSelectedSkill((previous) =>
        previous
          ? {
              ...previous,
              version: saved.version || previous.version,
              capabilityBindings: saved.capabilityBindings || [],
              componentBindings: saved.componentBindings || [],
              referenceCapabilities: saved.referenceCapabilities || [],
              referenceCapabilityDraftIds: saved.referenceCapabilityDraftIds || [],
              referenceRenderAssets: saved.referenceRenderAssets || [],
              referenceComponentCodes: saved.referenceComponentCodes || '',
            }
          : previous,
      );
      setReferenceComponentCodes(saved.referenceComponentCodes || '');
      message.success(successText);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Skill 绑定状态保存失败';
      message.error(errorMessage);
      if (
        errorMessage.includes('版本冲突') ||
        errorMessage?.toLowerCase()?.includes?.('skill version')
      ) {
        await loadDetail(selectedSkill.skillCode);
      }
    } finally {
      setActionLoading('');
    }
  };

  const handleCapabilityBind = async (
    capability: CapabilityActionDraft,
    bindMode: SkillFactoryCapabilityBindMode,
  ) => {
    const capabilityCode = capabilityActionCodeOf(capability);
    if (!capabilityCode) {
      message.error('当前业务能力缺少 actionCode，无法绑定');
      return;
    }
    const nextBinding: SkillFactoryCapabilityBinding = {
      draftId: capability.draftId,
      revision: capability.revision,
      published: capability.published,
      publishedVersion: capability.publishedVersion,
      capabilityCode,
      actionCode: capabilityCode,
      bindMode,
    };
    const existingIndex = capabilityBindings.findIndex(
      (item) => item.draftId === capability.draftId,
    );
    const nextBindings = [...capabilityBindings];
    if (existingIndex >= 0) {
      nextBindings.splice(existingIndex, 1, nextBinding);
    } else {
      nextBindings.push(nextBinding);
    }
    await replaceSkillBindings(
      nextBindings,
      componentBindings,
      bindMode === CAPABILITY_BIND_EXECUTION_AND_RENDER
        ? '业务能力已绑定到 Skill，并启用能力自身渲染配置'
        : '业务能力已绑定到 Skill，不启用渲染',
    );
  };

  const handleCapabilityUnbind = async (capability: CapabilityActionDraft) => {
    await replaceSkillBindings(
      capabilityBindings.filter((item) => item.draftId !== capability.draftId),
      componentBindings,
      '已解除业务能力绑定',
    );
  };

  const handleComponentBindingToggle = async (asset: SkillFactoryReferenceAsset) => {
    if (!canCurrentUserEditSkill) {
      message.warning(skillAccess.readonlyReason || '当前用户不是负责人，不能修改绑定');
      return;
    }
    if (!currentDraftEditable) {
      message.warning('当前 Skill 没有可编辑变更，请先新建变更');
      return;
    }
    const assetId = Number(asset.assetId || 0);
    const componentCode = referenceAssetKey(asset);
    const active = componentBindings.some((item) =>
      assetId > 0
        ? Number(item.assetId || 0) === assetId
        : Boolean(componentCode) && referenceAssetKey(item) === componentCode,
    );
    if (!active && (!assetId || !componentCode)) {
      message.error('当前组件不是组件中心已注册资产，无法绑定');
      return;
    }
    const nextBinding = { ...asset, assetId, componentCode };
    delete nextBinding.releaseEnvironmentFacts;
    const nextBindings = active
      ? componentBindings.filter((item) =>
          assetId > 0
            ? Number(item.assetId || 0) !== assetId
            : referenceAssetKey(item) !== componentCode,
        )
      : [...componentBindings, nextBinding];
    await replaceSkillBindings(
      capabilityBindings,
      nextBindings,
      active ? '已解除组件绑定' : '组件已绑定到当前 Skill',
    );
  };

  const handleOpenCapabilityCenter = (draftId?: string) => {
    if (typeof window !== 'undefined') {
      window.open(buildCapabilityCenterRoute(draftId), '_blank');
    }
  };

  const handleOpenComponentCenter = () => {
    const url =
      resolvedPageConfig.links?.componentCenterUrl || '/management/components';
    if (typeof window !== 'undefined') {
      window.open(url, '_blank');
    }
  };

  const handleOpenComponentDetail = (assetId?: number) => {
    if (!assetId || typeof window === 'undefined') return;
    const searchParams = new URLSearchParams(window.location.search);
    searchParams.delete('skillCode');
    searchParams.delete('tab');
    searchParams.set('id', String(assetId));
    window.open(`/management/components/detail?${searchParams.toString()}`, '_blank');
  };

  const openSkillInfoDrawer = (mode: SkillInfoMode, skill?: SkillDraft | null) => {
    const selectedSpecialistIds = skillSpecialistIds(skill, specialists);
    setSkillInfoMode(mode);
    skillInfoForm.setFieldsValue({
      skillCode: skill?.skillCode || '',
      skillNameCn: skill?.skillNameCn || '',
      skillDescription: skill?.skillDescription || '',
      businessDomain: skill?.businessDomain || undefined,
      capabilityDomain: skill?.capabilityDomain || undefined,
      specialistIds:
        selectedSpecialistIds.length > 0
          ? selectedSpecialistIds
          : [specialists?.[0]?.id].filter(Boolean),
      owner: skill?.owner || currentUserName,
      version: normalizeVersionText(skill?.versionLabel),
    });
    setSkillInfoDrawerOpen(true);
  };

  const handleEditSkillInfo = () => {
    if (!selectedSkill) {
      message.warning('请先选择一个 Skill');
      return;
    }
    if (!currentDraftEditable) {
      message.warning('当前 Skill 没有可编辑变更，请先新建变更');
      return;
    }
    if (!canCurrentUserEditSkill) {
      message.warning('只有负责人可以编辑 Skill 基本信息');
      return;
    }
    openSkillInfoDrawer('edit', selectedSkill);
  };

  const handleCreateNewSkill = () => {
    openSkillInfoDrawer('create');
  };

  const handleSaveSkillInfo = async () => {
    const values = (await skillInfoForm.validateFields()) as SkillInfoFormValues;
    if (skillInfoMode === 'edit' && !canCurrentUserEditSkill) {
      message.error('只有负责人可以编辑 Skill 基本信息');
      return;
    }
    if (skillInfoMode === 'edit' && !currentDraftEditable) {
      message.error('当前 Skill 没有可编辑变更，请先新建变更');
      return;
    }
    const actionMethod =
      skillInfoMode === 'create'
        ? SkillFactoryMethod.WORKSPACE_CREATE
        : SkillFactoryMethod.SKILL_UPDATE;
    setActionLoading(actionMethod);
    try {
      let saved: SkillDraft;
      const selectedSpecialists = specialists.filter((item) =>
        (values.specialistIds || []).includes(specialistOptionId(item)),
      );
      const specialistIds = selectedSpecialists
        ?.map((item) => specialistOptionId(item))
        ?.join?.(',');
      const specialistNames = selectedSpecialists
        ?.map((item) => specialistOptionName(item))
        ?.join?.(',');
      if (skillInfoMode === 'create') {
        const payload: SkillInfoPayload = {
          skillCode: values.skillCode?.trim?.(),
          skillNameCn: values.skillNameCn?.trim?.(),
          skillNameEn: values.skillCode?.trim?.(),
          skillDescription: values.skillDescription?.trim?.(),
          businessDomain: values.businessDomain,
          capabilityDomain: values.capabilityDomain,
          specialistId: specialistIds,
          specialistName: specialistNames,
          specialistIds,
          specialistNames,
          owner: values.owner?.trim?.(),
          ownersJson: jsonStringify(splitCsv(values.owner)) || '[]',
          version: normalizeVersionText(values.version),
        };
        saved = await skillFactoryApi.saveSkillInfo(payload);
      } else {
        saved = await skillFactoryApi.updateSkillInfo({
          skillCode: selectedSkill?.skillCode || values.skillCode?.trim?.(),
          skillNameCn: values.skillNameCn?.trim?.(),
          skillDescription: values.skillDescription?.trim?.(),
          businessDomain: values.businessDomain,
          capabilityDomain: values.capabilityDomain,
          specialistId: specialistIds,
          specialistIds,
        });
      }
      message.success(skillInfoMode === 'create' ? 'Skill 基本信息已注册' : 'Skill 基本信息已保存');
      setSkillInfoDrawerOpen(false);
      setSelectedSkillCode(saved.skillCode);
      setActiveTab('overview');
      navigate(buildSkillFactoryRoute(saved.skillCode, 'overview'));
      await loadList(keyword, saved.skillCode);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存 Skill 基本信息失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleCancelFileEdit = () => {
    setEditorContent(fileContent?.content || '');
    setIsFileEditing(false);
  };





  const handleWorkspaceZipDownload = async () => {
    if (!selectedSkill) {
      message.warning('请先选择一个 Skill');
      return;
    }
    if (
      workspaceViewMode === WORKSPACE_VIEW_ONLINE_RELEASE &&
      !currentWorkspaceViewParams.version
    ) {
      message.warning('请先选择一个正式版本');
      return;
    }
    setActionLoading(ZIP_EXPORT_ACTION_KEY);
    try {
      const result = await skillFactoryApi.exportWorkspaceZip(
        selectedSkill.workspaceId || selectedSkill.skillCode,
        currentWorkspaceViewParams,
      );
      const fileName = resolveWorkspaceZipFileName(selectedSkill.skillCode, result.zipFileName);
      const zipBytes = decodeWorkspaceZipBase64(result.zipBase64);
      triggerWorkspaceZipDownload(fileName, zipBytes);
      message.success(`${fileName} 已开始下载`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'ZIP 下载失败');
    } finally {
      setActionLoading('');
    }
  };

  const handleOpenTracePage = () => {
    openBindingTracePage();
  };

  const renderOverview = () => (
    <div className="skill-factory-section-grid">
      <Card
        title="Skill 信息"
        extra={
          <Button
            icon={<EditOutlined />}
            disabled={Boolean(skillInfoEditDisabledReason)}
            title={skillInfoEditDisabledReason || '编辑 Skill 基础信息'}
            onClick={handleEditSkillInfo}
          >
            编辑
          </Button>
        }
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="Skill 名称">
            {selectedSkill?.skillNameCn || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="Skill 英文名">
            {selectedSkill?.skillNameEn || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="Skill 描述" span={2}>
            {selectedSkill?.skillDescription || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="业务场域">
            {domainDisplayText(businessDomains, selectedSkill?.businessDomain)}
          </Descriptions.Item>
          <Descriptions.Item label="能力域">
            {domainDisplayText(capabilityDomains, selectedSkill?.capabilityDomain)}
          </Descriptions.Item>
          <Descriptions.Item label="所属专员">
            {selectedSkill?.specialistName || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="版本">{selectedSkill?.versionLabel || '-'}</Descriptions.Item>
          <Descriptions.Item label="创建人">{selectedSkill?.creator || '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {formatTime(selectedSkill?.createTime)}
          </Descriptions.Item>
          <Descriptions.Item label="修改人">{selectedSkill?.modifier || '-'}</Descriptions.Item>
          <Descriptions.Item label="修改时间">
            {formatTime(selectedSkill?.updateTime)}
          </Descriptions.Item>
          <Descriptions.Item label="workspaceId" span={2}>
            <Text code>{selectedSkill?.workspaceId || '-'}</Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="当前状态">
        <div className="skill-factory-status-list">
          <div className="skill-factory-status-action skill-factory-status-action-primary">
            <div className="skill-factory-status-action-copy">
              <strong>新建变更</strong>
              <span>从一个正式包版本复制到 PRT 编辑态后继续修改。</span>
            </div>
            {renderCreateChangeControl()}
          </div>
          <div>
            <Text type="secondary">注册状态</Text>
            <strong>{skillStatusLabel(selectedSkill?.registerStatus)}</strong>
          </div>
          <div>
            <Text type="secondary">变更状态</Text>
            <strong>
              {skillStatusLabel(currentDraftStatus)}
              {currentSealedVersion ? ` / ${currentSealedVersion}` : ''}
            </strong>
          </div>
          <div>
            <Text type="secondary">当前文件版本</Text>
            <strong>{selectedSkill?.fileTreeDigest || workspaceTree?.fileTreeDigest || '-'}</strong>
          </div>
          <div>
            <Text type="secondary">PRT 包版本</Text>
            <strong>{selectedSkill?.preprodVersionId || '-'}</strong>
          </div>
          <div>
            <Text type="secondary">正式包版本</Text>
            <strong>{releaseVersionList.length ? releaseVersionList.join(', ') : '-'}</strong>
          </div>
        </div>
      </Card>
    </div>
  );

  const renderCapabilityList = () => (
    <div className="skill-factory-section-grid skill-factory-capability-layout">
      <Card
        title="业务能力列表"
        extra={
          <Space className="skill-factory-component-toolbar">
            <Input
              allowClear
              className="skill-factory-component-search"
              placeholder="搜索能力名称 / actionCode / 草稿 ID"
              prefix={<SearchOutlined />}
              value={capabilityKeyword}
              onChange={(event) => setCapabilityKeyword(event.target.value)}
              onPressEnter={() => loadCapabilityDrafts(capabilityKeyword)}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => loadCapabilityDrafts()}>
              搜索
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => handleOpenCapabilityCenter()}>
              注册能力
            </Button>
          </Space>
        }
      >
        <div className="skill-factory-component-reference-note">
          这里展示业务能力中心维护的 CapabilityAction。绑定后会保存到当前 Skill 草稿，
          供手动编写 Skill 时引用；发布前请确认绑定能力与 Skill 内容一致。
        </div>
        <Spin spinning={capabilityLoading}>
          <div className="skill-factory-capability-grid">
            {capabilityDrafts.length ? (
              capabilityDrafts.map((capability) => {
                const binding = capabilityBindings.find(
                  (item) => item.draftId === capability.draftId,
                );
                const active = Boolean(binding);
                const basicInfo = capability.draft?.basicInfo || {};
                const apiSource = capability.draft?.apiSource || {};
                const governance = capability.draft?.governance || {};
                const inputCount = capability.draft?.modelContract?.inputFields?.length || 0;
                const presentationCount =
                  capability.draft?.resultContract?.presentationComponents?.length || 0;
                const capabilityBindable =
                  capability.releaseEnvironmentFacts?.effectivePreprod?.available === true;
                return (
                  <div
                    className={`skill-factory-capability-card${active ? ' active' : ''}`}
                    key={capability.draftId}
                  >
                    <div className="skill-factory-reference-asset-head">
                      <div>
                        <strong>{capabilityNameOf(capability)}</strong>
                        <span>{capabilityActionCodeOf(capability) || capability.draftId}</span>
                      </div>
                      <Tag color={active ? 'success' : capabilityStatusColor(capability)}>
                        {active
                          ? '已绑定'
                          : capabilityStatusText(capability.validationStatus || capability.status)}
                      </Tag>
                    </div>
                    <p>{basicInfo.description || '等待补充业务目标和模型调用边界。'}</p>
                    <div className="skill-factory-capability-meta">
                      <span>
                        业务域：{capability.businessDomainName || capability.businessDomain || '-'}
                      </span>
                      <span>来源：{capabilitySourceText(apiSource.sourceType)}</span>
                      <span>副作用：{capabilitySideEffectText(governance.sideEffectLevel)}</span>
                      <span>模型入参：{inputCount} 个</span>
                      <span>展示方案：{presentationCount} 个</span>
                      <span>正式版本：{capability.publishedVersion}</span>
                    </div>
                    <AssetEnvironmentFacts facts={capability.releaseEnvironmentFacts} />
                    <div className="skill-factory-reference-asset-actions">
                      <Button
                        size="small"
                        type={
                          binding?.bindMode === CAPABILITY_BIND_EXECUTION_ONLY
                            ? 'primary'
                            : undefined
                        }
                        disabled={
                          !canCurrentUserEditSkill || !currentDraftEditable || !capabilityBindable
                        }
                        title={
                          canCurrentUserEditSkill
                            ? '绑定到 Skill，不启用渲染'
                            : skillAccess.readonlyReason
                        }
                        loading={actionLoading === SkillFactoryMethod.SKILL_BINDINGS_REPLACE}
                        onClick={() =>
                          handleCapabilityBind(capability, CAPABILITY_BIND_EXECUTION_ONLY)
                        }
                      >
                        绑定到 Skill-不渲染
                      </Button>
                      <Button
                        size="small"
                        type={
                          binding?.bindMode === CAPABILITY_BIND_EXECUTION_AND_RENDER
                            ? 'primary'
                            : undefined
                        }
                        loading={actionLoading === SkillFactoryMethod.SKILL_BINDINGS_REPLACE}
                        disabled={
                          !canCurrentUserEditSkill ||
                          !currentDraftEditable ||
                          !capabilityBindable ||
                          presentationCount === 0
                        }
                        title={
                          !canCurrentUserEditSkill
                            ? skillAccess.readonlyReason
                            : presentationCount
                            ? '启用能力自身的展示方案'
                            : '该能力尚未配置包装组件'
                        }
                        onClick={() =>
                          handleCapabilityBind(capability, CAPABILITY_BIND_EXECUTION_AND_RENDER)
                        }
                      >
                        绑定到 Skill-渲染
                      </Button>
                      {active ? (
                        <Button
                          size="small"
                          disabled={!canCurrentUserEditSkill || !currentDraftEditable}
                          title={canCurrentUserEditSkill ? '取消绑定' : skillAccess.readonlyReason}
                          loading={actionLoading === SkillFactoryMethod.SKILL_BINDINGS_REPLACE}
                          onClick={() => handleCapabilityUnbind(capability)}
                        >
                          取消绑定
                        </Button>
                      ) : null}
                      <Button
                        size="small"
                        onClick={() => handleOpenCapabilityCenter(capability.draftId)}
                      >
                        查看详情
                      </Button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="skill-factory-reference-asset-empty">
                <div className="skill-factory-chat-empty small">没有匹配的业务能力</div>
              </div>
            )}
          </div>
        </Spin>
      </Card>
      <Card
        title="当前 Skill 已绑定能力"
        extra={
          <Tag color={referenceCapabilityDraftIds.length ? 'blue' : undefined}>
            {referenceCapabilityDraftIds.length} 个
          </Tag>
        }
      >
        <div className="skill-factory-bound-reference-list">
          {capabilityBindings.length ? (
            capabilityBindings.map((capability) => {
              const revision = Number(capability.revision || 0);
              const loadingKey = `capability:${capability.draftId}:${revision}`;
              return (
                <div className="skill-factory-bound-reference-item" key={capability.draftId}>
                  <div className="skill-factory-bound-reference-summary">
                    <Tag color="success">
                      {capability.bindMode === CAPABILITY_BIND_EXECUTION_AND_RENDER
                        ? '执行并渲染'
                        : '仅执行'}
                    </Tag>
                    <strong>
                      {capability.nameCn || capability.capabilityCode || capability.draftId}
                    </strong>
                  </div>
                  <AssetEnvironmentFacts facts={capability.releaseEnvironmentFacts} />

                </div>
              );
            })
          ) : (
            <div className="skill-factory-chat-empty small">暂未绑定业务能力</div>
          )}
        </div>
      </Card>
    </div>
  );

  const renderComponentList = () => (
    <div className="skill-factory-section-grid">
      <Card
        title="组件列表"
        extra={
          <Space className="skill-factory-component-toolbar">
            <Input
              allowClear
              className="skill-factory-component-search"
              placeholder="搜索组件名称 / code"
              prefix={<SearchOutlined />}
              value={componentNameKeyword}
              onChange={(event) => setComponentNameKeyword(event.target.value)}
            />
            <Button icon={<PlusOutlined />} onClick={handleOpenComponentCenter}>
              创建组件
            </Button>
          </Space>
        }
      >
        <div className="skill-factory-component-reference-note">
          这里展示组件中心维护的平台资产。绑定关系保存到当前 Skill。
          已禁用组件仍保留展示且只能显式解除；绑定操作不会修改 SKILL.md、examples 或 workspace 文件。
        </div>
        <div className="skill-factory-reference-asset-grid">
          {filteredReferenceRenderAssets.length ? (
            filteredReferenceRenderAssets.map((asset) => {
              const code = referenceAssetKey(asset);
              const active = componentBindings.some(
                (item) =>
                  (asset.assetId && item.assetId === asset.assetId) || item.componentCode === code,
              );
              const canBind =
                canCurrentUserEditSkill &&
                currentDraftEditable &&
                Number(asset.assetId || 0) > 0 &&
                asset.enabled !== false &&
                asset.releaseEnvironmentFacts?.effectivePreprod?.available === true;
              return (
                <div
                  className={`skill-factory-reference-asset-card${active ? ' active' : ''}`}
                  key={code}
                >
                  <div className="skill-factory-reference-asset-head">
                    <div>
                      <strong>{asset.name}</strong>
                      <span>{code}</span>
                    </div>
                    <Tag color={active ? 'success' : canBind ? 'blue' : undefined}>
                      {active ? '已绑定' : canBind ? '可绑定' : '暂不可绑定'}
                    </Tag>
                  </div>
                  <div className="skill-factory-reference-asset-tags">
                    <Tag>{assetTypeText(asset.assetType)}</Tag>
                    <Tag>{asset.renderProtocol || '-'}</Tag>
                    {asset.lifecycleStatus ? (
                      <Tag color="success">{asset.lifecycleStatus}</Tag>
                    ) : null}
                  </div>
                  <div className="skill-factory-reference-asset-meta">
                    <span>场景：{asset.scene || '-'}</span>
                    <span>负责人：{asset.owner || '-'}</span>
                    <span>最近状态：{asset.enabled === false ? '不可用' : '可用'}</span>
                    <span>正式版本：{asset.publishedVersion}</span>
                  </div>
                  <AssetEnvironmentFacts facts={asset.releaseEnvironmentFacts} />
                  {renderReferenceAssetPreview(asset)}
                  <p>{referenceAssetPrompt(asset) || '暂无接入提示词'}</p>
                  <div className="skill-factory-reference-asset-actions">
                    <Button
                      size="small"
                      type={active ? undefined : 'primary'}
                      disabled={!canBind}
                      loading={actionLoading === SkillFactoryMethod.SKILL_BINDINGS_REPLACE}
                      onClick={() => handleComponentBindingToggle(asset)}
                    >
                      {active ? '取消绑定' : '绑定到 Skill'}
                    </Button>
                    <Button
                      size="small"
                      disabled={Number(asset.assetId || 0) <= 0}
                      onClick={() => handleOpenComponentDetail(asset.assetId)}
                    >
                      查看详情
                    </Button>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="skill-factory-reference-asset-empty">
              <div className="skill-factory-chat-empty small">没有匹配的组件</div>
            </div>
          )}
        </div>
      </Card>
      <Card
        title="当前 Skill 已绑定组件"
        extra={
          <Tag color={activeReferenceRenderAssets.length ? 'blue' : undefined}>
            {activeReferenceRenderAssets.length} 个
          </Tag>
        }
      >
        <div className="skill-factory-bound-reference-list">
          {activeReferenceRenderAssets.length ? (
            activeReferenceRenderAssets.map((asset) => {
              const assetId = Number(asset.assetId || 0);
              const registryStateResolved =
                assetId > 0 &&
                Object.prototype.hasOwnProperty.call(boundComponentRegistryAssets, assetId);
              const registryAsset = registryStateResolved
                ? boundComponentRegistryAssets[assetId]
                : undefined;
              const componentAvailable = Boolean(
                registryAsset &&
                  registryAsset.enabled !== false &&
                  asset.releaseEnvironmentFacts?.effectivePreprod?.available === true,
              );
              const availabilityText = !registryStateResolved
                ? '核对中'
                : registryAsset?.enabled === false
                ? '已禁用'
                : componentAvailable
                ? '可用'
                : '不可用';
              const availabilityColor = componentAvailable
                ? 'success'
                : availabilityText === '核对中'
                ? undefined
                : 'warning';
              const componentCode =
                asset.componentName || asset.componentCode || referenceAssetKey(asset) || '-';
              const displayName = asset.componentNameCn || asset.name || componentCode;
              const hasIntegrationPrompt = Boolean(String(asset.integrationPrompt || '').trim());
              const fillDisabledReason = !componentAvailable
                ? availabilityText === '已禁用'
                  ? '组件已禁用，仅可解除绑定'
                  : availabilityText === '核对中'
                  ? '正在核对组件当前状态'
                  : '组件当前不可用，仅可解除绑定'
                : !hasIntegrationPrompt
                ? '该组件尚未配置 Skill 使用提示词'
                : undefined;
              const canUnbind = canCurrentUserEditSkill && currentDraftEditable;
              const unbindDisabledReason = !canCurrentUserEditSkill
                ? skillAccess.readonlyReason || '当前用户不是负责人，仅可查看'
                : !currentDraftEditable
                ? '当前 Skill 没有可编辑变更，请先新建变更'
                : undefined;
              return (
                <div
                  className="skill-factory-bound-reference-item"
                  key={`${assetId || 'component'}-${componentCode}`}
                >
                  <div className="skill-factory-bound-reference-content">
                    <div className="skill-factory-bound-reference-summary">
                      <strong>{displayName}</strong>
                      <Tag color={availabilityColor}>{availabilityText}</Tag>
                    </div>
                    <div className="skill-factory-bound-reference-code">{componentCode}</div>
                    <div className="skill-factory-bound-reference-meta">
                      <span>assetId: {assetId || '-'}</span>
                      <Tag>{assetTypeText(asset.assetType)}</Tag>
                      <Tag>{asset.renderProtocol || asset.dslType || '-'}</Tag>
                      {asset.interactionMode ? (
                        <Tag>{asset.interactionMode === 'INTERACTIVE' ? '需交互' : '纯展示'}</Tag>
                      ) : null}
                    </div>
                    <AssetEnvironmentFacts facts={asset.releaseEnvironmentFacts} />
                  </div>
                  <div className="skill-factory-bound-reference-actions">

                    <Button
                      size="small"
                      icon={<DeleteOutlined />}
                      disabled={!canUnbind}
                      loading={actionLoading === SkillFactoryMethod.SKILL_BINDINGS_REPLACE}
                      title={unbindDisabledReason}
                      onClick={() => handleComponentBindingToggle(asset)}
                    >
                      解除绑定
                    </Button>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="skill-factory-chat-empty small">当前 Skill 暂未绑定组件</div>
          )}
        </div>
      </Card>
      <Card title="render_component Tool 入参预览">
        <Space direction="vertical" style={{ width: '100%' }}>
          <TextArea
            value={renderPreviewInput}
            onChange={(event) => setRenderPreviewInput(event.target.value)}
            placeholder='{"dslType":"CARD_CONTAINER","componentName":"StoreDiagnostic","params":{...}}'
            autoSize={{ minRows: 8, maxRows: 16 }}
          />
          <Button
            type="primary"
            loading={actionLoading === SkillFactoryMethod.COMPONENT_RENDER_PREVIEW}
            onClick={handleRenderStringPreview}
          >
            预览
          </Button>
          {renderPreviewResult ? (
            <div className="skill-factory-debug-block final">
              <Space wrap>
                <Tag color={renderPreviewResult.valid ? 'success' : 'error'}>
                  {renderPreviewResult.valid ? 'READY' : 'ERROR'}
                </Tag>
                <Tag>{renderPreviewResult.renderProtocol || '-'}</Tag>
                {renderPreviewResult.agentUiDsl ? (
                  <Tag>{renderPreviewResult.agentUiDsl}</Tag>
                ) : null}
              </Space>
              {renderPreviewResult.errors?.map?.((item) => (
                <p key={item}>{item}</p>
              ))}
              {renderPreviewResult.messages?.length ? (
                <pre>{formatJson(renderPreviewResult.messages)}</pre>
              ) : null}
              {renderPreviewResult.data ? <pre>{formatJson(renderPreviewResult.data)}</pre> : null}
            </div>
          ) : null}
        </Space>
      </Card>
    </div>
  );

  const renderPatchSummary = (event: SkillFactoryCodingEvent) => {
    const changedFiles = patchChangedFiles(event);
    const status = patchReviewStatus(event);
    const conflictFiles = patchConflictFiles(event);
    if (!status) return null;
    const patchKey = patchEventKey(event, event.timestamp || event.eventId || 'patch');
    return (
      <button
        className="skill-factory-change-summary"
        key={patchKey}
        onClick={() => {
          setSelectedSkillPatchKey(patchKey);
          setSkillAuthoringRailOpen(true);
          setSkillAuthoringRailView('review');
        }}
        type="button"
      >
        <span className="skill-factory-change-summary-main">
          <Tag color="warning">PATCH</Tag>
          <strong>
            {status === 'CONFLICTED' && conflictFiles.length
              ? `${conflictFiles.length} 个文件存在冲突`
              : patchDisplayName(event)}
          </strong>
          <Text className="skill-factory-change-summary-meta" type="secondary">
            {changedFiles.length ? `${changedFiles.length} 个文件 · ` : ''}
            {formatTime(event.timestamp)}
          </Text>
        </span>
        <Tag className="skill-factory-change-summary-status" color={patchReviewStatusColor(status)}>
          {patchReviewStatusText(status)}
        </Tag>
      </button>
    );
  };

  const renderSkillPatchReview = () => {
    if (!selectedSkillPatch) return undefined;
    const { key, event } = selectedSkillPatch;
    const changedFiles = patchChangedFiles(event);
    const changedFilePaths = changedFiles
      ?.map((file) => String(file.path || ''))
      ?.filter?.(Boolean);
    const hasExplicitSelection = Object.prototype.hasOwnProperty.call(selectedSkillPatchFiles, key);
    const selectedFilePaths = hasExplicitSelection
      ? selectedSkillPatchFiles[key]
      : changedFilePaths;
    const selectedFilePathSet = new Set(selectedFilePaths);
    const updateSelectedFiles = (next: string[]) => {
      setSelectedSkillPatchFiles((current) => ({
        ...current,
        [key]: next,
      }));
    };
    const riskItems = (event.content?.riskItems || []) as unknown[];
    const conflictFiles = patchConflictFiles(event);
    const conflictFileSet = new Set(conflictFiles);
    const status = patchReviewStatus(event);
    if (!status) return undefined;
    const isPendingPatch =
      status === 'PENDING' && isActionablePatchProposal(event);
    const allowApply = isPendingPatch;
    const allowDiscard = isPendingPatch;
    const observationSummary = textOf(event.observation?.summary);
    const actionKey = actionLoading.endsWith(String(event.patchId)) ? actionLoading : '';
    return (
      <div className="skill-factory-patch-review">
        {skillPatchChangeSets.length > 1 ? (
          <Select
            className="skill-factory-patch-selector"
            value={key}
            onChange={(value) => setSelectedSkillPatchKey(String(value || ''))}
            options={skillPatchChangeSets.map((item) => ({
              label: `${patchDisplayName(item.event)} · ${formatTime(
                item.event?.timestamp,
              )} · ${patchReviewStatusText(patchReviewStatus(item.event))}`,
              value: item.key,
            }))}
          />
        ) : null}
        <AuthoringChangeReviewFrame
          title={patchDisplayName(event)}
          summary={
            status === 'CONFLICTED'
              ? event.errorMsg ||
                textOf(event.content?.errorMsg) ||
                '选中文件无法安全自动合并，本次未写入任何文件。'
              : `共 ${changedFiles.length} 个文件，已选择 ${selectedFilePaths.length} 个`
          }
          metadata={
            <div className="skill-factory-patch-meta">
              <span>
                <Text type="secondary">当前状态</Text>
                <Tag color={patchReviewStatusColor(status)}>{patchReviewStatusText(status)}</Tag>
              </span>

            </div>
          }
          adapter={{
            targetLabel: `Skill 工作区 ${
              selectedSkill?.workspaceId || selectedSkill?.skillCode || '-'
            }`,
            applyLabel: `应用选中（${selectedFilePaths.length}）`,
            appliedLabel: '已应用到工作区',
            applyDescription: '只应用已勾选文件；未选文件保持原状，本 Patch 随后结束审阅。',
            status,
            applying: actionKey === `confirm:${event.patchId}`,
            discarding: actionKey === `discard:${event.patchId}`,
            applyDisabled:
              !allowApply ||
              !selectedFilePaths.length ||
              !canUseCodingChat ||
              readonlyWorkspace ||
              (isCodingStreamLocked && actionKey !== `confirm:${event.patchId}`),
            discardDisabled:
              !allowDiscard ||
              !canUseCodingChat ||
              readonlyWorkspace ||
              (isCodingStreamLocked && actionKey !== `discard:${event.patchId}`),
            onApply: () => handlePatchAction('confirm', event, selectedFilePaths),
            onDiscard: () => handlePatchAction('discard', event),
            discardLabel: '丢弃全部',
          }}
          footerNote={
            observationSummary ? (
              <div className="skill-factory-observation-note">
                <Text type="secondary">Observation</Text>
                <span>{observationSummary}</span>
              </div>
            ) : undefined
          }
        >
          <div className="skill-factory-patch-review-list">
            {status === 'CONFLICTED' && conflictFiles.length ? (
              <div className="skill-factory-patch-conflict-summary">
                <strong>需要重新处理的文件</strong>
                <div>
                  {conflictFiles.map((filePath) => (
                    <Tag color="error" key={filePath}>
                      {filePath}
                    </Tag>
                  ))}
                </div>
              </div>
            ) : null}
            {isPendingPatch && changedFiles.length ? (
              <label className="skill-factory-patch-select-all">
                <input
                  aria-label="选择全部文件"
                  checked={
                    changedFilePaths.length > 0 &&
                    selectedFilePaths.length === changedFilePaths.length
                  }
                  onChange={(changeEvent) =>
                    updateSelectedFiles(changeEvent.target?.checked ? changedFilePaths : [])
                  }
                  type="checkbox"
                />
                <span>选择全部文件</span>
                <Text type="secondary">
                  {selectedFilePaths.length} / {changedFiles.length}
                </Text>
              </label>
            ) : null}
            {changedFiles.map((file, index) => {
              const filePath = String(file.path || '');
              const changeType = String(file.changeType || 'MODIFY');
              return (
                <article
                  className={`skill-factory-patch-file-review${
                    selectedFilePathSet.has(filePath) ? ' selected' : ''
                  }${conflictFileSet.has(filePath) ? ' conflicted' : ''}`}
                  key={`${filePath || 'file'}-${index}`}
                >
                  <div className="skill-factory-patch-file-head">
                    {isPendingPatch ? (
                      <input
                        aria-label={`选择文件 ${filePath}`}
                        checked={selectedFilePathSet.has(filePath)}
                        onChange={(changeEvent) => {
                          const next = new Set(selectedFilePaths);
                          if (changeEvent.target?.checked) next.add(filePath);
                          else next.delete(filePath);
                          updateSelectedFiles(changedFilePaths.filter((path) => next.has(path)));
                        }}
                        type="checkbox"
                      />
                    ) : null}
                    <Tag>{changeType}</Tag>
                    <strong>{filePath || '-'}</strong>
                    {conflictFileSet.has(filePath) ? <Tag color="error">冲突</Tag> : null}
                  </div>
                  <PatchDiffPreview changeType={changeType} diff={String(file.diffPreview || '')} />
                </article>
              );
            })}
            {riskItems.length ? (
              <div className="skill-factory-patch-risk-list">
                {riskItems.map((item, index) => (
                  <Tag color="warning" key={`${String(item)}-${index}`}>
                    {String(item)}
                  </Tag>
                ))}
              </div>
            ) : null}
          </div>
        </AuthoringChangeReviewFrame>
      </div>
    );
  };

  const renderValidationReportCard = (event: SkillFactoryCodingEvent) => {
    const report = validationReportOf(event);
    const status = textOf(
      report.status || event.content?.status || (event.success ? 'PARTIAL' : 'FAILED'),
    );
    const protocol = recordOf(report.protocol) || {};
    const checks = recordArrayOf(report.checks);
    const issues = recordArrayOf(report.issues);
    const taskId = textOf(report.taskId || event.eventId);
    return (
      <div className="skill-factory-validation-card" key={taskId || event.eventId}>
        <div className="skill-factory-validation-head">
          <Space>
            <Tag color={runtimeStatusColor(status)}>运行验证</Tag>
            <strong>当前 Skill 动态验证</strong>
          </Space>
          <Text type="secondary">{formatTime(event.timestamp)}</Text>
        </div>
        <div className="skill-factory-validation-summary">
          <span>
            <Text type="secondary">状态</Text>
            <Tag color={runtimeStatusColor(status)}>{status || '-'}</Tag>
          </span>
          <span>
            <Text type="secondary">测试输入</Text>
            <Text>{textOf(report.testInput) || '-'}</Text>
          </span>
          <span>
            <Text type="secondary">协议识别</Text>
            <Text code>
              {textOf(protocol.type) || 'unknown'}
              {textOf(protocol.code) ? `:${textOf(protocol.code)}` : ''}
            </Text>
          </span>
        </div>
        <div className="skill-factory-validation-checks">
          {checks.map((item) => (
            <div className="skill-factory-validation-check" key={textOf(item.key || item.label)}>
              <Tag color={runtimeStatusColor(textOf(item.status))}>{textOf(item.status)}</Tag>
              <strong>{textOf(item.label || item.key)}</strong>
              <span>{textOf(item.message)}</span>
            </div>
          ))}
        </div>
        {issues.length ? (
          <div className="skill-factory-validation-issues">
            {issues.map((item, index) => (
              <div
                className="skill-factory-validation-issue"
                key={`${textOf(item.message)}-${index}`}
              >
                <Tag color={textOf(item.severity) === 'ERROR' ? 'error' : 'warning'}>
                  {textOf(item.severity || 'WARN')}
                </Tag>
                <span>{textOf(item.message)}</span>
                {textOf(item.repairHint) ? <small>{textOf(item.repairHint)}</small> : null}
              </div>
            ))}
          </div>
        ) : null}
        <details className="skill-factory-validation-raw">
          <summary>查看原始输出</summary>
          <pre>{textOf(report.rawOutput) || formatJson(report)}</pre>
        </details>
        <Space className="skill-factory-validation-actions">


        </Space>
      </div>
    );
  };

  const renderBusinessCard = (assistantMessage: AssistantMessageState, card: A2uiSurfaceState) => {
    const componentRefs = stringListOf(card.dataModel?.componentRefs);
    const cardKey = `${assistantMessage.messageId}-${card.surfaceId}`;
    const expanded = Boolean(expandedBusinessCardKeys[cardKey]);
    const skillCode = textOf(card.dataModel?.skillCode) || selectedSkill?.skillCode || '-';
    const workspaceId = textOf(card.dataModel?.workspaceId) || selectedSkill?.workspaceId || '-';
    const componentSummary = componentRefs.length
      ? componentRefs.join(', ')
      : referenceComponentCodes || '-';
    const actionStatusText = assistantMessage?.executionTrace
      ?.filter?.(isObservationEvent)
      ?.map?.((event) => textOf(event.observation?.summary || event.content?.summary))
      ?.filter?.(Boolean);
    return (
      <div
        className={`skill-factory-a2ui-card${expanded ? ' expanded' : ' compact'}`}
        key={card.surfaceId}
      >
        <button
          className="skill-factory-a2ui-summary"
          onClick={() =>
            setExpandedBusinessCardKeys((current) => ({
              ...current,
              [cardKey]: !expanded,
            }))
          }
          type="button"
        >
          <Tag color="magenta">业务确认</Tag>
          <strong>{card.title}</strong>
          <span>
            {skillCode} · 参考组件 {componentSummary}
          </span>
          {actionStatusText.length ? <Tag color="success">已记录</Tag> : null}
          <DownOutlined className={`skill-factory-a2ui-arrow${expanded ? ' open' : ''}`} />
        </button>
        {expanded ? (
          <div className="skill-factory-a2ui-detail">
            <div className="skill-factory-a2ui-data">
              <span>
                <Text type="secondary">skillCode</Text>
                <Text code>{skillCode}</Text>
              </span>
              <span>
                <Text type="secondary">workspaceId</Text>
                <Text code>{workspaceId}</Text>
              </span>
              <span>
                <Text type="secondary">参考组件</Text>
                <Text code>{componentSummary}</Text>
              </span>
            </div>
            {textOf(card.dataModel?.message) ? (
              <div className="skill-factory-a2ui-requirement">
                {textOf(card.dataModel?.message)}
              </div>
            ) : null}
            {actionStatusText.length ? (
              <div className="skill-factory-observation-note">
                <Text type="secondary">Observation</Text>
                <span>{actionStatusText[actionStatusText.length - 1]}</span>
              </div>
            ) : null}
            <Space className="skill-factory-a2ui-actions">
              {card.actions?.map?.((item) => {
                const idempotencyKey = `${item.actionCode}-${assistantMessage.messageId}-${card.surfaceId}`;
                const loadingKey = `authoring:${idempotencyKey}`;
                return (
                  <Button
                    key={`${card.surfaceId}-${item.actionCode}-${item.sourceComponentId || ''}`}
                    loading={actionLoading === loadingKey}
                    disabled={
                      !canUseCodingChat || (isCodingStreamLocked && actionLoading !== loadingKey)
                    }
                    onClick={() => handleAuthoringCardAction(assistantMessage, card, item)}
                  >
                    {item.label || item.actionCode}
                  </Button>
                );
              })}
            </Space>
          </div>
        ) : null}
      </div>
    );
  };

  const renderTraceStage = (stage: ExecutionTraceStage, expanded: boolean) => {
    const stageDetails = stage.details || [];
    const stageEvents = stage.events || [];
    return (
      <div className={`skill-factory-trace-stage ${stage.status}`} key={stage.key}>
        <span className="skill-factory-trace-stage-dot">
          {stage.status === 'done' ? <CheckOutlined /> : null}
          {stage.status === 'running' ? (
            <span className="skill-factory-trace-stage-spinner" />
          ) : null}
          {stage.status === 'error' ? <StopOutlined /> : null}
        </span>
        <div className="skill-factory-trace-stage-main">
          <div className="skill-factory-trace-stage-title">
            <strong>{traceStageTitle(stage)}</strong>
            <Tag
              color={
                stage.status === 'error' ? 'error' : stage.status === 'done' ? 'blue' : 'warning'
              }
            >
              {traceStageStatusText(stage)}
            </Tag>
          </div>
          {stageDetails.length ? (
            <div className="skill-factory-trace-stage-details">
              {stageDetails.map((detail, index) => (
                <p key={`${stage.key}-detail-${index}`}>{detail}</p>
              ))}
            </div>
          ) : null}
          {expanded && stageEvents.length ? (
            <details className="skill-factory-trace-raw">
              <summary>查看原始事件</summary>
              <pre>
                {stageEvents
                  ?.map(
                    (event) =>
                      `${event.eventType} · ${debugEventTitle(event)}\n${debugEventBody(event)}`,
                  )
                  ?.join?.('\n\n')}
              </pre>
            </details>
          ) : null}
        </div>
      </div>
    );
  };

  const renderProgressTraceBlock = (
    assistantMessage: AssistantMessageState,
    block: ExecutionTraceRenderBlock,
  ) => {
    const traceKey = `${assistantMessage.messageId}-${block.key}`;
    const expanded = Boolean(expandedTraceKeys[traceKey]);
    const stages = block.stages || [];
    const displayStages = expanded ? stages : stages.slice(-TRACE_STAGE_COLLAPSED_COUNT);
    const hiddenStageCount = Math.max(0, stages.length - displayStages.length);
    const currentStage =
      [...stages]?.reverse()?.find?.((stage) => stage.status === 'running') ||
      stages[stages.length - 1];
    const title =
      block.status === 'done'
        ? '已回答完成'
        : block.status === 'error'
        ? '执行过程异常'
        : currentStage
        ? traceStageTitle(currentStage)
        : '正在处理请求';
    const thinkingText = collapseWhitespace(block.text || '');
    const hasMoreThinking = thinkingText.length > TRACE_RAW_DETAIL_MAX_LENGTH;
    return (
      <div className={`skill-factory-trace-panel ${block.status || 'running'}`} key={block.key}>
        <button
          className="skill-factory-trace-panel-head"
          onClick={() =>
            setExpandedTraceKeys((current) => ({
              ...current,
              [traceKey]: !expanded,
            }))
          }
          type="button"
        >
          <span className="skill-factory-trace-panel-icon">
            <ThunderboltOutlined />
          </span>
          <span className="skill-factory-trace-panel-title">{title}</span>
          <Text type="secondary">{formatTime(block.timestamp)}</Text>
          <DownOutlined className={`skill-factory-trace-panel-arrow${expanded ? ' open' : ''}`} />
        </button>
        {expanded && thinkingText ? (
          <details className="skill-factory-trace-thinking" open>
            <summary>{hasMoreThinking ? '查看完整思考摘要' : '查看思考摘要'}</summary>
            <pre>{thinkingText}</pre>
          </details>
        ) : null}
        {hiddenStageCount ? (
          <div className="skill-factory-trace-hidden-count">
            已收起 {hiddenStageCount} 个较早步骤
          </div>
        ) : null}
        <div className="skill-factory-trace-stage-list">
          {displayStages.map((stage) => renderTraceStage(stage, expanded))}
        </div>
      </div>
    );
  };

  const renderExecutionTraceBlock = (
    assistantMessage: AssistantMessageState,
    block: ExecutionTraceRenderBlock,
  ) => {
    if (block.type === 'progress') {
      return renderProgressTraceBlock(assistantMessage, block);
    }
    return block.event ? renderPatchSummary(block.event) : null;
  };

  const renderAssistantMessageContent = (assistantMessage: AssistantMessageState) => {
    const executionTraceBlocks = buildExecutionTraceBlocks(
      assistantMessage.executionTrace,
      assistantMessage.status === 'streaming' && !assistantMessage.answerText,
      assistantMessage.timestamp,
    );
    const progressBlocks = executionTraceBlocks.filter((block) => block.type === 'progress');
    const patchBlocks = executionTraceBlocks.filter((block) => block.type === 'patch');
    const renderExecutionBlocks = (blocks: ExecutionTraceRenderBlock[]) =>
      blocks.length ? (
        <div className="skill-factory-message-layer execution">
          <div className="skill-factory-debug-block-list">
            {blocks.map((block) => renderExecutionTraceBlock(assistantMessage, block))}
          </div>
        </div>
      ) : null;
    return (
      <>
        {renderExecutionBlocks(progressBlocks)}
        {assistantMessage.validationReports?.length ? (
          <div className="skill-factory-message-layer validation">
            {assistantMessage.validationReports?.map?.(renderValidationReportCard)}
          </div>
        ) : null}
        <AnswerLayer text={assistantMessage.answerText} status={assistantMessage.status} />
        {renderExecutionBlocks(patchBlocks)}
        {assistantMessage.businessCards?.length ? (
          <div className="skill-factory-message-layer business">
            {assistantMessage.businessCards?.map?.((card) =>
              renderBusinessCard(assistantMessage, card),
            )}
          </div>
        ) : null}
      </>
    );
  };

  const renderSkillAssistantMessage = (messageState: SkillFactoryAuthoringMessage) => {
    const projectedMessage = buildAssistantMessages(messageState.events)?.[0];
    const assistantMessage: AssistantMessageState = projectedMessage
      ? {
          ...projectedMessage,
          answerText: projectedMessage.answerText || messageState.answerText,
          status: messageState.status,
          timestamp: Math.min(projectedMessage.timestamp, messageState.timestamp),
        }
      : {
          messageId: messageState.messageId,
          sessionId: messageState.sessionId || '',
          runId: messageState.runId,
          timestamp: messageState.timestamp,
          answerText: messageState.answerText,
          status: messageState.status,
          businessCards: [],
          executionTrace: [],
          validationReports: [],
        };
    return assistantMessage ? renderAssistantMessageContent(assistantMessage) : null;
  };



  const renderChat = () => (
    <SkillFactoryAuthoringChat
      title="对话生成"
      chat={skillAuthoringChat}
      extra={
        isCodingStreamLocked ? (
          <Tag color="blue">流式处理中</Tag>
        ) : sealedCurrentDraft ? (
          <Tag color="warning">已封板</Tag>
        ) : null
      }
      renderAssistantMessage={renderSkillAssistantMessage}
      onOpenReview={(changeSetId) => {
        setSelectedSkillPatchKey(changeSetId);
        setSkillAuthoringRailOpen(true);
        setSkillAuthoringRailView('review');
      }}
      emptyText="暂无 AICoding 会话"
      quickActions={
        <>
          {skillAuthoringChat.authoringGuideConfig?.enabled &&
          skillAuthoringChat.authoringGuideConfig?.composerPrompts?.length ? null : (
            <>
              {quickPrompts.map((item) => (
                null
              ))}
            </>
          )}
        </>
      }
    />
  );

  const renderWithChatRail = (mainContent: React.ReactNode) => (
    <AuthoringWorkbenchLayout
      railOpen={skillAuthoringRailOpen}
      railView={skillAuthoringRailView}
      onRailOpenChange={setSkillAuthoringRailOpen}
      onRailViewChange={setSkillAuthoringRailView}
      railTitle="AI Skill 助手"
      railSubtitle="生成与修改当前 Skill 工作区"
      review={renderSkillPatchReview()}
      reviewCount={pendingSkillPatchCount}
      chat={renderChat()}
      className="skill-authoring-workbench"
    >
      {mainContent}
    </AuthoringWorkbenchLayout>
  );

  const renderFiles = () => (
    <div className="skill-factory-workspace">
      <Modal
        title="创建 SKILL.md"
        open={createSkillFileOpen}
        okText="创建并保存"
        cancelText="取消"
        confirmLoading={actionLoading === 'createSkillFile'}
        okButtonProps={{ disabled: !newSkillFileContent.trim() || readonlyWorkspace }}
        onOk={handleCreateSkillFile}
        onCancel={() => {
          if (actionLoading === 'createSkillFile') return;
          setCreateSkillFileOpen(false);
          setNewSkillFileContent('');
        }}
      >
        <Text type="secondary">填写完整 Skill 文件，包含 name、description 的 YAML frontmatter 和正文。保存不会自动发布。</Text>
        <TextArea
          aria-label="新建 SKILL.md 内容"
          value={newSkillFileContent}
          onChange={(event) => setNewSkillFileContent(event.target.value)}
          autoSize={{ minRows: 12, maxRows: 24 }}
          disabled={actionLoading === 'createSkillFile'}
        />
      </Modal>
      <Card className="skill-factory-workspace-meta-card">
        <div className="skill-factory-workspace-meta">
          <div>
            <Text type="secondary">workspaceId</Text>
            <strong>{selectedSkill?.workspaceId || '-'}</strong>
          </div>
          <div>
            <Text type="secondary">工作区视图</Text>
            <Select
              size="small"
              value={workspaceViewMode}
              style={{ minWidth: 138 }}
              options={[
                { label: 'PRT 编辑态', value: WORKSPACE_VIEW_PREPROD_CURRENT },
                { label: '正式包只读态', value: WORKSPACE_VIEW_ONLINE_RELEASE },
              ]}
              onChange={(value) => handleWorkspaceViewModeChange(value as WorkspaceViewMode)}
            />
          </div>
          <div>
            <Text type="secondary">正式包版本</Text>
            <Select
              size="small"
              value={selectedReleaseVersion || undefined}
              placeholder="无"
              disabled={workspaceViewMode !== WORKSPACE_VIEW_ONLINE_RELEASE}
              style={{ minWidth: 96 }}
              options={releaseVersionList.map((version) => ({
                label: String(version),
                value: String(version),
              }))}
              onChange={(value) => handleReleaseVersionChange(String(value || ''))}
            />
          </div>
          <div>
            <Text type="secondary">文件数</Text>
            <strong>{workspaceTree?.fileCount || 0} 个</strong>
          </div>
          <div>
            <Text type="secondary">摘要</Text>
            <strong>{workspaceTree?.fileTreeDigest || selectedSkill?.fileTreeDigest || '-'}</strong>
          </div>
          <div>
            <Text type="secondary">变更状态</Text>
            {workspaceViewMode === WORKSPACE_VIEW_ONLINE_RELEASE ? (
              <Tag>正式包只读</Tag>
            ) : sealedCurrentDraft ? (
              <Tag color="warning">已封板</Tag>
            ) : isFileEditing ? (
              <Tag color="warning">编辑中</Tag>
            ) : (
              <Tag color="success">可编辑</Tag>
            )}
          </div>
          <div>
            <Text type="secondary">状态来源</Text>
            <strong>
              {skillStatusLabel(currentDraftStatus)}
              {currentSealedVersion ? ` / ${currentSealedVersion}` : ''}
            </strong>
          </div>
        </div>
      </Card>

      <div className="skill-factory-file-workbench">
        <div className="skill-factory-file-layout">
          <div className="skill-factory-file-tree">
            <div className="skill-factory-file-panel-title">项目文件</div>
            {workspaceTree?.fileCount === 0 && !readonlyWorkspace ? (
              <Button
                icon={<PlusOutlined />}
                disabled={Boolean(actionLoading)}
                onClick={() => setCreateSkillFileOpen(true)}
              >
                创建 SKILL.md
              </Button>
            ) : null}
            <Tree
              blockNode
              showIcon
              defaultExpandAll
              expandAction="click"
              selectedKeys={[selectedFilePath]}
              treeData={treeData}
              titleRender={(treeNode) => {
                const node = treeNode as SkillTreeNode;
                return (
                  <div className="skill-factory-tree-node-title">
                    <span title={node.title}>{node.title}</span>
                    {!isProtectedWorkspaceTreeNode(node) && !readonlyWorkspace ? (
                      <Button
                        danger
                        type="text"
                        size="small"
                        className="skill-factory-tree-node-delete"
                        icon={<DeleteOutlined />}
                        loading={actionLoading === `deletePath:${node.filePath || node.key}`}
                        title={`删除${node.directory ? '目录' : '文件'}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          confirmDeleteWorkspacePath(node);
                        }}
                      />
                    ) : null}
                  </div>
                );
              }}
              onSelect={(keys, info) => {
                if (info.node?.directory) return;
                handleSelectFile(String(info.node?.filePath || keys?.[0] || ''));
              }}
            />
          </div>
          <div className="skill-factory-file-preview">
            <div className="skill-factory-file-header">
              <div>
                <div className="skill-factory-file-name">
                  {fileContent?.fileName || '未选择文件'}
                </div>
                <Text type="secondary">
                  {fileContent?.fileType || '-'} · {fileContent?.fileSize || 0} bytes
                  {selectedFilePath ? ` · ${selectedFilePath}` : ''}
                </Text>
              </div>
              <Space>
                <Button
                  icon={<EditOutlined />}
                  disabled={!fileContent || isFileEditing || readonlyWorkspace}
                  onClick={() => setIsFileEditing(true)}
                >
                  编辑
                </Button>
                <Button disabled={!isFileEditing} onClick={handleCancelFileEdit}>
                  取消
                </Button>
                <Button
                  icon={<SaveOutlined />}
                  loading={actionLoading === 'saveFile'}
                  onClick={handleSaveFile}
                  disabled={
                    !fileContent || !isFileEditing || !hasFileDraftChange || readonlyWorkspace
                  }
                >
                  保存文件
                </Button>
                <Button
                  type="primary"
                  loading={actionLoading === 'saveWorkspace'}
                  onClick={handleSaveWorkspace}
                  disabled={!selectedSkill || readonlyWorkspace}
                >
                  保存当前工作区
                </Button>
              </Space>
            </div>
            {isFileEditing ? (
              <TextArea
                className="skill-factory-code-editor editing"
                value={editorContent}
                onChange={(event) => setEditorContent(event.target.value)}
                autoSize={{ minRows: 18, maxRows: 32 }}
                disabled={readonlyWorkspace}
              />
            ) : (
              renderCodeLines(editorContent)
            )}
          </div>
        </div>

        <div className="skill-factory-workspace-side">
          <Card title="ZIP 下载" size="small"><Button
                block
                icon={<DownloadOutlined />}
                disabled={
                  !selectedSkill ||
                  (workspaceViewMode === WORKSPACE_VIEW_ONLINE_RELEASE && !selectedReleaseVersion)
                }
                loading={actionLoading === ZIP_EXPORT_ACTION_KEY}
                onClick={handleWorkspaceZipDownload}
              >
                下载 ZIP
              </Button></Card>

          <Card title="文件保护" size="small">
            <div className="skill-factory-rule-list">
              <span>默认只读，点击编辑后才允许修改当前文件。</span>
              <span>切换文件前必须保存或取消未保存改动。</span>
              <span>保存文件只写当前 workspace，保存当前工作区后才更新摘要。</span>
            </div>
            {workspaceNotice ? (
              <div className="skill-factory-workspace-notice">{workspaceNotice}</div>
            ) : null}
          </Card>

          <Card title="重置当前变更" size="small">
            <div className="skill-factory-danger-zone">
              <Text type="secondary">
                丢弃当前未发布改动，从成功 PRT Build 或线上正式版本恢复文件和全部绑定关系。当前
                Skill 版本、workspaceId、线上版本和环境生效指针不变。
              </Text>
              <Select
                value={resetSourceValue || undefined}
                placeholder="选择 PRT Build 或线上正式版本"
                disabled={!resetSourceGroups.length || readonlyWorkspace}
                options={resetSourceGroups}
                onChange={(value) => setResetSourceValue(String(value || ''))}
              />
              <Button
                danger
                block
                icon={<ReloadOutlined />}
                loading={actionLoading === SkillFactoryMethod.WORKSPACE_RESET_FROM_VERSION}
                disabled={
                  !selectedSkill ||
                  !selectedResetSource ||
                  !resetSourceGroups.length ||
                  readonlyWorkspace
                }
                onClick={confirmResetWorkspace}
              >
                从指定来源重置
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );

  const renderBinding = () => (
    <div className="skill-factory-section-grid">
      <Card title="调试页面">
        <Alert
          type="info"
          showIcon
          message="通过数字员工 PRT 变更绑定 Skill"
          description="系统会自动复用唯一的可编辑 PRT 变更；没有可编辑变更时新建一个，并在绑定后直接发布到 PRT。点击时服务端会再次校验当前版本。"
        />
        <div className="skill-factory-specialist-picker">
          <Text strong>选择调试专员</Text>
          <Select
            showSearch
            allowClear
            optionFilterProp="label"
            placeholder="请选择需要绑定当前 Skill 的专员"
            loading={debugSpecialistOptionsLoading}
            value={selectedDebugSpecialistId || undefined}
            options={debugSpecialistOptions}
            onChange={(value) => {
              setDebugSpecialistSelection({
                skillCode: selectedSkill?.skillCode || '',
                employeeId: String(value || ''),
              });
              setSpecialistPrtBindings({});
            }}
          />
        </div>
        {debugSpecialistOptionsError ? (
          <Alert type="error" showIcon message={debugSpecialistOptionsError} />
        ) : null}
        <Spin spinning={debugSpecialistOptionsLoading || specialistPrtLoading}>
          <div className="skill-factory-specialist-prt-list">
            {!debugSpecialists.length ? (
              <div className="skill-factory-empty">请选择一个专员查看并发布 PRT 绑定</div>
            ) : (
              debugSpecialists.map(({ employeeId, employeeName }) => {
                const state = specialistPrtBindings[employeeId];
                const action = resolveSpecialistPrtAction(state || {});
                return (
                  <div className="skill-factory-specialist-prt-item" key={employeeId}>
                    <div className="skill-factory-specialist-prt-summary">
                      <div>
                        <strong>{state?.employeeName || employeeName}</strong>
                        <Text type="secondary">employeeId={employeeId}</Text>
                      </div>
                      <div className="skill-factory-specialist-prt-tags">
                        {state?.versionLabel ? (
                          <Tag color="processing">
                            {state.versionLabel} · {state.versionStatus || 'PRT 变更'}
                          </Tag>
                        ) : (
                          <Tag>暂无可编辑 PRT 变更</Tag>
                        )}
                        {state?.prtEffective ? (
                          <Tag color="success">Skill 已在 PRT 生效</Tag>
                        ) : state?.containsSkill ? (
                          <Tag color="warning">已绑定，待 PRT 发布</Tag>
                        ) : (
                          <Tag>未绑定</Tag>
                        )}
                      </div>
                    </div>
                    {state?.blockedReason ? (
                      <Alert type="error" showIcon message={state.blockedReason} />
                    ) : null}
                    <div className="skill-factory-binding-actions">
                      {action ? (
                        <Button
                          type="primary"
                          disabled={!canCurrentUserEditSkill}
                          title={
                            canCurrentUserEditSkill ? action.label : skillAccess.readonlyReason
                          }
                          loading={actionLoading === `specialistPrt:${employeeId}`}
                          onClick={() => handleEnsureSpecialistPrtBinding(employeeId)}
                        >
                          {action.label}
                        </Button>
                      ) : null}
                      <Button
                        icon={<LinkOutlined />}
                        onClick={() =>
                          window.open(buildSpecialistManagementUrl(employeeId), '_blank')
                        }
                      >
                        打开专员页面
                      </Button>
                      <Button icon={<LinkOutlined />} onClick={handleOpenTracePage}>
                        打开链路透视
                      </Button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Spin>
      </Card>
    </div>
  );

  const renderRelease = () => (
    <AssetReleaseTab
      assetKey={selectedSkill?.skillCode || ''}
      assetType="SKILL"
      title="Skill 发布管理"
      showCreateChange={false}
    />
  );
  const renderSkillCatalog = () => {
    return (
      <>
        <div className="skill-factory-catalog-metrics">
          <div>
            <Text type="secondary">Skill 总数</Text>
            <strong>{skillTotal}</strong>
          </div>
          <div>
            <Text type="secondary">编辑中</Text>
            <strong>{skillCounts.editingCount}</strong>
          </div>
          <div>
            <Text type="secondary">已上线</Text>
            <strong>{skillCounts.onlineCount}</strong>
          </div>
        </div>

        <Card className="skill-factory-catalog-filter">
          <Space wrap>
            <Input
              allowClear
              className="skill-factory-catalog-search"
              placeholder="搜索 Skill / 专员 / 负责人"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onPressEnter={() =>
                loadList(keyword, '', businessDomainFilter, capabilityDomainFilter)
              }
            />
            <Select
              allowClear
              showSearch
              className="skill-factory-catalog-select"
              placeholder="业务场域"
              value={businessDomainFilter || undefined}
              options={businessDomainSelectOptions}
              onChange={(value) => setBusinessDomainFilter(value || '')}
            />
            <Select
              allowClear
              showSearch
              className="skill-factory-catalog-select"
              placeholder="能力域"
              value={capabilityDomainFilter || undefined}
              options={capabilityDomainSelectOptions}
              onChange={(value) => setCapabilityDomainFilter(value || '')}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="skill-factory-catalog-select"
              placeholder="所属专员"
              value={specialistFilter || undefined}
              options={specialistFilterSelectOptions}
              onChange={(value) => {
                setSpecialistFilter(value || '');
                loadList(keyword, '', businessDomainFilter, capabilityDomainFilter,
                  1, value || '', statusFilter);
              }}
            />
            <Select
              allowClear
              className="skill-factory-catalog-select"
              placeholder="状态"
              value={statusFilter || undefined}
              options={SKILL_STATUS_FILTER_OPTIONS}
              onChange={(value) => {
                setStatusFilter(value || '');
                loadList(keyword, '', businessDomainFilter, capabilityDomainFilter,
                  1, specialistFilter, value || '');
              }}
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={() => loadList(keyword, '', businessDomainFilter, capabilityDomainFilter)}
            >
              搜索
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleResetListFilters}>
              重置
            </Button>
          </Space>
        </Card>

        <div className="skill-factory-skill-card-grid">
          {skillList.length ? (
            skillList.map((item) => (
              <Card
                hoverable
                className="skill-factory-skill-card"
                key={item.skillCode}
              >
                <div className="skill-factory-skill-card-head">
                  <div>
                    <strong>{item.skillNameCn || item.skillCode}</strong>
                    <span>{item.skillCode}</span>
                  </div>
                  <div className="skill-factory-skill-status-tags">
                    <Tag color={skillStatusColor(item.versionStatus)}>
                      {skillStatusLabel(item.versionStatus)}
                    </Tag>
                    <Tag color={isSkillOnline(item) ? 'success' : undefined}>
                      {isSkillOnline(item) ? '已上线' : '未上线'}
                    </Tag>
                  </div>
                </div>
                <p>
                  {item.skillDescription ||
                    item.skillNameEn ||
                    item.workspaceId ||
                    'Skill 工作台草稿'}
                </p>
                <div className="skill-factory-skill-kv-grid">
                  <div>
                    <span>所属专员</span>
                    <b>{item.specialistName || '-'}</b>
                  </div>
                  <div>
                    <span>业务场域</span>
                    <b>{domainDisplayText(businessDomains, item.businessDomain)}</b>
                  </div>
                  <div>
                    <span>能力域</span>
                    <b>{domainDisplayText(capabilityDomains, item.capabilityDomain)}</b>
                  </div>
                  <div>
                    <span>负责人</span>
                    <b>{item.owner || item.creator || '-'}</b>
                  </div>
                  <div>
                    <span>版本</span>
                    <b>{item.versionLabel || '-'}</b>
                  </div>
                  <div>
                    <span>工作区</span>
                    <b>{item.workspaceId || item.skillCode}</b>
                  </div>
                </div>
                <div className="skill-factory-skill-card-footer">
                  <Tag>{item.workspaceId || item.skillCode}</Tag>
                  <Button type="primary" onClick={() => handleSelectSkill(item)}>
                    查看详情
                  </Button>
                </div>
              </Card>
            ))
          ) : (
            <Card className="skill-factory-empty-card">暂无符合条件的 Skill</Card>
          )}
        </div>
        <div className="skill-factory-catalog-pagination">
          <Text type="secondary">按创建时间倒序 · 每页 9 个</Text>
          <Pagination
            current={skillPage}
            pageSize={SKILL_LIST_PAGE_SIZE}
            total={skillTotal}
            showSizeChanger={false}
            disabled={loading}
            showTotal={(total) => `共 ${total} 个 Skill`}
            onChange={(page) => {
              const query = appliedListQuery.current;
              loadList(query.keyword || '', '', query.businessDomain || '',
                query.capabilityDomain || '', page, query.specialistId || '', query.status || '');
            }}
          />
        </div>
      </>
    );
  };

  const renderActivePanel = () => {
    if (activeTab === 'overview') return renderOverview();
    if (activeTab === 'capabilities') return renderCapabilityList();
    if (activeTab === 'components') return renderComponentList();
    if (activeTab === 'files') return renderFiles();
    if (activeTab === 'binding') return renderBinding();
    return renderRelease();
  };

  const renderDetailShell = () => (
    <div className="skill-factory-detail">
      <div className="skill-factory-detail-head">
        <Button onClick={handleBackToSkillList}>返回 Skill 列表</Button>
        {selectedSkill ? (
          <div className="skill-factory-detail-title">
            <strong>{selectedSkill.skillNameCn || selectedSkill.skillCode}</strong>
            <span>{selectedSkill.skillCode}</span>
          </div>
        ) : null}
        {selectedSkill ? (
          <div className="skill-factory-skill-status-tags">
            <Tag color={skillStatusColor(selectedSkill.versionStatus)}>
              {skillStatusLabel(selectedSkill.versionStatus)}
            </Tag>
            <Tag color={isSkillOnline(selectedSkill) ? 'success' : undefined}>
              {isSkillOnline(selectedSkill) ? '已上线' : '未上线'}
            </Tag>
          </div>
        ) : null}
      </div>
      <div className="skill-factory-tabs">
        {tabList.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={activeTab === tab.key ? 'active' : ''}
            disabled={isCodingStreamLocked && tab.key !== activeTab}
            onClick={() => handleTabChange(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {selectedSkill && !skillAccess.loading && !skillAccess.permissions.canEdit ? (
        <Alert
          type="warning"
          showIcon
          message={skillAccess.readonlyReason || '当前 Skill 仅可查看'}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      {skillAccess.error ? (
        <Alert type="error" showIcon message={skillAccess.error} style={{ marginBottom: 12 }} />
      ) : null}
      {selectedSkill ? (
        renderWithChatRail(renderActivePanel())
      ) : (
        <Card>正在加载 Skill 详情...</Card>
      )}
    </div>
  );

  return (
    <div className="page-container skill-factory-page">
      <div className="skill-factory-topbar">
        <div>
          <div className="skill-factory-title-row">
            <h1 className="page-title">Skill Factory</h1>
          </div>
          <div className="page-subtitle skill-factory-subtitle">
            <span>{isDetailMode ? '当前 Skill 详情页' : '选择 Skill 后开始完整上翻闭环'}</span>
          </div>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadList(keyword, routeSkillCode)}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateNewSkill}>
            注册新 Skill
          </Button>
        </Space>
      </div>

      {errorText ? <Card>{errorText}</Card> : null}

      <Drawer
        title={skillInfoMode === 'create' ? '注册 Skill 基本信息' : '编辑 Skill 基本信息'}
        visible={skillInfoDrawerOpen}
        onClose={() => setSkillInfoDrawerOpen(false)}
        width={720}
      >
        <Form form={skillInfoForm} layout="vertical">
          <div className="skill-factory-form-grid">
            <Form.Item label="Skill 英文名" name="skillCode" rules={[{ required: true }]}>
              <Input disabled={skillInfoMode === 'edit'} placeholder="live-plan-create-skill" />
            </Form.Item>
            <Form.Item label="Skill 名称" name="skillNameCn" rules={[{ required: true }]}>
              <Input disabled={skillInfoFieldsDisabled} placeholder="直播计划创建" />
            </Form.Item>
            <Form.Item
              label="Skill 描述"
              name="skillDescription"
              style={{ gridColumn: '1 / -1' }}
              rules={[
                {
                  validator: (_, value) =>
                    countSkillDescriptionCharacters(value) <= SKILL_DESCRIPTION_MAX_LENGTH
                      ? Promise.resolve()
                      : Promise.reject(new Error(SKILL_DESCRIPTION_MAX_LENGTH_ERROR)),
                },
              ]}
            >
              <TextArea
                autoSize={{ minRows: 3, maxRows: 6 }}
                disabled={skillInfoFieldsDisabled}
                placeholder="说明这个 Skill 的适用场景、核心能力和边界"
              />
            </Form.Item>
            <Form.Item label="业务场域" name="businessDomain" rules={[{ required: true }]}>
              <Select
                showSearch
                disabled={skillInfoFieldsDisabled}
                placeholder="请选择业务场域"
                options={businessDomainSelectOptions}
              />
            </Form.Item>
            <Form.Item label="能力域" name="capabilityDomain" rules={[{ required: true }]}>
              <Select
                showSearch
                disabled={skillInfoFieldsDisabled}
                placeholder="请选择能力域"
                options={capabilityDomainSelectOptions}
              />
            </Form.Item>
            <Form.Item label="所属专员" name="specialistIds" rules={[{ required: true }]}>
              <Select
                mode="multiple"
                showSearch
                disabled={skillInfoFieldsDisabled}
                options={specialists.map((item) => ({
                  label: specialistOptionName(item),
                  value: specialistOptionId(item),
                }))}
              />
            </Form.Item>
            <Form.Item label="负责人" name="owner" rules={[{ required: true }]}>
              <Input
                disabled={skillInfoMode === 'edit'}
                placeholder="用户 ID，多个用英文逗号分隔"
              />
            </Form.Item>
            <Form.Item label="版本" name="version">
              <Input disabled={skillInfoMode === 'edit'} placeholder="1" />
            </Form.Item>
          </div>
          <div className="component-center-drawer-footer">
            <Button onClick={() => setSkillInfoDrawerOpen(false)}>取消</Button>
            <Button
              type="primary"
              loading={
                actionLoading === SkillFactoryMethod.WORKSPACE_CREATE ||
                actionLoading === SkillFactoryMethod.SKILL_UPDATE
              }
              disabled={skillInfoFieldsDisabled}
              onClick={handleSaveSkillInfo}
            >
              保存
            </Button>
          </div>
        </Form>
      </Drawer>

      <Spin spinning={loading}>{isDetailMode ? renderDetailShell() : renderSkillCatalog()}</Spin>
    </div>
  );
};

export default SkillFactoryPage;
