/** mvp08.1 wire supplied by Runtime owner. No browser-authored identity. */
export type Json =
  | null
  | boolean
  | number
  | string
  | Json[]
  | { [key: string]: Json };
export type JsonObject = { [key: string]: Json };

export type Session = { userId: string; environment: string };
export type Workflow = { definitionKey: string; inputSchema: JsonObject };
export type RunItem = {
  runId: string;
  definitionKey: string;
  title: string;
  lifecycle: string;
  createdAt: string;
};
export type WireNode = {
  nodeId: string;
  title: string;
  order: number;
  status: 'PENDING' | 'RUNNING' | 'WAITING' | 'SUCCEEDED' | 'UNCONFIRMED' | 'STOPPED';
  summary: string | null;
};
export type WireCard = {
  cardId: string;
  nodeId: string;
  interactionId: string;
  applicationKey: string;
  applicationVersion: string;
  protocolProfile: string;
  componentCatalogRef: string;
  rootId: string;
  components: Json;
  data: JsonObject;
  inputSchema: JsonObject;
  actions: { actionName: string; inputSchema: JsonObject }[];
  state: 'WAITING' | 'READ_ONLY' | 'INVALIDATED';
  actionEligibility: 'REVALIDATION_REQUIRED' | 'NOT_OPERABLE';
};
export type WireView = {
  schemaVersion: 'mvp08.1';
  runId: string;
  definitionKey: string;
  title: string;
  definitionVersion: string;
  createdAt: string;
  lifecycle: string;
  revision: string;
  observedAt: string;
  nodes: WireNode[];
  cards: WireCard[];
  outputs: { nodeId: string; kind: 'MODEL_TEXT' | 'ACTION_RESULT'; content: Json }[];
  availability: 'AVAILABLE' | 'UNCONFIRMED';
};
export type ProgressRecord = {
  seq: number;
  kind: string;
  observedAt: string;
  payload: JsonObject;
};
export type Segment = {
  node_id: string;
  execution_id: string;
  sealed: boolean;
  incomplete: boolean;
  observation_outcome: string;
};
export type History = {
  runId: string;
  nodeId: string;
  executionId: string;
  records: ProgressRecord[];
  nextCursor: string;
  hasMore: boolean;
  capture: {
    sealed: boolean;
    incomplete: boolean;
    observation_outcome?: string;
  };
};

export class ContractError extends Error {
  constructor() {
    super('服务返回了不支持的数据格式');
  }
}

export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ContractError();
  }
  return value as Record<string, unknown>;
}

export function string(value: unknown): string {
  if (typeof value !== 'string') {
    throw new ContractError();
  }
  return value;
}

export function list(value: unknown): unknown[] {
  if (!Array.isArray(value) || value.length > 2000) {
    throw new ContractError();
  }
  return value;
}

export function jsonObject(value: unknown): JsonObject {
  return object(value) as JsonObject;
}

export function parseSession(value: unknown): Session {
  const session = object(value);
  return { userId: string(session.userId), environment: string(session.environment) };
}

/**
 * AssetReader.list_workflows deliberately exposes only definitionKey/inputSchema.
 * Title and nodes belong to the Runtime view, not the start catalog.
 */
export function parseWorkflows(value: unknown): Workflow[] {
  return list(object(value).items).map((item) => {
    const workflow = object(item);
    return {
      definitionKey: string(workflow.definitionKey),
      inputSchema: jsonObject(workflow.inputSchema),
    };
  });
}

export function parseView(value: unknown): WireView {
  const view = object(value);
  if (
    view.schemaVersion !== 'mvp08.1' ||
    !['AVAILABLE', 'UNCONFIRMED'].includes(string(view.availability))
  ) {
    throw new ContractError();
  }

  for (const key of [
    'runId',
    'definitionKey',
    'title',
    'definitionVersion',
    'createdAt',
    'lifecycle',
    'observedAt',
  ]) {
    string(view[key]);
  }
  if (typeof view.revision !== 'string') {
    throw new ContractError();
  }

  list(view.nodes).forEach((node) => {
    const parsed = object(node);
    string(parsed.nodeId);
    string(parsed.title);
    if (
      typeof parsed.order !== 'number' ||
      !['PENDING', 'RUNNING', 'WAITING', 'SUCCEEDED', 'UNCONFIRMED', 'STOPPED'].includes(
        string(parsed.status),
      ) ||
      (parsed.summary !== null && typeof parsed.summary !== 'string')
    ) {
      throw new ContractError();
    }
  });

  const cards = list(view.cards);
  if (cards.length > 16) {
    throw new ContractError();
  }
  cards.forEach((card) => {
    const parsed = object(card);
    for (const key of [
      'cardId',
      'nodeId',
      'interactionId',
      'applicationKey',
      'applicationVersion',
      'protocolProfile',
      'componentCatalogRef',
      'rootId',
    ]) {
      string(parsed[key]);
    }
    jsonObject(parsed.data);
    jsonObject(parsed.inputSchema);
    if (
      !['WAITING', 'READ_ONLY', 'INVALIDATED'].includes(string(parsed.state)) ||
      !['REVALIDATION_REQUIRED', 'NOT_OPERABLE'].includes(
        string(parsed.actionEligibility),
      )
    ) {
      throw new ContractError();
    }
    list(parsed.actions).forEach((action) => {
      const parsedAction = object(action);
      string(parsedAction.actionName);
      jsonObject(parsedAction.inputSchema);
    });
  });

  const outputs = list(view.outputs);
  if (outputs.length > 8) {
    throw new ContractError();
  }
  outputs.forEach((output) => {
    const parsed = object(output);
    string(parsed.nodeId);
    if (!['MODEL_TEXT', 'ACTION_RESULT'].includes(string(parsed.kind))) {
      throw new ContractError();
    }
  });

  return view as unknown as WireView;
}

export function parseHistory(value: unknown): History {
  const history = object(value);
  for (const key of ['runId', 'nodeId', 'executionId', 'nextCursor']) {
    string(history[key]);
  }
  if (typeof history.hasMore !== 'boolean') {
    throw new ContractError();
  }
  object(history.capture);
  list(history.records).forEach(parseRecord);
  return history as unknown as History;
}

export function parseRecord(value: unknown): ProgressRecord {
  const record = object(value);
  if (!Number.isSafeInteger(record.seq) || Number(record.seq) < 1) {
    throw new ContractError();
  }
  string(record.kind);
  string(record.observedAt);
  object(record.payload);
  return record as unknown as ProgressRecord;
}
