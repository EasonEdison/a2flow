import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { skillFactoryApi } from '../api';
import type { SkillFactorySpecialistOption } from '../api';
import {
  resolveSkillFactorySpecialists,
  specialistOptionId,
  specialistOptionName,
} from '../shared/specialistOptions';
import { workflowApi } from './workflowApi';
import type { WorkflowListItemView } from './types';
import './workflowList.less';

const { Text, Title } = Typography;
const { TextArea } = Input;

const errorMessage = (cause: unknown, fallback: string): string =>
  cause instanceof Error ? cause.message : fallback;

const pointerLabel = (item: WorkflowListItemView, environment: string): string => {
  const pointer = item.environmentPointers?.[environment];
  if (!pointer) return '未发布';
  if (pointer.version !== undefined) return `v${pointer.version}`;
  return pointer.sourceId || pointer.status || '已发布';
};

const formatTime = (timestamp?: number): string => {
  if (!timestamp) return '-';
  const milliseconds = timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp;
  const date = new Date(milliseconds);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN');
};

const WorkflowListPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [items, setItems] = useState<WorkflowListItemView[]>([]);
  const [specialists, setSpecialists] = useState<SkillFactorySpecialistOption[]>([]);
  const [nextPageToken, setNextPageToken] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [specialistFilter, setSpecialistFilter] = useState<string>();
  const [statusFilter, setStatusFilter] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createVisible, setCreateVisible] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [createSpecialistCode, setCreateSpecialistCode] = useState<string>();
  const [errorText, setErrorText] = useState('');

  const loadFirstPage = useCallback(async () => {
    setLoading(true);
    setErrorText('');
    const [pageResult, configResult] = await Promise.allSettled([
      workflowApi.list({ limit: 30 }),
      skillFactoryApi.config(),
    ]);
    if (configResult.status === 'fulfilled') {
      setSpecialists(resolveSkillFactorySpecialists(configResult.value?.specialists));
    } else {
      setSpecialists(resolveSkillFactorySpecialists());
      // 与 Skill 页面保持一致：配置不可用时使用同一默认专员集合。
      // eslint-disable-next-line no-console
      console.warn('SkillFactory config load failed', configResult.reason);
    }
    try {
      if (pageResult.status === 'rejected') {
        throw pageResult.reason;
      }
      const page = pageResult.value;
      setItems(page.items);
      setNextPageToken(page.nextPageToken || undefined);
    } catch (cause) {
      setErrorText(errorMessage(cause, 'Workflow 列表加载失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFirstPage();
  }, [loadFirstPage]);

  const specialistByCode = useMemo(
    () =>
      new Map(specialists.map((item) => [specialistOptionId(item), specialistOptionName(item)])),
    [specialists],
  );

  const statusOptions = useMemo(
    () =>
      Array.from(new Set(items.map((item) => item.workflow?.status))).map((status) => ({
        value: status,
        label: status,
      })),
    [items],
  );

  const visibleItems = useMemo(() => {
    const normalizedKeyword = keyword?.trim()?.toLowerCase?.();
    return items.filter((item) => {
      const workflow = item.workflow;
      const specialistName =
        specialistByCode.get(workflow.specialistCode) || workflow.specialistCode;
      const matchesKeyword =
        !normalizedKeyword ||
        [workflow.displayName, workflow.workflowCode, workflow.description, specialistName]
          ?.filter(Boolean)
          ?.some?.((value) => value?.toLowerCase()?.includes?.(normalizedKeyword));
      return (
        matchesKeyword &&
        (!specialistFilter || workflow.specialistCode === specialistFilter) &&
        (!statusFilter || workflow.status === statusFilter)
      );
    });
  }, [items, keyword, specialistByCode, specialistFilter, statusFilter]);

  const onlineCount = items?.filter((item) => item.environmentPointers?.ONLINE)?.length;
  const editingCount = items.length - onlineCount;

  const loadMore = async () => {
    if (!nextPageToken) return;
    setLoadingMore(true);
    try {
      const page = await workflowApi.list({
        pageToken: nextPageToken,
        limit: 30,
      });
      setItems((current) => [...current, ...page.items]);
      setNextPageToken(page.nextPageToken || undefined);
    } catch (cause) {
      message.error(errorMessage(cause, '更多 Workflow 加载失败'));
    } finally {
      setLoadingMore(false);
    }
  };

  const createWorkflow = async () => {
    if (!displayName.trim() || !createSpecialistCode) {
      message.warning('请填写 Workflow 名称并选择所属专员');
      return;
    }
    setCreating(true);
    try {
      const created = await workflowApi.create({
        displayName: displayName.trim(),
        description: description.trim(),
        specialistCode: createSpecialistCode,
      });
      message.success('Workflow 已创建');
      setCreateVisible(false);
      navigate(workflowDetailPath(created.workflowCode));
    } catch (cause) {
      message.error(errorMessage(cause, 'Workflow 创建失败'));
    } finally {
      setCreating(false);
    }
  };

  const workflowDetailPath = useCallback(
    (workflowCode: string) => {
      const searchParams = new URLSearchParams(location.search);
      searchParams.set('workflowCode', workflowCode);
      return `/management/workflows/detail?${searchParams.toString()}`;
    },
    [location.search],
  );

  const resetFilters = () => {
    setKeyword('');
    setSpecialistFilter(undefined);
    setStatusFilter(undefined);
  };

  return (
    <div className="page-container workflow-list-page">
      <header className="workflow-list-header">
        <div className="workflow-list-title-block">
          <div>
            <Title level={3}>Workflow 列表</Title>
            <Text type="secondary">管理 Workflow 配置、版本指针与发布状态</Text>
          </div>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void loadFirstPage()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateVisible(true)}>
            新建 Workflow
          </Button>
        </Space>
      </header>

      {errorText ? <Alert type="error" showIcon message={errorText} /> : null}

      <Spin spinning={loading}>
        <section className="workflow-list-metrics">
          <div>
            <Text type="secondary">Workflow 总数</Text>
            <strong>{items.length}</strong>
          </div>
          <div>
            <Text type="secondary">编辑中</Text>
            <strong>{editingCount}</strong>
          </div>
          <div>
            <Text type="secondary">已上线</Text>
            <strong>{onlineCount}</strong>
          </div>
        </section>

        <Card className="workflow-list-filter-card">
          <Space wrap>
            <Input
              allowClear
              className="workflow-list-search"
              prefix={<SearchOutlined />}
              placeholder="搜索 Workflow / 专员"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="workflow-list-select"
              placeholder="所属专员"
              value={specialistFilter}
              options={specialists.map((item) => ({
                value: specialistOptionId(item),
                label: specialistOptionName(item),
              }))}
              onChange={(value) =>
                setSpecialistFilter(typeof value === 'string' ? value : undefined)
              }
            />
            <Select
              allowClear
              className="workflow-list-select"
              placeholder="状态"
              value={statusFilter}
              options={statusOptions}
              onChange={(value) => setStatusFilter(typeof value === 'string' ? value : undefined)}
            />
            <Button icon={<ReloadOutlined />} onClick={resetFilters}>
              重置
            </Button>
          </Space>
        </Card>

        <section className="workflow-list-card-grid">
          {visibleItems.length ? (
            visibleItems.map((item) => {
              const workflow = item.workflow;
              return (
                <Card hoverable className="workflow-list-card" key={workflow.workflowCode}>
                  <div className="workflow-list-card-head">
                    <div>
                      <strong>{workflow.displayName || workflow.workflowCode}</strong>
                      <span>{workflow.workflowCode}</span>
                    </div>
                    <div className="workflow-list-card-tags">
                      <Tag>{workflow.status}</Tag>
                      <Tag color={item.environmentPointers?.ONLINE ? 'success' : undefined}>
                        {item.environmentPointers?.ONLINE ? '已上线' : '未上线'}
                      </Tag>
                    </div>
                  </div>
                  <p>{workflow.description || '暂无 Workflow 描述'}</p>
                  <div className="workflow-list-kv-grid">
                    <div>
                      <span>所属专员</span>
                      <b>
                        {specialistByCode.get(workflow.specialistCode) || workflow.specialistCode}
                      </b>
                    </div>
                    <div>
                      <span>草稿版本</span>
                      <b>revision {workflow.draftRevision}</b>
                    </div>
                    <div>
                      <span>PRT</span>
                      <b>{pointerLabel(item, 'PRT')}</b>
                    </div>
                    <div>
                      <span>ONLINE</span>
                      <b>{pointerLabel(item, 'ONLINE')}</b>
                    </div>
                    <div>
                      <span>更新人</span>
                      <b>{workflow.updatedBy || workflow.createdBy || '-'}</b>
                    </div>
                    <div>
                      <span>更新时间</span>
                      <b>{formatTime(workflow.updateTime)}</b>
                    </div>
                  </div>
                  <div className="workflow-list-card-footer">
                    <Tag>{workflow.workflowCode}</Tag>
                    <Button
                      type="primary"
                      onClick={() => navigate(workflowDetailPath(workflow.workflowCode))}
                    >
                      查看详情
                    </Button>
                  </div>
                </Card>
              );
            })
          ) : (
            <Card className="workflow-list-empty-card">
              <Empty description="暂无符合条件的 Workflow" />
            </Card>
          )}
        </section>

        {nextPageToken ? (
          <div className="workflow-list-load-more">
            <Button loading={loadingMore} onClick={() => void loadMore()}>
              加载更多
            </Button>
          </div>
        ) : null}
      </Spin>

      <Modal
        title="新建 Workflow"
        visible={createVisible}
        okText="创建"
        cancelText="取消"
        confirmLoading={creating}
        onOk={() => void createWorkflow()}
        onCancel={() => setCreateVisible(false)}
      >
        <div className="workflow-list-create-form">
          <label>
            <span>Workflow 名称</span>
            <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
          <label>
            <span>所属专员</span>
            <Select
              value={createSpecialistCode}
              placeholder="从受控列表选择"
              options={specialists.map((item) => ({
                value: specialistOptionId(item),
                label: specialistOptionName(item),
              }))}
              onChange={(value) =>
                setCreateSpecialistCode(typeof value === 'string' ? value : undefined)
              }
            />
          </label>
          <label>
            <span>描述</span>
            <TextArea
              rows={4}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <Alert type="info" showIcon message="workflowCode 由后端生成，所属专员创建后不可修改。" />
        </div>
      </Modal>
    </div>
  );
};

export default WorkflowListPage;
