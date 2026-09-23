export type ChangeReviewStatus = 'PENDING' | 'APPLIED' | 'DISCARDED' | 'CONFLICTED';

export interface PatchProjectionEvent {
  eventType: string;
  eventCode?: string;
  payloadType?: string;
  patchId?: string;

  content?: Record<string, unknown>;
  payload?: Record<string, unknown>;

  success?: boolean;
  toolSuccess?: boolean;
}

const PATCH_PROPOSED = 'PATCH_PROPOSED';
const PATCH_APPLIED = 'PATCH_APPLIED';
const PATCH_DISCARDED = 'PATCH_DISCARDED';
const PATCH_CONFLICT = 'PATCH_CONFLICT';
const PATCH_EVENT_CODES = new Set([PATCH_PROPOSED, PATCH_APPLIED, PATCH_DISCARDED, PATCH_CONFLICT]);

function recordOf(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function textOf(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function patchPayload(event: PatchProjectionEvent): Record<string, unknown> | undefined {
  return event.payload;
}

function patchContent(event: PatchProjectionEvent): Record<string, unknown> {
  const payloadContent = recordOf(patchPayload(event)?.content);
  return event.content || payloadContent || {};
}



export function patchEventCode(event: PatchProjectionEvent): string {
  const eventCode = textOf(event.eventCode || patchPayload(event)?.eventCode);
  if (PATCH_EVENT_CODES.has(eventCode)) return eventCode;
  return PATCH_EVENT_CODES.has(event.eventType) ? event.eventType : '';
}

export function patchStableId(event: PatchProjectionEvent): string {
  return textOf(event.patchId || patchPayload(event)?.patchId);
}

export function patchChangedFiles(event: PatchProjectionEvent): unknown[] {
  const changedFiles = patchContent(event).changedFiles;
  return Array.isArray(changedFiles) ? changedFiles : [];
}

export function isPatchDomainEvent(event: PatchProjectionEvent): boolean {
  return Boolean(patchEventCode(event));
}

export function isPatchSettledEvent(event: PatchProjectionEvent): boolean {
  return [PATCH_APPLIED, PATCH_DISCARDED, PATCH_CONFLICT].includes(patchEventCode(event));
}

export function isActionablePatchProposal(event: PatchProjectionEvent): boolean {
  if (patchEventCode(event) !== PATCH_PROPOSED) return false;
  if (!patchStableId(event) || patchChangedFiles(event).length === 0) return false;
  return true;
}

export function isPatchReviewEvent(event: PatchProjectionEvent): boolean {
  const eventCode = patchEventCode(event);
  if (eventCode === PATCH_PROPOSED) return isActionablePatchProposal(event);
  return isPatchSettledEvent(event) && Boolean(patchStableId(event));
}

export function patchReviewStatus(event: PatchProjectionEvent): ChangeReviewStatus | undefined {
  const eventCode = patchEventCode(event);
  if (eventCode === PATCH_APPLIED) return 'APPLIED';
  if (eventCode === PATCH_DISCARDED) return 'DISCARDED';
  if (eventCode === PATCH_CONFLICT) return 'CONFLICTED';
  return isActionablePatchProposal(event) ? 'PENDING' : undefined;
}
