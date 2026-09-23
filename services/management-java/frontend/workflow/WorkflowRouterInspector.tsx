import React from 'react';
import { Button, Input, Select, Space, Tag, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { normalizeWorkflowDraft } from './model';
import type {
  WorkflowDraft,
  WorkflowRouterCandidate,
  WorkflowRouterNode,
  WorkflowRoutingEdge,
} from './types';

const { Text } = Typography;
const { TextArea } = Input;

interface RouterInspectorProps {
  draft: WorkflowDraft;
  node: WorkflowRouterNode;
  readonly: boolean;
  targetOptions: Array<{ value: string; label: string }>;
  onChange: (draft: WorkflowDraft) => void;
}

interface CandidateCardProps {
  candidate: WorkflowRouterCandidate;
  edgeId?: string;
  index: number;
  count: number;
  readonly: boolean;
  targetOptions: Array<{ value: string; label: string }>;
  onUpdate: (index: number, patch: Partial<WorkflowRouterCandidate>) => void;
  onRemove: (index: number) => void;
}

const matchCandidateEdges = (
  candidates: WorkflowRouterCandidate[],
  routeEdges: WorkflowRoutingEdge[],
): Array<WorkflowRoutingEdge | undefined> => {
  const unused = new Set(routeEdges.map((edge) => edge.edgeId));
  return candidates.map((candidate, index) => {
    const exact = routeEdges.find(
      (edge) =>
        unused.has(edge.edgeId) &&
        edge.routeKey === candidate.routeKey &&
        edge.description === candidate.description &&
        edge.targetNodeCode === candidate.targetNodeCode,
    );
    const routeKeyMatch = routeEdges.find(
      (edge) => unused.has(edge.edgeId) && edge.routeKey === candidate.routeKey,
    );
    const indexed = routeEdges[index];
    const matched =
      exact ||
      routeKeyMatch ||
      (indexed && unused.has(indexed.edgeId) ? indexed : undefined) ||
      routeEdges.find((edge) => unused.has(edge.edgeId));
    if (matched) unused.delete(matched.edgeId);
    return matched;
  });
};

const nextRouteIdentity = (
  draft: WorkflowDraft,
  node: WorkflowRouterNode,
): { edgeId: string; routeKey: string } => {
  const edgeIds = new Set(draft.edges?.map?.((edge) => edge.edgeId));
  const routeKeys = new Set(node.candidates?.map?.((candidate) => candidate.routeKey));
  let index = 1;
  while (
    edgeIds.has(`${node.nodeCode}__ROUTE__${String(index).padStart(2, '0')}`) ||
    routeKeys.has(`route_${index}`)
  ) {
    index += 1;
  }
  return {
    edgeId: `${node.nodeCode}__ROUTE__${String(index).padStart(2, '0')}`,
    routeKey: `route_${index}`,
  };
};

const CandidateCard: React.FC<CandidateCardProps> = ({
  candidate,
  edgeId,
  index,
  count,
  readonly,
  targetOptions,
  onUpdate,
  onRemove,
}) => (
  <div className="workflow-router-candidate-card">
    <Space>
      <Tag>路径 {index + 1}</Tag>
      {!readonly ? (
        <Button
          type="text"
          icon={<DeleteOutlined />}
          disabled={count <= 2}
          onClick={() => onRemove(index)}
        />
      ) : null}
      <Text type="secondary">{edgeId}</Text>
    </Space>
    <Input
      disabled={readonly}
      value={candidate.routeKey}
      placeholder="routeKey"
      onChange={(event) => onUpdate(index, { routeKey: event.target.value })}
    />
    <TextArea
      disabled={readonly}
      rows={2}
      value={candidate.description}
      placeholder="业务说明"
      onChange={(event) => onUpdate(index, { description: event.target.value })}
    />
    <Select
      disabled={readonly}
      value={candidate.targetNodeCode || undefined}
      placeholder="目标节点"
      options={targetOptions}
      onChange={(value) => onUpdate(index, { targetNodeCode: value })}
    />
  </div>
);

const RouterNodeInspector: React.FC<RouterInspectorProps> = ({
  draft,
  node,
  readonly,
  targetOptions,
  onChange,
}) => {
  const routeEdges = draft.edges?.filter?.(
    (edge): edge is WorkflowRoutingEdge =>
      edge.edgeType === 'ROUTING' && edge.sourceNodeCode === node.nodeCode,
  );
  const candidateEdges = matchCandidateEdges(node.candidates, routeEdges);
  const updateNode = (patch: Partial<WorkflowRouterNode>) => {
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
  const updateRoute = (index: number, patch: Partial<WorkflowRouterCandidate>) => {
    if (readonly) return;
    const candidates = node.candidates?.map?.((candidate, candidateIndex) =>
      candidateIndex === index ? { ...candidate, ...patch } : candidate,
    );
    const edgeId = candidateEdges[index]?.edgeId;
    onChange(
      normalizeWorkflowDraft({
        ...draft,
        nodes: draft.nodes?.map?.((item) =>
          item.nodeCode === node.nodeCode ? { ...node, candidates } : item,
        ),
        edges: draft.edges?.map?.((edge) =>
          edge.edgeId === edgeId && edge.edgeType === 'ROUTING'
            ? { ...edge, ...candidates[index] }
            : edge,
        ),
      }),
    );
  };
  const addRoute = () => {
    if (readonly) return;
    const identity = nextRouteIdentity(draft, node);
    const candidate = {
      routeKey: identity.routeKey,
      description: '',
      targetNodeCode: '',
    };
    const edge: WorkflowRoutingEdge = {
      edgeId: identity.edgeId,
      edgeType: 'ROUTING',
      sourceNodeCode: node.nodeCode,
      targetNodeCode: '',
      routeKey: candidate.routeKey,
      description: '',
    };
    onChange(
      normalizeWorkflowDraft({
        ...draft,
        nodes: draft.nodes?.map?.((item) =>
          item.nodeCode === node.nodeCode
            ? { ...node, candidates: [...node.candidates, candidate] }
            : item,
        ),
        edges: [...draft.edges, edge],
      }),
    );
  };
  const removeRoute = (index: number) => {
    if (readonly || node.candidates?.length <= 2) return;
    const edgeId = candidateEdges[index]?.edgeId;
    onChange(
      normalizeWorkflowDraft({
        ...draft,
        nodes: draft.nodes?.map?.((item) =>
          item.nodeCode === node.nodeCode
            ? {
                ...node,
                candidates: node.candidates?.filter?.(
                  (_, candidateIndex) => candidateIndex !== index,
                ),
              }
            : item,
        ),
        edges: draft.edges?.filter?.((edge) => edge.edgeId !== edgeId),
      }),
    );
  };
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
        <span>Router Prompt</span>
        <TextArea
          disabled={readonly}
          rows={6}
          value={node.routerPrompt}
          placeholder="描述本次路由业务目标，不含平台 ID"
          onChange={(event) => updateNode({ routerPrompt: event.target.value })}
        />
      </label>
      <Text type="secondary">routerContractVersion（只读）：{node.routerContractVersion}</Text>
      <div className="workflow-router-candidate-heading">
        <Text strong>候选路由</Text>
        {!readonly ? (
          <Button size="small" icon={<PlusOutlined />} onClick={addRoute}>
            添加候选
          </Button>
        ) : null}
      </div>
      {node.candidates?.map?.((candidate, index) => (
        <CandidateCard
          key={candidateEdges[index]?.edgeId || `${node.nodeCode}-${index}`}
          candidate={candidate}
          edgeId={candidateEdges[index]?.edgeId}
          index={index}
          count={node.candidates?.length}
          readonly={readonly}
          targetOptions={targetOptions}
          onUpdate={updateRoute}
          onRemove={removeRoute}
        />
      ))}
    </>
  );
};

export default RouterNodeInspector;
