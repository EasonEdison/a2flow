import { useState, type ReactNode } from 'react';

import { statusLabels, terminal, type InteractiveCard, type NodeView } from '../presentation';
import { ApplicationCard, DisplayApplicationCard } from './ApplicationCard';
import { Icon } from './Icon';
import { MarkdownContent } from './MarkdownContent';

export function NodeCard({
  node,
  index,
  busy,
  onAction,
  onHistory,
  children,
}: {
  node: NodeView;
  index: number;
  busy: boolean;
  onAction: (card: InteractiveCard, value: string) => Promise<void>;
  onHistory: () => Promise<void>;
  children?: ReactNode;
}) {
  const [disclosure, setDisclosure] = useState<{ status: string; open: boolean } | null>(
    null,
  );
  const [resultOpen, setResultOpen] = useState(true);
  const open =
    disclosure?.status === node.status
      ? disclosure.open
      : !terminal(node.status) && node.status !== 'PENDING';
  const interactive = node.card?.kind === 'INTERACTIVE' ? node.card : undefined;
  const waitingInteractive =
    interactive && node.status === 'WAITING' ? interactive : undefined;
  const completedInteractive = interactive === waitingInteractive ? undefined : interactive;
  const display = node.card?.kind === 'DISPLAY_ONLY' ? node.card : undefined;
  const hasResult = Boolean(node.output) || Boolean(display) || Boolean(completedInteractive);

  const toggle = () => {
    setDisclosure({ status: node.status, open: !open });
    if (!open) {
      void onHistory();
    }
  };

  return (
    <article className={'node-card state-' + node.status.toLowerCase()} id={'node-' + node.id}>
      <header className="node-header">
        <span className="node-number">
          {node.status === 'SUCCEEDED' ? <Icon name="check" /> : index + 1}
        </span>
        <div className="node-title">
          <h2>{node.title}</h2>
          {node.summary ? <p>{node.summary}</p> : null}
        </div>
        <span className={'badge ' + node.status.toLowerCase()}>
          {statusLabels[node.status]}
        </span>
      </header>

      <div className="process">
        <button
          className="disclosure"
          aria-expanded={open}
          aria-controls={'details-' + node.id}
          onClick={toggle}
        >
          <Icon name="chevron" />
          <span>{terminal(node.status) ? '查看历史过程' : '思考与执行过程'}</span>
          <small>
            {terminal(node.status)
              ? '只读，不重新执行'
              : node.status === 'WAITING'
                ? '等待确认后继续'
                : ''}
          </small>
        </button>
        {open ? (
          <div id={'details-' + node.id} className="process-body">
            {node.records.length ? (
              node.records.map((record) => (
                <div key={record.id} className={'record ' + record.kind}>
                  {record.kind === 'reasoning' ? (
                    <span className="record-label">模型思考 · 与已验证结果分别展示</span>
                  ) : null}
                  <p>{record.text}</p>
                </div>
              ))
            ) : (
              <p className="muted">
                {node.status === 'PENDING' ? '节点尚未开始。' : '等待已保存的执行记录。'}
              </p>
            )}
            {node.incomplete ? (
              <p className="observation-warning">过程记录不完整，运行状态请以节点状态为准。</p>
            ) : null}
          </div>
        ) : null}
      </div>

      {waitingInteractive ? (
        <ApplicationCard
          key={waitingInteractive.id}
          card={waitingInteractive}
          busy={busy}
          onSubmit={(value) => onAction(waitingInteractive, value)}
        />
      ) : null}
      {children}

      {hasResult ? (
        <section className="result">
          <button
            className="result-disclosure"
            aria-expanded={resultOpen}
            aria-controls={'result-' + node.id}
            onClick={() => setResultOpen((value) => !value)}
          >
            <h3>节点结果</h3>
            <Icon name="chevron" />
          </button>
          {resultOpen ? (
            <div id={'result-' + node.id} className="result-body">
              {completedInteractive ? (
                <ApplicationCard
                  key={completedInteractive.id}
                  card={completedInteractive}
                  busy={busy}
                  onSubmit={(value) => onAction(completedInteractive, value)}
                />
              ) : null}
              {display ? <DisplayApplicationCard title={display.title} fields={display.fields} /> : null}
              {node.output ? <MarkdownContent markdown={node.output} /> : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </article>
  );
}
