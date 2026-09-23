import { strict as assert } from 'assert';
import {
  deleteWorkflowSkillNode,
  getWorkflowSkillNodeActionState,
  moveWorkflowSkillNode,
} from './model';
import type {
  WorkflowDraft,
  WorkflowEdge,
  WorkflowNode,
  WorkflowRouterNode,
  WorkflowSkillNode,
} from './types';

const skill = (nodeCode: string): WorkflowSkillNode => ({
  nodeCode,
  nodeType: 'SKILL',
  displayName: nodeCode,
  skillCode: `skill_${nodeCode.toLowerCase()}`,
  nodePrompt: `执行 ${nodeCode}`,
  controlPolicy: { allowSkip: false },
});

const summary = (): WorkflowNode => ({
  nodeCode: '__summary__',
  nodeType: 'SUMMARY',
  displayName: '总结',
  prompt: '汇总结果',
  allowSkip: false,
});

const normal = (source: string, target: string): WorkflowEdge => ({
  edgeId: `${source}_to_${target}`,
  edgeType: 'NORMAL',
  sourceNodeCode: source,
  targetNodeCode: target,
});

const draftOf = (nodes: WorkflowNode[], edges: WorkflowEdge[]): WorkflowDraft => ({
  snapshotContractVersion: 2,
  workflowCode: 'wf_skill_mutation_test',
  metadata: {},
  nodes,
  edges,
  summaryConfig: { prompt: '汇总结果', handlingSuggestions: [] },
});

const linearDraft = (): WorkflowDraft =>
  draftOf(
    [skill('A'), skill('B'), skill('C'), summary()],
    [normal('A', 'B'), normal('B', 'C'), normal('C', '__summary__')],
  );

const unwrap = (result: ReturnType<typeof moveWorkflowSkillNode>): WorkflowDraft => {
  if (!result.ok) throw new Error(result.reason);
  return result.draft;
};

const executionPath = (draft: WorkflowDraft): string[] => {
  const incoming = new Set(draft.edges?.map?.((edge) => edge.targetNodeCode));
  const entries = draft.nodes?.filter?.((node) => !incoming.has(node.nodeCode));
  assert.equal(entries.length, 1, 'single entry');
  const path: string[] = [];
  let current = entries?.[0]?.nodeCode;
  while (current) {
    path.push(current);
    const outgoing = draft.edges?.filter?.((edge) => edge.sourceNodeCode === current);
    if (outgoing.length !== 1) break;
    current = outgoing[0]?.targetNodeCode;
  }
  return path;
};

const assertNoDanglingReferences = (draft: WorkflowDraft, removedCode: string) => {
  const nodeCodes = new Set(draft.nodes?.map?.((node) => node.nodeCode));
  draft.edges?.forEach?.((edge) => {
    assert.equal(nodeCodes.has(edge.sourceNodeCode), true, `edge source ${edge.edgeId}`);
    assert.equal(nodeCodes.has(edge.targetNodeCode), true, `edge target ${edge.edgeId}`);
    assert.notEqual(edge.sourceNodeCode, removedCode, `removed source ${edge.edgeId}`);
    assert.notEqual(edge.targetNodeCode, removedCode, `removed target ${edge.edgeId}`);
  });
  draft.nodes?.forEach?.((node) => {
    if (node.nodeType !== 'ROUTER') return;
    node.candidates?.forEach?.((candidate) => {
      assert.equal(
        nodeCodes.has(candidate.targetNodeCode),
        true,
        `candidate ${candidate.routeKey}`,
      );
      assert.notEqual(
        candidate.targetNodeCode,
        removedCode,
        `removed candidate ${candidate.routeKey}`,
      );
    });
  });
};

{
  const source = linearDraft();
  const moved = unwrap(moveWorkflowSkillNode(source, 'B', 'UP'));
  assert.deepEqual(executionPath(moved), ['B', 'A', 'C', '__summary__'], 'move up execution path');
  assert.deepEqual(
    moved.nodes?.map?.((node) => node.nodeCode),
    source.nodes?.map?.((node) => node.nodeCode),
    'move up does not fake execution order by reordering nodes array',
  );
}

