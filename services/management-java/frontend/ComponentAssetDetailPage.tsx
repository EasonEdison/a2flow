import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { jsonParse, jsonStringify } from './shared/safeJson';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { assetReleaseApi, componentCenterApi } from './api';
import AssetReleaseTab from './shared/AssetReleaseTab';
import DynamicCardContainerPreview from './shared/DynamicCardContainerPreview';
import { useAssetAccess } from './shared/AssetAccessContext';
import JsonFormatTextArea from './shared/JsonFormatTextArea';
import { executeReleaseOperation } from './shared/releaseOperationFeedback';
import { useAssetReleaseEditability } from './shared/useAssetReleaseEditability';
import type {
  ComponentDslType,
  ComponentRenderPreviewParams,
  ComponentRenderPreviewResult,
  SkillFactoryComponentAsset,
} from './types';
import { DSL_TYPE_BUSINESS_DSL, DSL_TYPE_CARD_CONTAINER } from './cardContainerTemplate';

const { Text } = Typography;
const { TextArea } = Input;

type ComponentAssetFormValues = Omit<SkillFactoryComponentAsset, 'enabled' | 'protocolVersion'> & {
  enabled: string;
  protocolVersion: number | string;
};

const assetTypeOptions = [
  { label: '存量卡片组件', value: 'CARD_COMPONENT' },
  { label: '业务编排配置', value: 'BUSINESS_DSL' },
  { label: 'A2UI 原子', value: 'A2UI_ATOM' },
];

const dslTypeOptions = [
  { label: 'CARD_CONTAINER', value: 'CARD_CONTAINER' },
  { label: 'BUSINESS_DSL', value: 'BUSINESS_DSL' },
];

const clientOptions = [
  { label: 'PC', value: 'PC' },
  { label: 'APP', value: 'APP' },
];

const enabledOptions = [
  { label: '可引用', value: 'true' },
  { label: '不可引用', value: 'false' },
];

const protocolColor: Record<ComponentDslType, string> = {
  CARD_CONTAINER: 'blue',
  BUSINESS_DSL: 'geekblue',
};

function formatJsonText(value?: string): string {
  const parsed = jsonParse(value || '', null);
  return parsed ? jsonStringify(parsed, null, 2) || value || '' : value || '';
}

function buildAuthoringPath(asset: SkillFactoryComponentAsset): string {
  const basePath =
    asset.assetType === 'BUSINESS_DSL'
      ? '/management/components/create-business-dsl'
      : '/management/components/register-render-component';
  return `${basePath}?assetType=${asset.assetType}&assetId=${asset.id}`;
}

function isCardContainerAsset(asset?: SkillFactoryComponentAsset): boolean {
  return asset?.assetType === 'CARD_COMPONENT' && asset.dslType === DSL_TYPE_CARD_CONTAINER;
}

function formatTime(timestamp?: number): string {
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false });
}

function getPreviewData(rawJson?: string): Record<string, unknown> {
  const parsed = jsonParse(rawJson || '', {}) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
  const record = parsed as Record<string, unknown>;
  const data = record.data;
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    return data as Record<string, unknown>;
  }
  return record;
}

function toFormAsset(asset: SkillFactoryComponentAsset): ComponentAssetFormValues {
  return {
    ...asset,
    enabled: String(asset.enabled),
  };
}

function fromFormValues(values: ComponentAssetFormValues): SkillFactoryComponentAsset {
  return {
    ...values,
    enabled: values.enabled !== 'false',
    protocolVersion: Number(values.protocolVersion || 1),
  };
}

