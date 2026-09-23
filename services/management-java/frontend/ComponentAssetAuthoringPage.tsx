import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Space,
  Spin,
  Tag,
  Typography,
  message,
  Input,
  Select,
} from 'antd';
import { ArrowLeftOutlined, EyeOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { jsonParse, jsonStringify } from './shared/safeJson';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { componentCenterApi, skillFactoryApi, SKILL_FACTORY_CHAT_BIZ_KEYS } from './api';
import type {
  ComponentAssetType,
  ComponentRenderPreviewParams,
  ComponentRenderPreviewResult,
  SkillFactoryComponentAsset,
} from './types';
import {
  SkillFactoryAuthoringChat,
  authoringChangeSetId,
  eventPayload,
  useSkillFactoryChatStream,
} from './shared/authoringChat';
import { createComponentCenterAuthoringAdapter } from './shared/authoringChat/adapters/componentCenterAdapter';
import AuthoringWorkbenchLayout, {
  type AuthoringRailView,
} from './shared/AuthoringWorkbenchLayout';
import FormPatchReviewPanel from './shared/authoringFormPatch/FormPatchReview';
import {
  applyFormPatchReview,
  AuthoringFormAdapterRegistry,
  buildFormPatchReview,
  captureFormPatchBaseline,
  formPatchProposalOf,
  type FormPatchBaseline,
  type FormPatchConflictChoice,
  type FormPatchReview,
} from './shared/authoringFormPatch';
import { createComponentFormPatchAdapter } from './componentFormPatchAdapter';
import JsonFormatTextArea from './shared/JsonFormatTextArea';
import DynamicCardContainerPreview from './shared/DynamicCardContainerPreview';
import AssetReleaseTab from './shared/AssetReleaseTab';
import { useAssetAccess } from './shared/AssetAccessContext';
import { useAssetReleaseEditability } from './shared/useAssetReleaseEditability';
import type { SkillFactoryCodingEvent } from './api';
import { DSL_TYPE_BUSINESS_DSL, DSL_TYPE_CARD_CONTAINER } from './cardContainerTemplate';
import type { ChangeReviewStatus } from './shared/authoringChangeReview';

const { Text } = Typography;

const PAYLOAD_FORM_PATCH_PROPOSED = 'FORM_PATCH_PROPOSED';
const PAYLOAD_COMPONENT_VALIDATION = 'COMPONENT_ASSET_VALIDATION_RESULT';
const PAYLOAD_COMPONENT_PREVIEW = 'COMPONENT_ASSET_PREVIEW_RESULT';
const PAYLOAD_COMPONENT_SAVE_PREPARE = 'COMPONENT_ASSET_SAVE_PREPARE';

const DEFAULT_OWNER = '';
const DEFAULT_SCENE = '组件中心 AI 创建';
const DEFAULT_SUPPORT_CLIENTS = ['PC'];
const INTERACTION_MODE_DISPLAY_ONLY = 'DISPLAY_ONLY';
const INTERACTION_MODE_INTERACTIVE = 'INTERACTIVE';
const INTERACTION_MODE_OPTIONS = [
  { label: '纯展示', value: INTERACTION_MODE_DISPLAY_ONLY },
  { label: '需交互', value: INTERACTION_MODE_INTERACTIVE },
];
const COMPONENT_CENTER_AUTHORING_BIZ_KEY = SKILL_FACTORY_CHAT_BIZ_KEYS.COMPONENT_CENTER_AUTHORING;
const COMPONENT_CENTER_AUTHORING_AGENT_MISSING = `当前页面缺少组件中心 AI Authoring agentId 配置，请在 skillFactoryPageConfig 中配置 ${COMPONENT_CENTER_AUTHORING_BIZ_KEY} 场景的 agentId。`;
const DEFAULT_CARD_PC_BUNDLE_URL =
  'https://example.invalid/REQUIRES_CONFIGURATION';
const DEFAULT_CARD_APP_BUNDLE_URL =
  'https://example.invalid/REQUIRES_CONFIGURATION';
const CARD_PREVIEW_INVALIDATING_FIELDS: Array<keyof ComponentAssetDraft> = [
  'componentName',
  'componentNameCn',
  'interactionMode',
  'bundleUrl',
  'appBundleUrl',
  'messageDemoJson',
  'officialDemoJson',
  'paramsSchemaJson',
  'renderTemplateJson',
  'protocolVersion',
];
const DEFAULT_CARD_SKILL_OUTPUT = `{
  "dslType": "CARD_CONTAINER",
  "componentName": "StoreDiagnostic",
  "params": {
    "description": "今日已为您诊断出以下问题，请及时处理：",
    "cards": [
      {
        "iconUrl": "https://example.com/icon_score.png",
        "imageUrl": "",
        "description": "店铺体验分较昨日下降0.30分，请关注降分原因并及时改善。",
        "buttons": [
          {
            "text": "立即诊断",
            "sendText": "帮我诊断店铺体验分下降原因",
            "actionType": "SEND_TEXT",
            "pcUrl": "",
            "mobileUrl": ""
          }
        ]
      }
    ]
  }
}`;
const DEFAULT_CARD_CONTAINER_DEMO = `{
  "cardType": "StoreDiagnostic",
  "description": "今日已为您诊断出以下问题，请及时处理：",
  "cards": [
    {
      "iconUrl": "https://example.com/icon_score.png",
      "imageUrl": "",
      "description": "店铺体验分较昨日下降0.30分，请关注降分原因并及时改善。",
      "buttons": [
        {
          "text": "立即诊断",
          "sendText": "帮我诊断店铺体验分下降原因",
          "actionType": "SEND_TEXT",
          "pcUrl": "",
          "mobileUrl": ""
        }
      ]
    }
  ]
}`;
const DEFAULT_CARD_PARAMS_SCHEMA = `{
  "type": "object",
  "required": [
    "description",
    "cards"
  ],
  "properties": {
    "description": {
      "type": "string"
    },
    "cards": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "description",
          "buttons"
        ],
        "properties": {
          "iconUrl": {
            "type": "string"
          },
          "imageUrl": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "buttons": {
            "type": "array",
            "items": {
              "type": "object",
              "required": [
                "text",
                "actionType"
              ],
              "properties": {
                "text": {
                  "type": "string"
                },
                "sendText": {
                  "type": "string"
                },
                "actionType": {
                  "type": "string"
                },
                "pcUrl": {
                  "type": "string"
                },
                "mobileUrl": {
                  "type": "string"
                }
              }
            }
          }
        }
      }
    }
  }
}`;
const DEFAULT_CARD_TEMPLATE = `{
  "cardType": "{{componentName}}",
  "description": "{{params.description}}",
  "cards": [
    {{#each params.cards}}
    {
      "iconUrl": "{{iconUrl}}",
      "imageUrl": "{{imageUrl}}",
      "description": "{{description}}",
      "buttons": [
        {{#each buttons}}
        {
          "text": "{{text}}",
          "sendText": "{{sendText}}",
          "actionType": "{{actionType}}",
          "pcUrl": "{{pcUrl}}",
          "mobileUrl": "{{mobileUrl}}"
        }{{#unless @last}},{{/unless}}
        {{/each}}
      ]
    }{{#unless @last}},{{/unless}}
    {{/each}}
  ]
}`;

type ComponentAssetDraft = Partial<SkillFactoryComponentAsset> & {
  mode?: 'CREATE' | 'UPDATE';
  enableable?: boolean;
  status?: string;
};
type CardAuthoringStep = 1 | 2 | 3;
type CardPreviewClientType = 'PC' | 'APP';
interface ComponentCenterAuthoringConfig {
  agentId: string;
  ownerId?: string;
  disabledReason?: string;
}

function createDraftInstanceId(): string {
  return `draft_${Date.now()}_${Math.random()?.toString(36)?.slice?.(2, 10)}`;
}

function recordOf(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringOf(value: unknown): string {
  if (value === undefined || value === null) return '';
  return String(value);
}

function fieldString(
  record: Record<string, unknown> | null | undefined,
  ...keys: string[]
): string {
  if (!record) return '';
  for (const key of keys) {
    const value = stringOf(record[key])?.trim?.();
    if (value) return value;
  }
  return '';
}

function keyedConfigRecord(record: Record<string, unknown>): Record<string, unknown> | null {
  const bizConfigs = recordOf(record.bizConfigs);
  return (
    recordOf(bizConfigs?.[COMPONENT_CENTER_AUTHORING_BIZ_KEY]) ||
    recordOf(record[COMPONENT_CENTER_AUTHORING_BIZ_KEY])
  );
}

function resolveComponentCenterAuthoringConfig(config: unknown): ComponentCenterAuthoringConfig {
  const root = recordOf(config);
  if (!root) {
    return { agentId: '', disabledReason: COMPONENT_CENTER_AUTHORING_AGENT_MISSING };
  }
  const source = keyedConfigRecord(root);
  const agentId = fieldString(source, 'agentId');
  if (!agentId) {
    return { agentId: '', disabledReason: COMPONENT_CENTER_AUTHORING_AGENT_MISSING };
  }
  return {
    agentId,
    ownerId: fieldString(source, 'ownerId') || undefined,
  };
}

function formatJson(value: unknown): string {
  if (typeof value === 'string') {
    const parsed = jsonParse(value, null);
    return parsed ? jsonStringify(parsed, null, 2) || value : value;
  }
  return jsonStringify(value ?? {}, null, 2) || '{}';
}

function normalizeAssetType(value?: string | null): ComponentAssetType {
  if (value === 'CARD_COMPONENT' || value === 'A2UI_ATOM' || value === 'BUSINESS_DSL') {
    return value;
  }
  return 'BUSINESS_DSL';
}

function assetTypeFromPath(pathname: string): ComponentAssetType {
  if (pathname.includes('/register-render-component')) {
    return 'CARD_COMPONENT';
  }
  return 'BUSINESS_DSL';
}

function defaultDraft(assetType: ComponentAssetType): ComponentAssetDraft {
  const cardComponent = assetType === 'CARD_COMPONENT';
  return {
    assetType,
    protocolVersion: 1,
    interactionMode: cardComponent ? INTERACTION_MODE_DISPLAY_ONLY : undefined,
    owner: DEFAULT_OWNER,
    scene: cardComponent ? '通过 CARD_CONTAINER 协议渲染 Skill 结构化输出' : DEFAULT_SCENE,
    supportClients: DEFAULT_SUPPORT_CLIENTS,
    enabled: assetType === 'BUSINESS_DSL',
    dslType: cardComponent ? DSL_TYPE_CARD_CONTAINER : DSL_TYPE_BUSINESS_DSL,
    agentUiDsl: '',
    bundleUrl: cardComponent ? DEFAULT_CARD_PC_BUNDLE_URL : '',
    appBundleUrl: cardComponent ? DEFAULT_CARD_APP_BUNDLE_URL : '',
    paramsSchemaJson:
      assetType === 'BUSINESS_DSL'
        ? '{"type":"object","properties":{}}'
        : cardComponent
        ? DEFAULT_CARD_PARAMS_SCHEMA
        : '',
    renderTemplateJson:
      assetType === 'BUSINESS_DSL'
        ? '{"type":"updateComponents","surfaceId":"{{agentUiDsl}}","components":[]}'
        : cardComponent
        ? DEFAULT_CARD_TEMPLATE
        : '',
    allowedActionsJson: '[]',
    runtimeConfigJson: '{}',
    officialDemoJson:
      assetType === 'BUSINESS_DSL'
        ? '{"dslType":"BUSINESS_DSL","agentUiDsl":"","params":{}}'
        : cardComponent
        ? DEFAULT_CARD_CONTAINER_DEMO
        : '{"componentName":"","data":{}}',
    messageDemoJson: cardComponent
      ? DEFAULT_CARD_SKILL_OUTPUT
      : '{"dslType":"BUSINESS_DSL","agentUiDsl":"","params":{}}',
    integrationPrompt: cardComponent
      ? ''
      : '当需要使用当前业务编排时调用 render_component：dslType 固定 BUSINESS_DSL，agentUiDsl 填当前协议 code，params 按已发布 Schema 提供；完整 A2UI 由 Adviser 生成。',
  };
}

function normalizeDraft(raw: unknown, fallbackAssetType: ComponentAssetType): ComponentAssetDraft {
  const record = recordOf(raw) || {};
  const assetType = normalizeAssetType(stringOf(record.assetType || fallbackAssetType));
  const draft: ComponentAssetDraft = {
    ...defaultDraft(assetType),
    ...(record as ComponentAssetDraft),
    assetType,
  };
  const dslCode = stringOf(record.dslCode);
  const dslName = stringOf(record.dslName);
  if (!draft.componentName && dslCode) draft.componentName = dslCode;
  if (!draft.componentNameCn && dslName) draft.componentNameCn = dslName;
  if (assetType === 'CARD_COMPONENT') {
    draft.dslType = DSL_TYPE_CARD_CONTAINER;
    draft.agentUiDsl = '';
  } else if (assetType === 'BUSINESS_DSL') {
    draft.dslType = DSL_TYPE_BUSINESS_DSL;
    if (!draft.agentUiDsl) draft.agentUiDsl = stringOf(record.dslCode);
  }
  if (!draft.supportClients?.length) draft.supportClients = DEFAULT_SUPPORT_CLIENTS;
  draft.protocolVersion = Number(draft.protocolVersion || 1);
  return draft;
}

function payloadTypeOf(
  event: SkillFactoryCodingEvent,
  payload: Record<string, unknown> | null,
): string {
  const content = recordOf(payload?.content);
  return stringOf(
    event.payloadType ||
      payload?.payloadType ||
      content?.payloadType ||
      event.eventCode ||
      event.eventType,
  );
}

function payloadContent(payload: Record<string, unknown> | null): Record<string, unknown> {
  return recordOf(payload?.content) || payload || {};
}

function requiredFields(assetType?: ComponentAssetType): string[] {
  if (assetType === 'BUSINESS_DSL') {
    return [
      'componentName',
      'componentNameCn',
      'agentUiDsl',
      'paramsSchemaJson',
      'renderTemplateJson',
      'officialDemoJson',
      'integrationPrompt',
    ];
  }
  if (assetType === 'A2UI_ATOM') {
    return ['componentName', 'componentNameCn', 'officialDemoJson', 'integrationPrompt'];
  }
  return [
    'componentName',
    'componentNameCn',
    'interactionMode',
    'bundleUrl',
    'appBundleUrl',
    'messageDemoJson',
    'officialDemoJson',
    'paramsSchemaJson',
    'renderTemplateJson',
  ];
}

function filledFields(draft: ComponentAssetDraft): string[] {
  return requiredFields(draft.assetType)?.filter?.((field) => {
    const value = draft[field as keyof ComponentAssetDraft];
    return Array.isArray(value) ? value.length > 0 : Boolean(stringOf(value)?.trim?.());
  });
}

function isCardBasicReady(draft: ComponentAssetDraft): boolean {
  return Boolean(
    stringOf(draft.componentName).trim() &&
      stringOf(draft.componentNameCn).trim() &&
      stringOf(draft.interactionMode).trim() &&
      stringOf(draft.bundleUrl).trim() &&
      stringOf(draft.appBundleUrl).trim() &&
      stringOf(draft.scene).trim(),
  );
}

function buildRenderPreviewParams(draft: ComponentAssetDraft): ComponentRenderPreviewParams {
  const businessDsl = draft.assetType === 'BUSINESS_DSL';
  const inputMode: ComponentRenderPreviewParams['inputMode'] = businessDsl
    ? 'BUSINESS_DSL'
    : draft.dslType === 'CARD_CONTAINER'
    ? 'CARD_CONTAINER'
    : 'RAW_TEXT';
  return {
    assetType: draft.assetType,
    componentName: draft.componentName,
    agentUiDsl: businessDsl ? draft.agentUiDsl : undefined,
    dslType: businessDsl ? DSL_TYPE_BUSINESS_DSL : DSL_TYPE_CARD_CONTAINER,
    protocolVersion: Number(draft.protocolVersion || 1),
    interactionMode: draft.interactionMode,
    inputMode,
    source: 'component-center-ai-authoring',
    clientType: 'PC',
    toolArgsJson: businessDsl
      ? draft.messageDemoJson || draft.officialDemoJson || '{}'
      : draft.messageDemoJson || '{}',
    paramsSchemaJson: draft.paramsSchemaJson || '',
    renderTemplateJson: draft.renderTemplateJson || '',
    officialDemoJson: draft.officialDemoJson || '',
    allowedActionsJson: draft.allowedActionsJson || '',
    runtimeConfigJson: draft.runtimeConfigJson || '',
    bundleUrl: draft.bundleUrl || '',
    appBundleUrl: draft.appBundleUrl || '',
  };
}

function buildCardContainerRenderPreviewParams(
  draft: ComponentAssetDraft,
  clientType: CardPreviewClientType,
): ComponentRenderPreviewParams {
  return {
    assetType: 'CARD_COMPONENT',
    componentName: draft.componentName,
    componentNameCn: draft.componentNameCn,
    protocolVersion: Number(draft.protocolVersion || 1),
    interactionMode: draft.interactionMode,
    dslType: DSL_TYPE_CARD_CONTAINER,
    inputMode: 'CARD_CONTAINER',
    source: 'component-center-card-authoring',
    clientType,
    toolArgsJson: draft.messageDemoJson?.trim() || '{}',
    paramsSchemaJson: draft.paramsSchemaJson || '',
    renderTemplateJson: draft.renderTemplateJson || '',
    officialDemoJson: draft.officialDemoJson || '',
    allowedActionsJson: draft.allowedActionsJson || '',
    runtimeConfigJson: draft.runtimeConfigJson || '',
    bundleUrl: draft.bundleUrl || '',
    appBundleUrl: draft.appBundleUrl || '',
  };
}

interface ComponentPreviewErrorMessage {
  title: string;
  guidance: string;
}

function componentPreviewErrorMessage(error: string): ComponentPreviewErrorMessage {
  const normalized = error.trim();
  const missingTemplateValue = normalized.match(/template missing value:\s*(.+)$/i);
  if (missingTemplateValue) {
    const fieldPath = missingTemplateValue?.[1]?.trim?.();
    return {
      title: `转换模板引用的字段「${fieldPath}」没有取到值。`,
      guidance:
        '请检查模型 Tool 调用参数的 params 是否包含该字段，或修正模板占位符路径，然后重新预览。',
    };
  }
  const missingRequiredField = normalized.match(
    /(?:required field missing|missing required field|required property)[:\s]+(.+)$/i,
  );
  if (missingRequiredField) {
    const fieldPath = missingRequiredField?.[1]?.trim?.();
    return {
      title: `Tool 调用参数缺少必填参数「${fieldPath}」。`,
      guidance:
        '请在模型 Tool 调用参数的 params 中补充该字段；如果它不应该必填，请手动调整 paramsSchemaJson 后重新预览。',
    };
  }
  if (/renderTemplateJson is required/i.test(normalized)) {
    return {
      title: '转换模板不能为空。',
      guidance:
        '请根据 Tool 调用参数和 card-container 结果手动填写模板，再运行预览。',
    };
  }
  if (/paramsSchemaJson is required/i.test(normalized)) {
    return {
      title: 'paramsSchemaJson 不能为空。',
      guidance:
        '请手动填写参数的必填、非必填和类型约束，检查 Schema 后再运行预览。',
    };
  }
  if (/invalid json|json.*invalid|illegal json|not valid json/i.test(normalized)) {
    return {
      title: '运行结果不是合法的 JSON。',
      guidance: '请检查模板的括号、引号、逗号和循环分隔符，并根据报错手动修正模板。',
    };
  }
  if (/componentName.*(?:mismatch|not match|does not match)/i.test(normalized)) {
    return {
      title: '模板生成的 componentName 与当前组件 code 不一致。',
      guidance: '请把模板中的 componentName 和 data.cardType 改为当前组件 code，再重新运行预览。',
    };
  }
  return {
    title: `运行预览失败：${normalized || '服务端未返回具体原因'}`,
    guidance:
      '请依次检查模型 Tool 调用参数、paramsSchemaJson 和转换模板，根据报错手动修复后重新预览。',
  };
}

const JsonBlock: React.FC<{ value: unknown; maxHeight?: number }> = ({
  value,
  maxHeight = 280,
}) => (
  <pre className="component-authoring-json" style={{ maxHeight }}>
    {formatJson(value)}
  </pre>
);

const DraftFieldSummary: React.FC<{ draft: ComponentAssetDraft }> = ({ draft }) => {
  const allFields = requiredFields(draft.assetType);
  const filled = filledFields(draft);
  const percent = allFields.length ? Math.round((filled.length / allFields.length) * 100) : 0;
  return (
    <Card title="字段完整度" className="component-authoring-side-card">
      <div className="component-authoring-progress" aria-label={`字段完整度 ${percent}%`}>
        <span style={{ width: `${percent}%` }} />
      </div>
      <Text type="secondary">
        已完成 {filled.length}/{allFields.length} 项
      </Text>
      <div className="component-authoring-field-list">
        {allFields.map((field) => {
          const ready = filled.includes(field);
          return (
            <div className="component-authoring-field-row" key={field}>
              <Tag color={ready ? 'success' : 'warning'}>{ready ? '已填' : '缺失'}</Tag>
              <span>{field}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const ComponentAssetAuthoringPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const assetType = normalizeAssetType(
    searchParams.get('assetType') || assetTypeFromPath(location.pathname),
  );
  const assetId = searchParams.get('assetId') || searchParams.get('id') || '';
  const releaseEditability = useAssetReleaseEditability('COMPONENT', assetId || undefined);
  const assetAccess = useAssetAccess('COMPONENT', assetId || undefined);
  const [draft, setDraft] = useState<ComponentAssetDraft>(() => defaultDraft(assetType));
  const [validationPayload, setValidationPayload] = useState<Record<string, unknown>>();
  const [previewPayload, setPreviewPayload] = useState<Record<string, unknown>>();
  const [savePreparePayload, setSavePreparePayload] = useState<Record<string, unknown>>();
  const [localPreview, setLocalPreview] = useState<ComponentRenderPreviewResult>();
  const [previewRequestError, setPreviewRequestError] = useState('');
  const [previewClientType, setPreviewClientType] = useState<CardPreviewClientType>('PC');
  const [cardPreviewPassed, setCardPreviewPassed] = useState<
    Record<CardPreviewClientType, boolean>
  >({
    PC: false,
    APP: false,
  });
  const [loadingAsset, setLoadingAsset] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [savingBasicInfo, setSavingBasicInfo] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pageError, setPageError] = useState('');
  const [agentId, setAgentId] = useState('');
  const [ownerId, setOwnerId] = useState<string | undefined>();
  const [authoringConfigDisabledReason, setAuthoringConfigDisabledReason] =
    useState('组件中心 AI Authoring 配置加载中');
  const [componentCodeInput, setComponentCodeInput] = useState('');
  const draftRef = useRef<ComponentAssetDraft>(draft);
  const draftInstanceIdRef = useRef(createDraftInstanceId());
  const proposalBaselinesRef = useRef<Map<string, FormPatchBaseline<ComponentAssetDraft>>>(
    new Map(),
  );
  const [formRevision, setFormRevision] = useState(1);
  const [formPatchReviews, setFormPatchReviews] = useState<
    Record<string, FormPatchReview<ComponentAssetDraft>>
  >({});
  const [pendingReviewChangeSetId, setPendingReviewChangeSetId] = useState('');
  const [changeReviewStatuses, setChangeReviewStatuses] = useState<
    Record<string, ChangeReviewStatus>
  >({});
  const [selectedChangeIds, setSelectedChangeIds] = useState<Set<string>>(new Set());
  const [conflictChoices, setConflictChoices] = useState<Record<string, FormPatchConflictChoice>>(
    {},
  );
  const [railOpen, setRailOpen] = useState(true);
  const [railView, setRailView] = useState<AuthoringRailView>('chat');
  const [cardStep, setCardStep] = useState<CardAuthoringStep>(
    searchParams.get('step') === 'release' && assetId ? 3 : 1,
  );
  const pendingReview = formPatchReviews[pendingReviewChangeSetId];
  const componentScopeCode = (
    componentCodeInput ||
    (assetType === 'CARD_COMPONENT' ? draft.componentName : draft.agentUiDsl) ||
    draft.componentName ||
    draft.dslType ||
    ''
  ).trim();
  const entityId = assetId
    ? `component-asset:${assetId}`
    : `component-draft:${draftInstanceIdRef.current}`;
  const draftId = assetId
    ? `component_asset_${assetId}`
    : `component_authoring_${draftInstanceIdRef.current}`;
  const releaseEditDisabledReason = assetId
    ? assetAccess.loading
      ? '正在加载当前组件的操作权限'
      : !assetAccess.permissions?.canEdit
      ? assetAccess.readonlyReason || '当前用户不是负责人，仅可查看'
      : releaseEditability.loading
      ? '正在加载当前组件的变更状态'
      : releaseEditability.editable
      ? ''
      : '当前组件没有可编辑变更，请先在发布管理中新建变更'
    : '';

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);



  useEffect(() => {
    setCardStep(1);
    setFormRevision(1);
    setFormPatchReviews({});
    setPendingReviewChangeSetId('');
    setChangeReviewStatuses({});
    setSelectedChangeIds(new Set());
    setConflictChoices({});
    setRailView('chat');
    proposalBaselinesRef.current?.clear?.();
    if (!assetId) {
      setDraft(defaultDraft(assetType));
      setComponentCodeInput('');
      return;
    }
    setLoadingAsset(true);
    setPageError('');
    componentCenterApi
      .detail(Number(assetId))
      .then((asset) => {
        setDraft(normalizeDraft(asset, asset.assetType || assetType));
        setComponentCodeInput(
          asset.assetType === 'CARD_COMPONENT' ? asset.componentName || '' : asset.agentUiDsl || '',
        );
      })
      .catch((error) => {
        const errorMsg = error instanceof Error ? error.message : '资产详情加载失败';
        setPageError(errorMsg);
      })
      .finally(() => setLoadingAsset(false));
  }, [assetId, assetType]);

  const isCardContainerAsset = assetType === 'CARD_COMPONENT';
  const formAdapter = useMemo(
    () =>
      createComponentFormPatchAdapter({
        draft,
        entityId,
        revision: formRevision,
        editMode: Boolean(assetId),
        apply: (next) => {
          setDraft(normalizeDraft(next, next.assetType || assetType));
          setFormRevision((current) => current + 1);
          setLocalPreview(undefined);
          setCardPreviewPassed({ PC: false, APP: false });
          setValidationPayload(undefined);
        },
      }),
    [assetId, assetType, draft, entityId, formRevision],
  );
  const formAdapterRegistry = useMemo(
    () => new AuthoringFormAdapterRegistry().register(formAdapter),
    [formAdapter],
  );

  const handleAuthoringEvent = useCallback(
    (event: SkillFactoryCodingEvent) => {
      const payload = eventPayload(event) || recordOf(event.content);
      const type = payloadTypeOf(event, payload);
      const content = payloadContent(payload);
      if (type === PAYLOAD_FORM_PATCH_PROPOSED) {
        const proposal = formPatchProposalOf(content);
        if (!proposal) {
          message.warning(
            'AI 返回的表单修改建议缺少合法 identity、revision、fingerprint 或 operations。',
          );
          return;
        }
        const baseline = proposalBaselinesRef.current?.get?.(proposal.baseFingerprint);
        if (!baseline) {
          message.warning('AI 修改建议无法匹配本次请求基线，已拒绝写入当前表单。');
          return;
        }
        try {
          const activeAdapter = formAdapterRegistry.resolve<ComponentAssetDraft>(proposal.formKey);
          const review = buildFormPatchReview(activeAdapter, baseline, draftRef.current, proposal);
          const changeSetId = authoringChangeSetId(event);
          setFormPatchReviews((current) => ({ ...current, [changeSetId]: review }));
          setPendingReviewChangeSetId(changeSetId);
          setChangeReviewStatuses((current) => ({ ...current, [changeSetId]: 'PENDING' }));
          setSelectedChangeIds(
            new Set(
              review?.changes
                ?.filter?.((change) => change.status === 'safe')
                ?.map?.((change) => change.id),
            ),
          );
          setConflictChoices({});
          setRailOpen(true);
          setRailView('review');
          message.info('AI 已生成表单修改建议，请审阅后再应用。');
        } catch (error) {
          message.warning(error instanceof Error ? error.message : 'AI 表单修改建议校验失败');
        }
      }
      if (type === PAYLOAD_COMPONENT_VALIDATION) {
        setValidationPayload(content);
      }
      if (type === PAYLOAD_COMPONENT_PREVIEW) {
        setPreviewPayload(content);
      }
      if (type === PAYLOAD_COMPONENT_SAVE_PREPARE) {
        setSavePreparePayload(content);
      }
    },
    [formAdapterRegistry],
  );

  const adapter = useMemo(() => {
    const baseline = captureFormPatchBaseline(formAdapter);
    const baseAdapter = createComponentCenterAuthoringAdapter<ComponentAssetDraft>({
      assetType,
      assetId,
      draftId,
      formKey: formAdapter.formKey,
      entityId,
      revision: formRevision,
      baseFingerprint: baseline.fingerprint,
      componentCode: componentScopeCode,
      disabledReason:
        releaseEditDisabledReason ||
        authoringConfigDisabledReason ||
        (componentScopeCode ? undefined : '请先填写组件 code，再开始 AI 创建会话'),
      agentId,
      ownerId,
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
    assetType,
    assetId,
    draftId,
    entityId,
    formAdapter,
    formRevision,
    componentScopeCode,
    authoringConfigDisabledReason,
    releaseEditDisabledReason,
    agentId,
    ownerId,
    handleAuthoringEvent,
  ]);

  const authoringCurrentDraft = useMemo(
    () => ({
      ...draft,
      authoringInput: {
        officialSkillOutputJson: draft.messageDemoJson || '',
        finalRenderJson: draft.officialDemoJson || '',
      },
    }),
    [draft],
  );

  const chat = useSkillFactoryChatStream<ComponentAssetDraft>({
    adapter,
    workspaceId: 'component-center',
    currentDraft: authoringCurrentDraft,
  });

  const updateDraftField = (field: keyof ComponentAssetDraft, value: string) => {
    if (isCardContainerAsset && CARD_PREVIEW_INVALIDATING_FIELDS.includes(field)) {
      setLocalPreview(undefined);
      setPreviewRequestError('');
      setCardPreviewPassed({ PC: false, APP: false });
    }
    setDraft((prev) => ({
      ...prev,
      [field]: value,
      ...(field === 'componentName' && isCardContainerAsset
        ? { dslType: DSL_TYPE_CARD_CONTAINER }
        : {}),
    }));
    setFormRevision((current) => current + 1);
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

  const applyPendingReview = () => {
    if (!pendingReview) return;
    if (assetId && releaseEditDisabledReason) {
      message.warning(releaseEditDisabledReason || '当前组件没有可编辑变更');
      return;
    }
    const unresolvedConflicts = pendingReview.changes?.filter?.(
      (change) => change.status === 'conflict' && !conflictChoices[change.id],
    );
    if (unresolvedConflicts.length) {
      message.warning(`还有 ${unresolvedConflicts.length} 个冲突未选择。`);
      return;
    }
    try {
      const activeAdapter = formAdapterRegistry.resolve<ComponentAssetDraft>(
        pendingReview.proposal?.formKey,
      );
      const next = applyFormPatchReview(
        activeAdapter,
        pendingReview,
        selectedChangeIds,
        conflictChoices,
      );
      activeAdapter.apply(next);
      settlePendingReview('APPLIED');
      message.success('已应用到当前页面表单；预览、保存和发布仍需单独确认。');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'AI 修改未应用，当前表单保持不变');
    }
  };

  const handlePreview = async (clientType: CardPreviewClientType = 'PC') => {
    if (isCardContainerAsset && !isCardBasicReady(draft)) {
      message.warning('请先完成基础信息并点击确定');
      setCardStep(1);
      return;
    }
    setLocalPreview(undefined);
    setPreviewRequestError('');
    setPreviewClientType(clientType);
    setPreviewing(true);
    try {
      const result = await componentCenterApi.bizRenderPreview(
        isCardContainerAsset
          ? buildCardContainerRenderPreviewParams(draft, clientType)
          : buildRenderPreviewParams(draft),
      );
      setLocalPreview(result);
      if (isCardContainerAsset) {
        setCardPreviewPassed((current) => ({
          ...current,
          [clientType]: Boolean(result.valid),
        }));
      }
      if (result.valid) {
        message.success('预览校验通过');
      } else {
        message.warning('运行预览未通过，请根据下方提示修改后重试');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '预览请求失败';
      setPreviewRequestError(errorMessage);
      if (isCardContainerAsset) {
        setCardPreviewPassed((current) => ({
          ...current,
          [clientType]: false,
        }));
      }
      message.error(componentPreviewErrorMessage(errorMessage)?.title);
    } finally {
      setPreviewing(false);
    }
  };

  const handleConfirmSave = async () => {
    if (assetId && releaseEditDisabledReason) {
      message.warning(releaseEditDisabledReason || '当前组件没有可编辑变更');
      return;
    }
    if (isCardContainerAsset) {
      if (!isCardBasicReady(draft)) {
        message.warning('请先完成基础信息');
        setCardStep(1);
        return;
      }
      if (!cardPreviewPassed.PC || !cardPreviewPassed.APP) {
        message.warning('请先分别完成 PC 预览和 APP 预览验证');
        return;
      }
    }
    const preparedParams = recordOf(savePreparePayload?.params);
    const payload = normalizeDraft(preparedParams || draft, draft.assetType || assetType);
    if (payload.assetType === 'CARD_COMPONENT') {
      payload.dslType = DSL_TYPE_CARD_CONTAINER;
      payload.agentUiDsl = '';
      if (!payload.id && !assetId) {
        payload.enabled = true;
      }
    }
    setSaving(true);
    try {
      const saved =
        payload.id || assetId
          ? await componentCenterApi.update({
              ...payload,
              id: Number(payload.id || assetId),
            } as SkillFactoryComponentAsset)
          : await componentCenterApi.register(payload as SkillFactoryComponentAsset);
      setDraft(normalizeDraft(saved, saved.assetType || assetType));
      setFormRevision((current) => current + 1);
      proposalBaselinesRef.current?.clear?.();
      clearPendingReview();
      message.success(payload.id || assetId ? '组件资产已更新' : '组件资产已注册');
      if (isCardContainerAsset) {
        const nextSearchParams = new URLSearchParams(searchParams.toString());
        nextSearchParams.set('assetType', saved.assetType || 'CARD_COMPONENT');
        nextSearchParams.set('assetId', String(saved.id));
        nextSearchParams.set('step', 'release');
        nextSearchParams.delete('id');
        setCardStep(3);
        navigate(`${location.pathname}?${nextSearchParams.toString()}`, { replace: true });
      } else {
        navigate(`/management/components/detail?id=${saved.id}&tab=release`);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
      if (assetId) await assetAccess.refresh();
    } finally {
      setSaving(false);
    }
  };

  const confirmCardBasicInfo = async () => {
    if (!isCardBasicReady(draft)) {
      message.warning('请先填写组件 code、中文名、交互类型、PC/APP bundleUrl 和适用场景');
      return;
    }
    if (assetId && releaseEditDisabledReason) {
      message.warning(releaseEditDisabledReason);
      return;
    }
    if (assetId) {
      const payload = normalizeDraft(draft, draft.assetType || assetType);
      payload.dslType = DSL_TYPE_CARD_CONTAINER;
      payload.agentUiDsl = '';
      setSavingBasicInfo(true);
      try {
        const saved = await componentCenterApi.updateBasicInfo({
          ...payload,
          id: Number(assetId),
        } as SkillFactoryComponentAsset);
        setDraft((current) =>
          normalizeDraft(
            {
              ...current,
              id: saved.id,
              componentNameCn: saved.componentNameCn,
              interactionMode: saved.interactionMode,
              bundleUrl: saved.bundleUrl,
              appBundleUrl: saved.appBundleUrl,
              scene: saved.scene,
              operator: saved.operator,
              updateTime: saved.updateTime,
            },
            saved.assetType || assetType,
          ),
        );
        setFormRevision((current) => current + 1);
        proposalBaselinesRef.current?.clear?.();
        clearPendingReview();
        setValidationPayload(undefined);
        setPreviewPayload(undefined);
        setSavePreparePayload(undefined);
        message.success('基础信息已保存');
      } catch (error) {
        message.error(error instanceof Error ? error.message : '基础信息保存失败');
        await assetAccess.refresh();
        return;
      } finally {
        setSavingBasicInfo(false);
      }
    }
    setCardStep(2);
  };

  const goCardStep = (nextStep: CardAuthoringStep) => {
    if (nextStep === 3 && !assetId) {
      message.warning('请先保存组件，再进入发布管理');
      return;
    }
    setCardStep(nextStep);
  };

  const businessSidePanel = (
    <div className="component-authoring-side">
      <Card title="当前草稿" className="component-authoring-side-card">
        {draft.componentName || draft.componentNameCn ? (
          <div className="component-authoring-draft-title">
            <strong>{draft.componentNameCn || draft.componentName}</strong>
            <span>
              {isCardContainerAsset ? draft.componentName || '-' : draft.agentUiDsl || '-'}
            </span>
          </div>
        ) : (
          <Empty description="先描述要创建的组件或编排" />
        )}
        <Space wrap>
          <Tag color="blue">{draft.assetType || assetType}</Tag>
          <Tag>{draft.dslType || '-'}</Tag>
          <Tag color={draft.enabled ? 'success' : 'warning'}>
            {draft.enabled ? '可引用' : '不可引用'}
          </Tag>
        </Space>
      </Card>
      <DraftFieldSummary draft={draft} />
      {validationPayload ? (
        <Card title="校验结果" className="component-authoring-side-card">
          <JsonBlock value={validationPayload} />
        </Card>
      ) : null}
      {previewPayload || localPreview ? (
        <Card title="预览结果" className="component-authoring-side-card">
          <JsonBlock value={previewPayload || localPreview} />
        </Card>
      ) : null}
      {savePreparePayload ? (
        <Card title="待确认保存参数" className="component-authoring-side-card">
          <JsonBlock value={savePreparePayload} />
        </Card>
      ) : null}
      <Card className="component-authoring-side-card">
        <Space wrap>
          <Button icon={<EyeOutlined />} onClick={() => handlePreview('PC')}>
            预览草稿
          </Button>
        </Space>
      </Card>
    </div>
  );

  const cardContainerAuthoringPanel = isCardContainerAsset ? (
    <div className="component-card-authoring-panel">
      <div className="component-card-steps" role="tablist" aria-label="渲染组件注册步骤">
        <button
          type="button"
          className={cardStep === 1 ? 'active' : cardStep > 1 ? 'done' : ''}
          onClick={() => goCardStep(1)}
        >
          <span>1</span>
          <strong>基础信息</strong>
        </button>
        <button
          type="button"
          className={cardStep === 2 ? 'active' : cardStep > 2 ? 'done' : ''}
          onClick={() => goCardStep(2)}
        >
          <span>2</span>
          <strong>模板与预览</strong>
        </button>
        <button
          type="button"
          className={cardStep === 3 ? 'active' : ''}
          disabled={!assetId}
          onClick={() => goCardStep(3)}
        >
          <span>3</span>
          <strong>发布管理</strong>
        </button>
      </div>

      {cardStep === 1 ? (
        <Card
          title="基础信息"
          extra={
            <Button
              type="primary"
              loading={savingBasicInfo}
              onClick={() => void confirmCardBasicInfo()}
            >
              确定
            </Button>
          }
        >
          <div className="component-card-config-bar step-mode">
            <label>
              <span>组件 code</span>
              <Input
                value={draft.componentName || ''}
                placeholder="例如 StoreDiagnostic"
                disabled={Boolean(assetId)}
                onChange={(event) => {
                  const value = event.target.value;
                  setComponentCodeInput(value);
                  setLocalPreview(undefined);
                  setPreviewRequestError('');
                  setCardPreviewPassed({ PC: false, APP: false });
                  setDraft((prev) => ({
                    ...prev,
                    componentName: value,
                    dslType: DSL_TYPE_CARD_CONTAINER,
                  }));
                  setFormRevision((current) => current + 1);
                }}
              />
            </label>
            <label>
              <span>组件中文名</span>
              <Input
                value={draft.componentNameCn || ''}
                placeholder="例如 店铺诊断卡片"
                onChange={(event) => updateDraftField('componentNameCn', event.target.value)}
              />
            </label>
            <label>
              <span>交互类型</span>
              <Select
                value={draft.interactionMode || INTERACTION_MODE_DISPLAY_ONLY}
                options={INTERACTION_MODE_OPTIONS}
                onChange={(value) => updateDraftField('interactionMode', String(value))}
              />
            </label>
            <label>
              <span>PC bundleUrl</span>
              <Input
                value={draft.bundleUrl || ''}
                placeholder="PC 前端组件包地址"
                onChange={(event) => updateDraftField('bundleUrl', event.target.value)}
              />
            </label>
            <label>
              <span>APP bundleUrl</span>
              <Input
                value={draft.appBundleUrl || ''}
                placeholder="APP 前端组件包地址"
                onChange={(event) => updateDraftField('appBundleUrl', event.target.value)}
              />
            </label>
            <label>
              <span>适用场景</span>
              <Input
                value={draft.scene || ''}
                placeholder="例如 店铺诊断结果展示"
                onChange={(event) => updateDraftField('scene', event.target.value)}
              />
            </label>
            <Tag color="blue">dslType 固定 {DSL_TYPE_CARD_CONTAINER}</Tag>
          </div>
        </Card>
      ) : cardStep === 2 ? (
        <>
          <div className="component-card-basic-summary">
            <div className="component-card-summary-item">
              <span>组件 code</span>
              <strong>{draft.componentName || '-'}</strong>
            </div>
            <div className="component-card-summary-item">
              <span>组件名称</span>
              <strong>{draft.componentNameCn || '-'}</strong>
            </div>
            <div className="component-card-summary-item">
              <span>适用场景</span>
              <strong>{draft.scene || '-'}</strong>
            </div>
            <div className="component-card-summary-item">
              <span>交互类型</span>
              <strong>
                {draft.interactionMode === INTERACTION_MODE_INTERACTIVE ? '需交互' : '纯展示'}
              </strong>
            </div>
            <div className="component-card-summary-item component-card-summary-url">
              <span>PC bundleUrl</span>
              <strong title={draft.bundleUrl || '-'}>{draft.bundleUrl || '-'}</strong>
            </div>
            <div className="component-card-summary-item component-card-summary-url">
              <span>APP bundleUrl</span>
              <strong title={draft.appBundleUrl || '-'}>{draft.appBundleUrl || '-'}</strong>
            </div>
            <Button size="small" onClick={() => goCardStep(1)}>
              修改
            </Button>
          </div>

          <div className="component-card-reference-grid">
            <Card title="模型 Tool 调用参数" className="component-card-reference-card">
              <Text type="secondary">
                这里只维护 render_component arguments JSON；不要填写 bundle、模板、身份或 Marker。
              </Text>
              <JsonFormatTextArea
                value={draft.messageDemoJson || ''}
                onChange={(event) => updateDraftField('messageDemoJson', event.target.value)}
                onValueChange={(value) => updateDraftField('messageDemoJson', value)}
                className="component-card-reference-editor"
              />
            </Card>
            <Card title="官方 card-container 结果" className="component-card-reference-card">
              <Text type="secondary">
                这里只维护最终 card-container payload 的 data 对象；公共外壳由 Adviser
                运行时统一补齐。
              </Text>
              <JsonFormatTextArea
                value={draft.officialDemoJson || ''}
                onChange={(event) => updateDraftField('officialDemoJson', event.target.value)}
                onValueChange={(value) => updateDraftField('officialDemoJson', value)}
                className="component-card-reference-editor"
              />
            </Card>
          </div>

          <div className="component-card-schema-template-grid">
            <Card
              title={
                <Space>
                  <span>paramsSchemaJson</span>
                  <Tag color="blue">手动配置</Tag>
                </Space>
              }
              className="component-card-schema-card"
            >
              <Text type="secondary">
                只描述 Tool arguments.params。预览和运行态都会先按该 Schema 校验，再执行转换模板。
              </Text>
              <JsonFormatTextArea
                value={draft.paramsSchemaJson || ''}
                onChange={(event) => updateDraftField('paramsSchemaJson', event.target.value)}
                onValueChange={(value) => updateDraftField('paramsSchemaJson', value)}
                className="component-card-schema-editor"
              />
            </Card>

            <Card
              title={
                <Space>
                  <span>转换模板</span>
                  <Tag color="blue">手动配置</Tag>
                </Space>
              }
              className="component-card-template-card"
            >
              <Text type="secondary">
                这里只维护生成最终 data 对象的模板；bundle、组件身份和公共外壳由 Adviser 可信补齐。
              </Text>
              <Input.TextArea
                value={draft.renderTemplateJson || ''}
                onChange={(event) => updateDraftField('renderTemplateJson', event.target.value)}
                className="component-card-template-editor"
              />
            </Card>
          </div>

          <Card title="实时预览" className="component-card-preview-card">
            <div className="component-card-preview-layout">
              <div className="component-card-render-frame">
                <Spin spinning={previewing}>
                  <DynamicCardContainerPreview
                    result={localPreview}
                    clientType={previewClientType}
                  />
                </Spin>
              </div>
              <div className="component-card-preview-control">
                <Space wrap className="component-card-preview-actions">
                  <Button
                    icon={<EyeOutlined />}
                    loading={previewing && previewClientType === 'PC'}
                    disabled={previewing && previewClientType !== 'PC'}
                    onClick={() => handlePreview('PC')}
                  >
                    PC 预览
                  </Button>
                  <Button
                    icon={<EyeOutlined />}
                    loading={previewing && previewClientType === 'APP'}
                    disabled={previewing && previewClientType !== 'APP'}
                    onClick={() => handlePreview('APP')}
                  >
                    APP 预览
                  </Button>
                </Space>
                {localPreview || previewRequestError ? (
                  <div className="component-card-preview-state">
                    {localPreview ? (
                      <Space wrap>
                        <Tag color="blue">{previewClientType} 预览</Tag>
                        <Tag color={localPreview.valid ? 'success' : 'error'}>
                          {localPreview.valid ? '校验通过' : '校验失败'}
                        </Tag>
                        <Tag>{localPreview.renderProtocol || 'CARD_CONTAINER'}</Tag>
                        <Tag>{localPreview.componentName || '-'}</Tag>
                      </Space>
                    ) : null}
                    {[
                      ...(localPreview?.errors || []),
                      ...(previewRequestError ? [previewRequestError] : []),
                    ].length ? (
                      <div className="component-card-preview-errors">
                        {[
                          ...(localPreview?.errors || []),
                          ...(previewRequestError ? [previewRequestError] : []),
                        ].map((item) => {
                          const errorMessage = componentPreviewErrorMessage(item);
                          return (
                            <div className="component-card-preview-error-item" key={item}>
                              <strong>{errorMessage.title}</strong>
                              <span>{errorMessage.guidance}</span>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="component-card-preview-guide">
                    填写并审阅 Schema 与转换模板后，分别运行 PC 和 APP
                    预览；两端都通过后才能保存组件。
                  </div>
                )}
                <Space wrap className="component-card-preview-terminal-state">
                  <Tag color={cardPreviewPassed.PC ? 'success' : 'default'}>
                    PC {cardPreviewPassed.PC ? '已通过' : '待验证'}
                  </Tag>
                  <Tag color={cardPreviewPassed.APP ? 'success' : 'default'}>
                    APP {cardPreviewPassed.APP ? '已通过' : '待验证'}
                  </Tag>
                </Space>
              </div>
            </div>
          </Card>
        </>
      ) : (
        <AssetReleaseTab
          assetKey={assetId}
          assetType="COMPONENT"
          title="组件发布管理"
          onOverviewChange={releaseEditability.acceptOverview}
        />
      )}
    </div>
  ) : null;

  const authoringChat = (
    <SkillFactoryAuthoringChat
      title={
        <Space>
          <ThunderboltOutlined />
          <span>{isCardContainerAsset ? 'AI 模板助手' : '创建业务编排'}</span>
        </Space>
      }
      chat={chat}
      onOpenReview={(changeSetId) => {
        const review = formPatchReviews[changeSetId];
        if (!review) {
          message.info('该表单修改建议不属于当前组件草稿。');
          return;
        }
        setPendingReviewChangeSetId(changeSetId);
        setSelectedChangeIds(
          new Set(
            review?.changes
              ?.filter?.((change) => change.status === 'safe')
              ?.map?.((change) => change.id),
          ),
        );
        setConflictChoices({});
        setRailOpen(true);
        setRailView('review');
      }}
      changeReviewStatuses={changeReviewStatuses}
      extra={<Tag color="blue">{assetId ? '编辑草稿' : '创建草稿'}</Tag>}
      placeholder={
        isCardContainerAsset
          ? '请说明 params 参数的必填/非必填约束，AI 将结合 Tool 调用参数和渲染结果生成或检查 paramsSchemaJson 与转换模板...'
          : '描述业务目标、agentUiDsl、params 字段和 A2UI 模板转换...'
      }
    />
  );
  const formPatchReview = pendingReview ? (
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
        targetLabel: '当前组件表单草稿',
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
  ) : undefined;
  const businessDslPanel = !isCardContainerAsset ? (
    <div className="component-business-authoring-main">
      <Card className="component-authoring-side-card">
        <Space align="center" wrap>
          <Text strong>agentUiDsl</Text>
          <Input
            value={componentCodeInput}
            style={{ width: 320 }}
            disabled={Boolean(assetId)}
            placeholder="例如 live_stream_selector"
            onChange={(event) => {
              const value = event.target.value;
              setComponentCodeInput(value);
              setDraft((prev) => ({
                ...prev,
                agentUiDsl: value,
                dslType: DSL_TYPE_BUSINESS_DSL,
              }));
              setFormRevision((current) => current + 1);
            }}
          />
          <Text type="secondary">BUSINESS_DSL 使用 agentUiDsl 查找运行态模板。</Text>
        </Space>
      </Card>
      {businessSidePanel}
    </div>
  ) : null;

  return (
    <div className="page-container component-authoring-page">
      <div className="page-header component-authoring-header">
        <div>
          <h1 className="page-title">
            {isCardContainerAsset ? '注册渲染组件' : '创建业务编排'}
          </h1>
          <p className="page-subtitle">
            {isCardContainerAsset
              ? '把 Skill 结构化输出和前端卡片 JSON 对齐成 adviser 可执行模板'
              : '手动填写编排草稿，验证后保存到组件中心'}
          </p>
        </div>
        <Space>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/management/components')}
          >
            返回组件中心
          </Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} disabled={Boolean(releaseEditDisabledReason) || (isCardContainerAsset && (!cardPreviewPassed.PC || !cardPreviewPassed.APP))} onClick={handleConfirmSave}>
            确认保存
          </Button>
        </Space>
      </div>



      {pageError ? <Alert type="error" message={pageError} style={{ marginBottom: 12 }} /> : null}
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

      <Spin spinning={loadingAsset}>
        {isCardContainerAsset && cardStep === 3 ? (
          cardContainerAuthoringPanel
        ) : (
          <AuthoringWorkbenchLayout
            railOpen={railOpen}
            railView={railView}
            onRailOpenChange={setRailOpen}
            onRailViewChange={setRailView}
            railTitle={isCardContainerAsset ? 'AI 模板助手' : 'AI 编排助手'}
            reviewCount={pendingReview?.changes?.length || 0}
            review={formPatchReview}
            chat={authoringChat}
            className="component-authoring-workbench"
          >
            {isCardContainerAsset ? cardContainerAuthoringPanel : businessDslPanel}
          </AuthoringWorkbenchLayout>
        )}
      </Spin>
    </div>
  );
};

export default ComponentAssetAuthoringPage;
