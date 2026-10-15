import { useState, type ReactNode } from 'react';

import { statusLabels, type InteractiveCard, type NodeView } from '../presentation';
import { ApplicationCard, DisplayApplicationCard } from './ApplicationCard';
import { Icon } from './Icon';
import { MarkdownContent } from './MarkdownContent';
import { nodeSummary } from '../nodeSummary';
import { WorkflowExecution } from './WorkflowExecution';
import './workflow-presentation.css';

export function NodeCard({
  node,
  index,
  busy,
  onAction,
  children,
  defaultResultOpen = false,
}: {
  node: NodeView;
  index: number;
  busy: boolean;
  onAction: (card: InteractiveCard, value: string) => Promise<void>;
  onHistory: () => Promise<void>;
  children?: ReactNode;
  defaultResultOpen?: boolean;
}) {
  const [resultChoice, setResultChoice] = useState<boolean | null>(null);
  const resultOpen = resultChoice ?? defaultResultOpen;
  const interactive = node.card?.kind === 'INTERACTIVE' ? node.card : undefined;
  const waitingInteractive =
    interactive && node.status === 'WAITING' ? interactive : undefined;
  const completedInteractive = interactive === waitingInteractive ? undefined : interactive;
  const display = node.card?.kind === 'DISPLAY_ONLY' ? node.card : undefined;
  const hasResult = Boolean(node.output) || Boolean(display) || Boolean(completedInteractive);


  return (
    <article className={'node-card state-' + node.status.toLowerCase()} id={'node-' + node.id}>
      <header className="node-header">
        <span className="node-number">
          {node.status === 'SUCCEEDED' ? <Icon name="check" /> : index + 1}
        </span>
        <div className="node-title">
          <h2>{node.title}</h2>
          <p>{nodeSummary(node)}</p>
        </div>
        <span className={'badge ' + node.status.toLowerCase()}>
          {statusLabels[node.status]}
        </span>
      </header>

      {children ?? <WorkflowExecution node={node} />}
      {node.incomplete ? <p className="observation-warning">过程记录不完整，运行状态请以步骤状态为准。</p> : null}

      {waitingInteractive ? (
        <ApplicationCard
          key={waitingInteractive.id}
          card={waitingInteractive}
          busy={busy}
          onSubmit={(value) => onAction(waitingInteractive, value)}
        />
      ) : null}

      {node.abilityResults?.map((result, index) => <section className="workflow-assistant-note" key={`${result.abilityKey}-${index}`}>
        <h3>业务能力结果</h3>
        <p><strong>{result.status === 'SUCCEEDED' ? '调用成功' : result.status === 'FAILED' ? '调用失败' : '调用结果未确认'}</strong></p>
        {result.status !== 'SUCCEEDED' ? <p className="observation-warning">{result.status === 'UNKNOWN' ? '调用结果尚未确认，不会自动重试。' : '业务调用未成功，未自动重试。'}</p> : null}
        <details className="workflow-debug"><summary>查看能力返回结果</summary>
          <p>业务能力：{result.abilityKey}</p>
          {result.errorCode && /^[A-Z][A-Z0-9_]{0,159}$/.test(result.errorCode) ? <p>错误标识：<code>{result.errorCode}</code></p> : null}
          <pre>{JSON.stringify(result.result, null, 2)}</pre>
        </details>
      </section>)}

      {hasResult ? (
        <section className="workflow-assistant-note">
          <button
            className="result-disclosure"
            aria-expanded={resultOpen}
            aria-controls={'result-' + node.id}
            onClick={() => setResultChoice(!resultOpen)}
          >
            <h3>步骤结果</h3>
            <Icon name="chevron" />
          </button>
          {resultOpen ? (
            <div id={'result-' + node.id} className="result-body">
              <p className="muted">以下为助手整理的说明，操作结果请以卡片为准。</p>
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
      {node.actionResults?.length ? <details className="workflow-debug"><summary>调试详情 · 已保存的操作结果</summary><pre>{JSON.stringify(node.actionResults, null, 2)}</pre></details> : null}
    </article>
  );
}
