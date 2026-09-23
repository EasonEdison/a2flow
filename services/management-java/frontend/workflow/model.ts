import type {
  WorkflowDraft,
  WorkflowEdge,
  WorkflowHandlingSuggestion,
  WorkflowNode,
  WorkflowParallelEdge,
  WorkflowRoutingEdge,
  WorkflowRouterNode,
  WorkflowSkillNode,
  WorkflowSummaryNode,
} from './types';
import { jsonStringify } from '../shared/safeJson';

export const SUMMARY_NODE_CODE = '__summary__';
const DEFAULT_SUMMARY_PROMPT = '请基于所有已完成节点的结构化结果，输出结论和下一步建议。';
const DEFAULT_ROUTER_PROMPT = '请根据已完成节点的结构化结果，选择最合适的下一条执行路径。';
const ROUTER_SCHEMA_DIGEST_V1 = 'workflow-router-v1';
const JOIN_POLICY = 'ALL_SUCCESS_OR_SKIPPED' as const;
export const WORKFLOW_SNAPSHOT_CONTRACT_VERSION = 2;
export const WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH = 4096;
export const WORKFLOW_DETAIL_SUMMARY_PROMPT_MAX_LENGTH = 4096;
export const WORKFLOW_SUMMARY_ADVICE_MAX_COUNT = 10;
export const WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH = 4096;
export const WORKFLOW_SUMMARY_TITLE = '经营问题结论';
const UNSUPPORTED_WORKFLOW_SNAPSHOT_MESSAGE = 'Workflow草稿snapshotContractVersion仅支持v2';

const optionalText = (value?: string): string | undefined =>
  value === undefined ? undefined : value.trim();

const createNormalEdge = (sourceNodeCode: string, targetNodeCode: string): WorkflowEdge => ({
  edgeId: `${sourceNodeCode}__TO__${targetNodeCode}`,
  edgeType: 'NORMAL',
  sourceNodeCode,
  targetNodeCode,
});

const createSkillNode = (nodeCode: string, displayName: string): WorkflowSkillNode => ({
  nodeCode,
  nodeType: 'SKILL',
  displayName,
  skillCode: '',
  nodePrompt: '',
  controlPolicy: { allowSkip: false },
});

const createSummaryNode = (prompt: string): WorkflowSummaryNode => ({
  nodeCode: SUMMARY_NODE_CODE,
  nodeType: 'SUMMARY',
  displayName: WORKFLOW_SUMMARY_TITLE,
  prompt,
  allowSkip: false,
});

const normalizeHandlingSuggestion = (
  suggestion: WorkflowHandlingSuggestion,
): WorkflowHandlingSuggestion => {
  const normalized: WorkflowHandlingSuggestion = {
    suggestionId: suggestion.suggestionId?.trim?.(),
    displayText: suggestion.displayText?.trim?.(),
    sendMessageText: suggestion.sendMessageText?.trim?.(),
  };
  const iconUrl = optionalText(suggestion.iconUrl);
  if (iconUrl) normalized.iconUrl = iconUrl;
  return normalized;
};

const nextCode = (draft: WorkflowDraft, prefix: string): string => {
  const usedCodes = new Set(draft.nodes?.map?.((node) => node.nodeCode));
  let index = 1;
  let code = `${prefix}_${String(index).padStart(2, '0')}`;
  while (usedCodes.has(code)) {
    index += 1;
    code = `${prefix}_${String(index).padStart(2, '0')}`;
  }
  return code;
};

const redirectSummaryTargets = (
  draft: WorkflowDraft,
  replacementNodeCode: string,
): Pick<WorkflowDraft, 'nodes' | 'edges'> => ({
  nodes: draft.nodes?.map?.((node) =>
    node.nodeType === 'ROUTER'
      ? {
          ...node,
          candidates: node.candidates?.map?.((candidate) =>
            candidate.targetNodeCode === SUMMARY_NODE_CODE
              ? { ...candidate, targetNodeCode: replacementNodeCode }
              : candidate,
          ),
        }
      : node,
  ),
  edges: draft.edges?.map?.((edge) =>
    edge.targetNodeCode === SUMMARY_NODE_CODE
      ? { ...edge, targetNodeCode: replacementNodeCode }
      : edge,
  ),
});

