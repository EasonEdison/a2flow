import React, { useMemo } from 'react';
import { Button, Empty, Space, Tag, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import {
  appendParallelPair,
  appendWorkflowRouter,
  appendWorkflowSkill,
  buildWorkflowGraphLayers,
} from './model';
import type {
  WorkflowDraft,
  WorkflowEdge,
  WorkflowNode,
  WorkflowSkillOption,
  WorkflowValidationIssue,
} from './types';

const { Text } = Typography;

const nodeColor: Record<WorkflowNode['nodeType'], string> = {
  SKILL: 'blue',
  ROUTER: 'purple',
  PARALLEL_FORK: 'orange',
  PARALLEL_JOIN: 'gold',
  SUMMARY: 'green',
};

const nodeSummary = (node: WorkflowNode, skills: Map<string, WorkflowSkillOption>): string => {
  if (node.nodeType === 'SKILL') {
    return skills?.get(node.skillCode)?.displayName || node.skillCode || '尚未选择 Skill';
  }
  if (node.nodeType === 'ROUTER') return `${node.candidates?.length} 条候选路由`;
  if (node.nodeType === 'PARALLEL_FORK') return `最大并发 ${node.maxParallelism}`;
  if (node.nodeType === 'PARALLEL_JOIN') return `匹配 ${node.matchingNodeCode || '未配置'}`;
  return node.prompt || '尚未配置 Summary Prompt';
};

const edgeLabel = (edge: WorkflowEdge): string => {
  if (edge.edgeType === 'ROUTING')
    return `${edge.routeKey || 'routeKey?'} → ${edge.targetNodeCode || '未选择'}`;
  if (edge.edgeType === 'PARALLEL')
    return `${edge.branchKey || 'branchKey?'} #${edge.branchOrder} → ${
      edge.targetNodeCode || '未选择'
    }`;
  return `固定后继 → ${edge.targetNodeCode || '未选择'}`;
};

interface WorkflowCanvasProps {
  draft?: WorkflowDraft;
  skills: WorkflowSkillOption[];
  selectedNodeCode?: string;
  issues: WorkflowValidationIssue[];
  readonly: boolean;
  onSelectNode: (nodeCode: string) => void;
  onChange: (draft: WorkflowDraft) => void;
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  draft,
  skills,
  selectedNodeCode,
  issues,
  readonly,
  onSelectNode,
  onChange,
}) => {
  const layers = useMemo(() => (draft ? buildWorkflowGraphLayers(draft) : []), [draft]);
  const skillByCode = useMemo(
    () => new Map(skills.map((skill) => [skill.skillCode, skill])),
    [skills],
  );
  const issueNodes = useMemo(
    () => new Set(issues?.map((issue) => issue.nodeCode)?.filter?.(Boolean)),
    [issues],
  );
  const issueEdges = useMemo(
    () => new Set(issues?.map((issue) => issue.edgeId)?.filter?.(Boolean)),
    [issues],
  );

  if (!draft)
    return (
      <main className="workflow-canvas-panel">
        <Empty description="请选择 Workflow" />
      </main>
    );

  const add = (kind: 'SKILL' | 'ROUTER' | 'PARALLEL') => {
    if (readonly) return;
    if (kind === 'SKILL') onChange(appendWorkflowSkill(draft));
    if (kind === 'ROUTER') onChange(appendWorkflowRouter(draft));
    if (kind === 'PARALLEL') onChange(appendParallelPair(draft));
  };

  return (
    <main className="workflow-canvas-panel">
      <div className="workflow-canvas-toolbar">
        <Text type="secondary">
          唯一零入边节点是隐式入口；Summary 是唯一终点，不显示 START/END。
        </Text>
        {!readonly ? (
          <Space wrap>
            <Button size="small" icon={<PlusOutlined />} onClick={() => add('SKILL')}>
              Skill
            </Button>
            <Button size="small" icon={<PlusOutlined />} onClick={() => add('ROUTER')}>
              Router
            </Button>
            <Button size="small" icon={<PlusOutlined />} onClick={() => add('PARALLEL')}>
              Fork + Join
            </Button>
          </Space>
        ) : null}
      </div>
      {issues.length ? (
        <div className="workflow-validation-panel workflow-validation-summary">
          <strong>当前配置问题（{issues.length}）</strong>
          <ul>
            {issues.map((issue, index) => (
              <li key={`${issue.path}-${issue.nodeCode || issue.edgeId || index}`}>
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="workflow-canvas-scroll">
        {layers.map((layer, layerIndex) => (
          <React.Fragment key={`layer-${layerIndex}`}>
            {layerIndex ? <div className="workflow-flow-connector" /> : null}
            <div className={`workflow-graph-layer${layer.length > 1 ? ' branching' : ''}`}>
              {layer.map((node) => {
                const outgoing = draft.edges?.filter?.(
                  (edge) => edge.sourceNodeCode === node.nodeCode,
                );
                const active = selectedNodeCode === node.nodeCode;
                const invalid = issueNodes.has(node.nodeCode);
                return (
                  <button
                    type="button"
                    className={`workflow-graph-node workflow-${node.nodeType?.toLowerCase?.()}-node${
                      active ? ' active' : ''
                    }${invalid ? ' invalid' : ''}`}
                    key={node.nodeCode}
                    onClick={() => onSelectNode(node.nodeCode)}
                  >
                    <span className="workflow-node-content">
                      <span className="workflow-node-title-row">
                        <strong>{node.displayName || node.nodeCode}</strong>
                        <Tag color={nodeColor[node.nodeType]}>{node.nodeType}</Tag>
                        {node.nodeType === 'SKILL' ? (
                          node.controlPolicy?.allowSkip ? (
                            <Tag>允许跳过</Tag>
                          ) : null
                        ) : null}
                      </span>
                      <span className="workflow-node-prompt">{nodeSummary(node, skillByCode)}</span>
                      {outgoing.length ? (
                        <span className="workflow-edge-list">
                          {outgoing.map((edge) => (
                            <code
                              className={issueEdges.has(edge.edgeId) ? 'invalid' : ''}
                              key={edge.edgeId}
                            >
                              {edgeLabel(edge)}
                            </code>
                          ))}
                        </span>
                      ) : null}
                    </span>
                  </button>
                );
              })}
            </div>
          </React.Fragment>
        ))}
      </div>
    </main>
  );
};

export default WorkflowCanvas;
