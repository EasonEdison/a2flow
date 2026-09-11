import { ApiError } from '../api/client';

export type ControlKind = 'start' | 'action' | 'stop' | 'restart';
export type PendingControl = {
  id: string;
  kind: ControlKind;
  runId?: string;
};

const definitivelyRejected = new Set([
  'RESET_REQUIRED',
  'RUN_STOPPED',
  'TRUSTED_CONTEXT_REQUIRED',
  'CAPACITY_EXHAUSTED',
  'CONTROL_NOT_FOUND',
]);

/**
 * A 409 is not enough to discard the id: Runtime uses it for
 * RUN_OPERATION_PENDING_OR_UNCONFIRMED, which must remain observable.
 */
export function isDefinitelyRejected(error: unknown): boolean {
  return error instanceof ApiError && definitivelyRejected.has(error.code);
}

export function canDispatch(
  controls: PendingControl[],
  locks: ReadonlySet<ControlKind>,
  kind: ControlKind,
): boolean {
  if (locks.has(kind) || controls.some((control) => control.kind === kind)) {
    return false;
  }
  return kind === 'stop' || !controls.some((control) => control.kind !== 'stop');
}

export function stoppedRunAcceptsUpdate(
  stoppedRunIds: ReadonlySet<string>,
  runId: string,
): boolean {
  return !stoppedRunIds.has(runId);
}

export function beginRead(generations: Map<string, number>, runId: string): number {
  const next = (generations.get(runId) ?? 0) + 1;
  generations.set(runId, next);
  return next;
}

export function isCurrentRead(
  generations: ReadonlyMap<string, number>,
  runId: string,
  generation: number,
): boolean {
  return generations.get(runId) === generation;
}