function buildRenderPreviewParams(
  asset: SkillFactoryComponentAsset,
  toolArgsJson: string,
  clientType: 'PC' | 'APP',
): ComponentRenderPreviewParams {
  const businessDsl = asset.assetType === 'BUSINESS_DSL';
  const cardContainer = asset.dslType === DSL_TYPE_CARD_CONTAINER;
  return {
    assetType: asset.assetType,
    componentName: asset.componentName,
    componentNameCn: asset.componentNameCn,
    agentUiDsl: businessDsl ? asset.agentUiDsl : undefined,
    dslType: businessDsl ? DSL_TYPE_BUSINESS_DSL : DSL_TYPE_CARD_CONTAINER,
    protocolVersion: asset.protocolVersion,
    inputMode: businessDsl ? 'BUSINESS_DSL' : cardContainer ? 'CARD_CONTAINER' : 'RAW_TEXT',
    source: 'component-center',
    clientType,
    toolArgsJson: toolArgsJson.trim() || '{}',
    paramsSchemaJson: asset.paramsSchemaJson,
    renderTemplateJson: asset.renderTemplateJson,
    officialDemoJson: asset.officialDemoJson,
    allowedActionsJson: asset.allowedActionsJson,
    runtimeConfigJson: asset.runtimeConfigJson,
    bundleUrl: asset.bundleUrl,
    appBundleUrl: asset.appBundleUrl,
  };
}

const JsonCodeBlock: React.FC<{ value?: string; maxHeight?: number }> = ({
  value,
  maxHeight = 360,
}) => (
  <pre className="component-center-json-code" style={{ maxHeight }}>
    {formatJsonText(value)}
  </pre>
);

const ComponentPreviewCard: React.FC<{ asset?: SkillFactoryComponentAsset; json?: string }> = ({
  asset,
  json,
}) => {
  const data = getPreviewData(json);
  if (!asset) return <Empty description="请选择组件" />;
  if (asset.dslType === 'CARD_CONTAINER') {
    return (
      <div className="component-center-render-card">
        <Text type="secondary">{asset.componentName}</Text>
        <h3>{String(data.title || asset.componentNameCn || asset.componentName)}</h3>
        <p>{String(data.desc || data.description || asset.scene || '官方 demo 数据可渲染')}</p>
        <button type="button">{String(data.btnText || data.buttonText || '查看')}</button>
      </div>
    );
  }
  if (asset.assetType === 'BUSINESS_DSL') {
    return (
      <div className="component-center-render-card atom">
        <Text type="secondary">{String(data.agentUiDsl || asset.agentUiDsl || '-')}</Text>
        <h3>{asset.componentNameCn || asset.componentName}</h3>
        <p>{asset.scene || '通过 agentUiDsl + params 翻译成 A2UI payload'}</p>
        <Tag color="geekblue">协议版本 {asset.protocolVersion}</Tag>
      </div>
    );
  }
  return (
    <div className="component-center-render-card atom">
      <Text type="secondary">{asset.dslType || asset.assetType}</Text>
      <h3>{asset.componentNameCn || asset.componentName}</h3>
      <p>{asset.scene}</p>
      <Tag color={asset.dslType ? protocolColor[asset.dslType] : undefined}>
        协议版本 {asset.protocolVersion}
      </Tag>
    </div>
  );
};

const ComponentAssetDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const assetId = Number(searchParams.get('id'));
  const releaseEditability = useAssetReleaseEditability(
    'COMPONENT',
    assetId && !Number.isNaN(assetId) ? String(assetId) : undefined,
  );
  const assetAccess = useAssetAccess(
    'COMPONENT',
    assetId && !Number.isNaN(assetId) ? String(assetId) : undefined,
  );
  const [asset, setAsset] = useState<SkillFactoryComponentAsset>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creatingChange, setCreatingChange] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [changeModalOpen, setChangeModalOpen] = useState(false);
  const [changeName, setChangeName] = useState('');
  const [customPreviewJson, setCustomPreviewJson] = useState('');
  const [previewClientType, setPreviewClientType] = useState<'PC' | 'APP'>('PC');
  const [previewResult, setPreviewResult] = useState<ComponentRenderPreviewResult>();
  const [error, setError] = useState('');
  const [activeView, setActiveView] = useState<'detail' | 'release'>(
    searchParams.get('tab') === 'release' ? 'release' : 'detail',
  );
  const releaseEditDisabledReason = assetId
    ? assetAccess.loading
      ? '正在加载当前组件的操作权限'
      : !assetAccess.permissions?.canEdit
      ? assetAccess.readonlyReason || '当前用户不是负责人，仅可查看'
      : releaseEditability.loading
      ? '正在加载当前组件的变更状态'
      : releaseEditability.editable
      ? ''
      : '当前组件没有可编辑变更，请先在本页新建变更'
    : '';
  const canCreateChange = Boolean(
    asset &&
      isCardContainerAsset(asset) &&
      !releaseEditability.editable &&
      assetAccess.permissions.canEdit &&
      releaseEditability.overview?.allowedActions?.includes('CREATE_CHANGE') &&
      Number.isInteger(releaseEditability.overview?.nextVersion),
  );
  const createChangeDisabledReason =
    releaseEditability.loading || assetAccess.loading
      ? '正在加载组件变更状态'
      : !assetAccess.permissions?.canEdit
      ? assetAccess.readonlyReason || '当前用户无权新建组件变更'
      : !releaseEditability.overview?.allowedActions?.includes('CREATE_CHANGE')
      ? '当前发布状态不允许新建变更，请刷新后重试'
      : !Number.isInteger(releaseEditability.overview?.nextVersion)
      ? '后端未返回下一版本号，请刷新后重试'
      : '';

  const loadAsset = useCallback(async () => {
    if (!assetId || Number.isNaN(assetId)) return;
    setLoading(true);
    setError('');
    try {
      const detail = await componentCenterApi.detail(assetId);
      setAsset(detail);
      setCustomPreviewJson(
        formatJsonText(
          isCardContainerAsset(detail) ? detail.messageDemoJson : detail.officialDemoJson,
        ),
      );
      setPreviewResult(undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : '组件详情加载失败');
      setAsset(undefined);
    } finally {
      setLoading(false);
    }
  }, [assetId]);

  useEffect(() => {
    loadAsset();
  }, [loadAsset]);

  const openEditDrawer = () => {
    if (!asset) return;
    if (!releaseEditability.editable) {
      message.warning(releaseEditDisabledReason || '当前组件没有可编辑变更');
      return;
    }
    form.setFieldsValue({
      ...toFormAsset(asset),
      paramsSchemaJson: formatJsonText(asset.paramsSchemaJson),
      renderTemplateJson: asset.renderTemplateJson || '',
      officialDemoJson: formatJsonText(asset.officialDemoJson),
      messageDemoJson: formatJsonText(asset.messageDemoJson),
      allowedActionsJson: formatJsonText(asset.allowedActionsJson),
      runtimeConfigJson: formatJsonText(asset.runtimeConfigJson),
      attribute: formatJsonText(asset.attribute),
    });
    setDrawerOpen(true);
  };

  const handleCreateChange = async () => {
    if (!asset?.id || !canCreateChange) {
      message.warning(createChangeDisabledReason || '当前组件不能新建变更');
      return;
    }
    const normalizedName = changeName.trim();
    if (!normalizedName) {
      message.warning('请输入变更名称');
      return;
    }
    setCreatingChange(true);
    try {
      const execution = await executeReleaseOperation(
        () =>
          assetReleaseApi.createChange('COMPONENT', String(asset.id), undefined, normalizedName),
        () => assetReleaseApi.overview('COMPONENT', String(asset.id)),
      );
      const { feedback } = execution;
      if (feedback.kind === 'SUCCESS') {
        message.success(feedback.message);
      } else if (feedback.kind === 'PENDING') {
        message.info(feedback.message);
      } else {
        message.error(feedback.message);
      }
      if (execution.overview) {
        releaseEditability.acceptOverview(execution.overview);
      }
      if (execution.refreshError) {
        message.error('变更操作结果已返回，但发布状态刷新失败，请手动刷新');
      }
      setChangeModalOpen(false);
      setChangeName('');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '新建变更失败');
      await Promise.all([releaseEditability.refresh(), assetAccess.refresh()]);
    } finally {
      setCreatingChange(false);
    }
  };

  const handleSave = async () => {
    if (!asset) return;
    if (!releaseEditability.editable) {
      message.warning(releaseEditDisabledReason || '当前组件没有可编辑变更');
      return;
    }
    const values = (await form.validateFields()) as ComponentAssetFormValues;
    setSaving(true);
    try {
      const saved = await componentCenterApi.update({
        ...asset,
        ...fromFormValues(values),
        id: asset.id,
      });
      message.success('组件资产已更新');
      setDrawerOpen(false);
      setAsset(saved);
      setCustomPreviewJson(
        formatJsonText(
          isCardContainerAsset(saved) ? saved.messageDemoJson : saved.officialDemoJson,
        ),
      );
      setPreviewResult(undefined);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败');
      await assetAccess.refresh();
    } finally {
      setSaving(false);
    }
  };

  const handleOffline = () => {
    if (!asset?.id) return;
    if (!assetAccess.permissions?.canOffline) {
      message.warning(assetAccess.readonlyReason || '当前用户无权下线组件');
      return;
    }
    Modal.confirm({
      title: '下线组件资产',
      content: `确认下线 ${asset.componentName}？下线后不会进入新 Skill 的参考组件列表。`,
      okText: '下线',
      cancelText: '取消',
      onOk: async () => {
        const offlined = await componentCenterApi.offline(asset.id as number);
        message.success('组件资产已下线');
        setAsset(offlined);
      },
    });
  };

  const handlePreview = async (clientType: 'PC' | 'APP' = previewClientType) => {
    if (!asset) return;
    setPreviewClientType(clientType);
    try {
      const result = await componentCenterApi.bizRenderPreview(
        buildRenderPreviewParams(asset, customPreviewJson, clientType),
      );
      setPreviewResult(result);
      if (result.valid) {
        message.success('运行态预览通过');
      } else {
        message.warning('运行态预览存在错误');
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : '预览失败');
    }
  };

  if (!assetId || Number.isNaN(assetId)) {
    return (
      <div className="page-container component-center-page component-center-detail-page">
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/management/components')}
        >
          返回组件中心
        </Button>
        <Card>
          <Empty description="缺少组件资产 ID" />
        </Card>
      </div>
    );
  }

  return (
    <div className="page-container component-center-page component-center-detail-page">
      <div className="page-header component-center-header">
        <div>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/management/components')}
          >
            返回组件中心
          </Button>
          <h1 className="page-title">
            {asset?.componentNameCn || asset?.componentName || '组件详情'}
          </h1>
          <p className="page-subtitle">协议详情、官方 demo、运行态预览和状态管理</p>
        </div>
        {asset ? (
          <Space>
            {isCardContainerAsset(asset) && !releaseEditability.editable ? (
              <Button
                icon={<PlusOutlined />}
                disabled={!canCreateChange}
                title={canCreateChange ? '新建组件变更' : createChangeDisabledReason}
                onClick={() => setChangeModalOpen(true)}
              >
                新建变更
              </Button>
            ) : null}
            <Button
              icon={<ThunderboltOutlined />}
              disabled={Boolean(releaseEditDisabledReason)}
              onClick={() => navigate(buildAuthoringPath(asset))}
            >
              AI 辅助修改
            </Button>
            <Button
              icon={<EditOutlined />}
              disabled={Boolean(releaseEditDisabledReason)}
              onClick={() => {
                if (isCardContainerAsset(asset)) {
                  navigate(buildAuthoringPath(asset));
                  return;
                }
                openEditDrawer();
              }}
            >
              编辑
            </Button>
            <Button
              danger
              icon={<StopOutlined />}
              disabled={!asset.enabled || !assetAccess.permissions?.canOffline}
              title={
                assetAccess.permissions?.canOffline ? '下线组件资产' : assetAccess.readonlyReason
              }
              onClick={handleOffline}
            >
              下线
            </Button>
          </Space>
        ) : null}
      </div>

      {error ? <Alert type="error" message={error} style={{ marginBottom: 12 }} /> : null}
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

      <Modal
        title="新建组件变更"
        visible={changeModalOpen}
        okText="新建变更"
        cancelText="取消"
        okButtonProps={{ disabled: !changeName.trim() }}
        confirmLoading={creatingChange}
        onCancel={() => {
          if (creatingChange) return;
          setChangeModalOpen(false);
          setChangeName('');
        }}
        onOk={handleCreateChange}
      >
        <Form layout="vertical">
          <Form.Item label="目标版本">
            <Input readOnly value={String(releaseEditability.overview?.nextVersion ?? '-')} />
          </Form.Item>
          <Form.Item label="变更名称" required>
            <Input
              autoFocus
              maxLength={80}
              placeholder="请输入本次变更名称"
              value={changeName}
              onChange={(event) => setChangeName(event.target.value)}
              onPressEnter={handleCreateChange}
            />
          </Form.Item>
        </Form>
      </Modal>

      <div className="skill-factory-tabs component-center-detail-tabs" role="tablist">
        <button
          aria-selected={activeView === 'detail'}
          className={activeView === 'detail' ? 'active' : ''}
          onClick={() => setActiveView('detail')}
          role="tab"
          type="button"
        >
          资产详情
        </button>
        <button
          aria-selected={activeView === 'release'}
          className={activeView === 'release' ? 'active' : ''}
          onClick={() => setActiveView('release')}
          role="tab"
          type="button"
        >
          发布管理
        </button>
      </div>

      {activeView === 'release' && asset?.id ? (
        <AssetReleaseTab
          assetKey={String(asset.id)}
          assetType="COMPONENT"
          title="组件发布控制"
          onOverviewChange={releaseEditability.acceptOverview}
        />
      ) : (
        <Spin spinning={loading}>
          {asset ? (
            <div className="component-center-detail">
              <Card title="协议详情">
                <Descriptions column={2} bordered size="small">
                  <Descriptions.Item label="componentName">
                    <Text code>{asset.componentName}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="中文名">{asset.componentNameCn}</Descriptions.Item>
                  <Descriptions.Item label="协议">
                    <Tag color={asset.dslType ? protocolColor[asset.dslType] : undefined}>
                      {asset.dslType || '-'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="资产类型">{asset.assetType}</Descriptions.Item>
                  <Descriptions.Item label="dslType">
                    <Text code>{asset.dslType || '-'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="agentUiDsl">
                    <Text code>{asset.agentUiDsl || '-'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="协议版本">{asset.protocolVersion}</Descriptions.Item>
                  <Descriptions.Item label="交互类型">
                    {asset.interactionMode === 'INTERACTIVE'
                      ? '需交互'
                      : asset.interactionMode === 'DISPLAY_ONLY'
                      ? '纯展示'
                      : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="负责人">
                    {assetAccess.access?.owners?.length
                      ? assetAccess.access?.owners?.map?.((owner) => (
                          <Tag key={`${owner.principalType}-${owner.principalId}`}>
                            {owner.principalId}
                          </Tag>
                        ))
                      : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="支持端">
                    {asset.supportClients?.map((item) => (
                      <Tag key={item}>{item}</Tag>
                    ))}
                  </Descriptions.Item>
                  <Descriptions.Item label="PC bundleUrl" span={2}>
                    <Text code>{asset.bundleUrl || '-'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="APP bundleUrl" span={2}>
                    <Text code>{asset.appBundleUrl || '-'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="引用状态">
                    <Tag color={asset.enabled ? 'success' : 'default'}>
                      {asset.enabled ? 'enabled' : 'disabled'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="更新时间" span={2}>
                    {formatTime(asset.updateTime)}
                  </Descriptions.Item>
                </Descriptions>
              </Card>

              {asset.assetType === 'BUSINESS_DSL' ? (
                <div className="component-center-preview-grid">
                  <Card title="Tool 入参与参数约束">
                    <Text type="secondary">agentUiDsl</Text>
                    <p>
                      <Text code>{asset.agentUiDsl || '-'}</Text>
                    </p>
                    <Text type="secondary">paramsSchemaJson</Text>
                    <JsonCodeBlock value={asset.paramsSchemaJson} maxHeight={220} />
                  </Card>
                  <Card title="A2UI 模板">
                    <Text type="secondary">renderTemplateJson</Text>
                    <JsonCodeBlock value={asset.renderTemplateJson} maxHeight={320} />
                  </Card>
                </div>
              ) : null}

              {isCardContainerAsset(asset) ? (
                <div className="component-center-card-detail-grid">
                  <Card title="模型 Tool 调用参数">
                    <div className="component-center-equal-card-body">
                      <Text type="secondary">render_component arguments JSON，不含 Marker。</Text>
                      <JsonCodeBlock value={asset.messageDemoJson} maxHeight={300} />
                    </div>
                  </Card>
                  <Card title="官方模板">
                    <div className="component-center-equal-card-body">
                      <Text type="secondary">adviser 运行态执行的 card-container 模板。</Text>
                      <JsonCodeBlock value={asset.renderTemplateJson} maxHeight={300} />
                    </div>
                  </Card>
                  <Card title="官方渲染 Demo">
                    <div className="component-center-equal-card-body">
                      <JsonCodeBlock value={asset.officialDemoJson} maxHeight={332} />
                    </div>
                  </Card>
                  <Card title="官方渲染预览" className="component-center-card-detail-wide">
                    <div className="component-center-equal-card-body">
                      <ComponentPreviewCard asset={asset} json={asset.officialDemoJson} />
                    </div>
                  </Card>
                  <Card
                    title="Tool 调用参数预览"
                    className="component-center-card-detail-wide"
                    extra={
                      <Space>
                        <Button
                          type={previewClientType === 'PC' ? 'primary' : undefined}
                          icon={<EyeOutlined />}
                          onClick={() => handlePreview('PC')}
                        >
                          PC 预览
                        </Button>
                        <Button
                          type={previewClientType === 'APP' ? 'primary' : undefined}
                          icon={<EyeOutlined />}
                          onClick={() => handlePreview('APP')}
                        >
                          APP 预览
                        </Button>
                      </Space>
                    }
                  >
                    <div className="component-center-card-skill-preview">
                      <JsonFormatTextArea
                        value={customPreviewJson}
                        onChange={(event) => setCustomPreviewJson(event.target.value)}
                        onValueChange={setCustomPreviewJson}
                        autoSize={{ minRows: 8, maxRows: 14 }}
                      />
                      <div>
                        <DynamicCardContainerPreview
                          result={previewResult}
                          clientType={previewClientType}
                        />
                        {previewResult ? (
                          <div className="component-center-preview-result">
                            <Tag color={previewResult.valid ? 'success' : 'error'}>
                              {previewResult.valid ? '校验通过' : '校验失败'}
                            </Tag>
                            {previewResult.errors?.map?.((item) => (
                              <p key={item}>{item}</p>
                            ))}
                            {previewResult.messages?.length ? (
                              <JsonCodeBlock
                                value={jsonStringify(previewResult.messages, null, 2)}
                                maxHeight={160}
                              />
                            ) : null}
                            {previewResult.data ? (
                              <JsonCodeBlock
                                value={jsonStringify(previewResult.data, null, 2)}
                                maxHeight={160}
                              />
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </Card>
                </div>
              ) : (
                <>
                  <div className="component-center-preview-grid">
                    <Card title="官方 demo">
                      <JsonCodeBlock value={asset.officialDemoJson} />
                    </Card>
                    <Card title="官方 demo 预览">
                      <ComponentPreviewCard asset={asset} json={asset.officialDemoJson} />
                    </Card>
                  </div>
                  <Card
                    title="运行态 JSON 预览"
                    extra={
                      <Button type="primary" icon={<EyeOutlined />} onClick={() => handlePreview()}>
                        运行预览
                      </Button>
                    }
                  >
                    <div className="component-center-custom-preview">
                      <JsonFormatTextArea
                        value={customPreviewJson}
                        onChange={(event) => setCustomPreviewJson(event.target.value)}
                        onValueChange={setCustomPreviewJson}
                        autoSize={{ minRows: 12, maxRows: 22 }}
                      />
                      <div>
                        <ComponentPreviewCard asset={asset} json={customPreviewJson} />
                        {previewResult ? (
                          <div className="component-center-preview-result">
                            <Tag color={previewResult.valid ? 'success' : 'error'}>
                              {previewResult.valid ? '校验通过' : '校验失败'}
                            </Tag>
                            {asset.assetType === 'BUSINESS_DSL' ? (
                              <Tag color={previewResult.paramsValid ? 'success' : 'error'}>
                                params
                              </Tag>
                            ) : null}
                            {previewResult.errors?.map?.((item) => (
                              <p key={item}>{item}</p>
                            ))}
                            {previewResult.messages?.length ? (
                              <JsonCodeBlock
                                value={jsonStringify(previewResult.messages, null, 2)}
                                maxHeight={220}
                              />
                            ) : null}
                            {previewResult.data ? (
                              <JsonCodeBlock
                                value={jsonStringify(previewResult.data, null, 2)}
                                maxHeight={220}
                              />
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </Card>
                </>
              )}
            </div>
          ) : (
            <Card>
              <Empty description="组件资产不存在或未加载" />
            </Card>
          )}
        </Spin>
      )}

      <Drawer
        title="编辑组件资产"
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={880}
      >
        <Form form={form} layout="vertical">
          <Alert
            type="info"
            message="组件中心只保存协议和编排配置，不支持上传 Java、Groovy、JavaScript 等可执行代码。"
            style={{ marginBottom: 16 }}
          />
          <div className="component-center-form-grid">
            <Form.Item label="资产类型" name="assetType" rules={[{ required: true }]}>
              <Select options={assetTypeOptions} />
            </Form.Item>
            <Form.Item label="运行协议族" name="dslType">
              <Select allowClear options={dslTypeOptions} />
            </Form.Item>
            <Form.Item label="componentName" name="componentName" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item label="组件中文名" name="componentNameCn" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item label="协议版本" name="protocolVersion" rules={[{ required: true }]}>
              <Input type="number" min={1} />
            </Form.Item>
            {asset?.assetType === 'CARD_COMPONENT' ? (
              <Form.Item label="交互类型" name="interactionMode" rules={[{ required: true }]}>
                <Select
                  options={[
                    { label: '纯展示', value: 'DISPLAY_ONLY' },
                    { label: '需交互', value: 'INTERACTIVE' },
                  ]}
                />
              </Form.Item>
            ) : null}
            <Form.Item label="PC bundleUrl" name="bundleUrl">
              <Input />
            </Form.Item>
            <Form.Item label="APP bundleUrl" name="appBundleUrl">
              <Input />
            </Form.Item>
            <Form.Item label="负责人" name="owner">
              <Input />
            </Form.Item>
            <Form.Item label="agentUiDsl" name="agentUiDsl">
              <Input />
            </Form.Item>
            <Form.Item label="支持端" name="supportClients">
              <Select mode="multiple" options={clientOptions} />
            </Form.Item>
            <Form.Item label="是否可引用" name="enabled">
              <Select options={enabledOptions} />
            </Form.Item>
          </div>
          <Form.Item label="适用场景" name="scene">
            <Input />
          </Form.Item>
          <Form.Item label="接入提示词" name="integrationPrompt">
            <TextArea autoSize={{ minRows: 3, maxRows: 8 }} />
          </Form.Item>
          <Form.Item label="paramsSchemaJson" name="paramsSchemaJson">
            <JsonFormatTextArea autoSize={{ minRows: 4, maxRows: 12 }} />
          </Form.Item>
          <Form.Item label="renderTemplateJson" name="renderTemplateJson">
            <JsonFormatTextArea formatMode="template" autoSize={{ minRows: 4, maxRows: 12 }} />
          </Form.Item>
          <Form.Item label="officialDemoJson" name="officialDemoJson">
            <JsonFormatTextArea autoSize={{ minRows: 6, maxRows: 18 }} />
          </Form.Item>
          <Form.Item label="模型 Tool 调用参数（messageDemoJson）" name="messageDemoJson">
            <JsonFormatTextArea autoSize={{ minRows: 3, maxRows: 10 }} />
          </Form.Item>
          <Form.Item label="allowedActionsJson" name="allowedActionsJson">
            <JsonFormatTextArea autoSize={{ minRows: 3, maxRows: 10 }} />
          </Form.Item>
          <Form.Item label="runtimeConfigJson" name="runtimeConfigJson">
            <JsonFormatTextArea autoSize={{ minRows: 3, maxRows: 10 }} />
          </Form.Item>
          <Form.Item label="attribute" name="attribute">
            <JsonFormatTextArea autoSize={{ minRows: 3, maxRows: 10 }} />
          </Form.Item>
          <div className="component-center-drawer-footer">
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button
              type="primary"
              loading={saving}
              disabled={Boolean(releaseEditDisabledReason)}
              onClick={handleSave}
            >
              保存
            </Button>
          </div>
        </Form>
      </Drawer>
    </div>
  );
};

export default ComponentAssetDetailPage;