const countNodesByType = (nodes: WorkflowNode[], nodeType: WorkflowNode['nodeType']): number => {
  let count = 0;
  nodes.forEach((node) => {
    if (node.nodeType === nodeType) count += 1;
  });
  return count;
};

const groupSummaryNodes = (
  nodes: WorkflowNode[],
): { contentNodes: WorkflowNode[]; summaryNodes: WorkflowNode[] } => {
  const contentNodes: WorkflowNode[] = [];
  const summaryNodes: WorkflowNode[] = [];
  nodes.forEach((node) => {
    if (node.nodeType === 'SUMMARY') summaryNodes.push(node);
    else contentNodes.push(node);
  });
  return { contentNodes, summaryNodes };
};

export const createWorkflowDraft = (workflowCode: string): WorkflowDraft => {
  const skill = createSkillNode('SKILL_01', 'Skill 节点 1');
  const summary = createSummaryNode(DEFAULT_SUMMARY_PROMPT);
  return {
    snapshotContractVersion: WORKFLOW_SNAPSHOT_CONTRACT_VERSION,
    workflowCode: workflowCode.trim(),
    metadata: {},
    nodes: [skill, summary],
    edges: [createNormalEdge(skill.nodeCode, summary.nodeCode)],
    summaryConfig: { prompt: summary.prompt, handlingSuggestions: [] },
  };
};

const normalizeNode = (node: WorkflowNode): WorkflowNode => {
  const base = {
    ...node,
    nodeCode: node.nodeCode?.trim?.(),
    displayName: optionalText(node.displayName),
  };
  switch (node.nodeType) {
    case 'SKILL':
      const normalizedSkill: WorkflowSkillNode = {
        ...base,
        nodeType: 'SKILL',
        skillCode: node.skillCode?.trim?.(),
        nodePrompt: node.nodePrompt?.trim?.(),
        controlPolicy: { allowSkip: Boolean(node.controlPolicy?.allowSkip) },
      };
      const quickTriggerMessage = optionalText(node.quickTriggerMessage);
      if (quickTriggerMessage) {
        normalizedSkill.quickTriggerMessage = quickTriggerMessage;
      } else {
        delete normalizedSkill.quickTriggerMessage;
      }
      return normalizedSkill;
    case 'ROUTER':
      return {
        ...base,
        nodeType: 'ROUTER',
        routerPrompt: node.routerPrompt?.trim?.(),
        routerContractVersion: 1,
        routerSchemaDigest: node.routerSchemaDigest?.trim?.(),
        candidates: node.candidates?.map?.((candidate) => ({
          routeKey: candidate.routeKey?.trim?.(),
          description: candidate.description?.trim?.(),
          targetNodeCode: candidate.targetNodeCode?.trim?.(),
        })),
      };
    case 'PARALLEL_FORK':
      return {
        ...base,
        nodeType: 'PARALLEL_FORK',
        matchingNodeCode: node.matchingNodeCode?.trim?.(),
        joinPolicy: node.joinPolicy,
        maxParallelism: node.maxParallelism,
      };
    case 'PARALLEL_JOIN':
      return {
        ...base,
        nodeType: 'PARALLEL_JOIN',
        matchingNodeCode: node.matchingNodeCode?.trim?.(),
        joinPolicy: node.joinPolicy,
      };
    case 'SUMMARY':
      return {
        ...base,
        nodeType: 'SUMMARY',
        displayName: WORKFLOW_SUMMARY_TITLE,
        prompt: node.prompt?.trim?.(),
        allowSkip: false,
      };
  }
};

const normalizeEdge = (edge: WorkflowEdge): WorkflowEdge => {
  const base = {
    ...edge,
    edgeId: edge.edgeId?.trim?.(),
    sourceNodeCode: edge.sourceNodeCode?.trim?.(),
    targetNodeCode: edge.targetNodeCode?.trim?.(),
  };
  if (edge.edgeType === 'ROUTING') {
    return {
      ...base,
      edgeType: 'ROUTING',
      routeKey: edge.routeKey?.trim?.(),
      description: edge.description?.trim?.(),
    };
  }
  if (edge.edgeType === 'PARALLEL') {
    return {
      ...base,
      edgeType: 'PARALLEL',
      branchKey: edge.branchKey?.trim?.(),
      branchOrder: edge.branchOrder,
    };
  }
  return { ...base, edgeType: 'NORMAL' };
};

