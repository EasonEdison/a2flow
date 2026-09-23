import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Input, Select, Space, Spin, Table } from 'antd';
import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { a2uiApplicationApi } from './api';
import { a2uiApplicationEditorRoute } from './a2uiCatalogContracts';
import type { A2uiApplicationQuery, A2uiApplicationRecord } from './a2uiApplicationContracts';
import { extractShowComponents } from './a2uiApplicationShowAst';
import {
  A2uiApplicationReleaseStatus,
  applicationStatusOptions,
} from './A2uiApplicationReleaseStatus';

const A2uiApplicationListPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState<A2uiApplicationQuery>({ status: 'ALL' });
  const [applications, setApplications] = useState<A2uiApplicationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadApplications = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setApplications(
        await a2uiApplicationApi.list({
          keyword: query.keyword?.trim(),
          status: query.status,
        }),
      );
    } catch (reason) {
      setApplications([]);
      setError(reason instanceof Error ? reason.message : 'A2UI 编排列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    loadApplications();
  }, [loadApplications]);

  const openEditor = (id?: string) => {
    navigate(a2uiApplicationEditorRoute(id, searchParams));
  };

  return (
    <div className="page-container component-center-page">
      <div className="page-header component-center-header">
        <div>
          <h1 className="page-title">A2UI Application 编排</h1>
          <p className="page-subtitle">
            商品卡、确认表单和页面都在这里由基础组件编排，不进入基础组件库
          </p>
        </div>
        <Space>
          <Button onClick={() => navigate('/management/components')}>
            返回组件中心
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>
            创建 A2UI 编排
          </Button>
        </Space>
      </div>

      <Alert
        type="warning"
        message="当前只提供 M 端配置、结构/JSON/contract preview"
        description="B 端 Renderer 尚未接入，不能把结构预览称为最终视觉预览；Catalog PRT/ONLINE 精确版本与服务端扫描 blocker 未闭合时发布必须 fail closed。"
        style={{ marginBottom: 16 }}
      />

      <Card className="component-center-filter-card">
        <Space wrap>
          <Select
            value={query.status || 'ALL'}
            options={applicationStatusOptions}
            style={{ width: 180 }}
            onChange={(value) =>
              setQuery((current) => ({
                ...current,
                status: value as A2uiApplicationQuery['status'],
              }))
            }
          />
          <Input
            value={query.keyword}
            placeholder="搜索 appCode / 中文名"
            allowClear
            style={{ width: 320 }}
            onChange={(event) =>
              setQuery((current) => ({ ...current, keyword: event.target.value }))
            }
          />
          <Button onClick={loadApplications}>刷新</Button>
        </Space>
      </Card>

      {error ? <Alert type="error" message={error} style={{ marginBottom: 12 }} /> : null}

      <Card title="Application 列表">
        <Spin spinning={loading}>
          <Table
            rowKey="id"
            dataSource={applications}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无 A2UI Application" /> }}
            onRow={(record) => ({ onClick: () => openEditor(record.id) })}
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
                width: 210,
                render: (_: unknown, record: A2uiApplicationRecord) => (
                  <span>
                    {record.catalog?.catalogId}@{record.catalog?.revision || '-'}
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
                      openEditor(record.id);
                    }}
                  >
                    编辑
                  </Button>
                ),
              },
            ]}
          />
        </Spin>
      </Card>
    </div>
  );
};

export default A2uiApplicationListPage;
