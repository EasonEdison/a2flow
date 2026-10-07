/** Product view models, not a published Runtime wire contract. */
export type NodeStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'WAITING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'SKIPPED'
  | 'STOPPED'
  | 'UNKNOWN';

export type RecordLine = {
  id: string;
  kind: 'reasoning' | 'text' | 'operation' | 'notice';
  text: string;
  eventKind?: string;
  observedAt?: string;
  operationId?: string;
  modelCallId?: string;
  toolName?: string;
  payload?: import('./api/contracts').JsonObject;
};

export type Choice = {
  value: string;
  label: string;
  description?: string;
};

export type InteractiveCard = {
  kind: 'INTERACTIVE';
  id: string;
  prompt: string;
  choices: Choice[];
  selected?: string;
  operable: boolean;
  actionName: string;
  interactionId: string;
  buttonLabel: string;
  confirmed: boolean;
};

export type DisplayCard = {
  kind: 'DISPLAY_ONLY';
  id: string;
  title: string;
  fields: { label: string; markdown: string }[];
};

export type CardView = InteractiveCard | DisplayCard;

export type NodeView = {
  id: string;
  title: string;
  status: NodeStatus;
  summary?: string;
  records: RecordLine[];
  historyStatus?: 'loading' | 'ready' | 'incomplete';
  output?: string;
  actionResults?: import('./api/contracts').Json[];
  card?: CardView;
  incomplete?: boolean;
};

export type RunView = {
  id: string;
  title: string;
  lifecycle: NodeStatus;
  requirement?: string;
  nodes: NodeView[];
};

export const statusLabels: Record<NodeStatus, string> = {
  PENDING: '待执行',
  RUNNING: '正在执行',
  WAITING: '等待你确认',
  SUCCEEDED: '已完成',
  FAILED: '执行失败',
  SKIPPED: '已跳过',
  STOPPED: '已停止',
  UNKNOWN: '执行结果未确认',
};

export function terminal(status: NodeStatus) {
  return ['SUCCEEDED', 'FAILED', 'SKIPPED', 'STOPPED'].includes(status);
}