export const normalizeWorkflowDraft = (draft: WorkflowDraft): WorkflowDraft => {
  if (Number(draft.snapshotContractVersion) !== WORKFLOW_SNAPSHOT_CONTRACT_VERSION) {
    throw new Error(UNSUPPORTED_WORKFLOW_SNAPSHOT_MESSAGE);
  }
  let nodes = draft.nodes?.map?.(normalizeNode);
  let summary = nodes.find((node): node is WorkflowSummaryNode => node.nodeType === 'SUMMARY');

  // Ensure SUMMARY node always exists
  if (!summary) {
    const prompt = draft.summaryConfig?.prompt?.trim() || DEFAULT_SUMMARY_PROMPT;
    summary = createSummaryNode(prompt);
    nodes = [...nodes, summary];
  }

  const prompt = (summary.prompt || draft.summaryConfig?.prompt || DEFAULT_SUMMARY_PROMPT).trim();
  if (!Array.isArray(draft.summaryConfig?.handlingSuggestions)) {
    throw new Error('Workflow草稿summaryConfig.handlingSuggestions必须是数组');
  }
  const detailSummaryPrompt = optionalText(draft.summaryConfig?.detailSummaryPrompt);
  const summaryConfig: WorkflowDraft['summaryConfig'] = {
    prompt,
    handlingSuggestions: draft.summaryConfig?.handlingSuggestions?.map?.(
      normalizeHandlingSuggestion,
    ),
  };
  if (detailSummaryPrompt) {
    summaryConfig.detailSummaryPrompt = detailSummaryPrompt;
  }
  return {
    snapshotContractVersion: WORKFLOW_SNAPSHOT_CONTRACT_VERSION,
    workflowCode: draft.workflowCode?.trim?.(),
    metadata: { ...draft.metadata },
    nodes,
    edges: draft.edges?.map?.(normalizeEdge),
    summaryConfig,
  };
};

export const appendWorkflowSkill = (draft: WorkflowDraft): WorkflowDraft => {
  const nodeCode = nextCode(draft, 'SKILL');
  const skillCount = countNodesByType(draft.nodes, 'SKILL');
  const redirected = redirectSummaryTargets(draft, nodeCode);
  const groups = groupSummaryNodes(redirected.nodes);
  const node = createSkillNode(nodeCode, `Skill 节点 ${skillCount + 1}`);
  return normalizeWorkflowDraft({
    ...draft,
    nodes: [...groups.contentNodes, node, ...groups.summaryNodes],
    edges: [...redirected.edges, createNormalEdge(nodeCode, SUMMARY_NODE_CODE)],
  });
};

export const appendWorkflowRouter = (draft: WorkflowDraft): WorkflowDraft => {
  const nodeCode = nextCode(draft, 'ROUTER');
  const routerCount = countNodesByType(draft.nodes, 'ROUTER');
  const redirected = redirectSummaryTargets(draft, nodeCode);
  const groups = groupSummaryNodes(redirected.nodes);
  const router: WorkflowRouterNode = {
    nodeCode,
    nodeType: 'ROUTER',
    displayName: `路由 ${routerCount + 1}`,
    routerPrompt: DEFAULT_ROUTER_PROMPT,
    routerContractVersion: 1,
    routerSchemaDigest: ROUTER_SCHEMA_DIGEST_V1,
    candidates: [
      {
        routeKey: 'route_a',
        description: '主要路径',
        targetNodeCode: SUMMARY_NODE_CODE,
      },
      {
        routeKey: 'route_b',
        description: '备选路径',
        targetNodeCode: SUMMARY_NODE_CODE,
      },
    ],
  };
  const routingEdges: WorkflowRoutingEdge[] = router.candidates.map((candidate, index) => ({
    edgeId: `${nodeCode}__ROUTE__${String(index + 1).padStart(2, '0')}`,
    edgeType: 'ROUTING',
    sourceNodeCode: nodeCode,
    targetNodeCode: candidate.targetNodeCode,
    routeKey: candidate.routeKey,
    description: candidate.description,
  }));
  return normalizeWorkflowDraft({
    ...draft,
    nodes: [...groups.contentNodes, router, ...groups.summaryNodes],
    edges: [...redirected.edges, ...routingEdges],
  });
};

