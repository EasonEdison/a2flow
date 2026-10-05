import { serverMessageKey } from './a2uiApplicationShowAst';
import type {
  A2uiResultAdapter,
  A2uiResultOutcome,
  A2uiResultTransform,
} from './a2uiApplicationContracts';

function hasText(value: string | undefined): boolean {
  return Boolean(value?.trim());
}

function readsBusinessDataThroughMetadata(
  source: string | undefined,
  sourcePath: string | undefined,
): boolean {
  const normalized = sourcePath?.trim();
  return (
    source === 'CAPABILITY_META' &&
    (normalized === '/data' || normalized?.startsWith('/data/') === true)
  );
}

function validJsonPointer(value: unknown): value is string {
  if (typeof value !== 'string' || !value.startsWith('/')) return false;
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === '~' && !['0', '1'].includes(value[index + 1])) return false;
  }
  return true;
}

function validateResultTransform(transform: A2uiResultTransform | undefined, errors: string[]): void {
  if (!transform) return;
  const raw = transform as unknown as Record<string, unknown>;
  const allowed = new Set([
    'type',
    'scale',
    'componentIds',
    'pageSize',
    'pageNumber',
    'actionPagePath',
    'valuePath',
    'labelColumns',
    'labelSeparator',
  ]);
  if (Object.keys(raw).some((key) => !allowed.has(key))) {
    errors.push('A2UI_RESULT_TRANSFORM_INVALID');
    return;
  }
  if (transform.type !== 'ARRAY_OBJECT_TO_OPTIONS') return;
  const columns = transform.labelColumns || [];
  const legacyFields = [
    transform.scale,
    transform.componentIds,
    transform.pageSize,
    transform.pageNumber,
    transform.actionPagePath,
  ];
  if (
    legacyFields.some((value) => value !== undefined) ||
    !validJsonPointer(transform.valuePath) ||
    !hasText(transform.labelSeparator) ||
    transform.labelSeparator!.length > 8 ||
    columns.length < 1 ||
    columns.length > 20 ||
    columns.some(
      (column) => !hasText(column?.label) || !validJsonPointer(column?.sourcePath),
    )
  ) {
    errors.push('A2UI_RESULT_TRANSFORM_INVALID');
  }
}

function validateAdapters(adapters: A2uiResultAdapter[], errors: string[]): void {
  const orders = adapters.map((adapter) => adapter.order);
  if (orders.some((order) => !Number.isInteger(order) || order < 1)) {
    errors.push('A2UI_RESULT_ADAPTER_ORDER_INVALID');
  }
  if (new Set(orders).size !== orders.length) {
    errors.push('A2UI_RESULT_ADAPTER_ORDER_DUPLICATE');
  }
  adapters.forEach((adapter) => {
    const raw = adapter as unknown as Record<string, unknown>;
    if (
      adapter.type === 'MESSAGE_TEMPLATE' &&
      (!adapter.messageTemplate ||
        adapter.messageTemplate.version !== 'v0.9.1' ||
        !serverMessageKey(adapter.messageTemplate) ||
        Object.prototype.hasOwnProperty.call(raw, 'messages'))
    ) {
      errors.push('A2UI_MESSAGE_TEMPLATE_REQUIRED');
    }
    if (
      adapter.type === 'MESSAGE_TEMPLATE' &&
      (!hasText(adapter.templateCode) ||
        !hasText(adapter.templateRevision) ||
        !hasText(adapter.templateDigest))
    ) {
      errors.push('A2UI_MESSAGE_TEMPLATE_CLOSURE_REQUIRED');
    }
    if (adapter.type === 'MESSAGE_TEMPLATE') {
      (adapter.bindings || []).forEach((binding) => {
        if (
          !hasText(binding.targetPath) ||
          ![
            'CAPABILITY_DATA',
            'CAPABILITY_META',
            'TRUSTED_CONTEXT',
            'ACTION_CONTEXT',
            'CONSTANT',
          ].includes(
            binding.source,
          ) ||
          (binding.source !== 'CONSTANT' && !hasText(binding.sourcePath)) ||
          readsBusinessDataThroughMetadata(binding.source, binding.sourcePath)
        ) {
          errors.push('A2UI_MESSAGE_TEMPLATE_BINDING_INVALID');
        }
        validateResultTransform(binding.transform, errors);
      });
    }
    if (adapter.type === 'A2UI_PASSTHROUGH') {
      if (
        !['CAPABILITY_DATA', 'CAPABILITY_META'].includes(adapter.source || '') ||
        readsBusinessDataThroughMetadata(adapter.source, adapter.sourcePath)
      ) {
        errors.push('A2UI_PASSTHROUGH_SOURCE_ROOT_INVALID');
      }
      if (!hasText(adapter.sourcePath)) errors.push('A2UI_PASSTHROUGH_SOURCE_REQUIRED');
      if (!adapter.cardinality) errors.push('A2UI_PASSTHROUGH_CARDINALITY_REQUIRED');
      if (typeof adapter.required !== 'boolean') errors.push('A2UI_PASSTHROUGH_REQUIRED_INVALID');
    }
  });
}

export function validateAdapterOutcome(
  outcome: A2uiResultOutcome | undefined,
  adapters: A2uiResultAdapter[],
  errors: string[],
): void {
  if (!outcome) {
    errors.push('A2UI_RESULT_OUTCOME_REQUIRED');
    return;
  }
  if (outcome === 'NO_UI_MESSAGES' && adapters.length) {
    errors.push('A2UI_NO_UI_MESSAGES_ADAPTER_CONFLICT');
    return;
  }
  if (outcome === 'ADAPTER_PIPELINE' && !adapters.length) {
    errors.push('A2UI_RESULT_ADAPTER_REQUIRED');
    return;
  }
  if (outcome === 'ADAPTER_PIPELINE') validateAdapters(adapters, errors);
}
