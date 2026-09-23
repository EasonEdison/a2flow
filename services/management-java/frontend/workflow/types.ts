export type WorkflowNodeType = 'SKILL' | 'ROUTER' | 'PARALLEL_FORK' | 'PARALLEL_JOIN' | 'SUMMARY';

export type WorkflowEdgeType = 'NORMAL' | 'ROUTING' | 'PARALLEL';

export interface WorkflowNodeBase {
  nodeCode: string;
  nodeType: WorkflowNodeType;
  displayName?: string;
}

export interface WorkflowNodeControlPolicy {
  allowSkip: boolean;
}

export interface WorkflowSkillNode extends WorkflowNodeBase {
  nodeType: 'SKILL';
  skillCode: string;
  quickTriggerMessage?: string;
  nodePrompt: string;
  controlPolicy: WorkflowNodeControlPolicy;
}

export interface WorkflowRouterCandidate {
  routeKey: string;
  description: string;
  targetNodeCode: string;
}

export interface WorkflowRouterNode extends WorkflowNodeBase {
  nodeType: 'ROUTER';
  routerPrompt: string;
  routerContractVersion: 1;
  routerSchemaDigest: string;
  candidates: WorkflowRouterCandidate[];
}

export type WorkflowJoinPolicy = 'ALL_SUCCESS_OR_SKIPPED';

export interface WorkflowParallelForkNode extends WorkflowNodeBase {
  nodeType: 'PARALLEL_FORK';
  matchingNodeCode: string;
  joinPolicy: WorkflowJoinPolicy;
  maxParallelism: number;
}

export interface WorkflowParallelJoinNode extends WorkflowNodeBase {
  nodeType: 'PARALLEL_JOIN';
  matchingNodeCode: string;
  joinPolicy: WorkflowJoinPolicy;
}

export interface WorkflowSummaryNode extends WorkflowNodeBase {
  nodeType: 'SUMMARY';
  prompt: string;
  allowSkip: false;
}

export type WorkflowNode =
  | WorkflowSkillNode
  | WorkflowRouterNode
  | WorkflowParallelForkNode
  | WorkflowParallelJoinNode
  | WorkflowSummaryNode;

interface WorkflowEdgeBase {
  edgeId: string;
  sourceNodeCode: string;
  targetNodeCode: string;
  edgeType: WorkflowEdgeType;
}

export interface WorkflowNormalEdge extends WorkflowEdgeBase {
  edgeType: 'NORMAL';
}

export interface WorkflowRoutingEdge extends WorkflowEdgeBase {
  edgeType: 'ROUTING';
  routeKey: string;
  description: string;
}

export interface WorkflowParallelEdge extends WorkflowEdgeBase {
  edgeType: 'PARALLEL';
  branchKey: string;
  branchOrder: number;
}

export type WorkflowEdge = WorkflowNormalEdge | WorkflowRoutingEdge | WorkflowParallelEdge;

export interface WorkflowSummaryConfig {
  prompt: string;
  detailSummaryPrompt?: string;
  handlingSuggestions: WorkflowHandlingSuggestion[];
}

export interface WorkflowHandlingSuggestion {
  suggestionId: string;
  iconUrl?: string;
  displayText: string;
  sendMessageText: string;
}

export interface WorkflowDraft {
  snapshotContractVersion: 2;
  workflowCode: string;
  metadata: Record<string, unknown>;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  summaryConfig: WorkflowSummaryConfig;
}

export interface WorkflowDefinitionView {
  workflowCode: string;
  specialistCode: string;
  displayName: string;
  description: string;
  status: string;
  draftRevision: number;
  draftDigest?: string;
  draftContractVersion: number;
  createdBy: string;
  updatedBy: string;
  createTime: number;
  updateTime: number;
}

export interface WorkflowEnvironmentPointer {
  environment?: string;
  sourceType?: string;
  sourceId?: string;
  version?: number;
  digest?: string;
  status?: string;
  updatedAt?: number;
  updatedBy?: string;
}

export interface WorkflowListItemView {
  workflow: WorkflowDefinitionView;
  environmentPointers: Record<string, WorkflowEnvironmentPointer>;
}

export interface WorkflowListPageView {
  items: WorkflowListItemView[];
  nextPageToken?: string;
}

export interface WorkflowCreateResult {
  workflowCode: string;
  draftRevision: number;
  draftDigest: string;
  createdAt: number;
}

export interface WorkflowDraftPayloadView {
  workflowCode: string;
  draftPayloadJson: string;
  draftRevision: number;
  draftDigest?: string;
}

export interface WorkflowDraftUpdateResult {
  workflowCode: string;
  draftRevision: number;
  draftDigest: string;
}

export interface WorkflowSkillOption {
  skillCode: string;
  displayName: string;
  description: string;
  status: string;
}

export interface WorkflowGraphValidationError {
  errorCode: string;
  message: string;
  fieldPath?: string;
  nodeCode?: string;
  edgeId?: string;
  graphPath?: string[];
}

export interface WorkflowCompiledPlan {
  compiledPlanContractVersion: number;
  compiledPlanDigest: string;
  [key: string]: unknown;
}

export interface WorkflowGraphPreviewResult {
  compiledPlan?: WorkflowCompiledPlan;
  errors: WorkflowGraphValidationError[];
}

export interface WorkflowValidationIssue {
  path: string;
  message: string;
  nodeCode?: string;
  edgeId?: string;
}

export interface WorkflowSpecialistOption {
  specialistCode: string;
  specialistName: string;
}