export const appendParallelPair = (draft: WorkflowDraft): WorkflowDraft => {
  const forkCode = nextCode(draft, 'FORK');
  const joinCode = nextCode(draft, 'JOIN');
  const firstBranch = createSkillNode(nextCode(draft, 'BRANCH_A'), '并行分支 A');
  const draftWithFirst = { ...draft, nodes: [...draft.nodes, firstBranch] };
  const secondBranch = createSkillNode(nextCode(draftWithFirst, 'BRANCH_B'), '并行分支 B');
  const fork: WorkflowNode = {
    nodeCode: forkCode,
    nodeType: 'PARALLEL_FORK',
    displayName: '并行分叉',
    matchingNodeCode: joinCode,
    joinPolicy: JOIN_POLICY,
    maxParallelism: 10,
  };
  const join: WorkflowNode = {
    nodeCode: joinCode,
    nodeType: 'PARALLEL_JOIN',
    displayName: '并行汇合',
    matchingNodeCode: forkCode,
    joinPolicy: JOIN_POLICY,
  };
  const branchEdges: WorkflowParallelEdge[] = [firstBranch, secondBranch].map((node, index) => ({
    edgeId: `${forkCode}__BRANCH__${index + 1}`,
    edgeType: 'PARALLEL',
    sourceNodeCode: forkCode,
    targetNodeCode: node.nodeCode,
    branchKey: `branch_${String.fromCharCode(97 + index)}`,
    branchOrder: index + 1,
  }));
  const redirected = redirectSummaryTargets(draft, forkCode);
  const nodes = redirected.nodes?.filter?.((item) => item.nodeType !== 'SUMMARY');
  const summary = redirected.nodes?.filter?.((item) => item.nodeType === 'SUMMARY');
  return normalizeWorkflowDraft({
    ...draft,
    nodes: [...nodes, fork, firstBranch, secondBranch, join, ...summary],
    edges: [
      ...redirected.edges,
      ...branchEdges,
      createNormalEdge(firstBranch.nodeCode, joinCode),
      createNormalEdge(secondBranch.nodeCode, joinCode),
      createNormalEdge(joinCode, SUMMARY_NODE_CODE),
    ],
  });
};

export const updateWorkflowNode = (
  draft: WorkflowDraft,
  nodeCode: string,
  updater: (node: WorkflowNode) => WorkflowNode,
): WorkflowDraft => {
  const nodes = draft.nodes?.map?.((node) => (node.nodeCode === nodeCode ? updater(node) : node));
  return normalizeWorkflowDraft({ ...draft, nodes });
};

export const updateWorkflowSkillSelection = (
  draft: WorkflowDraft,
  nodeCode: string,
  skillCode: string,
): WorkflowDraft =>
  updateWorkflowNode(draft, nodeCode, (node) =>
    node.nodeType === 'SKILL'
      ? {
          ...node,
          skillCode,
          quickTriggerMessage: undefined,
        }
      : node,
  );

export const updateWorkflowEdge = (
  draft: WorkflowDraft,
  edgeId: string,
  updater: (edge: WorkflowEdge) => WorkflowEdge,
): WorkflowDraft =>
  normalizeWorkflowDraft({
    ...draft,
    edges: draft.edges?.map?.((edge) => (edge.edgeId === edgeId ? updater(edge) : edge)),
  });

export type WorkflowSkillMoveDirection = 'UP' | 'DOWN';

export type WorkflowSkillNodeMutationResult =
  | { ok: true; draft: WorkflowDraft }
  | { ok: false; reason: string };

export interface WorkflowSkillNodeActionState {
  moveUp: { enabled: boolean; reason?: string };
  moveDown: { enabled: boolean; reason?: string };
  delete: { enabled: boolean; reason?: string };
}

const mutationFailure = (reason: string): WorkflowSkillNodeMutationResult => ({
  ok: false,
  reason,
});

