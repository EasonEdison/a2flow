import {
  object,
  string,
  list,
  ContractError,
  type JsonObject,
  type ProgressRecord,
  type WireCard,
  type WireView,
} from './contracts';
import type {
  CardView,
  Choice,
  DisplayCard,
  InteractiveCard,
  NodeStatus,
  RecordLine,
  RunView,
} from '../presentation';

const MAX_TEXT_LENGTH = 8000;

const allowedKeys = (value: Record<string, unknown>, keys: string[]) => {
  if (Object.keys(value).some((key) => !keys.includes(key))) {
    throw new ContractError();
  }
};

const binding = (value: unknown, path: string) => {
  const parsed = object(value);
  allowedKeys(parsed, ['path']);
  if (parsed.path !== path) {
    throw new ContractError();
  }
};

const bounded = (value: unknown, max: number) => {
  const result = string(value);
  if (!result.length || result.length > max) {
    throw new ContractError();
  }
  return result;
};

const componentById = (
  components: Record<string, unknown>[],
  id: string,
): Record<string, unknown> => {
  const component = components.find((item) => item.id === id);
  if (!component) {
    throw new ContractError();
  }
  return component;
};

const parseChoices = (data: JsonObject): { choices: Choice[]; selected?: string } => {
  const choices = list(data.options).map((item) => {
    const option = object(item);
    allowedKeys(option, ['label', 'value']);
    return {
      label: bounded(option.label, 2000),
      value: bounded(option.value, 128),
    };
  });
  if (
    choices.length < 2 ||
    choices.length > 8 ||
    new Set(choices.map((choice) => choice.value)).size !== choices.length
  ) {
    throw new ContractError();
  }
  const selected = data.optionId === undefined ? undefined : bounded(data.optionId, 128);
  if (selected !== undefined && !choices.some((choice) => choice.value === selected)) {
    throw new ContractError();
  }
  return { choices, selected };
};

const parseInteractiveCard = (card: WireCard, active: boolean): InteractiveCard => {
  const components = list(card.components).map(object);
  if (
    components.length !== 4 ||
    new Set(components.map((component) => string(component.id))).size !== 4 ||
    card.rootId !== 'root'
  ) {
    throw new ContractError();
  }

  const root = componentById(components, 'root');
  allowedKeys(root, ['id', 'component', 'children']);
  if (
    root.component !== 'Column' ||
    list(root.children).map(string).join(',') !== 'prompt,selection,submit'
  ) {
    throw new ContractError();
  }

  const prompt = componentById(components, 'prompt');
  allowedKeys(prompt, ['id', 'component', 'text']);
  if (prompt.component !== 'Text') {
    throw new ContractError();
  }
  binding(prompt.text, '/prompt');

  const selection = componentById(components, 'selection');
  allowedKeys(selection, ['id', 'component', 'options', 'value', 'variant']);
  if (selection.component !== 'ChoicePicker' || selection.variant !== 'mutuallyExclusive') {
    throw new ContractError();
  }
  binding(selection.options, '/options');
  binding(selection.value, '/optionId');

  const submit = componentById(components, 'submit');
  allowedKeys(submit, ['id', 'component', 'label', 'action']);
  if (submit.component !== 'Button') {
    throw new ContractError();
  }
  const action = object(submit.action);
  allowedKeys(action, ['event']);
  const event = object(action.event);
  allowedKeys(event, ['name', 'context']);
  const actionName = string(event.name);
  if (!['select_activity_plan', 'confirm_schedule'].includes(actionName)) {
    throw new ContractError();
  }

  const context = object(event.context);
  const expectedContext = actionName === 'select_activity_plan'
    ? ['optionId']
    : ['optionId', 'confirmed'];
  allowedKeys(context, expectedContext);
  binding(context.optionId, '/optionId');
  const confirmed = actionName === 'confirm_schedule';
  if (confirmed) {
    const confirmation = object(context.confirmed);
    allowedKeys(confirmation, ['literal']);
    if (confirmation.literal !== true) {
      throw new ContractError();
    }
  }

  if (card.actions.length !== 1 || card.actions[0].actionName !== actionName) {
    throw new ContractError();
  }
  const actionSchema = card.actions[0].inputSchema;
  allowedKeys(actionSchema, ['type', 'required', 'additionalProperties', 'properties']);
  const required = list(actionSchema.required).map(string);
  const properties = object(actionSchema.properties);
  if (
    actionSchema.type !== 'object' ||
    actionSchema.additionalProperties !== false ||
    required.join(',') !== (confirmed ? 'optionId,confirmed' : 'optionId') ||
    Object.keys(properties).sort().join(',') !==
      (confirmed ? 'confirmed,optionId' : 'optionId')
  ) {
    throw new ContractError();
  }
  const optionId = object(properties.optionId);
  allowedKeys(optionId, ['type']);
  if (optionId.type !== 'string') {
    throw new ContractError();
  }
  if (confirmed) {
    const confirmation = object(properties.confirmed);
    allowedKeys(confirmation, ['const']);
    if (confirmation.const !== true) {
      throw new ContractError();
    }
  }

  allowedKeys(card.data, ['prompt', 'options', 'optionId']);
  const { choices, selected } = parseChoices(card.data);
  return {
    kind: 'INTERACTIVE',
    id: card.cardId,
    prompt: bounded(card.data.prompt, 2000),
    choices,
    selected,
    operable:
      active &&
      card.state === 'WAITING' &&
      card.actionEligibility === 'REVALIDATION_REQUIRED',
    actionName,
    interactionId: card.interactionId,
    buttonLabel: bounded(submit.label, 2000),
    confirmed,
  };
};

