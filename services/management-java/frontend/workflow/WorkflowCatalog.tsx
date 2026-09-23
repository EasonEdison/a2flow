import React, { useMemo, useState } from 'react';
import { Alert, Button, Empty, Input, Modal, Select, Tag, Typography, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { WorkflowListItemView, WorkflowSpecialistOption } from './types';

const { Text } = Typography;
const { TextArea } = Input;

const pointerLabel = (item: WorkflowListItemView, environment: string): string => {
  const pointer = item.environmentPointers?.[environment];
  if (!pointer) return '未发布';
  if (pointer.version !== undefined) return `v${pointer.version}`;
  return pointer.sourceId || pointer.status || '已发布';
};

interface WorkflowCatalogProps {
  items: WorkflowListItemView[];
  activeWorkflowCode?: string;
  specialists: WorkflowSpecialistOption[];
  readonly: boolean;
  creating: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onSelect: (workflowCode: string) => void;
  onCreate: (payload: {
    displayName: string;
    description: string;
    specialistCode: string;
  }) => Promise<void>;
}

const WorkflowCatalog: React.FC<WorkflowCatalogProps> = ({
  items,
  activeWorkflowCode,
  specialists,
  readonly,
  creating,
  hasMore,
  loadingMore,
  onLoadMore,
  onSelect,
  onCreate,
}) => {
  const [visible, setVisible] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [specialistCode, setSpecialistCode] = useState<string>();
  const specialistByCode = useMemo(
    () => new Map(specialists.map((item) => [item.specialistCode, item.specialistName])),
    [specialists],
  );

  const submit = async () => {
    if (!displayName.trim() || !specialistCode) {
      message.warning('请填写 Workflow 名称并选择所属专员');
      return;
    }
    try {
      await onCreate({
        displayName: displayName.trim(),
        description: description.trim(),
        specialistCode,
      });
      setVisible(false);
      setDisplayName('');
      setDescription('');
      setSpecialistCode(undefined);
    } catch {
      // 父页面已展示真实后端错误；保留用户输入便于修正后重试。
    }
  };

  return (
    <aside className="workflow-catalog-panel">
      <div className="workflow-panel-heading">
        <div>
          <Text strong>Workflow 资产</Text>
          <Text type="secondary">{items.length} 个配置</Text>
        </div>
        {!readonly ? (
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setVisible(true)}
          >
            新建
          </Button>
        ) : null}
      </div>
      <div className="workflow-catalog-list">
        {items.length ? (
          items.map((item) => {
            const workflow = item.workflow;
            const active = workflow.workflowCode === activeWorkflowCode;
            return (
              <button
                type="button"
                className={`workflow-catalog-item${active ? ' active' : ''}`}
                key={workflow.workflowCode}
                onClick={() => onSelect(workflow.workflowCode)}
              >
                <span className="workflow-catalog-title-row">
                  <strong>{workflow.displayName || workflow.workflowCode}</strong>
                  <Tag>{workflow.status}</Tag>
                </span>
                <span className="workflow-catalog-code">{workflow.workflowCode}</span>
                <span className="workflow-catalog-description">
                  {workflow.description || '暂无描述'}
                </span>
                <span className="workflow-catalog-meta">
                  {specialistByCode.get(workflow.specialistCode) || workflow.specialistCode} ·
                  revision {workflow.draftRevision} · PRT {pointerLabel(item, 'PRT')} ·
                  ONLINE {pointerLabel(item, 'ONLINE')}
                </span>
              </button>
            );
          })
        ) : (
          <Empty description="暂无可见 Workflow" />
        )}
        {hasMore ? (
          <Button loading={loadingMore} onClick={onLoadMore}>
            加载更多
          </Button>
        ) : null}
      </div>
      <Modal
        title="新建 Workflow"
        visible={visible}
        okText="创建"
        cancelText="取消"
        confirmLoading={creating}
        onOk={() => void submit()}
        onCancel={() => setVisible(false)}
      >
        <div className="workflow-create-form">
          <label>
            <span>Workflow 名称</span>
            <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
          <label>
            <span>所属专员</span>
            <Select
              value={specialistCode}
              placeholder="从受控列表选择"
              options={specialists.map((item) => ({
                value: item.specialistCode,
                label: item.specialistName,
              }))}
              onChange={(value) => setSpecialistCode(typeof value === 'string' ? value : undefined)}
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
          <Alert type="info" showIcon message="workflowCode 由后端生成，专员创建后不可修改。" />
        </div>
      </Modal>
    </aside>
  );
};

export default WorkflowCatalog;