const workflowMutationTopologyError = (draft: WorkflowDraft): string | undefined => {
  const nodeByCode = new Map<string, WorkflowNode>();
  for (const node of draft.nodes) {
    if (!node.nodeCode || nodeByCode.has(node.nodeCode)) return '节点标识为空或重复';
    nodeByCode.set(node.nodeCode, node);
  }
  const skillCount = draft?.nodes?.filter?.((node) => node.nodeType === 'SKILL')?.length;
  if (!skillCount) return 'Workflow 至少保留一个 Skill 节点';
  const summaries = draft.nodes?.filter?.((node) => node.nodeType === 'SUMMARY');
  if (summaries.length !== 1 || summaries?.[0]?.nodeCode !== SUMMARY_NODE_CODE) {
    return 'Workflow 必须且只能包含一个 Summary 终点';
  }

  const edgeIds = new Set<string>();
  const incoming = new Map<string, WorkflowEdge[]>();
  const outgoing = new Map<string, WorkflowEdge[]>();
  for (const node of draft.nodes) {
    incoming.set(node.nodeCode, []);
    outgoing.set(node.nodeCode, []);
  }
  for (const edge of draft.edges) {
    if (!edge.edgeId || edgeIds.has(edge.edgeId)) return 'Edge 标识为空或重复';
    edgeIds.add(edge.edgeId);
    if (!nodeByCode.has(edge.sourceNodeCode) || !nodeByCode.has(edge.targetNodeCode)) {
      return `Edge ${edge.edgeId} 存在悬空节点引用`;
    }
    outgoing?.get(edge.sourceNodeCode)?.push?.(edge);
    incoming?.get(edge.targetNodeCode)?.push?.(edge);
  }

  for (const node of draft.nodes) {
    const nodeOutgoing = outgoing.get(node.nodeCode) || [];
    if (node.nodeType === 'SUMMARY') {
      if (nodeOutgoing.length) return 'Summary 必须是零出边终点';
      continue;
    }
    if (node.nodeType === 'SKILL' || node.nodeType === 'PARALLEL_JOIN') {
      if (nodeOutgoing.length !== 1 || nodeOutgoing?.[0]?.edgeType !== 'NORMAL') {
        return `${node.nodeCode} 必须只有一个 NORMAL 后继`;
      }
      continue;
    }
    if (node.nodeType === 'ROUTER') {
      const routingEdges = nodeOutgoing.filter((edge) => edge.edgeType === 'ROUTING');
      const routeKeys = node.candidates?.map?.((candidate) => candidate.routeKey);
      if (
        routingEdges.length < 2 ||
        routingEdges.length !== node.candidates?.length ||
        new Set(routeKeys).size !== routeKeys.length
      ) {
        return `Router ${node.nodeCode} 的候选与 Routing Edge 不一致`;
      }
      for (const candidate of node.candidates) {
        const matches = routingEdges.filter(
          (edge) =>
            edge.edgeType === 'ROUTING' &&
            edge.routeKey === candidate.routeKey &&
            edge.targetNodeCode === candidate.targetNodeCode &&
            edge.description === candidate.description,
        );
        if (matches.length !== 1 || !nodeByCode.has(candidate.targetNodeCode)) {
          return `Router ${node.nodeCode} 存在悬空或不唯一候选引用`;
        }
      }
      continue;
    }
    const join = nodeByCode.get(node.matchingNodeCode);
    const parallelEdges = nodeOutgoing.filter((edge) => edge.edgeType === 'PARALLEL');
    const branchKeys = parallelEdges.map((edge) => edge.branchKey);
    const branchOrders = parallelEdges.map((edge) => edge.branchOrder);
    if (
      join?.nodeType !== 'PARALLEL_JOIN' ||
      join.matchingNodeCode !== node.nodeCode ||
      parallelEdges.length < 2 ||
      parallelEdges.length !== nodeOutgoing.length ||
      new Set(branchKeys).size !== branchKeys.length ||
      new Set(branchOrders).size !== branchOrders.length
    ) {
      return `Fork ${node.nodeCode} 与 Join 或并行分支不一致`;
    }
    if (parallelEdges.some((edge) => edge.targetNodeCode === node.matchingNodeCode)) {
      return `Fork ${node.nodeCode} 不能直接连接 matching Join`;
    }
  }

  for (const node of draft.nodes) {
    if (node.nodeType !== 'PARALLEL_JOIN') continue;
    const fork = nodeByCode.get(node.matchingNodeCode);
    if (fork?.nodeType !== 'PARALLEL_FORK' || fork.matchingNodeCode !== node.nodeCode) {
      return `Join ${node.nodeCode} 与 Fork 引用不一致`;
    }
  }

  const entries = draft.nodes?.filter?.((node) => !(incoming.get(node.nodeCode) || []).length);
  if (entries.length !== 1) return 'Workflow 必须且只能有一个入口节点';

  const reachable = new Set<string>();
  const pending = [entries?.[0]?.nodeCode || ''];
  while (pending.length) {
    const nodeCode = pending.pop();
    if (!nodeCode || reachable.has(nodeCode)) continue;
    reachable.add(nodeCode);
    (outgoing.get(nodeCode) || []).forEach((edge) => pending.push(edge.targetNodeCode));
  }
  if (reachable.size !== draft.nodes?.length) return 'Workflow 存在不可达节点';

  const indegree = new Map(
    draft.nodes?.map?.((node) => [node.nodeCode, (incoming.get(node.nodeCode) || []).length]),
  );
  const acyclicPending = entries.map((node) => node.nodeCode);
  let visitedCount = 0;
  while (acyclicPending.length) {
    const nodeCode = acyclicPending.shift();
    if (!nodeCode) continue;
    visitedCount += 1;
    (outgoing.get(nodeCode) || []).forEach((edge) => {
      const nextIndegree = (indegree.get(edge.targetNodeCode) || 0) - 1;
      indegree.set(edge.targetNodeCode, nextIndegree);
      if (nextIndegree === 0) acyclicPending.push(edge.targetNodeCode);
    });
  }
  if (visitedCount !== draft.nodes?.length) return 'Workflow 存在环路';

  const reachesSummary = new Set<string>([SUMMARY_NODE_CODE]);
  const reversePending = [SUMMARY_NODE_CODE];
  while (reversePending.length) {
    const nodeCode = reversePending.pop();
    if (!nodeCode) continue;
    (incoming.get(nodeCode) || []).forEach((edge) => {
      if (reachesSummary.has(edge.sourceNodeCode)) return;
      reachesSummary.add(edge.sourceNodeCode);
      reversePending.push(edge.sourceNodeCode);
    });
  }
  if (reachesSummary.size !== draft.nodes?.length) return '并非所有路径都能到达 Summary';
  return undefined;
};