{
  const moved = unwrap(moveWorkflowSkillNode(linearDraft(), 'B', 'DOWN'));
  assert.deepEqual(
    executionPath(moved),
    ['A', 'C', 'B', '__summary__'],
    'move down execution path',
  );
}

{
  const result = unwrap(deleteWorkflowSkillNode(linearDraft(), 'B'));
  assert.deepEqual(executionPath(result), ['A', 'C', '__summary__'], 'middle deletion bridge');
  assertNoDanglingReferences(result, 'B');
}

{
  const result = unwrap(deleteWorkflowSkillNode(linearDraft(), 'A'));
  assert.deepEqual(executionPath(result), ['B', 'C', '__summary__'], 'entry deletion promotion');
  assertNoDanglingReferences(result, 'A');
}

{
  const router: WorkflowRouterNode = {
    nodeCode: 'R',
    nodeType: 'ROUTER',
    displayName: '路由',
    routerPrompt: '选择路径',
    routerContractVersion: 1,
    routerSchemaDigest: 'router-v1',
    candidates: [
      { routeKey: 'main', description: '主路径', targetNodeCode: 'A' },
      { routeKey: 'backup', description: '备选路径', targetNodeCode: 'C' },
    ],
  };
  const source = draftOf(
    [router, skill('A'), skill('B'), skill('C'), summary()],
    [
      {
        edgeId: 'route_main',
        edgeType: 'ROUTING',
        sourceNodeCode: 'R',
        targetNodeCode: 'A',
        routeKey: 'main',
        description: '主路径',
      },
      {
        edgeId: 'route_backup',
        edgeType: 'ROUTING',
        sourceNodeCode: 'R',
        targetNodeCode: 'C',
        routeKey: 'backup',
        description: '备选路径',
      },
      normal('A', 'B'),
      normal('B', '__summary__'),
      normal('C', '__summary__'),
    ],
  );
  assert.equal(
    getWorkflowSkillNodeActionState(source, 'A')?.moveUp?.enabled,
    false,
    'Router boundary move disabled',
  );
  const result = unwrap(deleteWorkflowSkillNode(source, 'A'));
  const updatedRouter = result.nodes?.find?.(
    (node): node is WorkflowRouterNode => node.nodeCode === 'R',
  );
  assert.equal(
    updatedRouter?.candidates?.find((candidate) => candidate.routeKey === 'main')?.targetNodeCode,
    'B',
  );
  assert.equal(result?.edges?.find?.((edge) => edge.edgeId === 'route_main')?.targetNodeCode, 'B');
  assertNoDanglingReferences(result, 'A');
}

{
  const fork: WorkflowNode = {
    nodeCode: 'F',
    nodeType: 'PARALLEL_FORK',
    displayName: 'Fork',
    matchingNodeCode: 'J',
    joinPolicy: 'ALL_SUCCESS_OR_SKIPPED',
    maxParallelism: 2,
  };
  const join: WorkflowNode = {
    nodeCode: 'J',
    nodeType: 'PARALLEL_JOIN',
    displayName: 'Join',
    matchingNodeCode: 'F',
    joinPolicy: 'ALL_SUCCESS_OR_SKIPPED',
  };
  const source = draftOf(
    [fork, skill('A'), skill('B'), join, summary()],
    [
      {
        edgeId: 'branch_a',
        edgeType: 'PARALLEL',
        sourceNodeCode: 'F',
        targetNodeCode: 'A',
        branchKey: 'a',
        branchOrder: 1,
      },
      {
        edgeId: 'branch_b',
        edgeType: 'PARALLEL',
        sourceNodeCode: 'F',
        targetNodeCode: 'B',
        branchKey: 'b',
        branchOrder: 2,
      },
      normal('A', 'J'),
      normal('B', 'J'),
      normal('J', '__summary__'),
    ],
  );
  const state = getWorkflowSkillNodeActionState(source, 'A');
  assert.equal(state.moveUp?.enabled, false, 'Parallel boundary move up disabled');
  assert.equal(state.moveDown?.enabled, false, 'Join boundary move down disabled');
  const result = deleteWorkflowSkillNode(source, 'A');
  assert.equal(result.ok, false, 'Fork direct Join deletion rejected');
  if (result.ok) throw new Error('expected Fork direct Join rejection');
  assert.match(result.reason, /Fork|Join|并行/);
}

