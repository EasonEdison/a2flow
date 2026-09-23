import type { AssetReleaseOperationResult } from '../types';

export type ReleaseOperationFeedbackKind = 'SUCCESS' | 'PENDING' | 'FAILURE';

export interface ReleaseOperationFeedback {
  kind: ReleaseOperationFeedbackKind;
  status: string;
  message: string;
}

export interface ReleaseOperationExecution<TOverview> {
  feedback: ReleaseOperationFeedback;
  overview?: TOverview;
  refreshError?: unknown;
}

const successfulStatuses = new Set(['SUCCEEDED', 'PUBLISHED', 'ACTIVE', 'USED']);

const pendingStatuses = new Set([
  'PUBLISHING',
  'PLATFORM_PENDING',
  'PREPARING',
  'PENDING',
  'PROCESSING',
  'ACCEPTED',
  'RUNNING',
  'SUBMITTED',
]);

const normalizeStatus = (status?: string): string => status?.trim()?.toUpperCase?.() || 'UNKNOWN';

export const isPendingReleaseOperationStatus = (status?: string): boolean =>
  pendingStatuses.has(normalizeStatus(status));

export const classifyReleaseOperation = (
  result: AssetReleaseOperationResult,
): ReleaseOperationFeedback => {
  const status = normalizeStatus(result.status);
  const kind: ReleaseOperationFeedbackKind = successfulStatuses.has(status)
    ? 'SUCCESS'
    : pendingStatuses.has(status)
    ? 'PENDING'
    : 'FAILURE';
  const fallbackMessage =
    kind === 'SUCCESS'
      ? '操作成功'
      : kind === 'PENDING'
      ? '操作已提交，正在处理'
      : `操作失败，当前状态：${status}`;
  return {
    kind,
    status,
    message: result.message?.trim() || fallbackMessage,
  };
};

export const executeReleaseOperation = async <TOverview>(
  operation: () => Promise<AssetReleaseOperationResult>,
  refreshOverview: () => Promise<TOverview>,
): Promise<ReleaseOperationExecution<TOverview>> => {
  const feedback = classifyReleaseOperation(await operation());
  try {
    return { feedback, overview: await refreshOverview() };
  } catch (refreshError) {
    return { feedback, refreshError };
  }
};