const swapAdjacentSkillNodes = (
  draft: WorkflowDraft,
  earlierNodeCode: string,
  laterNodeCode: string,
  connectingEdge: WorkflowEdge,
): WorkflowSkillNodeMutationResult => {
  const incomingEarlier = draft.edges?.filter?.(
    (edge) => edge.targetNodeCode === earlierNodeCode && edge.edgeId !== connectingEdge.edgeId,
  );
  const outgoingEarlier = draft.edges?.filter?.(
    (edge) => edge.sourceNodeCode === earlierNodeCode && edge.edgeId !== connectingEdge.edgeId,
  );
  const incomingLater = draft.edges?.filter?.(
    (edge) => edge.targetNodeCode === laterNodeCode && edge.edgeId !== connectingEdge.edgeId,
  );
  const outgoingLater = draft.edges?.filter?.(
    (edge) => edge.sourceNodeCode === laterNodeCode && edge.edgeId !== connectingEdge.edgeId,
  );
  if (incomingEarlier.length > 1 || outgoingEarlier.length || incomingLater.length) {
    return mutationFailure('节点前驱或后继不唯一，不能调整顺序');
  }
  const boundaryEdge = incomingEarlier?.[0];
  if (boundaryEdge) {
    const boundaryNode = draft.nodes?.find?.(
      (node) => node.nodeCode === boundaryEdge.sourceNodeCode,
    );
    if (boundaryEdge.edgeType !== 'NORMAL' || boundaryNode?.nodeType !== 'SKILL') {
      return mutationFailure('Router、Fork 或 Join 边界内不能调整 Skill 顺序');
    }
  }
  if (outgoingLater.length !== 1 || outgoingLater?.[0]?.edgeType !== 'NORMAL') {
    return mutationFailure('节点后继不唯一或不是 NORMAL Edge，不能调整顺序');
  }

  const outgoingEdge = outgoingLater?.[0];
  const edges = draft.edges?.map?.((edge): WorkflowEdge => {
    if (boundaryEdge && edge.edgeId === boundaryEdge.edgeId) {
      return { ...edge, targetNodeCode: laterNodeCode };
    }
    if (edge.edgeId === connectingEdge.edgeId) {
      return {
        ...edge,
        sourceNodeCode: laterNodeCode,
        targetNodeCode: earlierNodeCode,
      };
    }
    if (edge.edgeId === outgoingEdge.edgeId) {
      return { ...edge, sourceNodeCode: earlierNodeCode };
    }
    return edge;
  });
  const candidate = normalizeWorkflowDraft({ ...draft, edges });
  const error = workflowMutationTopologyError(candidate);
  return error ? mutationFailure(error) : { ok: true, draft: candidate };
};

