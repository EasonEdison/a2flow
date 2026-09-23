import type {
  CapabilityActionAllowedValue,
  CapabilityActionInputField,
  CapabilityActionValueSchema,
  CapabilityActionValueSchemaType,
} from './api';

const valueSchemaTypes = new Set<CapabilityActionValueSchemaType>([
  'string',
  'number',
  'integer',
  'boolean',
  'object',
  'array',
]);

function normalizeCapabilityValueSchema(
  value?: CapabilityActionValueSchema,
): CapabilityActionValueSchema | undefined {
  if (!value?.type || !valueSchemaTypes.has(value.type)) return undefined;
  if (value.type === 'array') {
    return {
      type: 'array',
      description: value.description,
      items: normalizeCapabilityValueSchema(value.items),
    };
  }
  if (value.type === 'object') {
    const properties = Object.fromEntries(
      Object.entries(value.properties || {})
        ?.map(([name, schema]) => [name, normalizeCapabilityValueSchema(schema)] as const)
        ?.filter?.((entry): entry is [string, CapabilityActionValueSchema] => Boolean(entry?.[1])),
    );
    const propertyNames = new Set(Object.keys(properties));
    const required = (value.required || []).filter((name) => propertyNames.has(name));
    return {
      type: 'object',
      description: value.description,
      properties,
      ...(required.length ? { required } : {}),
    };
  }
  return { type: value.type, description: value.description };
}

export function capabilityAllowedValueFromText(
  type: CapabilityActionInputField['type'],
  rawValue: string,
): string | number | undefined {
  if (type !== 'number' && type !== 'integer') return rawValue;
  if (!rawValue.trim()) return undefined;
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) && (type !== 'integer' || Number.isSafeInteger(parsed)) ? parsed : undefined;
}

export function normalizeCapabilityAllowedValuesForType(
  type: CapabilityActionInputField['type'],
  values?: CapabilityActionAllowedValue[],
): CapabilityActionAllowedValue[] | undefined {
  if (!values?.length) return undefined;
  return values.map((item) => ({
    value: capabilityAllowedValueFromText(type, item.value === undefined ? '' : String(item.value)),
    label: item.label,
    description: item.description,
  }));
}

export function normalizeCapabilityInputField(
  value: CapabilityActionInputField,
): CapabilityActionInputField {
  const source =
    value.source === 'MODEL_INPUT' ||
    value.source === 'CONSTANT' ||
    value.source === 'SYSTEM_VARIABLE'
      ? value.source
      : undefined;
  const type =
    value.type === 'string' ||
    value.type === 'number' ||
    value.type === 'integer' ||
    value.type === 'boolean' ||
    value.type === 'array'
      ? value.type
      : undefined;
  const systemVariable =
    value.systemVariable === 'userId' || value.systemVariable === 'client'
      ? value.systemVariable
      : undefined;
  return {
    toolField: value.toolField,
    type,
    businessMeaning: value.businessMeaning,
    unit: value.unit,
    source,
    ...(type === 'array' ? { items: normalizeCapabilityValueSchema(value.items) } : {}),
    ...(source === 'CONSTANT'
      ? { constantValue: value.constantValue, required: false }
      : source === 'SYSTEM_VARIABLE'
      ? {
          systemVariable,
          required: false,
          ...(systemVariable === 'client' && value.valueMapping
            ? { valueMapping: value.valueMapping }
            : {}),
        }
      : source === 'MODEL_INPUT'
      ? {
          required: value.required,
          examples: value.examples,
          ...(type === 'string' || type === 'number' || type === 'integer'
            ? { allowedValues: normalizeCapabilityAllowedValuesForType(type, value.allowedValues) }
            : {}),
        }
      : { required: value.required }),
  };
}
