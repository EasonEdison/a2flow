import type { NodeStatus, NodeView } from './presentation';

const summaries: Record<NodeStatus, string> = {
  PENDING: '等待前置步骤完成',
  RUNNING: '正在执行本步骤',
  WAITING: '等待你完成卡片操作',
  SUCCEEDED: '本步骤已完成，结果见下方',
  FAILED: '本步骤执行失败',
  SKIPPED: '本步骤已跳过',
  STOPPED: '本步骤已停止',
  UNKNOWN: '执行状态待确认',
};

const nodeEndEvents = new Set(['NODE_RETURNED', 'NODE_INTERRUPTED', 'NODE_UNCONFIRMED']);

function durationLabel(milliseconds: number): string {
  const seconds = Math.round(milliseconds / 1000);
  if (seconds === 0) return '不足 1 秒';
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return seconds % 60 ? `${minutes} 分 ${seconds % 60} 秒` : `${minutes} 分钟`;
}

/** Describe only state and observed events; model output remains in the result panel. */
export function nodeSummary(node: NodeView): string {
  const parts = [summaries[node.status]];
  const toolCalls = new Set<string>();
  const nodeStarts = new Map<string, number>();
  let durationMs = 0;
  let completedIntervals = 0;

  for (const record of node.records) {
    if (record.eventKind === 'TOOL_STARTED') {
      toolCalls.add(record.operationId ?? record.id);
    }
    if (!record.operationId || !record.observedAt) continue;
    const observedAt = Date.parse(record.observedAt);
    if (!Number.isFinite(observedAt)) continue;
    if (record.eventKind === 'NODE_STARTED') {
      nodeStarts.set(record.operationId, observedAt);
    } else if (record.eventKind && nodeEndEvents.has(record.eventKind)) {
      const startedAt = nodeStarts.get(record.operationId);
      if (startedAt !== undefined && observedAt >= startedAt) {
        durationMs += observedAt - startedAt;
        completedIntervals++;
      }
      nodeStarts.delete(record.operationId);
    }
  }

  if (toolCalls.size) parts.push(`已记录 ${toolCalls.size} 次工具调用`);
  if (completedIntervals) parts.push(`已记录执行耗时 ${durationLabel(durationMs)}`);
  return parts.join(' · ');
}