export const moveWorkflowSkillNode = (
  source: WorkflowDraft,
  nodeCode: string,
  direction: WorkflowSkillMoveDirection,
): WorkflowSkillNodeMutationResult => {
  const sourceError = workflowMutationTopologyError(source);
  if (sourceError) return mutationFailure(`当前拓扑不可安全调整：${sourceError}`);
  const draft = normalizeWorkflowDraft(source);
  const node = draft.nodes?.find?.((item) => item.nodeCode === nodeCode);
  if (node?.nodeType !== 'SKILL') return mutationFailure('只有 Skill 节点可以调整顺序');

  const connectingEdges = draft.edges?.filter?.((edge) =>
    direction === 'UP' ? edge.targetNodeCode === nodeCode : edge.sourceNodeCode === nodeCode,
  );
  if (connectingEdges.length !== 1) {
    return mutationFailure(
      connectingEdges.length
        ? '节点前驱或后继不唯一，不能调整顺序'
        : direction === 'UP'
        ? '当前 Skill 已是入口节点'
        : '当前 Skill 已在该线性片段末端',
    );
  }
  const connectingEdge = connectingEdges?.[0];
  const adjacentNodeCode =
    direction === 'UP' ? connectingEdge.sourceNodeCode : connectingEdge.targetNodeCode;
  const adjacentNode = draft.nodes?.find?.((item) => item.nodeCode === adjacentNodeCode);
  if (connectingEdge.edgeType !== 'NORMAL' || adjacentNode?.nodeType !== 'SKILL') {
    return mutationFailure('不能跨越 Router、Fork、Join 或 Summary 边界调整顺序');
  }
  return direction === 'UP'
    ? swapAdjacentSkillNodes(draft, adjacentNodeCode, nodeCode, connectingEdge)
    : swapAdjacentSkillNodes(draft, nodeCode, adjacentNodeCode, connectingEdge);
};

export const deleteWorkflowSkillNode = (
  source: WorkflowDraft,
  nodeCode: string,
): WorkflowSkillNodeMutationResult => {
  const sourceError = workflowMutationTopologyError(source);
  if (sourceError) return mutationFailure(`当前拓扑不可安全删除：${sourceError}`);
  const draft = normalizeWorkflowDraft(source);
  const node = draft.nodes?.find?.((item) => item.nodeCode === nodeCode);
  if (node?.nodeType !== 'SKILL') return mutationFailure('只有 Skill 节点可以删除');
  if (draft?.nodes?.filter?.((item) => item.nodeType === 'SKILL')?.length <= 1) {
    return mutationFailure('Workflow 至少保留一个 Skill 节点');
  }

  const incoming = draft.edges?.filter?.((edge) => edge.targetNodeCode === nodeCode);
  const outgoing = draft.edges?.filter?.((edge) => edge.sourceNodeCode === nodeCode);
  if (incoming.length > 1 || outgoing.length !== 1) {
    return mutationFailure('节点前驱或后继不唯一，不能安全删除');
  }
  const successorEdge = outgoing?.[0];
  if (successorEdge.edgeType !== 'NORMAL') {
    return mutationFailure('删除 Skill 只支持唯一 NORMAL 后继');
  }
  const predecessorEdge = incoming?.[0];
  if (predecessorEdge?.edgeType === 'PARALLEL') {
    const fork = draft.nodes?.find?.(
      (item) =>
        item.nodeCode === predecessorEdge.sourceNodeCode && item.nodeType === 'PARALLEL_FORK',
    );
    if (
      fork?.nodeType !== 'PARALLEL_FORK' ||
      successorEdge.targetNodeCode === fork.matchingNodeCode
    ) {
      return mutationFailure('删除后会形成 Fork 直连 Join，不能安全删除并行分支入口');
    }
  }

  let routerReferenceMatched = !predecessorEdge || predecessorEdge.edgeType !== 'ROUTING';
  const nodes = draft?.nodes
    ?.filter?.((item) => item.nodeCode !== nodeCode)
    ?.map?.((item): WorkflowNode => {
      if (
        item.nodeType !== 'ROUTER' ||
        predecessorEdge?.edgeType !== 'ROUTING' ||
        item.nodeCode !== predecessorEdge.sourceNodeCode
      ) {
        return item;
      }
      const matches = item.candidates?.filter?.(
        (candidate) =>
          candidate.routeKey === predecessorEdge.routeKey && candidate.targetNodeCode === nodeCode,
      );
      if (matches.length !== 1) return item;
      routerReferenceMatched = true;
      return {
        ...item,
        candidates: item.candidates?.map?.((candidate) =>
          candidate.routeKey === predecessorEdge.routeKey && candidate.targetNodeCode === nodeCode
            ? { ...candidate, targetNodeCode: successorEdge.targetNodeCode }
            : candidate,
        ),
      };
    });
  if (!routerReferenceMatched) {
    return mutationFailure('Router candidate 引用不唯一，不能安全删除');
  }

  const edges = draft?.edges
    ?.filter?.((edge) => edge.edgeId !== successorEdge.edgeId)
    ?.map?.(
      (edge): WorkflowEdge =>
        predecessorEdge && edge.edgeId === predecessorEdge.edgeId
          ? { ...edge, targetNodeCode: successorEdge.targetNodeCode }
          : edge,
    );
  const candidate = normalizeWorkflowDraft({ ...draft, nodes, edges });
  const error = workflowMutationTopologyError(candidate);
  return error ? mutationFailure(error) : { ok: true, draft: candidate };
};

