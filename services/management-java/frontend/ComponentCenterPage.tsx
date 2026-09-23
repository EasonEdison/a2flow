import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
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
import { EditOutlined, EyeOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { jsonParse, jsonStringify } from './shared/safeJson';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { a2uiApplicationApi, assetReleaseApi, componentCenterApi } from './api';
import {
  COMPONENT_CENTER_ASSET_VIEWS,
  COMPONENT_CENTER_HEADER_ACTIONS,
  a2uiApplicationEditorRoute,
  a2uiRouteWithChangeId,
  componentCenterDataSourceFor,
  type ComponentCenterAssetViewKey,
} from './a2uiCatalogContracts';
import type { A2uiApplicationQuery, A2uiApplicationRecord } from './a2uiApplicationContracts';
import { extractShowComponents } from './a2uiApplicationShowAst';
import {
  A2uiApplicationReleaseStatus,
  applicationStatusOptions,
} from './A2uiApplicationReleaseStatus';
import JsonFormatTextArea from './shared/JsonFormatTextArea';
import { isAssetReleaseEditable } from './shared/useAssetReleaseEditability';
import type {
  ComponentAssetQuery,
  ComponentAssetType,
  ComponentDslType,
  SkillFactoryComponentAsset,
} from './types';

const { Text } = Typography;
const { TextArea } = Input;

const assetTypeOptions = [
  { label: '全部资产', value: 'ALL' },
  { label: '存量卡片组件', value: 'CARD_COMPONENT' },
  { label: '业务编排配置', value: 'BUSINESS_DSL' },
  { label: 'A2UI 原子', value: 'A2UI_ATOM' },
];

const dslTypeOptions = [
  { label: '全部协议', value: 'ALL' },
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

type ComponentAssetFormValues = Omit<SkillFactoryComponentAsset, 'enabled' | 'protocolVersion'> & {
  enabled: string;
  protocolVersion: number | string;
};

const protocolColor: Record<ComponentDslType, string> = {
  CARD_CONTAINER: 'blue',
  BUSINESS_DSL: 'geekblue',
};

const defaultDemo = jsonStringify(
  {
    componentName: 'MerchantActionCard',
    data: {
      title: '组件标题',
      desc: '官方 demo 数据',
      btnText: '查看',
    },
  },
  null,
  2,
);

const defaultAsset: SkillFactoryComponentAsset = {
  assetType: 'CARD_COMPONENT',
  componentName: '',
  componentNameCn: '',
  dslType: 'CARD_CONTAINER',
  protocolVersion: 1,
  interactionMode: 'DISPLAY_ONLY',
  bundleUrl: '',
  appBundleUrl: '',
  owner: '',
  scene: '',
  officialDemoJson: defaultDemo || '{}',
  integrationPrompt: '',
  allowedActionsJson: '[]',
  supportClients: ['PC'],
  enabled: false,
};

function formatJsonText(value?: string): string {
  const parsed = jsonParse(value || '', null);
  return parsed ? jsonStringify(parsed, null, 2) || value || '' : value || '';
}

function normalizeQuery(query: ComponentAssetQuery): ComponentAssetQuery {
  return {
    keyword: query.keyword?.trim?.(),
    assetType: query.assetType,
    dslType: query.dslType,
  };
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

function isCardContainerAsset(asset?: SkillFactoryComponentAsset): boolean {
  return asset?.assetType === 'CARD_COMPONENT' && asset.dslType === 'CARD_CONTAINER';
}

function buildCardAuthoringPath(asset: SkillFactoryComponentAsset): string {
  return `/management/components/register-render-component?assetType=${asset.assetType}&assetId=${asset.id}`;
}

function isApplicationAssetView(view: ComponentCenterAssetViewKey): view is 'A2UI_APPLICATION' {
  return componentCenterDataSourceFor(view) === 'A2UI_APPLICATION_LIST';
}

const ComponentCenterPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const [assets, setAssets] = useState<SkillFactoryComponentAsset[]>([]);
  const [applications, setApplications] = useState<A2uiApplicationRecord[]>([]);
  const [activeAssetViewKey, setActiveAssetViewKey] =
    useState<ComponentCenterAssetViewKey>('A2UI_ATOM');
  const [query, setQuery] = useState<ComponentAssetQuery>({
    assetType: 'A2UI_ATOM',
    dslType: 'ALL',
  });
  const [applicationQuery, setApplicationQuery] = useState<A2uiApplicationQuery>({
    status: 'ALL',
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<SkillFactoryComponentAsset>();
  const [error, setError] = useState('');

  const isApplicationView = activeAssetViewKey === 'A2UI_APPLICATION';

  const currentListCount = isApplicationView ? applications.length : assets.length;

  const enabledCount = useMemo(
    () =>
      isApplicationView
        ? applications?.filter((item) => item.status === 'VALIDATED')?.length
        : assets?.filter((item) => item.enabled)?.length,
    [applications, assets, isApplicationView],
  );

  const protocolCount = useMemo(
    () =>
      new Set(
        isApplicationView
          ? applications?.map((item) => item.protocolVersion)?.filter?.(Boolean)
          : assets?.map((item) => item.dslType)?.filter?.(Boolean),
      ).size,
    [applications, assets, isApplicationView],
  );

  const activeAssetView = useMemo(
    () =>
      COMPONENT_CENTER_ASSET_VIEWS.find((item) => item.value === activeAssetViewKey) ||
      COMPONENT_CENTER_ASSET_VIEWS?.[0],
    [activeAssetViewKey],
  );

  const listEmptyText = useMemo(() => {
    if (activeAssetViewKey === 'A2UI_APPLICATION') return '暂无 A2UI 编排';
    if (activeAssetViewKey === 'CARD_COMPONENT') return '暂无渲染组件';
    return '暂无 A2UI 原子';
  }, [activeAssetViewKey]);

  const loadAssets = useCallback(
    async (nextQuery?: ComponentAssetQuery) => {
      setLoading(true);
      setError('');
      try {
        const requestQuery = nextQuery || query;
        const list = await componentCenterApi.list(normalizeQuery(requestQuery));
        setAssets(list);
        setApplications([]);
      } catch (e) {
        const msg = e instanceof Error ? e.message : '组件资产加载失败';
        setError(msg);
        setAssets([]);
      } finally {
        setLoading(false);
      }
    },
    [query],
  );

  const loadApplications = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const list = await a2uiApplicationApi.list({
        keyword: applicationQuery.keyword?.trim(),
        status: applicationQuery.status,
      });
      setApplications(list);
      setAssets([]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'A2UI 编排列表加载失败';
      setError(msg);
      setApplications([]);
    } finally {
      setLoading(false);
    }
  }, [applicationQuery]);

  useEffect(() => {
    if (isApplicationAssetView(activeAssetViewKey)) {
      loadApplications();
      return;
    }
    loadAssets({
      ...query,
      assetType: activeAssetViewKey,
    });
  }, [activeAssetViewKey, loadApplications, loadAssets, query]);

  const switchAssetView = (assetType: ComponentCenterAssetViewKey) => {
    setActiveAssetViewKey(assetType);
    if (assetType !== 'A2UI_APPLICATION') {
      setQuery((prev) => ({
        ...prev,
        assetType,
        dslType: 'ALL',
      }));
    }
  };

  const ensureAssetEditable = async (asset: SkillFactoryComponentAsset): Promise<boolean> => {
    if (!asset.id) return true;
    try {
      const overview = await assetReleaseApi.overview('COMPONENT', String(asset.id));
      if (isAssetReleaseEditable(overview)) return true;
      message.warning('当前组件没有可编辑变更，请先在详情页新建变更');
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '组件发布状态加载失败');
    }
    return false;
  };

  const openEditDrawer = async (asset: SkillFactoryComponentAsset) => {
    if (!(await ensureAssetEditable(asset))) return;
    if (isCardContainerAsset(asset) && asset.id) {
      navigate(buildCardAuthoringPath(asset));
      return;
    }
    setEditingAsset(asset);
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

  const openDetailPage = (asset: SkillFactoryComponentAsset) => {
    if (!asset.id) return;
    navigate(`/management/components/detail?id=${asset.id}`);
  };

  const openApplicationEditor = (id?: string) => {
    navigate(a2uiApplicationEditorRoute(id, searchParams));
  };

  const refreshCurrentView = () => {
    if (isApplicationAssetView(activeAssetViewKey)) {
      loadApplications();
      return;
    }
    loadAssets({
      ...query,
      assetType: activeAssetViewKey,
    });
  };

  const handleSave = async () => {
    const values = (await form.validateFields()) as ComponentAssetFormValues;
    if (editingAsset && !(await ensureAssetEditable(editingAsset))) return;
    setSaving(true);
    try {
      const payload: SkillFactoryComponentAsset = {
        ...defaultAsset,
        ...editingAsset,
        ...fromFormValues(values),
        id: editingAsset?.id,
      };
      const saved = editingAsset
        ? await componentCenterApi.update(payload)
        : await componentCenterApi.register(payload);
      message.success(editingAsset ? '组件资产已更新' : '组件资产已注册');
      setDrawerOpen(false);
      const nextQuery: ComponentAssetQuery = {
        ...query,
        assetType: saved.assetType || payload.assetType || query.assetType,
      };
      setQuery(nextQuery);
      await loadAssets(nextQuery);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page-container component-center-page">
      <div className="page-header component-center-header">
        <div>
          <h1 className="page-title">组件中心</h1>
          <p className="page-subtitle">A2UI 原子、Application 编排和存量渲染组件管理中心</p>
        </div>
        <Space>
          <Button onClick={() => navigate('/management')}>返回 Skill 工作台</Button>
          {COMPONENT_CENTER_HEADER_ACTIONS.map((entry) => (
            <Button
              key={entry.id}
              type={entry.buttonType}
              icon={entry.id === 'catalog' ? undefined : <ThunderboltOutlined />}
              onClick={() => navigate(a2uiRouteWithChangeId(entry.route, searchParams))}
            >
              {entry.label}
            </Button>
          ))}
        </Space>
      </div>

      <div className="component-center-asset-tabs" role="tablist" aria-label="组件中心资产类型">
        {COMPONENT_CENTER_ASSET_VIEWS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={activeAssetViewKey === item.value}
            className={activeAssetViewKey === item.value ? 'active' : ''}
            onClick={() => switchAssetView(item.value)}
          >
            <strong>{item.title}</strong>
            <span>{item.description}</span>
          </button>
        ))}
      </div>

      <div className="component-center-metrics">
        <div>
          <Text type="secondary">当前列表资产</Text>
          <strong>{currentListCount}</strong>
        </div>
        <div>
          <Text type="secondary">{isApplicationView ? '当前已验证' : '当前可引用'}</Text>
          <strong>{enabledCount}</strong>
        </div>
        <div>
          <Text type="secondary">当前协议数</Text>
          <strong>{protocolCount}</strong>
        </div>
      </div>

      <Card className="component-center-filter-card">
        <Space wrap>
          {isApplicationView ? (
            <>
              <Select
                value={applicationQuery.status || 'ALL'}
                options={applicationStatusOptions}
                style={{ width: 170 }}
                onChange={(value) =>
                  setApplicationQuery((prev) => ({
                    ...prev,
                    status: value as A2uiApplicationQuery['status'],
                  }))
                }
              />
              <Input
                value={applicationQuery.keyword}
                placeholder="搜索 appCode / 中文名"
                onChange={(event) =>
                  setApplicationQuery((prev) => ({
                    ...prev,
                    keyword: event.target.value,
                  }))
                }
                style={{ width: 320 }}
                allowClear
              />
            </>
          ) : (
            <>
              <Select
                value={query.dslType || 'ALL'}
                onChange={(value) =>
                  setQuery((prev) => ({
                    ...prev,
                    dslType: value as ComponentAssetQuery['dslType'],
                  }))
                }
                options={dslTypeOptions}
                style={{ width: 170 }}
              />
              <Input
                value={query.keyword}
                placeholder="搜索 componentName / 负责人 / 场景"
                onChange={(event) =>
                  setQuery((prev) => ({
                    ...prev,
                    keyword: event.target.value,
                  }))
                }
                style={{ width: 320 }}
                allowClear
              />
            </>
          )}
          <Button onClick={refreshCurrentView}>刷新</Button>
        </Space>
      </Card>

      {error ? <Alert type="error" message={error} style={{ marginBottom: 12 }} /> : null}

      <Card title={activeAssetView.listTitle} className="component-center-list-card">
        <Spin spinning={loading}>
          {isApplicationView ? (
            <Table
              rowKey="id"
              dataSource={applications}
              pagination={false}
              locale={{ emptyText: <Empty description={listEmptyText} /> }}
              onRow={(record) => ({
                onClick: () => openApplicationEditor(record.id),
              })}
              columns={[
                {
                  title: 'Application',
                  dataIndex: 'appCode',
                  render: (value: string, record: A2uiApplicationRecord) => (
                    <div className="component-center-name-cell">
                      <strong>{record.nameCn || value}</strong>
                      <span>{value}</span>
                    </div>
                  ),
                },
                { title: '协议', dataIndex: 'protocolVersion', width: 110 },
                {
                  title: 'Catalog',
                  width: 240,
                  render: (_: unknown, record: A2uiApplicationRecord) => (
                    <span>
                      {record.catalog?.catalogId || '-'}@{record.catalog?.revision || '-'}
                    </span>
                  ),
                },
                {
                  title: 'Show / Action',
                  width: 140,
                  render: (_: unknown, record: A2uiApplicationRecord) => (
                    <span>
                      {extractShowComponents(record.showTemplate)?.length} /{' '}
                      {record.actionBindings?.length}
                    </span>
                  ),
                },
                {
                  title: '发布状态',
                  dataIndex: 'status',
                  width: 230,
                  render: (_: unknown, record: A2uiApplicationRecord) => (
                    <A2uiApplicationReleaseStatus record={record} />
                  ),
                },
                {
                  title: '操作',
                  width: 100,
                  render: (_: unknown, record: A2uiApplicationRecord) => (
                    <Button
                      type="link"
                      icon={<EditOutlined />}
                      onClick={(event) => {
                        event.stopPropagation();
                        openApplicationEditor(record.id);
                      }}
                    >
                      编辑
                    </Button>
                  ),
                },
              ]}
            />
          ) : (
            <Table
              rowKey="id"
              dataSource={assets}
              pagination={false}
              locale={{ emptyText: <Empty description={listEmptyText} /> }}
              onRow={(record) => ({
                onClick: () => openDetailPage(record),
              })}
              columns={[
                {
                  title: '组件',
                  dataIndex: 'componentName',
                  render: (value: string, record: SkillFactoryComponentAsset) => (
                    <div className="component-center-name-cell">
                      <strong>{record.componentNameCn || value}</strong>
                      <span>{value}</span>
                    </div>
                  ),
                },
                {
                  title: '类型',
                  dataIndex: 'assetType',
                  width: 132,
                  render: (value: ComponentAssetType) => <Tag>{value}</Tag>,
                },
                {
                  title: '协议',
                  dataIndex: 'dslType',
                  width: 148,
                  render: (value?: ComponentDslType) => (
                    <Tag color={value ? protocolColor[value] : undefined}>{value || '-'}</Tag>
                  ),
                },
                {
                  title: '负责人',
                  dataIndex: 'owner',
                  width: 140,
                },
                {
                  title: '场景',
                  dataIndex: 'scene',
                  ellipsis: true,
                },
                {
                  title: '状态',
                  dataIndex: 'enabled',
                  width: 116,
                  render: (value: boolean, record: SkillFactoryComponentAsset) => (
                    <Space wrap>
                      <Tag color={value ? 'success' : undefined}>{value ? '可引用' : '未启用'}</Tag>
                      {record.published ? <Tag color="blue">v{record.publishedVersion}</Tag> : null}
                    </Space>
                  ),
                },
                {
                  title: '操作',
                  width: 164,
                  render: (_: unknown, record: SkillFactoryComponentAsset) => (
                    <Space>
                      <Button
                        type="link"
                        icon={<EyeOutlined />}
                        onClick={(event) => {
                          event.stopPropagation();
                          openDetailPage(record);
                        }}
                      >
                        详情
                      </Button>
                      <Button
                        type="link"
                        icon={<EditOutlined />}
                        onClick={(event) => {
                          event.stopPropagation();
                          openEditDrawer(record);
                        }}
                      >
                        编辑
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          )}
        </Spin>
      </Card>

      <Drawer
        title={editingAsset ? '编辑组件资产' : '注册新组件'}
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
              <Select options={assetTypeOptions.filter((item) => item.value !== 'ALL')} />
            </Form.Item>
            <Form.Item label="运行协议族" name="dslType">
              <Select allowClear options={dslTypeOptions.filter((item) => item.value !== 'ALL')} />
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
            <Form.Item label="交互类型" name="interactionMode">
              <Select
                options={[
                  { label: '纯展示', value: 'DISPLAY_ONLY' },
                  { label: '需交互', value: 'INTERACTIVE' },
                ]}
              />
            </Form.Item>
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
            <Button type="primary" loading={saving} onClick={handleSave}>
              保存
            </Button>
          </div>
        </Form>
      </Drawer>
    </div>
  );
};

export default ComponentCenterPage;
