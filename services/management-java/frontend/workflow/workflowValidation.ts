import {
  normalizeWorkflowDraft,
  WORKFLOW_DETAIL_SUMMARY_PROMPT_MAX_LENGTH,
  WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH,
  WORKFLOW_SUMMARY_ADVICE_MAX_COUNT,
  WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH,
} from './model';
import type {
  WorkflowDraft,
  WorkflowParallelEdge,
  WorkflowRoutingEdge,
  WorkflowValidationIssue,
} from './types';

interface ScopedValue {
  key: string;
  value: string;
  path: string;
  label: string;
  nodeCode?: string;
}

export const WORKFLOW_BRANCH_KEY_MAX_LENGTH = 62;

const duplicateIssues = (values: ScopedValue[]): WorkflowValidationIssue[] => {
  const counts = new Map<string, number>();
  values.forEach(({ key }) => counts.set(key, (counts.get(key) || 0) + 1));
  return values
    ?.filter(({ key }) => Boolean(key) && Number(counts.get(key) || 0) > 1)
    ?.map?.(({ path, label, value, nodeCode }) => ({
      path,
      nodeCode,
      message: `${label} ${value} 重复`,
    }));
};

const nestedForkIssues = (draft: WorkflowDraft): WorkflowValidationIssue[] => {
  const nodeByCode = new Map(draft.nodes?.map?.((node) => [node.nodeCode, node]));
  const outgoing = new Map<string, string[]>();
  draft.edges?.forEach?.((edge) => {
    const targets = outgoing.get(edge.sourceNodeCode) || [];
    targets.push(edge.targetNodeCode);
    outgoing.set(edge.sourceNodeCode, targets);
  });
  const issues: WorkflowValidationIssue[] = [];
  const reported = new Set<string>();
  draft?.nodes
    ?.filter?.((node) => node.nodeType === 'PARALLEL_FORK')
    ?.forEach?.((fork) => {
      const branchEdges = draft.edges?.filter?.(
        (edge): edge is WorkflowParallelEdge =>
          edge.edgeType === 'PARALLEL' && edge.sourceNodeCode === fork.nodeCode,
      );
      branchEdges.forEach((branchEdge) => {
        const directTarget = nodeByCode.get(branchEdge.targetNodeCode);
        if (directTarget?.nodeType === 'PARALLEL_JOIN') {
          issues.push({
            path: `edges.${branchEdge.edgeId}.targetNodeCode`,
            edgeId: branchEdge.edgeId,
            nodeCode: directTarget.nodeCode,
            message: '并行分支入口不能直接选择 Join',
          });
        }
        const pending = [branchEdge.targetNodeCode];
        const visited = new Set<string>();
        while (pending.length) {
          const nodeCode = pending.pop();
          if (!nodeCode || visited.has(nodeCode)) continue;
          visited.add(nodeCode);
          if (nodeCode === fork.matchingNodeCode) continue;
          const current = nodeByCode.get(nodeCode);
          if (current?.nodeType === 'PARALLEL_FORK') {
            const findingKey = `${fork.nodeCode}:${current.nodeCode}`;
            if (!reported.has(findingKey)) {
              reported.add(findingKey);
              issues.push({
                path: `nodes.${current.nodeCode}.nodeType`,
                nodeCode: current.nodeCode,
                message: `嵌套 Fork 不支持（位于 ${fork.nodeCode} 分支）`,
              });
            }
          }
          (outgoing.get(nodeCode) || []).forEach((target) => pending.push(target));
        }
      });
    });
  return issues;
};

const promptIssues = (draft: WorkflowDraft): WorkflowValidationIssue[] =>
  draft.nodes?.flatMap?.((node) => {
    if (node.nodeType === 'SKILL') {
      if (node.nodePrompt?.trim?.()) return [];
      return [
        {
          path: `nodes.${node.nodeCode}.nodePrompt`,
          nodeCode: node.nodeCode,
          message: '请填写节点任务 Prompt',
        },
      ];
    }
    if (node.nodeType === 'ROUTER') {
      if (node.routerPrompt?.trim?.()) return [];
      return [
        {
          path: `nodes.${node.nodeCode}.routerPrompt`,
          nodeCode: node.nodeCode,
          message: '请填写 Router Prompt',
        },
      ];
    }
    if (node.nodeType === 'SUMMARY') {
      if (node.prompt?.trim?.()) return [];
      return [
        {
          path: `nodes.${node.nodeCode}.prompt`,
          nodeCode: node.nodeCode,
          message: '请填写 Summary Prompt',
        },
      ];
    }
    return [];
  });

const scopedRouteValues = (draft: WorkflowDraft): ScopedValue[] =>
  draft?.edges
    ?.filter?.((edge): edge is WorkflowRoutingEdge => edge.edgeType === 'ROUTING')
    ?.map?.((edge) => ({
      key: `${edge.sourceNodeCode}:${edge.routeKey}`,
      value: edge.routeKey,
      path: `edges.${edge.edgeId}.routeKey`,
      label: 'routeKey',
      nodeCode: edge.sourceNodeCode,
    }));

