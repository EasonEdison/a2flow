import {
  capabilityAllowedValueFromText,
  normalizeCapabilityInputField,
} from './capabilityInputFieldContract';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${description}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`,
    );
  }
}

const modelInput = normalizeCapabilityInputField({
  toolField: 'timeRange',
  type: 'string',
  source: 'MODEL_INPUT',
  unit: '自然日',
  allowedValues: [
    { value: 'ONE_DAY', label: '单日' },
    { value: 'SEVEN_DAY', label: '近七日', description: '最近七个自然日' },
  ],
});
assertEqual(modelInput.unit, '自然日', 'unit metadata');
assertEqual(
  modelInput.allowedValues?.map((item) => item.value),
  ['ONE_DAY', 'SEVEN_DAY'],
  'model allowed values',
);

const constant = normalizeCapabilityInputField({
  toolField: 'timeRange',
  type: 'string',
  source: 'CONSTANT',
  allowedValues: [{ value: 'ONE_DAY', label: '单日' }],
});
assertEqual(constant.allowedValues, undefined, 'non-model source strips allowed values');
assertEqual(capabilityAllowedValueFromText('number', '7'), 7, 'number enum value');
assertEqual(capabilityAllowedValueFromText('number', ''), undefined, 'empty number enum value');

console.log('PASS capability input allowedValues contract');