{
  const fork: WorkflowNode = {
    nodeCode: 'F',
    nodeType: 'PARALLEL_FORK',
    displayName: 'Fork',
    matchingNodeCode: 'J',
    joinPolicy: 'ALL_SUCCESS_OR_SKIPPED',
    maxParallelism: 2,
  };
  const join: WorkflowNode = {
    nodeCode: 'J',
    nodeType: 'PARALLEL_JOIN',
    displayName: 'Join',
    matchingNodeCode: 'F',
    joinPolicy: 'ALL_SUCCESS_OR_SKIPPED',
  };
  const source = draftOf(
    [fork, skill('A'), skill('B'), skill('C'), join, summary()],
    [
      {
        edgeId: 'branch_a',
        edgeType: 'PARALLEL',
        sourceNodeCode: 'F',
        targetNodeCode: 'A',
        branchKey: 'a',
        branchOrder: 1,
      },
      {
        edgeId: 'branch_b',
        edgeType: 'PARALLEL',
        sourceNodeCode: 'F',
        targetNodeCode: 'B',
        branchKey: 'b',
        branchOrder: 2,
      },
      normal('A', 'C'),
      normal('C', 'J'),
      normal('B', 'J'),
      normal('J', '__summary__'),
    ],
  );
  const result = unwrap(deleteWorkflowSkillNode(source, 'A'));
  const branch = result.edges?.find?.((edge) => edge.edgeId === 'branch_a');
  assert.equal(branch?.targetNodeCode, 'C', 'Parallel branch identity retargeted');
  assert.equal(branch?.edgeType, 'PARALLEL', 'Parallel branch type preserved');
  assertNoDanglingReferences(result, 'A');
}

{
  const router: WorkflowRouterNode = {
    nodeCode: 'R',
    nodeType: 'ROUTER',
    routerPrompt: '选择路径',
    routerContractVersion: 1,
    routerSchemaDigest: 'router-v1',
    candidates: [
      { routeKey: 'main', description: '主路径', targetNodeCode: 'A' },
      { routeKey: 'backup', description: '备选路径', targetNodeCode: 'A' },
    ],
  };
  const source = draftOf(
    [router, skill('A'), skill('B'), summary()],
    [
      {
        edgeId: 'route_main',
        edgeType: 'ROUTING',
        sourceNodeCode: 'R',
        targetNodeCode: 'A',
        routeKey: 'main',
        description: '主路径',
      },
      {
        edgeId: 'route_backup',
        edgeType: 'ROUTING',
        sourceNodeCode: 'R',
        targetNodeCode: 'A',
        routeKey: 'backup',
        description: '备选路径',
      },
      normal('A', 'B'),
      normal('B', '__summary__'),
    ],
  );
  const state = getWorkflowSkillNodeActionState(source, 'A');
  assert.equal(state.delete?.enabled, false, 'ambiguous predecessor deletion disabled');
  assert.match(state.delete?.reason || '', /前驱或后继不唯一/);
}

{
  const source = draftOf([skill('A'), summary()], [normal('A', '__summary__')]);
  const state = getWorkflowSkillNodeActionState(source, 'A');
  assert.equal(state.moveDown?.enabled, false, 'Summary boundary move down disabled');
  assert.equal(state.delete?.enabled, false, 'last Skill delete disabled');
  assert.match(state.delete?.reason || '', /至少保留一个 Skill/);
  assert.equal(deleteWorkflowSkillNode(source, 'A')?.ok, false, 'last Skill delete rejected');
  assert.equal(
    deleteWorkflowSkillNode(source, '__summary__')?.ok,
    false,
    'Summary deletion rejected',
  );
}

console.log('workflowSkillNodeMutations.test.ts PASS');
