import React from 'react';
import { Alert, Button, Input, Select, Space, Tag, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { normalizeWorkflowDraft } from './model';
import { WORKFLOW_BRANCH_KEY_MAX_LENGTH } from './workflowValidation';
import type { WorkflowDraft, WorkflowParallelEdge, WorkflowParallelForkNode } from './types';

const { Text } = Typography;

interface ParallelInspectorProps {
  draft: WorkflowDraft;
  node: WorkflowParallelForkNode;
  readonly: boolean;
  targetOptions: Array<{ value: string; label: string }>;
  onChange: (draft: WorkflowDraft) => void;
}

interface BranchCardProps {
  edge: WorkflowParallelEdge;
  count: number;
  readonly: boolean;
  targetOptions: Array<{ value: string; label: string }>;
  onUpdate: (edgeId: string, patch: Partial<WorkflowParallelEdge>) => void;
  onRemove: (edgeId: string) => void;
}

const BranchCard: React.FC<BranchCardProps> = ({
  edge,
  count,
  readonly,
  targetOptions,
  onUpdate,
  onRemove,
}) => (
  <div className="workflow-router-candidate-card">
    <Space>
      <Tag>顺序 {edge.branchOrder}</Tag>
      {!readonly ? (
        <Button
          type="text"
          icon={<DeleteOutlined />}
          disabled={count <= 2}
          onClick={() => onRemove(edge.edgeId)}
        />
      ) : null}
    </Space>
    <Input
      disabled={readonly}
      value={edge.branchKey}
      placeholder="branchKey"
      maxLength={WORKFLOW_BRANCH_KEY_MAX_LENGTH}
      onChange={(event) => onUpdate(edge.edgeId, { branchKey: event.target.value })}
    />
    <Input
      disabled={readonly}
      type="number"
      min={1}
      value={edge.branchOrder}
      onChange={(event) => onUpdate(edge.edgeId, { branchOrder: Number(event.target.value) })}
    />
    <Select
      disabled={readonly}
      value={edge.targetNodeCode || undefined}
      placeholder="分支入口节点"
      options={targetOptions}
      onChange={(value) => onUpdate(edge.edgeId, { targetNodeCode: value })}
    />
  </div>
);

const ParallelForkInspector: React.FC<ParallelInspectorProps> = ({
  draft,
  node,
  readonly,
  targetOptions,
  onChange,
}) => {
  const branchEdges = draft.edges?.filter?.(
    (edge): edge is WorkflowParallelEdge =>
      edge.edgeType === 'PARALLEL' && edge.sourceNodeCode === node.nodeCode,
  );
  const updateNode = (patch: Partial<WorkflowParallelForkNode>) => {
    if (readonly) return;
    onChange(
      normalizeWorkflowDraft({
        ...draft,
        nodes: draft.nodes?.map?.((item) =>
          item.nodeCode === node.nodeCode ? { ...node, ...patch } : item,
        ),
      }),
    );
  };
  const updateBranch = (edgeId: string, patch: Partial<WorkflowParallelEdge>) => {
    if (readonly) return;
    onChange(
      normalizeWorkflowDraft({
        ...draft,
        edges: draft.edges?.map?.((edge) =>
          edge.edgeId === edgeId && edge.edgeType === 'PARALLEL' ? { ...edge, ...patch } : edge,
        ),
      }),
    );
  };
  const addBranch = () => {
    if (readonly) return;
    const branchOrder = Math.max(0, ...branchEdges.map((edge) => edge.branchOrder)) + 1;
    const edge: WorkflowParallelEdge = {
      edgeId: `${node.nodeCode}__BRANCH__${branchOrder}`,
      edgeType: 'PARALLEL',
      sourceNodeCode: node.nodeCode,
      targetNodeCode: '',
      branchKey: `branch_${branchOrder}`,
      branchOrder,
    };
    onChange(normalizeWorkflowDraft({ ...draft, edges: [...draft.edges, edge] }));
  };
  const removeBranch = (edgeId: string) => {
    if (readonly || branchEdges.length <= 2) return;
    onChange(
      normalizeWorkflowDraft({
        ...draft,
        edges: draft.edges?.filter?.((edge) => edge.edgeId !== edgeId),
      }),
    );
  };
  const joinOptions = draft?.nodes
    ?.filter?.((item) => item.nodeType === 'PARALLEL_JOIN')
    ?.map?.((item) => ({
      value: item.nodeCode,
      label: item.displayName || item.nodeCode,
    }));
  const invalidSystemTargets = branchEdges.flatMap((edge) => {
    const target = draft.nodes?.find?.((item) => item.nodeCode === edge.targetNodeCode);
    if (target?.nodeType !== 'PARALLEL_FORK' && target?.nodeType !== 'PARALLEL_JOIN') {
      return [];
    }
    return [`${edge.branchKey || edge.edgeId} → ${target.nodeCode}`];
  });
  return (
    <>
      <label>
        <span>节点名称（可选）</span>
        <Input
          disabled={readonly}
          value={node.displayName || ''}
          onChange={(event) => updateNode({ displayName: event.target.value })}
        />
      </label>
      <label>
        <span>匹配 Join</span>
        <Select
          disabled={readonly}
          value={node.matchingNodeCode || undefined}
          options={joinOptions}
          onChange={(value) => updateNode({ matchingNodeCode: value })}
        />
      </label>
      <label>
        <span>maxParallelism</span>
        <Input
          disabled={readonly}
          type="number"
          min={2}
          value={node.maxParallelism}
          onChange={(event) => updateNode({ maxParallelism: Number(event.target.value) })}
        />
      </label>
      <Text type="secondary">joinPolicy（只读）：{node.joinPolicy}</Text>
      <div className="workflow-router-candidate-heading">
        <Text strong>并行分支</Text>
        {!readonly ? (
          <Button size="small" icon={<PlusOutlined />} onClick={addBranch}>
            添加分支
          </Button>
        ) : null}
      </div>
      {branchEdges.map((edge) => (
        <BranchCard
          key={edge.edgeId}
          edge={edge}
          count={branchEdges.length}
          readonly={readonly}
          targetOptions={targetOptions}
          onUpdate={updateBranch}
          onRemove={removeBranch}
        />
      ))}
      {invalidSystemTargets.length ? (
        <Alert
          type="warning"
          showIcon
          message={`分支目标不能直接选择 Fork/Join：${invalidSystemTargets.join('、')}`}
        />
      ) : null}
    </>
  );
};

export default ParallelForkInspector;