const parseDisplayCard = (card: WireCard): DisplayCard => {
  if (
    card.state !== 'READ_ONLY' ||
    card.actionEligibility !== 'NOT_OPERABLE' ||
    card.actions.length !== 0 ||
    card.rootId !== 'root'
  ) {
    throw new ContractError();
  }
  allowedKeys(card.inputSchema, ['type', 'additionalProperties']);
  if (
    card.inputSchema.type !== 'object' ||
    card.inputSchema.additionalProperties !== false
  ) {
    throw new ContractError();
  }
  const components = list(card.components).map(object);
  if (
    components.length !== 5 ||
    new Set(components.map((component) => string(component.id))).size !== 5
  ) {
    throw new ContractError();
  }
  const root = componentById(components, 'root');
  allowedKeys(root, ['id', 'component', 'children']);
  if (
    root.component !== 'Column' ||
    list(root.children).map(string).join(',') !== 'title,plan,schedule,package'
  ) {
    throw new ContractError();
  }

  const definitions = [
    ['title', '/title', '最终活动包'],
    ['plan', '/selectedPlan', '已选活动方案'],
    ['schedule', '/confirmedSchedule', '已确认执行安排'],
    ['package', '/packageSummary', '最终方案、执行清单与宣传文案'],
  ] as const;
  const fields = definitions.map(([id, path, label]) => {
    const component = componentById(components, id);
    allowedKeys(component, ['id', 'component', 'text']);
    if (component.component !== 'Text') {
      throw new ContractError();
    }
    binding(component.text, path);
    const key = path.slice(1);
    return { label, markdown: bounded(card.data[key], MAX_TEXT_LENGTH) };
  });
  allowedKeys(card.data, ['title', 'selectedPlan', 'confirmedSchedule', 'packageSummary']);
  return { kind: 'DISPLAY_ONLY', id: card.cardId, title: fields[0].markdown, fields: fields.slice(1) };
};

export function cardView(card: WireCard, active: boolean): CardView {
  if (
    card.protocolProfile !== 'a2flow.mvp08.v1' ||
    typeof card.componentCatalogRef !== 'string'
  ) {
    throw new ContractError();
  }
  return card.state === 'READ_ONLY'
    ? parseDisplayCard(card)
    : parseInteractiveCard(card, active);
}

export function recordLine(execution: string, record: ProgressRecord): RecordLine {
  const payload = record.payload;
  const labels: Record<string, string> = {
    MODEL_STARTED: '模型开始处理',
    MODEL_RETURNED: '模型调用返回',
    MODEL_UNCONFIRMED: '模型调用结果未确认',
    TOOL_STARTED: '能力调用开始',
    TOOL_RETURNED: '能力调用返回',
    TOOL_INTERRUPTED: '能力等待交互',
    TOOL_UNCONFIRMED: '能力调用结果未确认',
    NODE_STARTED: '节点开始执行',
    NODE_RETURNED: '节点调用返回',
    NODE_INTERRUPTED: '节点等待交互',
    NODE_UNCONFIRMED: '节点执行结果未确认',
    CAPTURE_INCOMPLETE: '过程记录不完整',
  };
  return {
    id: execution + ':' + record.seq,
    kind:
      record.kind === 'REASONING_DELTA'
        ? 'reasoning'
        : record.kind === 'TEXT_DELTA'
          ? 'text'
          : 'operation',
    text:
      ['REASONING_DELTA', 'TEXT_DELTA'].includes(record.kind)
        ? string(payload.text)
        : (labels[record.kind] ?? '已记录执行事件') +
          (typeof payload.toolName === 'string' ? ' · ' + payload.toolName : ''),
  };
}

const chineseNodeTitles: Record<string, string> = {
  choose_plan: '活动方案选择',
  confirm_schedule: '执行安排确认',
  show_activity_package: '最终活动包',
};

export function toView(
  wire: WireView,
  records: Record<string, RecordLine[]>,
): RunView {
  const status = (value: string): NodeStatus =>
    ['PENDING', 'RUNNING', 'WAITING', 'SUCCEEDED', 'STOPPED'].includes(value)
      ? (value as NodeStatus)
      : 'UNKNOWN';

  return {
    id: wire.runId,
    title: wire.title,
    lifecycle: status(wire.lifecycle),
    nodes: [...wire.nodes]
      .sort((left, right) => left.order - right.order)
      .map((node) => {
        const cards = wire.cards.filter((card) => card.nodeId === node.nodeId);
        if (cards.length > 1) {
          throw new ContractError();
        }
        return {
          id: node.nodeId,
          title: chineseNodeTitles[node.nodeId] ?? node.title,
          status: status(node.status),
          summary: node.summary ?? undefined,
          records: records[node.nodeId] ?? [],
          card: cards[0]
            ? cardView(cards[0], wire.lifecycle === 'RUNNING' && node.status === 'WAITING')
            : undefined,
          output:
            wire.outputs
              .filter((output) => output.nodeId === node.nodeId)
              .map((output) =>
                (output.kind === 'MODEL_TEXT' ? '模型输出\n' : '已保存的交互结果\n') +
                (typeof output.content === 'string'
                  ? output.content
                  : JSON.stringify(output.content, null, 2)),
              )
              .join('\n\n') || undefined,
          incomplete: wire.availability === 'UNCONFIRMED',
        };
      }),
  };
}
