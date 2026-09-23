export interface ToolResultProjectionEvent {
  eventType: string;
  eventCode?: string;
  payloadType?: string;
  toolCallId?: string;
  payload?: Record<string, unknown>;
  content?: Record<string, unknown>;
  toolSuccess?: boolean;
  success?: boolean;
}

const GENERIC_TOOL_RESULT_EVENTS = new Set(['TOOL_CALL_FINISHED', 'TOOL_RESULT']);
const DOMAIN_RESULT_EVENT_TYPES = new Set([
  'ARTIFACT_CREATED',
  'BUSINESS_INTERACTION_CREATED',
  'OBSERVATION_CREATED',
  'AG_UI_EVENT',
  'VALIDATION_REPORT_CREATED',
  'ERROR',
]);
const DOMAIN_RESULT_EVENT_CODES = new Set([
  'PATCH_PROPOSED',
  'PATCH_APPLIED',
  'PATCH_DISCARDED',
  'PATCH_CONFLICT',
  'A2UI_MESSAGE',
  'AUTHORING_OBSERVATION',
  'AUTHORING_DRAFT_CHANGE',
  'CAPABILITY_DRAFT_VALIDATED',
  'AG_UI_EVENT',
  'VALIDATION_REPORT_CREATED',
  'FAILED',
]);

function recordOf(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function textOf(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

export function toolResultCallId(event: ToolResultProjectionEvent): string {
  const payloadContent = recordOf(event.payload?.content);
  return textOf(
    event.toolCallId ||
      event.payload?.toolCallId ||
      event.content?.toolCallId ||
      payloadContent?.toolCallId,
  );
}

export function isDomainToolResult(event: ToolResultProjectionEvent): boolean {
  if (!toolResultCallId(event) || GENERIC_TOOL_RESULT_EVENTS.has(event.eventType)) return false;
  const eventCode = textOf(event.eventCode || event.payload?.eventCode);
  return DOMAIN_RESULT_EVENT_TYPES.has(event.eventType) || DOMAIN_RESULT_EVENT_CODES.has(eventCode);
}

export function domainResultToolCallIds(events: readonly ToolResultProjectionEvent[]): Set<string> {
  return new Set(events.filter(isDomainToolResult).map(toolResultCallId).filter(Boolean));
}

export function shouldDisplayGenericToolResult(
  event: ToolResultProjectionEvent,
  domainResultIds: ReadonlySet<string>,
): boolean {
  if (!GENERIC_TOOL_RESULT_EVENTS.has(event.eventType)) return true;
  const payloadContent = recordOf(event.payload?.content);
  const toolSuccess =
    typeof event.toolSuccess === 'boolean'
      ? event.toolSuccess
      : typeof event.payload?.toolSuccess === 'boolean'
      ? event.payload.toolSuccess
      : typeof event.payload?.success === 'boolean'
      ? event.payload.success
      : typeof event.content?.toolSuccess === 'boolean'
      ? event.content.toolSuccess
      : typeof payloadContent?.toolSuccess === 'boolean'
      ? payloadContent.toolSuccess
      : event.success;
  if (toolSuccess !== false) return true;
  const toolCallId = toolResultCallId(event);
  return !toolCallId || !domainResultIds.has(toolCallId);
}
