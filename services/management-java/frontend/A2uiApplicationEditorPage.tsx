import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { jsonStringify } from './shared/safeJson';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  a2uiApplicationApi,
  a2uiCatalogApi,
  a2uiCatalogComponentApi,
  SKILL_FACTORY_CHAT_BIZ_KEYS,
  skillBindingCandidateApi,
  skillFactoryApi,
  type CapabilityActionDraft,
} from './api';
import {
  createEmptyA2uiApplicationDraft,
  parseA2uiApplicationForm,
  projectA2uiApplicationActionScanResult,
  toA2uiApplicationFormValues,
  type A2uiApplicationActionScanResult,
  type A2uiActionBinding,
  type A2uiApplicationBlueprintOption,
  type A2uiApplicationDraft,
  type A2uiApplicationBlueprintCode,
  type A2uiApplicationFormValues,
  type A2uiInteractionMode,
  type A2uiApplicationRecord,
} from './a2uiApplicationContracts';
import {
  A2UI_CATALOG_SOURCE_LABELS,
  a2uiPublishedCatalogOptionValue,
  a2uiApplicationEditorRoute,
  a2uiApplicationIdFromSearchParams,
  a2uiApplicationListRoute,
  collectPublishedA2uiCatalogOptions,
  type A2uiCatalogComponentRecord,
  type A2uiCatalogRecord,
  type A2uiPublishedCatalogOption,
} from './a2uiCatalogContracts';
import { buildDetailedA2uiContractPreview } from './a2uiApplicationPreview';
import A2uiApplicationRendererPreview from './A2uiApplicationRendererPreview';
import A2uiApplicationPrtPreview from './A2uiApplicationPrtPreview';
import {
  buildA2uiApplicationLocalPreview,
  buildA2uiLocalActionSummary,
  buildA2uiSampleParams,
  type A2uiLocalActionSummary,
} from './a2uiApplicationLocalPreview';
import {
  extractShowComponents,
  type A2uiExtractedComponent,
  type A2uiShowTemplate,
} from './a2uiApplicationShowAst';
import {
  validateA2uiApplicationBuildIssues,
  type A2uiApplicationValidationIssue,
} from './a2uiApplicationValidationIssues';
import {
  A2UI_APPLICATION_EDITOR_STAGES,
  buildA2uiActionClosureRows,
  buildA2uiActionHttpRequest,
  buildA2uiApplicationToolInvocation,
  buildA2uiPublicEventEnvelope,
  createA2uiApplicationEditorViewModel,
  createA2uiValidationPreviewViewModel,
  resolveA2uiApplicationReleaseAssetKey,
  type A2uiActionClosureRow,
  type A2uiApplicationEditableStage,
  type A2uiApplicationEditorStage,
} from './a2uiApplicationEditorModel';
import { A2UI_APPLICATION_STAGE_FORM_FIELDS } from './a2uiApplicationForm';
import JsonFormatTextArea from './shared/JsonFormatTextArea';
import A2uiActionAuthoringEditor from './A2uiActionAuthoringEditor';
import A2uiShowAuthoringEditor from './A2uiShowAuthoringEditor';
import AssetReleaseTab from './shared/AssetReleaseTab';
import AuthoringWorkbenchLayout, {
  type AuthoringRailView,
} from './shared/AuthoringWorkbenchLayout';
import { SkillFactoryAuthoringChat, useSkillFactoryChatStream } from './shared/authoringChat';
import { createA2uiApplicationAuthoringAdapter } from './shared/authoringChat/adapters/a2uiApplicationAdapter';

const { Paragraph, Text } = Typography;

function previewJson(value: unknown): string {
  return jsonStringify(value, null, 2) || '{}';
}

function serverIssues(errors: string[]): A2uiApplicationValidationIssue[] {
  return [...new Set(errors)].map((code) => ({ code, path: '$.server' }));
}

function applicationDraftContractError(application: A2uiApplicationDraft): string | undefined {
  const source = application as unknown as Record<string, unknown>;
  const showTemplate = source.showTemplate;
  if (!showTemplate || Array.isArray(showTemplate) || typeof showTemplate !== 'object') {
    return 'Application 草稿字段 $.showTemplate 缺失或不是对象，已阻止编辑与预览';
  }
  const show = showTemplate as Record<string, unknown>;
  const requiredArrays: Array<[string, unknown]> = [
    ['$.showTemplate.surfaceDeclarations', show.surfaceDeclarations],
    ['$.showTemplate.messageTemplates', show.messageTemplates],
    ['$.showTemplate.inputBindings', show.inputBindings],
    ['$.loadBindings', source.loadBindings],
    ['$.actionBindings', source.actionBindings],
  ];
  const invalidField = requiredArrays.find(([, value]) => !Array.isArray(value));
  return invalidField
    ? `Application 草稿字段 ${invalidField?.[0]} 缺失或不是数组，已阻止编辑与预览`
    : undefined;
}

function projectCatalogSelection<TApplication extends A2uiApplicationDraft>(
  application: TApplication,
  options: A2uiPublishedCatalogOption[],
): TApplication {
  const option = options.find(
    (candidate) => candidate.catalogId === application.catalog?.catalogId,
  );
  if (!option) {
    return {
      ...application,
      catalog: {
        ...application.catalog,
        revision: application.catalog?.revision || '',
        digest: application.catalog?.digest || '',
      },
    } as TApplication;
  }
  return {
    ...application,
    catalog: {
      catalogId: option.catalogId,
      revision: option.revision,
      digest: option.digest,
      catalogSourceType: option.catalogSourceType,
      componentTypes: option.componentTypes,
      componentOrigins: option.componentOrigins,
      releases: option.releases,
    },
  } as TApplication;
}

