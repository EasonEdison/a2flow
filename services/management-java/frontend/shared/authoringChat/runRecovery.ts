const TERMINAL_RUN_STATES = new Set(['COMPLETED', 'FAILED', 'CANCELLED']);
const DEFAULT_RECOVERY_POLL_INTERVAL_MS = 500;

export interface RecoverableRunStatus {
  status: string;
}

export type RunRecoveryOutcome<TStatus extends RecoverableRunStatus> =
  | { kind: 'terminal'; status: TStatus }
  | { kind: 'cancelled'; status?: undefined };

export interface RunRecoveryOptions<TStatus extends RecoverableRunStatus> {
  signal?: AbortSignal;
  queryStatus: () => Promise<TStatus>;
  waitForNextPoll?: () => Promise<void>;
  onStatus?: (status: TStatus) => void;
}

const waitForRecoveryPoll = (): Promise<void> =>
  new Promise((resolve) => window.setTimeout(resolve, DEFAULT_RECOVERY_POLL_INTERVAL_MS));

/**
 * SSE 在业务终态前断开时，持续读取后端持久化运行状态；浏览器不根据耗时自行推断完成。
 */
export async function recoverCodingRunAfterTransportEof<TStatus extends RecoverableRunStatus>({
  signal,
  queryStatus,
  waitForNextPoll = waitForRecoveryPoll,
  onStatus,
}: RunRecoveryOptions<TStatus>): Promise<RunRecoveryOutcome<TStatus>> {
  while (!signal?.aborted) {
    const status = await queryStatus();
    if (signal?.aborted) return { kind: 'cancelled' };
    onStatus?.(status);
    if (TERMINAL_RUN_STATES.has(status.status)) {
      return { kind: 'terminal', status };
    }
    await waitForNextPoll();
  }
  return { kind: 'cancelled' };
}
