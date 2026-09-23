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
import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { jsonStringify } from './shared/safeJson';
import { useNavigate } from 'react-router-dom';
import { a2uiCatalogApi, a2uiCatalogComponentApi } from './api';
import {
  A2UI_MANAGED_CATALOG_SOURCE_URL,
  A2UI_CATALOG_SOURCE_LABELS,
  A2UI_COMPONENT_ORIGIN_LABELS,
  a2uiCatalogReleaseFor,
  a2uiCatalogReleaseAssetBinding,
  collectPublishedA2uiCatalogOptions,
  createEmptyA2uiCatalogComponent,
  filterA2uiCatalogComponents,
  filterA2uiCatalogs,
  isA2uiCatalogEditable,
  isA2uiCatalogComponentEditable,
  parseA2uiCatalogAuthoringJson,
  parseA2uiCatalogComponentForm,
  projectA2uiCatalogMembership,
  toA2uiCatalogAuthoringSource,
  type A2uiCatalogComponentContract,
  type A2uiCatalogComponentFormValues,
  type A2uiCatalogComponentRecord,
  type A2uiCatalogRecord,
  type A2uiManagedCatalogImportResult,
} from './a2uiCatalogContracts';
import JsonFormatTextArea from './shared/JsonFormatTextArea';
import AssetReleaseTab from './shared/AssetReleaseTab';

const { Paragraph, Text } = Typography;
const categoryOptions = [
  { label: '布局', value: 'LAYOUT' },
  { label: '内容', value: 'CONTENT' },
  { label: '操作', value: 'ACTION' },
  { label: '输入', value: 'INPUT' },
  { label: '媒体', value: 'MEDIA' },
  { label: '容器', value: 'CONTAINER' },
];

function jsonText(value: unknown): string {
  return jsonStringify(value, null, 2) || '{}';
}

function toFormValues(component: A2uiCatalogComponentContract): A2uiCatalogComponentFormValues {
  return {
    componentCode: component.componentCode,
    type: component.type,
    nameCn: component.nameCn,
    category: component.category,
    compositionKind: component.compositionKind,
    propsSchemaJson: jsonText(component.propsSchema),
    eventSchemaJson: jsonText(component.eventSchema),
    childrenConstraintJson: jsonText(component.childrenConstraint),
    validMessageExampleJson: jsonText(component.validMessageExample),
    invalidMessageExampleJson: jsonText(component.invalidMessageExample),
  };
}

function isAvailable(record: A2uiCatalogComponentRecord): boolean {
  return record.release?.enabled === true;
}

