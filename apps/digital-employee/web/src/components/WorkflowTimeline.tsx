import { Fragment, useMemo, type ReactNode } from 'react';
import type { NodeView, RecordLine } from '../presentation';
import type { WorkflowCard } from '../productApi';
import { WorkflowExecution } from './WorkflowExecution';

type TimelineBlock = { id: string; records: RecordLine[]; card?: WorkflowCard };

/** Match persisted call identities, never guess ordering from application names. */
export function workflowBlocks(node: NodeView, entries: WorkflowCard[]): TimelineBlock[] {
  const byCall = new Map(entries.filter(entry => entry.toolCallId).map(entry => [entry.toolCallId!, entry]));
  const operationCalls = new Map<string, string>();
  node.records.forEach(record => {
    if (record.operationId && typeof record.payload?.toolCallId === 'string') {
      operationCalls.set(record.operationId, record.payload.toolCallId);
    }
  });
  const placed = new Set<string>();
  const blocks: TimelineBlock[] = [];
  let records: RecordLine[] = [];
  for (const record of node.records) {
    records.push(record);
    const call = record.operationId ? operationCalls.get(record.operationId) : undefined;
    const card = call ? byCall.get(call) : undefined;
    if (!card || placed.has(card.card.cardId) || !['TOOL_INTERRUPTED', 'TOOL_RETURNED'].includes(record.eventKind ?? '')) continue;
    placed.add(card.card.cardId);
    blocks.push({ id: card.card.cardId, records, card });
    records = [];
  }
  if (records.length) blocks.push({ id: 'remaining-process', records });
  for (const card of entries) {
    if (!placed.has(card.card.cardId)) blocks.push({ id: card.card.cardId, records: [], card });
  }
  return blocks;
}

export function WorkflowTimeline({ node, entries, renderCard }: {
  node: NodeView;
  entries: WorkflowCard[];
  renderCard: (entry: WorkflowCard) => ReactNode;
}) {
  const blocks = useMemo(() => workflowBlocks(node, entries), [node, entries]);
  return <div className="workflow-timeline">
    {node.historyStatus === 'loading' ? <p className="muted" role="status">正在加载执行过程…</p> : null}
    {blocks.map(block => <Fragment key={block.id}>
      {block.records.length ? <WorkflowExecution node={{ ...node, records: block.records }} /> : null}
      {block.card ? <section className="workflow-business-surface">{renderCard(block.card)}</section> : null}
    </Fragment>)}
    {!blocks.length && node.historyStatus !== 'loading' ? <p className="muted">{
      node.historyStatus === 'incomplete' ? '执行记录未完整加载，暂不展示调用总数。' :
      node.status === 'PENDING' ? '步骤尚未开始。'
        : ['RUNNING', 'WAITING'].includes(node.status) ? '正在读取执行记录…'
          : '暂无已保存的执行记录。'
    }</p> : null}
  </div>;
}