const A2uiApplicationEditorPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const id = a2uiApplicationIdFromSearchParams(searchParams);
  const [form] = Form.useForm();
  const [record, setRecord] = useState<A2uiApplicationRecord>();
  const [draft, setDraft] = useState<A2uiApplicationDraft>(createEmptyA2uiApplicationDraft());
  const [savedDraft, setSavedDraft] = useState<A2uiApplicationDraft>(
    createEmptyA2uiApplicationDraft(),
  );
  const [catalogComponents, setCatalogComponents] = useState<A2uiCatalogComponentRecord[]>([]);
  const [catalogs, setCatalogs] = useState<A2uiCatalogRecord[]>([]);
  const [capabilityActions, setCapabilityActions] = useState<CapabilityActionDraft[]>([]);
  const [capabilityActionError, setCapabilityActionError] = useState('');
  const [validationIssues, setValidationIssues] = useState<A2uiApplicationValidationIssue[]>([]);
  const [activeStage, setActiveStage] = useState<A2uiApplicationEditorStage>('basic');
  const [validationPreviewMode, setValidationPreviewMode] = useState<'structure' | 'visual' | 'prt'>(
    'visual',
  );
  const [sampleParamsJson, setSampleParamsJson] = useState('{}');
  const [localActionSummary, setLocalActionSummary] = useState<A2uiLocalActionSummary>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scanningActions, setScanningActions] = useState(false);
  const [importingBlueprint, setImportingBlueprint] = useState(false);
  const [loadingBlueprints, setLoadingBlueprints] = useState(false);
  const [blueprints, setBlueprints] = useState<A2uiApplicationBlueprintOption[]>([]);
  const [blueprintError, setBlueprintError] = useState('');
  const [blueprintCode, setBlueprintCode] = useState<A2uiApplicationBlueprintCode>();
  const [actionScan, setActionScan] = useState<A2uiApplicationActionScanResult>();
  const [error, setError] = useState('');
  const [authoringAgentId, setAuthoringAgentId] = useState('');
  const [authoringOwnerId, setAuthoringOwnerId] = useState<string>();
  const [authoringConfigDisabledReason, setAuthoringConfigDisabledReason] =
    useState('AI 辅助配置加载中');
  const [authoringRailOpen, setAuthoringRailOpen] = useState(false);
  const [authoringRailView, setAuthoringRailView] = useState<AuthoringRailView>('chat');
  const [authoringDraftId] = useState(
    () => `a2ui_application_${Date.now()}_${Math.random()?.toString(36)?.slice?.(2, 8)}`,
  );
  const publishedCatalogOptions = useMemo(
    () => collectPublishedA2uiCatalogOptions(catalogs),
    [catalogs],
  );
  const publishedCatalogSelectOptions = useMemo(
    () =>
      publishedCatalogOptions.map((option) => ({
        value: a2uiPublishedCatalogOptionValue(option),
        label: `${A2UI_CATALOG_SOURCE_LABELS[option.catalogSourceType]} · ${option.catalogId}@${
          option.revision
        }`,
      })),
    [publishedCatalogOptions],
  );
  const capabilityActionSelectOptions = useMemo(() => {
    const options = new Map<string, { value: string; label: string }>();
    capabilityActions.forEach((record) => {
      const actionCode = record.draft?.basicInfo?.actionCode?.trim();
      if (!actionCode || options.has(actionCode)) return;
      const nameCn = record.draft?.basicInfo?.nameCn?.trim?.();
      options.set(actionCode, {
        value: actionCode,
        label: nameCn ? `${actionCode} · ${nameCn}` : actionCode,
      });
    });
    return [...options.values()].sort((left, right) => left.value?.localeCompare?.(right.value));
  }, [capabilityActions]);
  const selectedCatalogOption = useMemo(
    () => publishedCatalogOptions.find((option) => option.catalogId === draft.catalog?.catalogId),
    [draft.catalog, publishedCatalogOptions],
  );
  const catalogSelectOptions = useMemo(() => {
    const options = publishedCatalogOptions.map((option) => ({
      value: a2uiPublishedCatalogOptionValue(option),
      label: `${A2UI_CATALOG_SOURCE_LABELS[option.catalogSourceType]} · ${option.catalogId}@${
        option.revision
      } · ${option.digest}`,
    }));
    const draftCatalogId = draft.catalog?.catalogId?.trim?.();
    if (
      draftCatalogId &&
      !publishedCatalogOptions.some((option) => option.catalogId === draftCatalogId)
    ) {
      options.push({
        value: draftCatalogId,
        label: `模板指定 · ${draftCatalogId}（待发布闭合）`,
      });
    }
    return options;
  }, [draft.catalog?.catalogId, publishedCatalogOptions]);
  const selectedBlueprint = useMemo(
    () => blueprints.find((blueprint) => blueprint.blueprintCode === blueprintCode),
    [blueprintCode, blueprints],
  );

  const applyWorkingProjection = useCallback(
    (application: A2uiApplicationDraft, components: A2uiCatalogComponentRecord[]) => {
      setDraft(application);
      setValidationIssues(validateA2uiApplicationBuildIssues(application, components));
    },
    [],
  );

  const applyCanonicalProjection = useCallback((application: A2uiApplicationRecord) => {
    const canonicalActionScan = application.actionScan
      ? projectA2uiApplicationActionScanResult(application.actionScan)
      : undefined;
    setDraft(application);
    setActionScan(canonicalActionScan);
    setValidationIssues(
      serverIssues(
        canonicalActionScan
          ? [...canonicalActionScan.validationErrors, ...canonicalActionScan.releaseBlockers]
          : ['A2UI_ACTION_SCAN_PROJECTION_MISSING'],
      ),
    );
  }, []);

  const loadEditor = useCallback(async () => {
    setLoading(true);
    setError('');
    if (!id) {
      const emptyApplication = createEmptyA2uiApplicationDraft();
      setSavedDraft(emptyApplication);
      form.setFieldsValue(toA2uiApplicationFormValues(emptyApplication));
      setActionScan(undefined);
      applyWorkingProjection(emptyApplication, []);
    }
    try {
      const [loadedCatalogs, components, loaded] = await Promise.all([
        a2uiCatalogApi.list(),
        a2uiCatalogComponentApi.list(),
        id ? a2uiApplicationApi.detail(id) : Promise.resolve(undefined),
      ]);
      const catalogOptions = collectPublishedA2uiCatalogOptions(loadedCatalogs);
      const application = projectCatalogSelection(
        loaded || createEmptyA2uiApplicationDraft(),
        catalogOptions,
      );
      setCatalogs(loadedCatalogs);
      setCatalogComponents(components);
      setSampleParamsJson(
        previewJson(buildA2uiSampleParams(application.showTemplate.paramsSchema).params),
      );
      if (loaded) {
        const canonicalRecord = {
          ...loaded,
          ...application,
          actionScan: loaded.actionScan,
        };
        applyCanonicalProjection(canonicalRecord);
        setRecord(canonicalRecord);
        setSavedDraft(canonicalRecord);
        form.setFieldsValue(toA2uiApplicationFormValues(canonicalRecord));
      } else {
        setRecord(undefined);
        setSavedDraft(application);
        form.setFieldsValue(toA2uiApplicationFormValues(application));
        applyWorkingProjection(application, components);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'A2UI Application 编辑器加载失败');
    } finally {
      setLoading(false);
    }
  }, [applyCanonicalProjection, applyWorkingProjection, form, id]);

  useEffect(() => {
    loadEditor();
  }, [loadEditor]);

  useEffect(() => {
    let active = true;
    setCapabilityActionError('');
    skillBindingCandidateApi
      .capabilityList()
      .then((items) => {
        if (active) setCapabilityActions(items);
      })
      .catch((reason) => {
        if (!active) return;
        setCapabilityActions([]);
        setCapabilityActionError(
          reason instanceof Error ? reason.message : '当前环境 CapabilityAction 列表加载失败',
        );
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    if (id) {
      setBlueprints([]);
      setBlueprintError('');
      return () => {
        active = false;
      };
    }
    setLoadingBlueprints(true);
    setBlueprintError('');
    a2uiApplicationApi
      .listBlueprints()
      .then((items) => {
        if (!active) return;
        setBlueprints(items);
      })
      .catch((reason) => {
        if (!active) return;
        setBlueprints([]);
        setBlueprintError(reason instanceof Error ? reason.message : '平台示例模板列表加载失败');
      })
      .finally(() => {
        if (active) setLoadingBlueprints(false);
      });
    return () => {
      active = false;
    };
  }, [id]);



  const readFormApplication = async (): Promise<A2uiApplicationDraft | undefined> => {
    await form.validateFields();
    const values = form.getFieldsValue(true) as A2uiApplicationFormValues;
    const parsed = parseA2uiApplicationForm(values);
    if (parsed.ok === false) {
      setValidationIssues(parsed.errors?.map?.((code) => ({ code, path: '$' })));
      message.error(`Application JSON 校验失败：${parsed.errors?.join?.('、')}`);
      return undefined;
    }
    const parsedApplication =
      parsed.application?.catalog?.catalogId === draft.catalog?.catalogId
        ? { ...parsed.application, catalog: draft.catalog }
        : parsed.application;
    const projectedApplication = projectCatalogSelection(
      parsedApplication,
      publishedCatalogOptions,
    );
    applyWorkingProjection(projectedApplication, catalogComponents);
    return projectedApplication;
  };

  const handleRefreshPreview = async () => {
    const application = await readFormApplication();
    if (application) message.success('本地预览已刷新（未调用业务接口）');
  };

  const handleSaveStage = async (stage: A2uiApplicationEditableStage) => {
    if (!record && stage !== 'basic') {
      message.warning('请先保存基础信息，再保存当前 Tab');
      setActiveStage('basic');
      return;
    }
    const fieldNames = A2UI_APPLICATION_STAGE_FORM_FIELDS[stage];
    try {
      await form.validateFields(fieldNames);
    } catch {
      return;
    }
    const values = form.getFieldsValue(true) as A2uiApplicationFormValues;
    const parsed = parseA2uiApplicationForm(values, {
      baseApplication: savedDraft,
      stage,
    });
    if (parsed.ok === false) {
      setValidationIssues(parsed.errors?.map?.((code) => ({ code, path: '$' })));
      message.error(`当前 Tab JSON 校验失败：${parsed.errors?.join?.('、')}`);
      return;
    }
    const application = projectCatalogSelection(parsed.application, publishedCatalogOptions);
    setSaving(true);
    try {
      const saved = record
        ? await a2uiApplicationApi.update(record.id, application)
        : await a2uiApplicationApi.create(application);
      const canonical = projectCatalogSelection(saved, publishedCatalogOptions);
      applyCanonicalProjection(canonical);
      setRecord(canonical);
      setSavedDraft(canonical);
      const savedValues = toA2uiApplicationFormValues(canonical);
      const savedStageValues = fieldNames.reduce<Partial<A2uiApplicationFormValues>>(
        (result, fieldName) => ({ ...result, [fieldName]: savedValues[fieldName] }),
        {},
      );
      form.setFieldsValue(savedStageValues);
      message.success(
        `${
          A2UI_APPLICATION_EDITOR_STAGES?.find((item) => item.id === stage)?.label || '当前 Tab'
        }已保存`,
      );
      if (!id) {
        navigate(a2uiApplicationEditorRoute(saved.id, searchParams), {
          replace: true,
        });
      }
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : 'A2UI Application 保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleImportBlueprint = async () => {
    if (!blueprintCode) {
      message.warning('请选择平台示例模板');
      return;
    }
    setImportingBlueprint(true);
    try {
      const imported = projectCatalogSelection(
        await a2uiApplicationApi.importBlueprint(blueprintCode),
        publishedCatalogOptions,
      );
      setSavedDraft(imported);
      form.setFieldsValue(toA2uiApplicationFormValues(imported));
      setActionScan(undefined);
      applyWorkingProjection(imported, catalogComponents);
      message.success('样板已载入当前编辑器，尚未保存');
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '平台示例模板导入失败');
    } finally {
      setImportingBlueprint(false);
    }
  };

  const handleScanActions = async () => {
    setScanningActions(true);
    try {
      const application = await readFormApplication();
      if (!application) return;
      setActionScan(undefined);
      const scanned = await a2uiApplicationApi.scanActions(application);
      setActionScan(scanned);
      setValidationIssues(serverIssues([...scanned.validationErrors, ...scanned.releaseBlockers]));
      message.success('Action 扫描完成；当前草稿尚未保存');
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : 'Action 扫描失败');
    } finally {
      setScanningActions(false);
    }
  };

  const handleStructuredShowTemplateChange = (showTemplate: A2uiShowTemplate) => {
    form.setFieldsValue({ showTemplateJson: previewJson(showTemplate) });
    applyWorkingProjection({ ...draft, showTemplate }, catalogComponents);
  };

  const handleStructuredActionBindingsChange = (actionBindings: A2uiActionBinding[]) => {
    form.setFieldsValue({ actionBindingsJson: previewJson(actionBindings) });
    applyWorkingProjection({ ...draft, actionBindings }, catalogComponents);
  };

  const declarations = actionScan?.actionDeclarations || [];
  const contractPreviewState = useMemo(() => {
    const contractError = applicationDraftContractError(draft);
    if (contractError) return { preview: undefined, error: contractError };
    try {
      return { preview: buildDetailedA2uiContractPreview(draft), error: '' };
    } catch (reason) {
      return {
        preview: undefined,
        error:
          reason instanceof Error
            ? `Application 草稿无法生成契约预览：${reason.message}`
            : 'Application 草稿无法生成契约预览，已阻止编辑与预览',
      };
    }
  }, [draft]);
  const contractPreview = contractPreviewState.preview;
  const editorView = createA2uiApplicationEditorViewModel({
    mode: record ? 'edit' : 'create',
    activeStage,
    availableComponentCount: catalogComponents?.filter(
      (item) =>
        item.catalogSourceType === 'PLATFORM_MANAGED' &&
        item.componentOriginType === 'PLATFORM_CUSTOM' &&
        item.release?.enabled === true,
    )?.length,
    interactionGapCount: declarations?.filter((declaration) => declaration.status !== 'BOUND')
      ?.length,
    validationIssueCount: validationIssues.length,
  });
  const sampleParamsPreview = useMemo(() => {
    try {
      const value = JSON.parse(sampleParamsJson) as unknown;
      return value && !Array.isArray(value) && typeof value === 'object'
        ? { params: value as Record<string, unknown>, error: '' }
        : { params: {}, error: 'sample params 必须是 JSON object' };
    } catch {
      return { params: {}, error: 'sample params 不是合法 JSON' };
    }
  }, [sampleParamsJson]);
  const localVisualPreview = useMemo(
    () =>
      sampleParamsPreview.error
        ? { messages: [], errors: [sampleParamsPreview.error], requiredLoadFixtureIds: [] }
        : buildA2uiApplicationLocalPreview(draft, sampleParamsPreview.params),
    [draft, sampleParamsPreview.error, sampleParamsPreview.params],
  );
  const sampleParamDefaults = useMemo(
    () => buildA2uiSampleParams(draft.showTemplate.paramsSchema),
    [draft.showTemplate.paramsSchema],
  );
  const handleLocalAction = useCallback(
    (event: Parameters<typeof buildA2uiLocalActionSummary>[2]) => {
      setLocalActionSummary(buildA2uiLocalActionSummary(draft, sampleParamsPreview.params, event));
    },
    [draft, sampleParamsPreview.params],
  );
  useEffect(() => {
    setLocalActionSummary(undefined);
  }, [draft, sampleParamsJson]);
  const toolInvocation = buildA2uiApplicationToolInvocation(
    draft.appCode || '<appCode>',
    sampleParamsPreview.params,
  );
  const actionClosureRows = buildA2uiActionClosureRows(declarations, draft.actionBindings);
  const completingActionCount = draft?.actionBindings?.filter?.(
    (binding) => binding.completeWorkflowInteractionOnSuccess === true,
  )?.length;
  const workflowInteractionError =
    draft.interactionMode === 'INTERACTIVE' && completingActionCount === 0
      ? 'INTERACTIVE 至少需要一个“成功后完成 Workflow 交互”的 ActionBinding。'
      : draft.interactionMode === 'DISPLAY_ONLY' && completingActionCount > 0
      ? 'DISPLAY_ONLY 不允许 ActionBinding 完成 Workflow 交互。'
      : '';
  const firstDeclaration = declarations?.[0];
  const publicA2uiEventExample = contractPreview
    ? buildA2uiPublicEventEnvelope(contractPreview.messageBatch)
    : undefined;
  const actionRequestExample = firstDeclaration
    ? buildA2uiActionHttpRequest('<conversationId>', '<messageId>', {
        name: firstDeclaration.actionCode,
        surfaceId: firstDeclaration.surfaceId,
        sourceComponentId: firstDeclaration.sourceComponentId,
        timestamp: '<ISO-8601 timestamp>',
        context: { '<field>': '<resolved component value>' },
      })
    : undefined;
  const validationPreview = createA2uiValidationPreviewViewModel(
    validationPreviewMode === 'prt' ? 'visual' : validationPreviewMode,
  );
  const authoringAdapter = useMemo(
    () =>
      createA2uiApplicationAuthoringAdapter<A2uiApplicationDraft>({
        applicationId: record ? String(record.id) : undefined,
        draftId: authoringDraftId,
        appCode: draft.appCode,
        agentId: authoringAgentId,
        ownerId: authoringOwnerId,
        disabledReason: authoringConfigDisabledReason || undefined,
      }),
    [
      authoringAgentId,
      authoringConfigDisabledReason,
      authoringDraftId,
      authoringOwnerId,
      draft.appCode,
      record,
    ],
  );
  const authoringChat = useSkillFactoryChatStream<A2uiApplicationDraft>({
    adapter: authoringAdapter,
    workspaceId: authoringAdapter.sessionScope?.workspaceId || authoringDraftId,
    currentDraft: draft,
  });

  const renderSaveDraftButton = (stage: A2uiApplicationEditableStage) => (
    <Button
      type="primary"
      icon={<SaveOutlined />}
      loading={saving}
      onClick={() => handleSaveStage(stage)}
    >
      保存草稿
    </Button>
  );

  const renderBasicStage = () => (
    <Card title="基础信息">
      {!record ? (
        <Card size="small" title="从平台示例模板创建" style={{ marginBottom: 16 }}>
          <Space wrap>
            <Select
              value={blueprintCode}
              placeholder={loadingBlueprints ? '正在加载平台示例模板' : '选择平台示例模板'}
              loading={loadingBlueprints}
              disabled={loadingBlueprints || !blueprints.length}
              style={{ width: 360 }}
              options={blueprints.map((blueprint) => ({
                value: blueprint.blueprintCode,
                label: blueprint.name,
              }))}
              onChange={(value) => setBlueprintCode(value as A2uiApplicationBlueprintCode)}
            />
            <Button loading={importingBlueprint} onClick={handleImportBlueprint}>
              载入样板
            </Button>
            <Text type="secondary">仅载入普通草稿，不自动创建、不自动发布。</Text>
          </Space>
          {selectedBlueprint ? (
            <Paragraph type="secondary" style={{ margin: '12px 0 0' }}>
              {selectedBlueprint.description} · Catalog {selectedBlueprint.catalogId}
            </Paragraph>
          ) : null}
          {blueprintError ? (
            <Alert
              type="error"
              message="平台示例模板列表不可用"
              description={`${blueprintError}；页面不会使用本地硬编码模板或 Workflow fallback。`}
              style={{ marginTop: 12 }}
            />
          ) : null}
        </Card>
      ) : null}
      <div className="component-center-form-grid">
        <Form.Item
          label="appCode"
          name="appCode"
          rules={[{ required: true, message: '请输入 appCode' }]}
        >
          <Input placeholder="例如 order.confirm.application" />
        </Form.Item>
        <Form.Item
          label="中文名"
          name="nameCn"
          rules={[{ required: true, message: '请输入中文名' }]}
        >
          <Input placeholder="请输入 Application 中文名" />
        </Form.Item>
      </div>
      <Form.Item label="业务说明" name="description">
        <Input.TextArea
          autoSize={{ minRows: 3, maxRows: 8 }}
          placeholder="说明页面用途和使用边界"
        />
      </Form.Item>
      <Form.Item
        label="Workflow 交互模式"
        name="interactionMode"
        rules={[{ required: true, message: '请选择 Workflow 交互模式' }]}
        extra="仅展示：首屏完成后继续 Workflow；交互式：首屏完成后等待用户操作，且至少一个 Action 必须标记为完成交互。"
      >
        <Select
          options={[
            { value: 'DISPLAY_ONLY', label: '仅展示（DISPLAY_ONLY）' },
            { value: 'INTERACTIVE', label: '交互式（INTERACTIVE）' },
          ]}
          onChange={(value) =>
            applyWorkingProjection(
              {
                ...draft,
                interactionMode: value as A2uiInteractionMode,
              },
              catalogComponents,
            )
          }
        />
      </Form.Item>
      <Form.Item
        label="Catalog"
        name="catalogId"
        rules={[{ required: true, message: '请先载入模板或选择服务端 Catalog' }]}
      >
        <Select
          placeholder={
            publishedCatalogOptions.length
              ? '选择 Catalog；revision/digest 由服务端解析'
              : draft.catalog?.catalogId
              ? '模板已指定 Catalog；当前可保存草稿，发布仍需闭合'
              : '先载入服务端模板或等待 Catalog 选项'
          }
          disabled={!catalogSelectOptions.length}
          options={catalogSelectOptions}
        />
      </Form.Item>
      {selectedCatalogOption ? (
        <Space wrap style={{ marginBottom: 12 }}>
          <Tag color="purple">
            {A2UI_CATALOG_SOURCE_LABELS[selectedCatalogOption.catalogSourceType]}
          </Tag>
          <Text type="secondary">
            membership {selectedCatalogOption.componentTypes?.join?.(', ') || '-'}
          </Text>
          <Tag color="success">PRT 已发布</Tag>
          <Tag color={selectedCatalogOption.releases?.ONLINE?.enabled ? 'success' : 'default'}>
            ONLINE {selectedCatalogOption.releases?.ONLINE?.enabled ? '已发布' : '未发布'}
          </Tag>
        </Space>
      ) : (
        <Alert
          type={draft.catalog?.catalogId ? 'info' : 'warning'}
          message={
            draft.catalog?.catalogId
              ? 'Catalog 尚未完成发布闭合，当前仍可保存草稿'
              : '当前草稿还没有 Catalog'
          }
          description={
            draft.catalog?.catalogId
              ? '模板返回的 exact catalogId 已保留；PRT/ONLINE revision 与 digest 由服务端闭合，发布继续 fail closed。'
              : '请先载入服务端模板；不会使用 draft、latest、全局默认或 catalogId 推断。'
          }
          style={{ marginBottom: 12 }}
        />
      )}
      <Alert
        type="info"
        message="Catalog 环境版本是服务端只读投影"
        description={`${draft.catalog?.catalogId || '待选择'} / PRT ${
          draft.catalog?.releases?.PRT?.revision || '未发布'
        } · ${draft.catalog?.releases?.PRT?.digest || '-'} / ONLINE ${
          draft.catalog?.releases?.ONLINE?.revision || '未发布'
        } · ${draft.catalog?.releases?.ONLINE?.digest || '-'}`}
      />
    </Card>
  );

  const renderShowStage = () => (
    <>
      <Card
        title="A2UI 展示编排配置"
        style={{ marginBottom: 16 }}
      >
        <Alert
          type="info"
          message="所有 Application 统一使用专用 Tool；模型业务参数只有 appCode + params。"
          description="不接收 appBuildId、raw messages、Capability endpoint、ResultAdapter、identity、environment、credential 或 script；旧 render_component / CARD_CONTAINER 链路保持平级隔离。"
          style={{ marginBottom: 16 }}
        />
        <Alert
          type="warning"
          message="按钮 action.event.name/context 是唯一作者态真值"
          description="保存后只读抽取 ActionDeclaration；不要在这里或 Action 阶段维护第二份按钮 Action JSON。"
          style={{ marginBottom: 12 }}
        />
        <A2uiShowAuthoringEditor
          showTemplate={draft.showTemplate}
          sampleParamsJson={sampleParamsJson}
          onShowTemplateChange={handleStructuredShowTemplateChange}
          onSampleParamsChange={setSampleParamsJson}
        />
        <Card size="small" title="高级 ShowTemplate JSON" style={{ marginTop: 16 }}>
          <Form.Item
            name="showTemplateJson"
            rules={[{ required: true, message: '请输入 ShowTemplate JSON' }]}
            style={{ marginBottom: 0 }}
          >
            <JsonFormatTextArea autoSize={{ minRows: 18, maxRows: 40 }} />
          </Form.Item>
        </Card>
      </Card>

      <Card title="Tool 与 Input Schema 只读预览" style={{ marginBottom: 16 }}>
        <div className="component-center-preview-grid">
          <Card size="small" title="Tool 调用示例">
            <Paragraph code>render_a2ui_application({'{appCode, params}'})</Paragraph>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{previewJson(toolInvocation)}</pre>
          </Card>
          <Card size="small" title="Application Input Schema">
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
              {previewJson(draft.showTemplate?.paramsSchema)}
            </pre>
          </Card>
        </div>
      </Card>

      <Card title="组件树与数据绑定">
        <Table<A2uiExtractedComponent>
          rowKey={(item) => `${item.surfaceId}:${item.definition?.id}`}
          dataSource={extractShowComponents(draft.showTemplate)}
          pagination={false}
          columns={[
            { title: 'Surface', dataIndex: 'surfaceId' },
            {
              title: '组件 ID',
              render: (_: unknown, item: A2uiExtractedComponent) => item.definition?.id,
            },
            {
              title: '组件 type',
              render: (_: unknown, item: A2uiExtractedComponent) => item.definition?.component,
            },
            {
              title: 'children',
              render: (_: unknown, item: A2uiExtractedComponent) =>
                item.definition?.children?.join?.(', ') || '-',
            },
          ]}
        />
        <Paragraph type="secondary" style={{ marginTop: 16 }}>
          Show input bindings（结构化 source → target）
        </Paragraph>
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
          {previewJson(draft.showTemplate?.inputBindings)}
        </pre>
      </Card>
    </>
  );

  const renderActionStage = () => (
    <>
      <Card
        title="Action 与结果配置"
        extra={
          <Space>
            <Button loading={scanningActions} onClick={handleScanActions}>
              扫描 Action
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Alert
          type="info"
          message="按交互点闭合 ActionBinding → 稳定 actionCode → request mapping → ordered ResultAdapter"
          description="ActionDeclaration 来自服务端递归扫描，只读；CapabilityAction 版本由运行时解析当前生效版本。这里不配置 A2UI 权限、审批、幂等或客户端 revision/ack。"
          style={{ marginBottom: 16 }}
        />
        <Alert
          type={workflowInteractionError ? 'error' : 'success'}
          message={`当前模式：${draft.interactionMode} · 完成交互 Action ${completingActionCount} 个`}
          description={
            workflowInteractionError ||
            '完成标记只在 Capability 成功后生效；失败 Action 不会完成 Workflow 交互。'
          }
          style={{ marginBottom: 16 }}
        />
        {capabilityActionError ? (
          <Alert
            type="error"
            message="当前环境 CapabilityAction 列表加载失败，已禁止手填"
            description={capabilityActionError}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        <A2uiActionAuthoringEditor
          rows={actionClosureRows}
          actionBindings={draft.actionBindings}
          catalogOptions={publishedCatalogSelectOptions}
          capabilityActionOptions={capabilityActionSelectOptions}
          onActionBindingsChange={handleStructuredActionBindingsChange}
        />
        <Card
          size="small"
          title="高级 ActionBinding JSON"
          style={{ marginTop: 16, marginBottom: 16 }}
        >
          <Form.Item
            name="actionBindingsJson"
            rules={[{ required: true, message: '请输入 ActionBindings JSON' }]}
            style={{ marginBottom: 0 }}
          >
            <JsonFormatTextArea autoSize={{ minRows: 18, maxRows: 42 }} />
          </Form.Item>
        </Card>
        <Alert
          type="info"
          message="LoadBinding 只允许 READ；每个 outcome 使用自身 ordered adapters 或显式 NO_UI_MESSAGES。"
          style={{ marginBottom: 12 }}
        />
        <Form.Item
          label="READ LoadBindings JSON"
          name="loadBindingsJson"
          rules={[{ required: true, message: '请输入 LoadBindings JSON' }]}
        >
          <JsonFormatTextArea autoSize={{ minRows: 8, maxRows: 22 }} />
        </Form.Item>
      </Card>

      <Card title="交互闭包预览" style={{ marginBottom: 16 }}>
        <Table<A2uiActionClosureRow>
          rowKey={(item) => `${item.stableKey}:${item.binding?.bindingId || 'unbound'}`}
          dataSource={actionClosureRows}
          pagination={false}
          columns={[
            {
              title: '交互点',
              render: (_: unknown, item: A2uiActionClosureRow) =>
                `${item.declaration?.surfaceId} / ${item.declaration?.sourceComponentId}`,
            },
            {
              title: 'ActionDeclaration',
              render: (_: unknown, item: A2uiActionClosureRow) => item.declaration?.actionCode,
            },
            {
              title: '状态',
              width: 180,
              render: (_: unknown, item: A2uiActionClosureRow) => (
                <Tag
                  color={
                    item.status === 'BOUND'
                      ? 'success'
                      : item.status === 'RESERVED'
                      ? 'error'
                      : 'warning'
                  }
                >
                  {item.status}
                </Tag>
              ),
            },
            {
              title: 'CapabilityAction',
              render: (_: unknown, item: A2uiActionClosureRow) =>
                item.capabilityAction || <Tag color="error">{item.gap || item.status}</Tag>,
            },
            {
              title: 'Mapping / Runtime / Adapters',
              render: (_: unknown, item: A2uiActionClosureRow) =>
                item.status !== 'BOUND' ? (
                  <Tag color="error">{item.gap || '未闭合'}</Tag>
                ) : (
                  <span>
                    {item.requestMappingCount} mappings / {item.policySummary} /{' '}
                    {item.orderedAdapterIds?.join?.('→') || 'NO_UI_MESSAGES'}
                  </span>
                ),
            },
            {
              title: '递归来源',
              render: (_: unknown, item: A2uiActionClosureRow) =>
                item.declaration?.discoveredFrom?.length ? (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                    {previewJson(item.declaration?.discoveredFrom)}
                  </pre>
                ) : (
                  <Text type="secondary">原声明已消失；仅保留 Binding</Text>
                ),
            },
          ]}
        />
      </Card>

      <Card title="只读 ActionDeclaration（服务端递归扫描）" style={{ marginBottom: 16 }}>
        {actionScan ? (
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{previewJson(declarations)}</pre>
        ) : (
          <Alert
            type="warning"
            message="尚未取得服务端 Action 扫描投影"
            description="点击“扫描 Action”分析当前未保存编辑态；页面不会从 demo/runtime payload 或本地 AST 猜测递归 Action。"
          />
        )}
      </Card>
    </>
  );

  const renderValidationStage = () => {
    if (!contractPreview) {
      return (
        <Card title="联调验证">
          <Alert
            type="error"
            message="Application 草稿契约无效"
            description={contractPreviewState.error}
          />
        </Card>
      );
    }
    return (
      <Card title="联调验证">
        <Alert
          type={validationPreviewMode === 'prt' ? 'warning' : 'info'}
          message={validationPreviewMode === 'prt'
            ? 'PRT 真实联调使用已发布 Application，不执行当前未发布草稿'
            : '本页只验证 Application 的本地编排与真实 renderer，不调用 CapabilityAction'}
          description={validationPreviewMode === 'prt'
            ? '启动后 LoadBinding 会真实调用 PRT；每个 Action 执行前都会展示 target userId 与提交 context 并要求确认。'
            : '输入仅使用 sample params；不需要 Cookie、curl 或真实用户凭据。本地模式不执行 LoadBinding；业务按钮只展示事件与映射参数。'}
          style={{ marginBottom: 16 }}
        />
        <div role="tablist" aria-label="联调验证预览类型" style={{ marginBottom: 16 }}>
          <Button
            type={validationPreviewMode === 'structure' ? 'primary' : 'default'}
            role="tab"
            aria-selected={validationPreviewMode === 'structure'}
            onClick={() => setValidationPreviewMode('structure')}
          >
            结构预览
          </Button>
          <Button
            type={validationPreviewMode === 'visual' ? 'primary' : 'default'}
            role="tab"
            aria-selected={validationPreviewMode === 'visual'}
            onClick={() => setValidationPreviewMode('visual')}
            style={{ marginLeft: 8 }}
          >
            真实视觉预览
          </Button>
          <Button
            type={validationPreviewMode === 'prt' ? 'primary' : 'default'}
            role="tab"
            aria-selected={validationPreviewMode === 'prt'}
            onClick={() => setValidationPreviewMode('prt')}
            style={{ marginLeft: 8 }}
          >
            PRT 真实联调
          </Button>
        </div>
        {validationPreview.activeMode === 'structure' ? (
          <>
            <Card size="small" title={validationPreview.structure?.sectionLabels?.join?.(' / ')}>
              <pre style={{ margin: 0, maxHeight: 680, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                {previewJson(contractPreview)}
              </pre>
            </Card>
            <Card size="small" title="Tool / SSE 下行协议示例" style={{ marginTop: 16 }}>
              <Text type="secondary">
                首屏、Action、历史快照与 Redis tail 的 event:a2ui data.value 都直接是
                A2UIMessage[]。
              </Text>
              <pre
                style={{
                  margin: '12px 0 0',
                  maxHeight: 360,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {previewJson(publicA2uiEventExample)}
              </pre>
            </Card>
            <Card size="small" title="Action HTTP 请求示例" style={{ marginTop: 16 }}>
              <Text type="secondary">
                同一 HTTP 直接返回 SSE；请求仅含 conversationId、messageId 与标准 v0.9.1 Action。
              </Text>
              <pre
                style={{
                  margin: '12px 0 0',
                  maxHeight: 360,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {previewJson(
                  actionRequestExample || { message: '当前 ShowTemplate 没有 ActionDeclaration' },
                )}
              </pre>
            </Card>
            <Space style={{ marginTop: 16 }}>
              <Button onClick={handleRefreshPreview}>刷新结构预览</Button>
              <Text type="secondary">整批原子校验失败时不暴露部分消息。</Text>
            </Space>
          </>
        ) : validationPreviewMode === 'visual' ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card
              size="small"
              title="本地 sample params"
              extra={
                <Button
                  size="small"
                  onClick={() => setSampleParamsJson(previewJson(sampleParamDefaults.params))}
                >
                  重置本地契约样例
                </Button>
              }
            >
              <JsonFormatTextArea
                value={sampleParamsJson}
                onChange={(event) => setSampleParamsJson(event.target.value)}
                onValueChange={setSampleParamsJson}
                autoSize={{ minRows: 5, maxRows: 14 }}
              />
              {sampleParamDefaults.missingRequired.length ? (
                <Alert
                  type="warning"
                  showIcon
                  message={`以下必填参数没有 Schema examples/default，请补充样例：${sampleParamDefaults.missingRequired.join(', ')}`}
                  style={{ marginTop: 12 }}
                />
              ) : null}
              {sampleParamDefaults.generatedFields.length ? (
                <Alert
                  type="info"
                  showIcon
                  message={`以下字段由前端生成本地契约样例，不代表真实业务数据：${sampleParamDefaults.generatedFields.join(', ')}`}
                  style={{ marginTop: 12 }}
                />
              ) : null}
            </Card>
            {localVisualPreview.errors.length ? (
              <Alert
                type="error"
                showIcon
                message="本地 Application 预览未生成"
                description={localVisualPreview.errors.join('；')}
              />
            ) : (
              <Card size="small" title="真实 A2UI Application 视觉预览">
                <A2uiApplicationRendererPreview
                  catalogId={draft.catalog.catalogId}
                  messages={localVisualPreview.messages}
                  onAction={handleLocalAction}
                />
              </Card>
            )}
            {localActionSummary ? (
              <Card size="small" title="本地 Action 事件（未调用业务 API）">
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                  {previewJson(localActionSummary)}
                </pre>
              </Card>
            ) : null}
          </Space>
        ) : (
          <A2uiApplicationPrtPreview
            applicationId={record ? String(record.id) : undefined}
            defaultParamsJson={previewJson(sampleParamDefaults.params)}
          />
        )}
      </Card>
    );
  };

  const releaseAssetKey = resolveA2uiApplicationReleaseAssetKey(
    record ? String(record.id) : undefined,
    draft.appCode,
    authoringDraftId,
  );

  const renderReleaseStage = () => (
    <div className="a2ui-application-release-stage">
      {!actionScan ? null : actionScan.releaseBlockers?.length ? (
        <Alert
          type="error"
          message="服务端重新扫描发现发布阻塞"
          description={actionScan.releaseBlockers?.join?.('、')}
          style={{ marginBottom: 16 }}
        />
      ) : (
        <Alert
          type="info"
          message="当前扫描未返回 Action blocker"
          description="最终准出仍完全由共享发布服务端门禁决定，前端不自行判定发布通过。"
          style={{ marginBottom: 16 }}
        />
      )}
      <AssetReleaseTab
        assetKey={releaseAssetKey}
        assetType="A2UI_APPLICATION"
        title="A2UI Application 发布管理"
      />
    </div>
  );

  const renderActiveStage = () => {
    switch (activeStage) {
      case 'basic':
        return renderBasicStage();
      case 'show':
        return renderShowStage();
      case 'actions':
        return renderActionStage();
      case 'validation':
        return renderValidationStage();
      case 'release':
        return renderReleaseStage();
      default:
        return null;
    }
  };

  const authoringChatPanel = (
    <SkillFactoryAuthoringChat
      title="AI 对话助手"
      chat={authoringChat}
      extra={<Tag color="blue">{record ? '编辑草稿' : '创建草稿'}</Tag>}
      emptyText="暂无 A2UI Authoring 会话"
      placeholder="描述要编排的组件、params、按钮交互或结果适配，AI 会结合当前 Application 草稿协助你完善..."
    />
  );

  return (
    <AuthoringWorkbenchLayout
      className={editorView.authoringWorkbenchClassName}
      railOpen={authoringRailOpen}
      railView={authoringRailView}
      onRailOpenChange={setAuthoringRailOpen}
      onRailViewChange={setAuthoringRailView}
      railTitle="AI 对话助手"
      railSubtitle="结合当前 Application 草稿协助编排，确认后由你保存"
      chat={authoringChatPanel}
    >
      <div className="page-container component-center-page a2ui-application-editor-page">
        <div className="page-header component-center-header">
          <div>
            <h1 className="page-title">
              {record ? `编辑 ${record.nameCn}` : '创建 A2UI Application'}
            </h1>
            <p className="page-subtitle">
              {editorView.header?.applicationLabel} / {editorView.header?.draftStatus}
            </p>
          </div>
          <Space className="a2ui-application-header-actions">
            {activeStage === 'basic' || activeStage === 'show' || activeStage === 'actions'
              ? renderSaveDraftButton(activeStage) : null}

            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate(a2uiApplicationListRoute(searchParams))}
            >
              返回编排列表
            </Button>
          </Space>
        </div>

        <Card className="a2ui-application-editor-summary" style={{ marginBottom: 16 }}>
          <Space wrap>
            <Text strong>{editorView.header?.applicationLabel}</Text>
            <Tag>{editorView.header?.draftStatus}</Tag>
            <Tag color="blue">AVAILABLE {editorView.header?.availableComponentCount}</Tag>
            <Tag color={editorView.header?.interactionClosure === '已闭合' ? 'success' : 'warning'}>
              交互：{editorView.header?.interactionClosure}
            </Tag>
            <Tag color={editorView.header?.validationSummary === '已通过' ? 'success' : 'warning'}>
              验证：{editorView.header?.validationSummary}
            </Tag>
          </Space>
        </Card>

        <div
          className="a2ui-application-editor-steps"
          role="tablist"
          aria-label="A2UI Application editor stages"
        >
          {A2UI_APPLICATION_EDITOR_STAGES.map((stage) => (
            <button
              key={stage.id}
              className={activeStage === stage.id ? 'active' : ''}
              role="tab"
              aria-selected={activeStage === stage.id}
              onClick={() => setActiveStage(stage.id)}
              type="button"
            >
              {stage.label}
            </button>
          ))}
        </div>


         {error ? <Alert type="error" message={error} style={{ marginBottom: 16 }} /> : null}

        <Spin spinning={loading}>
          {contractPreviewState.error ? (
            <Alert
              type="error"
              message="Application 草稿契约无效"
              description={`${contractPreviewState.error}；请修复服务端草稿数据后刷新页面。`}
            />
          ) : (
            <Form
              form={form}
              layout="vertical"
              onValuesChange={(changedValues) => {
                if (typeof changedValues.sampleParamsJson === 'string') {
                  setSampleParamsJson(changedValues.sampleParamsJson);
                }
                if (Object.keys(changedValues).some((field) => field !== 'sampleParamsJson')) {
                  setActionScan(undefined);
                }
              }}
            >
              {renderActiveStage()}
            </Form>
          )}
        </Spin>
      </div>
    </AuthoringWorkbenchLayout>
  );
};

export default A2uiApplicationEditorPage;