const A2uiCatalogPage: React.FC = () => {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [keyword, setKeyword] = useState('');
  const [sourceUrl, setSourceUrl] = useState(A2UI_MANAGED_CATALOG_SOURCE_URL);
  const [importResult, setImportResult] = useState<A2uiManagedCatalogImportResult>();
  const [importError, setImportError] = useState('');
  const [catalogs, setCatalogs] = useState<A2uiCatalogRecord[]>([]);
  const [components, setComponents] = useState<A2uiCatalogComponentRecord[]>([]);
  const [selectedCatalog, setSelectedCatalog] = useState<A2uiCatalogRecord>();
  const [catalogDrawerOpen, setCatalogDrawerOpen] = useState(false);
  const [catalogJsonText, setCatalogJsonText] = useState('{}');
  const [selected, setSelected] = useState<A2uiCatalogComponentRecord>();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importingManaged, setImportingManaged] = useState(false);
  const [error, setError] = useState('');
  const availableCount = useMemo(
    () =>
      components?.filter(
        (component) =>
          component.catalogSourceType === 'PLATFORM_MANAGED' &&
          component.componentOriginType === 'PLATFORM_CUSTOM' &&
          isAvailable(component),
      )?.length,
    [components],
  );
  const filteredComponents = useMemo(
    () => filterA2uiCatalogComponents(components, 'ALL'),
    [components],
  );
  const filteredCatalogs = useMemo(() => filterA2uiCatalogs(catalogs, 'ALL'), [catalogs]);
  const publishedCatalogs = useMemo(() => collectPublishedA2uiCatalogOptions(catalogs), [catalogs]);
  const selectedReadonly = Boolean(selected && !isA2uiCatalogComponentEditable(selected));
  const selectedCatalogReadonly = Boolean(
    selectedCatalog && !isA2uiCatalogEditable(selectedCatalog),
  );
  const selectedCatalogMembership = useMemo(
    () => (selectedCatalog ? projectA2uiCatalogMembership(selectedCatalog) : undefined),
    [selectedCatalog],
  );
  const selectedCatalogReleaseBinding = useMemo(
    () =>
      selectedCatalog?.catalogId?.trim()
        ? a2uiCatalogReleaseAssetBinding(selectedCatalog)
        : undefined,
    [selectedCatalog],
  );

  const loadAssets = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [loadedCatalogs, loadedComponents] = await Promise.all([
        a2uiCatalogApi.list({
          keyword: keyword.trim() || undefined,
          catalogSourceType: 'PLATFORM_MANAGED',
        }),
        a2uiCatalogComponentApi.list({ keyword: keyword.trim() || undefined }),
      ]);
      setCatalogs(loadedCatalogs);
      setComponents(loadedComponents);
    } catch (reason) {
      setCatalogs([]);
      setComponents([]);
      setError(reason instanceof Error ? reason.message : 'A2UI Catalog 加载失败');
    } finally {
      setLoading(false);
    }
  }, [keyword]);

  useEffect(() => {
    loadAssets();
  }, [loadAssets]);

  const openCreate = () => {
    setSelected(undefined);
    form.setFieldsValue(toFormValues(createEmptyA2uiCatalogComponent()));
    setDrawerOpen(true);
  };

  const openCatalogCreate = () => {
    setSelectedCatalog(undefined);
    setCatalogJsonText('{}');
    setCatalogDrawerOpen(true);
  };

  const openCatalogDetail = async (record: A2uiCatalogRecord) => {
    setLoading(true);
    try {
      const detail = await a2uiCatalogApi.detail(record.id);
      setSelectedCatalog(detail);
      setCatalogJsonText(jsonText(toA2uiCatalogAuthoringSource(detail)));
      setCatalogDrawerOpen(true);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : 'A2UI Catalog 详情加载失败');
    } finally {
      setLoading(false);
    }
  };

  const openDetail = async (record: A2uiCatalogComponentRecord) => {
    setLoading(true);
    try {
      const detail = await a2uiCatalogComponentApi.detail(record.id);
      setSelected(detail);
      form.setFieldsValue(toFormValues(detail));
      setDrawerOpen(true);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : 'A2UI 组件详情加载失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (selected && !isA2uiCatalogComponentEditable(selected)) {
      message.warning('当前组件不是可编辑的平台自研组件，已阻止保存');
      return;
    }
    const values = (await form.validateFields()) as A2uiCatalogComponentFormValues;
    const parsed = parseA2uiCatalogComponentForm(values);
    if (parsed.ok === false) {
      message.error(`组件合同校验失败：${parsed.errors?.join?.('、')}`);
      return;
    }
    setSaving(true);
    try {
      if (selected) await a2uiCatalogComponentApi.update(selected.id, parsed.component);
      else await a2uiCatalogComponentApi.create(parsed.component);
      message.success(selected ? 'A2UI 组件合同已更新' : 'A2UI 组件合同已创建');
      setDrawerOpen(false);
      await loadAssets();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : 'A2UI 组件合同保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleCatalogSave = async () => {
    if (selectedCatalog && !isA2uiCatalogEditable(selectedCatalog)) {
      message.warning('当前 Catalog 不是可编辑的平台自研 Catalog，已阻止保存');
      return;
    }
    const parsed = parseA2uiCatalogAuthoringJson(catalogJsonText);
    if (parsed.ok === false) {
      message.error(`Catalog JSON 校验失败：${parsed.errors?.join?.('、')}`);
      return;
    }
    setSaving(true);
    try {
      if (selectedCatalog) await a2uiCatalogApi.update(selectedCatalog.id, parsed.catalog);
      else await a2uiCatalogApi.create(parsed.catalog);
      message.success(selectedCatalog ? '平台自研 Catalog 已更新' : '平台自研 Catalog 已创建');
      setCatalogDrawerOpen(false);
      await loadAssets();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : 'A2UI Catalog 保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleManagedImport = async () => {
    setImportingManaged(true);
    setImportResult(undefined);
    setImportError('');
    try {
      const result = await a2uiCatalogApi.importManaged(sourceUrl);
      setImportResult(result);
      message.success('平台 Catalog JSON 导入完成');
      await loadAssets();
    } catch (reason) {
      const importFailure = reason instanceof Error ? reason.message : '平台 Catalog JSON 导入失败';
      setImportError(importFailure);
      message.error(importFailure);
    } finally {
      setImportingManaged(false);
    }
  };

  return (
    <div className="page-container component-center-page">
      <div className="page-header component-center-header">
        <div>
          <h1 className="page-title">A2UI Catalog</h1>
          <p className="page-subtitle">
            平台自研 Catalog 与组件合同；导入和 PRT/ONLINE 发布状态均由服务端投影
          </p>
        </div>
        <Space>
          <Button onClick={() => navigate('/management/components')}>
            返回组件中心
          </Button>
          <Button icon={<PlusOutlined />} onClick={openCreate}>
            新建平台组件
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCatalogCreate}>
            新建平台 Catalog
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        message="当前页面只展示平台自研资产"
        description="Catalog 必须由服务端投影为 PLATFORM_MANAGED，组件必须为 PLATFORM_CUSTOM；不根据 catalogId 猜来源，也不接受客户端自报 revision、digest、membership 或 release authority。"
        style={{ marginBottom: 16 }}
      />

      <Card title="导入 Catalog JSON" style={{ marginBottom: 16 }}>
        <Space wrap style={{ width: '100%' }}>
          <Input
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="输入受信的公开 Catalog JSON URL"
            style={{ width: 720, maxWidth: '100%' }}
          />
          <Button type="primary" loading={importingManaged} onClick={handleManagedImport}>
            导入 Catalog JSON
          </Button>
        </Space>
        <Paragraph type="secondary" style={{ margin: '12px 0 0' }}>
          请求只提交 sourceUrl；来源类型、摘要、成员和环境发布版本由服务端校验并生成。
        </Paragraph>
        {importResult ? (
          <Alert
            type={importResult.errors?.length ? 'warning' : 'success'}
            message={`${importResult.catalogId} · ${importResult.protocolVersion}`}
            description={`组件 ${importResult.importedAtomCount} / Functions ${
              importResult.functionCount
            } / rawDigest ${importResult.rawDigest}${
              importResult.errors?.length ? ` / ${importResult.errors?.join?.('、')}` : ''
            }`}
            style={{ marginTop: 12 }}
          />
        ) : null}
        {importError ? (
          <Alert
            type="error"
            message="Catalog JSON 导入失败"
            description={importError}
            style={{ marginTop: 12 }}
          />
        ) : null}
      </Card>

      <div className="component-center-metrics">
        <div>
          <Text type="secondary">Catalog</Text>
          <strong>{filteredCatalogs.length}</strong>
        </div>
        <div>
          <Text type="secondary">组件合同</Text>
          <strong>{filteredComponents.length}</strong>
        </div>
        <div>
          <Text type="secondary">已发布组件</Text>
          <strong>{availableCount}</strong>
        </div>
        <div>
          <Text type="secondary">PRT 可供 Application 选择</Text>
          <strong>{publishedCatalogs.length}</strong>
        </div>
      </div>

      <Card className="component-center-filter-card">
        <Space wrap>
          <Input
            value={keyword}
            placeholder="搜索 componentCode / type / 中文名"
            allowClear
            style={{ width: 320 }}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <Button onClick={loadAssets}>刷新</Button>
        </Space>
      </Card>
      {error ? <Alert type="error" message={error} style={{ marginBottom: 12 }} /> : null}

      <Card title="Catalog 资产" style={{ marginBottom: 16 }}>
        <Spin spinning={loading}>
          <Table
            rowKey="id"
            dataSource={filteredCatalogs}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无 A2UI Catalog" /> }}
            onRow={(record) => ({ onClick: () => openCatalogDetail(record) })}
            columns={[
              {
                title: 'Catalog',
                dataIndex: 'catalogId',
                render: (value: string, record: A2uiCatalogRecord) => (
                  <div className="component-center-name-cell">
                    <strong>{value}</strong>
                    <span>
                      PRT {a2uiCatalogReleaseFor(record, 'PRT')?.revision || '未发布'}
                    </span>
                  </div>
                ),
              },
              {
                title: '来源',
                width: 130,
                render: (_: unknown, record: A2uiCatalogRecord) => (
                  <Tag color="purple">{A2UI_CATALOG_SOURCE_LABELS[record.catalogSourceType]}</Tag>
                ),
              },
              {
                title: 'PRT digest',
                width: 240,
                render: (_: unknown, record: A2uiCatalogRecord) =>
                  a2uiCatalogReleaseFor(record, 'PRT')?.digest || '-',
              },
              {
                title: '导入成员 / 发布闭包',
                width: 180,
                render: (_: unknown, record: A2uiCatalogRecord) => {
                  const membership = projectA2uiCatalogMembership(record);
                  return `${membership.importedCount ?? '待详情'} / ${membership.releasedCount}`;
                },
              },
              {
                title: '环境发布',
                width: 220,
                render: (_: unknown, record: A2uiCatalogRecord) => (
                  <Space wrap>
                    <Tag
                      color={
                        a2uiCatalogReleaseFor(record, 'PRT')?.enabled ? 'success' : 'default'
                      }
                    >
                      PRT{' '}
                      {a2uiCatalogReleaseFor(record, 'PRT')?.enabled ? '已发布' : '未发布'}
                    </Tag>
                    <Tag
                      color={
                        a2uiCatalogReleaseFor(record, 'ONLINE')?.enabled ? 'success' : 'default'
                      }
                    >
                      ONLINE{' '}
                      {a2uiCatalogReleaseFor(record, 'ONLINE')?.enabled ? '已发布' : '未发布'}
                    </Tag>
                  </Space>
                ),
              },
              {
                title: '操作',
                width: 100,
                render: (_: unknown, record: A2uiCatalogRecord) => (
                  <Button
                    type="link"
                    icon={isA2uiCatalogEditable(record) ? <EditOutlined /> : undefined}
                    onClick={(event) => {
                      event.stopPropagation();
                      openCatalogDetail(record);
                    }}
                  >
                    {isA2uiCatalogEditable(record) ? '编辑' : '查看'}
                  </Button>
                ),
              },
            ]}
          />
        </Spin>
      </Card>

      <Card title="Catalog 组件合同">
        <Spin spinning={loading}>
          <Table
            rowKey="id"
            dataSource={filteredComponents}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无 A2UI 基础组件合同" /> }}
            onRow={(record) => ({ onClick: () => openDetail(record) })}
            columns={[
              {
                title: '组件',
                dataIndex: 'componentCode',
                render: (value: string, record: A2uiCatalogComponentRecord) => (
                  <div className="component-center-name-cell">
                    <strong>{record.nameCn || record.type}</strong>
                    <span>{value}</span>
                  </div>
                ),
              },
              {
                title: 'Catalog 来源',
                width: 130,
                render: (_: unknown, record: A2uiCatalogComponentRecord) => (
                  <Tag color="purple">{A2UI_CATALOG_SOURCE_LABELS[record.catalogSourceType]}</Tag>
                ),
              },
              {
                title: '组件来源',
                width: 120,
                render: (_: unknown, record: A2uiCatalogComponentRecord) =>
                  A2UI_COMPONENT_ORIGIN_LABELS[record.componentOriginType],
              },
              { title: 'type', dataIndex: 'type', width: 130 },
              { title: '分类', dataIndex: 'category', width: 110 },
              {
                title: 'Catalog revision',
                width: 180,
                render: (_: unknown, record: A2uiCatalogComponentRecord) =>
                  record.release?.revision || '-',
              },
              {
                title: '发布状态',
                width: 140,
                render: (_: unknown, record: A2uiCatalogComponentRecord) => (
                  <Tag color={record.release?.enabled ? 'success' : 'default'}>
                    {record.release?.enabled ? '已发布' : '未发布'}
                  </Tag>
                ),
              },
              {
                title: '操作',
                width: 120,
                render: (_: unknown, record: A2uiCatalogComponentRecord) => (
                  <Button
                    type="link"
                    icon={isA2uiCatalogComponentEditable(record) ? <EditOutlined /> : undefined}
                    onClick={(event) => {
                      event.stopPropagation();
                      openDetail(record);
                    }}
                  >
                    {isA2uiCatalogComponentEditable(record) ? '编辑' : '查看'}
                  </Button>
                ),
              },
            ]}
          />
        </Spin>
      </Card>

      <Drawer
        title={
          selectedCatalog
            ? `${selectedCatalog.catalogId} · ${
                selectedCatalogReadonly ? '只读 Catalog' : 'Catalog'
              }`
            : '新建平台自研 Catalog'
        }
        visible={catalogDrawerOpen}
        onClose={() => setCatalogDrawerOpen(false)}
        width={920}
      >
        {selectedCatalog ? (
          <Alert
            type={selectedCatalogReadonly ? 'warning' : 'info'}
            message={
              selectedCatalogReadonly
                ? '当前 Catalog 不可通过普通编辑修改'
                : '仅 catalogJson 可编辑'
            }
            description={`${
              A2UI_CATALOG_SOURCE_LABELS[selectedCatalog.catalogSourceType]
            } / PRT ${
              a2uiCatalogReleaseFor(selectedCatalog, 'PRT')?.revision || '未发布'
            } · ${a2uiCatalogReleaseFor(selectedCatalog, 'PRT')?.digest || '-'} / ONLINE ${
              a2uiCatalogReleaseFor(selectedCatalog, 'ONLINE')?.revision || '未发布'
            } · ${a2uiCatalogReleaseFor(selectedCatalog, 'ONLINE')?.digest || '-'}`}
            style={{ marginBottom: 16 }}
          />
        ) : (
          <Alert
            type="info"
            message="普通创建固定为平台自研 Catalog"
            description="catalogSourceType、readOnly/editable 与 PRT/ONLINE revision/digest 均由服务端生成，catalogJson 不得自报这些权威字段。"
            style={{ marginBottom: 16 }}
          />
        )}
        {selectedCatalogMembership ? (
          <Card size="small" title="Catalog membership" style={{ marginBottom: 16 }}>
            <Space wrap style={{ marginBottom: 12 }}>
              <Tag color="blue">
                导入源成员 {selectedCatalogMembership.importedCount ?? '详情未投影'}
              </Tag>
              <Tag color="green">已发布组件类型 {selectedCatalogMembership.releasedCount}</Tag>
            </Space>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">导入源 canonical componentCodes</Text>
              <div style={{ marginTop: 8 }}>
                {selectedCatalogMembership.importedComponentCodes?.length ? (
                  <Space wrap>
                    {selectedCatalogMembership.importedComponentCodes?.map?.((componentCode) => (
                      <Tag key={componentCode}>{componentCode}</Tag>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">详情未返回 canonical componentCodes</Text>
                )}
              </div>
            </div>
            <div>
              <Text type="secondary">已发布 componentOrigins</Text>
              <div style={{ marginTop: 8 }}>
                {selectedCatalogMembership.releasedComponentOrigins?.length ? (
                  <Space wrap>
                    {selectedCatalogMembership.releasedComponentOrigins?.map?.((origin) => (
                      <Tag key={origin.type}>
                        {origin.type} · {A2UI_COMPONENT_ORIGIN_LABELS[origin.componentOriginType]}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">尚无已发布 membership 闭包</Text>
                )}
              </div>
            </div>
          </Card>
        ) : null}
        <Form layout="vertical">
          <Form.Item label="Catalog authoring JSON">
            <JsonFormatTextArea
              value={catalogJsonText}
              disabled={selectedCatalogReadonly}
              autoSize={{ minRows: 18, maxRows: 30 }}
              onChange={(event) => setCatalogJsonText(event.target.value)}
            />
          </Form.Item>
          <Space>
            <Button onClick={() => setCatalogDrawerOpen(false)}>关闭</Button>
            {selectedCatalogReadonly ? null : (
              <Button type="primary" loading={saving} onClick={handleCatalogSave}>
                保存 Catalog
              </Button>
            )}
          </Space>
        </Form>
        {selectedCatalogReleaseBinding ? (
          <div style={{ marginTop: 24 }}>
            <AssetReleaseTab
              assetType={selectedCatalogReleaseBinding.assetType}
              assetKey={selectedCatalogReleaseBinding.assetKey}
              title="A2UI Catalog 发布管理"
            />
          </div>
        ) : selectedCatalog ? (
          <Alert
            type="error"
            message="Catalog 详情缺少 catalogId，已阻止打开发布管理"
            style={{ marginTop: 24 }}
          />
        ) : null}
      </Drawer>

      <Drawer
        title={
          selected
            ? `${selected.nameCn || selected.type} · ${selectedReadonly ? '只读合同' : '组件合同'}`
            : '新建平台自研组件'
        }
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={920}
      >
        {selected ? (
          <Alert
            type={selectedReadonly ? 'warning' : 'info'}
            message={selectedReadonly ? '当前组件不可通过普通编辑修改' : 'Catalog 发布信息只读'}
            description={`${selected.release?.catalogId || '待服务端返回'} / ${
              selected.release?.revision || '-'
            } / ${selected.release?.digest || '-'} / ${
              selected.release?.enabled ? '已发布' : '未发布'
            }`}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        <Form form={form} layout="vertical">
          <div className="component-center-form-grid">
            <Form.Item label="componentCode" name="componentCode" rules={[{ required: true }]}>
              <Input disabled={Boolean(selected)} />
            </Form.Item>
            <Form.Item label="A2UI component type" name="type" rules={[{ required: true }]}>
              <Input disabled={selectedReadonly} />
            </Form.Item>
            <Form.Item label="中文名" name="nameCn" rules={[{ required: true }]}>
              <Input disabled={selectedReadonly} />
            </Form.Item>
            <Form.Item label="分类" name="category" rules={[{ required: true }]}>
              <Select disabled={selectedReadonly} options={categoryOptions} />
            </Form.Item>
            <Form.Item label="资产粒度" name="compositionKind">
              <Input disabled />
            </Form.Item>
          </div>
          <Form.Item label="Props schema" name="propsSchemaJson" rules={[{ required: true }]}>
            <JsonFormatTextArea
              disabled={selectedReadonly}
              autoSize={{ minRows: 5, maxRows: 16 }}
            />
          </Form.Item>
          <Form.Item label="Event schema" name="eventSchemaJson" rules={[{ required: true }]}>
            <JsonFormatTextArea
              disabled={selectedReadonly}
              autoSize={{ minRows: 5, maxRows: 16 }}
            />
          </Form.Item>
          <Form.Item
            label="Children / slot 约束"
            name="childrenConstraintJson"
            rules={[{ required: true }]}
          >
            <JsonFormatTextArea
              disabled={selectedReadonly}
              autoSize={{ minRows: 4, maxRows: 12 }}
            />
          </Form.Item>
          <Form.Item
            label="合法消息示例"
            name="validMessageExampleJson"
            rules={[{ required: true }]}
          >
            <JsonFormatTextArea
              disabled={selectedReadonly}
              autoSize={{ minRows: 5, maxRows: 16 }}
            />
          </Form.Item>
          <Form.Item
            label="非法消息示例"
            name="invalidMessageExampleJson"
            rules={[{ required: true }]}
          >
            <JsonFormatTextArea
              disabled={selectedReadonly}
              autoSize={{ minRows: 5, maxRows: 16 }}
            />
          </Form.Item>
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>关闭</Button>
            {selectedReadonly ? null : (
              <Button type="primary" loading={saving} onClick={handleSave}>
                保存组件合同
              </Button>
            )}
          </Space>
        </Form>
      </Drawer>
    </div>
  );
};

export default A2uiCatalogPage;