const scopedBranchValues = (draft: WorkflowDraft): ScopedValue[] =>
  draft?.edges
    ?.filter?.((edge): edge is WorkflowParallelEdge => edge.edgeType === 'PARALLEL')
    ?.map?.((edge) => ({
      key: `${edge.sourceNodeCode}:${edge.branchKey}`,
      value: edge.branchKey,
      path: `edges.${edge.edgeId}.branchKey`,
      label: 'branchKey',
      nodeCode: edge.sourceNodeCode,
    }));

export const validateWorkflowDraft = (source: WorkflowDraft): WorkflowValidationIssue[] => {
  const draft = normalizeWorkflowDraft(source);
  const issues = [
    ...promptIssues(draft),
    ...duplicateIssues(scopedRouteValues(draft)),
    ...duplicateIssues(scopedBranchValues(draft)),
    ...nestedForkIssues(draft),
  ];
  draft.nodes?.forEach?.((node) => {
    if (node.nodeType === 'SKILL' && !node.skillCode) {
      issues.push({
        path: `nodes.${node.nodeCode}.skillCode`,
        nodeCode: node.nodeCode,
        message: '请选择 Skill',
      });
    }
    if (
      node.nodeType === 'SKILL' &&
      node.quickTriggerMessage &&
      node.quickTriggerMessage.length > WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH
    ) {
      issues.push({
        path: `nodes.${node.nodeCode}.quickTriggerMessage`,
        nodeCode: node.nodeCode,
        message: `一键触发消息不能超过 ${WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH} 个字符`,
      });
    }
  });
  const suggestions = draft.summaryConfig?.handlingSuggestions;
  if (
    (draft.summaryConfig?.detailSummaryPrompt?.length || 0) >
    WORKFLOW_DETAIL_SUMMARY_PROMPT_MAX_LENGTH
  ) {
    issues.push({
      path: 'summaryConfig.detailSummaryPrompt',
      nodeCode: '__summary__',
      message: `Detail Summary Prompt 不能超过 ${WORKFLOW_DETAIL_SUMMARY_PROMPT_MAX_LENGTH} 个字符`,
    });
  }
  if (suggestions.length > WORKFLOW_SUMMARY_ADVICE_MAX_COUNT) {
    issues.push({
      path: 'summaryConfig.handlingSuggestions',
      nodeCode: '__summary__',
      message: `处理建议不能超过 ${WORKFLOW_SUMMARY_ADVICE_MAX_COUNT} 条`,
    });
  }
  const suggestionIdCounts = new Map<string, number>();
  suggestions.forEach(({ suggestionId }) => {
    if (suggestionId) {
      suggestionIdCounts.set(suggestionId, (suggestionIdCounts.get(suggestionId) || 0) + 1);
    }
  });
  suggestions.forEach((suggestion, index) => {
    const itemPath = `summaryConfig.handlingSuggestions[${index}]`;
    if (!suggestion.suggestionId) {
      issues.push({
        path: `${itemPath}.suggestionId`,
        nodeCode: '__summary__',
        message: '请填写建议标识',
      });
    } else if ((suggestionIdCounts.get(suggestion.suggestionId) || 0) > 1) {
      issues.push({
        path: `${itemPath}.suggestionId`,
        nodeCode: '__summary__',
        message: `建议标识 ${suggestion.suggestionId} 重复`,
      });
    }
    if (!suggestion.displayText) {
      issues.push({
        path: `${itemPath}.displayText`,
        nodeCode: '__summary__',
        message: '请填写展示文案',
      });
    } else if (suggestion.displayText?.length > WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH) {
      issues.push({
        path: `${itemPath}.displayText`,
        nodeCode: '__summary__',
        message: `展示文案不能超过 ${WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH} 个字符`,
      });
    }
    if (!suggestion.sendMessageText) {
      issues.push({
        path: `${itemPath}.sendMessageText`,
        nodeCode: '__summary__',
        message: '请填写发送消息',
      });
    } else if (suggestion.sendMessageText?.length > WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH) {
      issues.push({
        path: `${itemPath}.sendMessageText`,
        nodeCode: '__summary__',
        message: `发送消息不能超过 ${WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH} 个字符`,
      });
    }
  });
  draft.edges?.forEach?.((edge) => {
    if (edge.edgeType === 'ROUTING' && (!edge.description || !edge.targetNodeCode)) {
      issues.push({
        path: `edges.${edge.edgeId}`,
        edgeId: edge.edgeId,
        message: '候选路由说明和目标节点不能为空',
      });
    }
    if (edge.edgeType === 'PARALLEL' && !edge.branchKey) {
      issues.push({
        path: `edges.${edge.edgeId}.branchKey`,
        edgeId: edge.edgeId,
        message: 'branchKey 不能为空',
      });
    }
    if (edge.edgeType === 'PARALLEL' && edge.branchKey.length > WORKFLOW_BRANCH_KEY_MAX_LENGTH) {
      issues.push({
        path: `edges.${edge.edgeId}.branchKey`,
        edgeId: edge.edgeId,
        message: `branchKey 不能超过 ${WORKFLOW_BRANCH_KEY_MAX_LENGTH} 个字符`,
      });
    }
  });
  return issues;
};
