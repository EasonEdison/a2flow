import { domainResultToolCallIds, shouldDisplayGenericToolResult } from './toolResultProjection';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function test(description: string, callback: () => void) {
  callback();
  console.log(`PASS ${description}`);
}

test('generic Tool failure is displayed when no custom result exists', () => {
  const genericFailure = {
    eventType: 'TOOL_CALL_FINISHED',
    toolCallId: 'tool_generic',
    toolSuccess: false,
  };
  const customResultIds = domainResultToolCallIds([genericFailure]);

  assertEqual(
    shouldDisplayGenericToolResult(genericFailure, customResultIds),
    true,
    'generic failure fallback',
  );
});

test('custom Tool failure suppresses duplicate generic result copy', () => {
  const genericFailure = {
    eventType: 'TOOL_CALL_FINISHED',
    toolCallId: 'tool_custom',
    toolSuccess: false,
  };
  const customFailure = {
    eventType: 'ERROR',
    eventCode: 'FAILED',
    payloadType: 'ERROR',
    toolCallId: 'tool_custom',
    success: false,
  };
  const customResultIds = domainResultToolCallIds([genericFailure, customFailure]);

  assertEqual(customResultIds.has('tool_custom'), true, 'custom failure correlation');
  assertEqual(
    shouldDisplayGenericToolResult(genericFailure, customResultIds),
    false,
    'custom failure display precedence',
  );
});

test('validation domain result owns display while Tool lifecycle remains successful', () => {
  const genericSuccess = {
    eventType: 'TOOL_CALL_FINISHED',
    toolCallId: 'tool_validation',
    toolSuccess: true,
  };
  const validationFailure = {
    eventType: 'VALIDATION_REPORT_CREATED',
    eventCode: 'VALIDATION_REPORT_CREATED',
    payloadType: 'VALIDATION_REPORT',
    toolCallId: 'tool_validation',
    success: true,
    content: {
      report: {
        status: 'FAILED',
      },
    },
  };
  const customResultIds = domainResultToolCallIds([genericSuccess, validationFailure]);

  assertEqual(customResultIds.has('tool_validation'), true, 'validation result correlation');
  assertEqual(
    shouldDisplayGenericToolResult(genericSuccess, customResultIds),
    true,
    'successful Tool lifecycle remains visible',
  );
  assertEqual(validationFailure.content.report.status, 'FAILED', 'validation domain status');
});