const actionAvailability = (
  result: WorkflowSkillNodeMutationResult,
): { enabled: boolean; reason?: string } =>
  result.ok ? { enabled: true } : { enabled: false, reason: result.reason };

export const getWorkflowSkillNodeActionState = (
  draft: WorkflowDraft,
  nodeCode: string,
): WorkflowSkillNodeActionState => ({
  moveUp: actionAvailability(moveWorkflowSkillNode(draft, nodeCode, 'UP')),
  moveDown: actionAvailability(moveWorkflowSkillNode(draft, nodeCode, 'DOWN')),
  delete: actionAvailability(deleteWorkflowSkillNode(draft, nodeCode)),
});

export const serializeWorkflowDraft = (draft: WorkflowDraft): string => {
  const serialized = jsonStringify(normalizeWorkflowDraft(draft));
  if (!serialized) throw new Error('Workflow 草稿序列化失败');
  return serialized;
};

export const buildWorkflowGraphLayers = (draft: WorkflowDraft): WorkflowNode[][] => {
  const nodes = new Map(draft.nodes?.map?.((node) => [node.nodeCode, node]));
  const indegree = new Map(draft.nodes?.map?.((node) => [node.nodeCode, 0]));
  draft.edges?.forEach?.((edge) => {
    if (nodes.has(edge.sourceNodeCode) && nodes.has(edge.targetNodeCode)) {
      indegree.set(edge.targetNodeCode, (indegree.get(edge.targetNodeCode) || 0) + 1);
    }
  });
  let current = draft.nodes?.filter?.((node) => (indegree.get(node.nodeCode) || 0) === 0);
  const layers: WorkflowNode[][] = [];
  const visited = new Set<string>();
  while (current.length) {
    layers.push(current);
    current.forEach((node) => visited.add(node.nodeCode));
    const next = new Set<string>();
    current.forEach((node) =>
      draft?.edges
        ?.filter?.((edge) => edge.sourceNodeCode === node.nodeCode)
        ?.forEach?.((edge) => {
          const remaining = (indegree.get(edge.targetNodeCode) || 0) - 1;
          indegree.set(edge.targetNodeCode, remaining);
          if (remaining === 0) next.add(edge.targetNodeCode);
        }),
    );
    current = [...next]
      ?.map((nodeCode) => nodes.get(nodeCode))
      ?.filter?.((node): node is WorkflowNode => {
        if (!node) return false;
        return !visited.has(node.nodeCode);
      });
  }
  const unresolved = draft.nodes?.filter?.((node) => !visited.has(node.nodeCode));
  return unresolved.length ? [...layers, unresolved] : layers;
};
