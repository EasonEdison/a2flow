import { useState } from 'react';

import { toView } from './api/adapter';
import { Icon } from './components/Icon';
import { NodeCard } from './components/NodeCard';
import { WorkflowSidebar } from './components/WorkflowSidebar';
import { fixture, type FixtureState } from './dev/fixtures';
import { useProgress } from './hooks/useProgress';
import { useRuntime } from './hooks/useRuntime';
import { statusLabels, type InteractiveCard, type RunView } from './presentation';

const fixtureMode = new URLSearchParams(location.search).get('preview') === 'fixture';

export function App() {
  const [fixtureState, setFixtureState] = useState<FixtureState>('WAITING');
  const [fixtureActive, setFixtureActive] = useState(true);
  const [requirement, setRequirement] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  const runtime = useRuntime(!fixtureMode);
  const progress = useProgress(fixtureMode ? null : runtime.runId);

  let run: RunView | null = null;
  let viewError = '';
  try {
    run = fixtureMode
      ? fixtureActive
        ? fixture(fixtureState, requirement || undefined)
        : null
      : runtime.view
        ? toView(runtime.view, progress.records)
        : null;
  } catch {
    viewError = '此运行包含暂不支持的卡片或展示格式，操作已禁用。';
  }

  const activeBusy = busy || runtime.nonStopPending;
  const start = async () => {
    if (!requirement.trim()) {
      return;
    }
    setFormError('');
    if (fixtureMode) {
      setFixtureActive(true);
      setFixtureState('RUNNING');
      return;
    }

    const workflow = runtime.workflows[0];
    if (!workflow) {
      setFormError('预置 Workflow 暂不可用。');
      return;
    }

    setBusy(true);
    try {
      await runtime.start(workflow.definitionKey, { requirement: requirement.trim() });
    } catch {
      // Runtime retains an uncertain control id for later read-only observation.
    } finally {
      setBusy(false);
    }
  };

  const action = async (
    nodeId: string,
    card: InteractiveCard,
    value: string,
  ) => {
    if (fixtureMode) {
      setFixtureState('SUCCEEDED');
      return;
    }
    if (!card.operable || activeBusy) {
      return;
    }
    await runtime.action(nodeId, card.interactionId, card.actionName, {
      optionId: value,
      ...(card.confirmed ? { confirmed: true } : {}),
    });
  };

  const stop = async () => {
    if (!window.confirm('停止后无法继续本次运行，已完成的结果仍会保留。确认停止？')) {
      return;
    }
    if (fixtureMode) {
      setFixtureState('STOPPED');
      return;
    }
    try {
      await runtime.stop();
    } catch {
      // Stop has an independent control id and stays observable.
    }
  };

  const restart = async () => {
    if (!requirement.trim()) {
      setFormError('请填写本次重新开始的活动要求。');
      return;
    }
    if (!window.confirm('将从入口开始新的运行，不继承旧运行的结果。继续？')) {
      return;
    }
    if (fixtureMode) {
      setFixtureState('RUNNING');
      return;
    }
    try {
      await runtime.restart({ requirement: requirement.trim() });
    } catch {
      // Runtime retains an uncertain control id for later read-only observation.
    }
  };

  const newRun = () => {
    if (activeBusy) {
      return;
    }
    if (fixtureMode) {
      setFixtureActive(false);
    } else {
      runtime.select(null);
    }
  };

  return (
    <div className="app">
      {fixtureMode ? (
        <div className="fixture-banner">
          <strong>开发示例 · Fixture</strong>
          <span>所有内容均为模拟数据，未调用模型、数据库或业务服务。</span>
          <label>
            示例状态
            <select
              aria-label="示例状态"
              value={fixtureState}
              onChange={(event) => {
                setFixtureState(event.target.value as FixtureState);
                setFixtureActive(true);
              }}
            >
              <option value="RUNNING">执行中</option>
              <option value="WAITING">等待确认</option>
              <option value="SUCCEEDED">已完成</option>
              <option value="UNCONFIRMED">执行结果未确认</option>
              <option value="STOPPED">已停止</option>
            </select>
          </label>
        </div>
      ) : null}

      <div className="workspace">
        <nav className="navigation" aria-label="主导航">
          <a className="brand" href={fixtureMode ? '?preview=fixture' : '/'}>
            <span>A2</span>Flow
          </a>
          <span className="nav-item selected">
            <Icon name="workflow" />
            数字员工
          </span>
          <div className="history-section">
            <h2>
              <Icon name="history" size={17} />
              运行记录
            </h2>
            {fixtureMode ? (
              <button className="history-item" onClick={() => setFixtureActive(true)}>
                周末活动策划
                <small>开发示例</small>
              </button>
            ) : runtime.runs.length ? (
              runtime.runs.map((item) => (
                <button
                  key={item.runId}
                  className={'history-item ' + (runtime.runId === item.runId ? 'current' : '')}
                  disabled={activeBusy}
                  onClick={() => runtime.select(item.runId)}
                >
                  {item.title}
                  <small>
                    {item.lifecycle === 'SUCCEEDED'
                      ? '已完成'
                      : item.lifecycle === 'STOPPED'
                        ? '已停止'
                        : '查看运行记录'}
                  </small>
                </button>
              ))
            ) : (
              <p className="muted">暂无已保存的运行</p>
            )}
          </div>
          <div className="identity">
            {fixtureMode
              ? '开发预览'
              : runtime.session
                ? '已认证 · ' + runtime.session.environment
                : '等待可信身份'}
          </div>
        </nav>

        <main>
          <header className="page-header">
            <div>
              <h1>活动策划助手</h1>
              <p>从一个想法，到活动方案与宣传文案。</p>
            </div>
            {run ? (
              <div className="header-actions">
                <span className={'badge ' + run.lifecycle.toLowerCase()}>
                  {statusLabels[run.lifecycle]}
                </span>
                {['RUNNING', 'WAITING'].includes(run.lifecycle) ? (
                  <button
                    className="quiet danger"
                    disabled={runtime.stopPending}
                    onClick={() => void stop()}
                  >
                    <Icon name="stop" size={16} />
                    停止
                  </button>
                ) : null}
              </div>
            ) : null}
          </header>

          {runtime.error || viewError ? (
            <div className="error-banner" role="alert">
              <strong>{viewError || runtime.error}</strong>
              {runtime.pendingControls.length ? (
                <p>
                  已保存 {runtime.pendingControls.length} 个请求，正在查询处理结果。
                </p>
              ) : null}
            </div>
          ) : null}
          {progress.error ? (
            <p className="observation-warning" role="status">
              {progress.error}
            </p>
          ) : null}
          {runtime.loading ? (
            <div className="empty-state" role="status">
              正在连接可信会话…
            </div>
          ) : null}

          {run ? (
            <>
              <div className="requirement-message">
                {run.requirement ?? '本次 Workflow 的执行记录'}
                <small>{fixtureMode ? '模拟活动需求' : '运行 ' + run.id}</small>
              </div>
              <div className="nodes">
                {run.nodes.map((node, index) => (
                  <NodeCard
                    key={run.id + ':' + node.id}
                    node={node}
                    index={index}
                    busy={activeBusy}
                    onAction={(card, value) => action(node.id, card, value)}
                    onHistory={async () => {
                      if (!fixtureMode) {
                        await runtime.refresh();
                      }
                    }}
                  />
                ))}
              </div>
              {run.lifecycle === 'STOPPED' ? (
                <section className="restart-panel">
                  <h2>本次运行已停止</h2>
                  <p>历史记录可继续查看。重新开始需要填写新的活动要求。</p>
                  <label htmlFor="restart-input">本次活动要求</label>
                  <textarea
                    id="restart-input"
                    value={requirement}
                    maxLength={2000}
                    onChange={(event) => setRequirement(event.target.value)}
                  />
                  <button
                    className="primary"
                    disabled={activeBusy || !requirement.trim()}
                    onClick={() => void restart()}
                  >
                    重新开始
                  </button>
                </section>
              ) : null}
            </>
          ) : !runtime.loading ? (
            <section className="start-panel">
              <span className="start-symbol">
                <Icon name="workflow" size={32} />
              </span>
              <h2>准备一场值得期待的活动</h2>
              <p>描述人数、预算与想法。助手将准备候选方案，等你确认后，再生成宣传文案。</p>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void start();
                }}
              >
                <label htmlFor="requirement">活动要求</label>
                <textarea
                  id="requirement"
                  value={requirement}
                  onChange={(event) => setRequirement(event.target.value)}
                  maxLength={2000}
                  required
                  placeholder="例如：为 12 位同事策划周末活动，预算 2,400 元，希望轻松、有交流。"
                />
                <div className="form-footer">
                  <small>{requirement.length} / 2000</small>
                  <button
                    className="primary"
                    disabled={
                      activeBusy ||
                      !requirement.trim() ||
                      (!fixtureMode && !runtime.workflows.length)
                    }
                  >
                    开始 Workflow <Icon name="arrow" size={17} />
                  </button>
                </div>
              </form>
            </section>
          ) : null}

          {formError ? (
            <p role="alert" className="inline-error">
              {formError}
            </p>
          ) : null}
          <footer className="main-footer">
            生成的内容保留在本次运行中，不会发布到外部平台。
          </footer>
        </main>

        <WorkflowSidebar run={run} onNew={newRun} />
      </div>
    </div>
  );
}
