import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { NodeCard } from './components/NodeCard';
import { WorkflowTimeline } from './components/WorkflowTimeline';
import { WorkflowApplications } from './components/WorkflowApplications';
import { productProgress } from './api/client';
import { useProgress } from './hooks/useProgress';
import { MemorySettingsPage } from './components/MemorySettingsPage';
import { AssistantThread } from './components/AssistantThread';
import './chat.css';
import { FixturePreview } from './FixturePreview';
import { applyChatStreamEvent, preserveUpdatedCards } from './assistantChat';
import { apiErrorMessage, messageFromContent, productApi, type ChatCard, type Conversation, type Message, type Notification, type RunItem, type Schedule, type Session, type Workflow } from './productApi';
import type { WorkflowCard } from './productApi';
import type { InteractiveCard, RunView } from './presentation';

const fixtureMode = new URLSearchParams(location.search).get('preview') === 'fixture';
type Page = 'chat' | 'workflows' | 'schedules' | 'notifications' | 'memory';
const runLabels: Record<string, string> = { RUNNING: '运行中', WAITING: '等待确认', SUCCEEDED: '已完成', STOPPED: '已停止', FAILED: '失败', SUBMITTED: '已提交' };
const notificationLabels: Record<string, string> = { WAITING: '等待确认', COMPLETED: '完成', STOPPED: '停止', FAILED: '失败', SYSTEM: '系统' };

function Login({ onSession }: { onSession: (session: Session) => void }) {
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  return <main className="auth-page">
    <section className="auth-brand"><div className="brand-mark">A2</div><h1>A2Flow</h1><p>让数字员工接手重复工作，把精力留给重要决策。</p></section>
    <section className="auth-card">
      <h2>{register ? '创建 A2Flow 账号' : '登录 A2Flow'}</h2>
      <p>{register ? '注册后立即进入数字员工工作台' : '欢迎回来，请使用企业账号登录'}</p>
      <form onSubmit={async (event) => { event.preventDefault(); setError(''); try { onSession(await (register ? productApi.register(username, password) : productApi.login(username, password))); } catch (error) { setError(apiErrorMessage(error, '操作失败，请检查账号信息')); } }}>
        <label htmlFor="username">用户名</label><input id="username" value={username} onChange={(event) => setUsername(event.target.value)} required autoComplete="username" />
        <label htmlFor="password">密码</label><input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required autoComplete={register ? 'new-password' : 'current-password'} />
        <button className="primary full" type="submit">{register ? '注册并登录' : '登录'}</button>
      </form>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      <button className="auth-switch" onClick={() => setRegister((value) => !value)}>{register ? '已有账号，去登录' : '注册账号'}</button>
    </section>
  </main>;
}

function Shell({ session, page, unread, onPage, onLogout, children }: { session: Session; page: Page; unread: number; onPage: (page: Page) => void; onLogout: () => void; children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = (next: Page) => { onPage(next); setMobileOpen(false); };
  return <div className="product-shell">
    <header className="topbar"><button className="mobile-menu" aria-label="打开导航" onClick={() => setMobileOpen((value) => !value)}>☰</button><button className="top-brand" onClick={() => navigate('chat')}><strong>A2</strong>Flow</button><div className="top-user"><button className="notification-button" aria-label={`通知中心，${unread} 条未读`} onClick={() => navigate('notifications')}>铃铛{unread ? <span>{unread}</span> : null}</button><b>{session.username}</b><em>{session.role}</em><button className="text-button" aria-label="退出登录" onClick={onLogout}>退出</button></div></header>
    <aside className={`product-nav ${mobileOpen ? 'open' : ''}`} aria-label="主导航">
      <button className={page === 'chat' ? 'active' : ''} onClick={() => navigate('chat')}>对话工作台</button>
      <button className={page === 'workflows' ? 'active' : ''} onClick={() => navigate('workflows')}>工作流中心</button>
      <button className={page === 'schedules' ? 'active' : ''} onClick={() => navigate('schedules')}>定时管理</button>
      <button className={page === 'notifications' ? 'active' : ''} onClick={() => navigate('notifications')}>通知中心{unread ? <span className="nav-count">{unread}</span> : null}</button>
      <button className={page === 'memory' ? 'active' : ''} onClick={() => navigate('memory')}>设置 · 个人记忆</button>
    </aside>
    <section className="product-content">{children}</section>
  </div>;
}

function RunDetail({ runId, onBack }: { runId: string; onBack?: () => void }) {
  const [run, setRun] = useState<RunView | null>(null);
  const [busy, setBusy] = useState(false);
  const [cards, setCards] = useState<WorkflowCard[]>([]);
  const [error, setError] = useState('');
  const currentRunId = useRef(runId);
  const cardReadEpoch = useRef(0);
  currentRunId.current = runId;
  const refresh = useCallback(async () => {
    const epoch = ++cardReadEpoch.current;
    try {
      const [view, entries] = await Promise.all([productApi.run(runId), productApi.runCards(runId)]);
      if (currentRunId.current !== runId || cardReadEpoch.current !== epoch) return;
      setRun(view); setCards(entries); setError('');
    } catch { if (currentRunId.current === runId) setError('运行或卡片状态同步失败，请刷新页面重试。'); }
  }, [runId]);
  useEffect(() => { setRun(null); setCards([]); void refresh(); }, [refresh]);
  const active = run ? ['RUNNING', 'WAITING', 'PENDING'].includes(run.lifecycle) : false;
  const progress = useProgress(run?.nodes.length ? runId : null, productProgress, active);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let loading = false;
    const timer = window.setInterval(() => {
      if (loading) return;
      loading = true;
      const epoch = cardReadEpoch.current;
      void productApi.runCards(runId, controller.signal).then(entries => {
        if (!controller.signal.aborted && epoch === cardReadEpoch.current) { setCards(entries); setError(''); }
      }).catch(() => {
        if (!controller.signal.aborted) setError('卡片状态同步失败，正在等待重新读取。');
      }).finally(() => { loading = false; });
    }, 2000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [runId, active]);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let closed = false;
    const apply = (view: RunView) => { if (!closed) setRun(view); };
    void (async () => {
      while (!closed) {
        try {
          await productApi.subscribeSurface(runId, apply, controller.signal);
          if (closed) return;
          const current = await productApi.run(runId);
          apply(current);
          if (!['RUNNING', 'WAITING', 'PENDING'].includes(current.lifecycle)) return;
        } catch {
          if (closed) return;
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      }
    })();
    return () => { closed = true; controller.abort(); };
  }, [runId, active]);
  if (!run) return <div className="loading">{error ? <p role="alert">{error}</p> : '正在加载运行…'}</div>;
  return <section className="run-detail">
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    {progress.error ? <p className="observation-warning" role="status">{progress.error}</p> : null}
    <div className="section-heading">{onBack ? <button className="secondary" onClick={onBack}>返回</button> : null}<div><h2>{run.title}</h2><p>{run.requirement}</p></div><span className={`status ${run.lifecycle.toLowerCase()}`}>{runLabels[run.lifecycle] ?? run.lifecycle}</span>{['RUNNING', 'WAITING'].includes(run.lifecycle) ? <button className="quiet danger" onClick={async () => { if (!confirm('停止后无法恢复，确认停止？')) return; await productApi.stopRun(run.id); await refresh(); }}>停止运行</button> : null}</div>
    <div className="nodes">{run.nodes.map((node, index) => {
      const entries = cards.filter(entry => entry.nodeId === node.id);
      const observedNode = { ...node, records: progress.records[node.id] ?? [], historyStatus: progress.historyStatus, ...(entries.length ? { card: undefined } : {}) };
      return <NodeCard key={node.id} node={observedNode} index={index} busy={busy} onHistory={refresh} onAction={async (card: InteractiveCard, value: string) => { setBusy(true); try { await productApi.runAction(run.id, node.id, card.interactionId, card.actionName, value, card.confirmed, (view) => setRun(view)); await refresh(); } finally { setBusy(false); } }}>
        <WorkflowTimeline node={observedNode} entries={entries} renderCard={entry => <WorkflowApplications title={node.title} runId={run.id} entries={[entry]} disabled={!['RUNNING', 'WAITING'].includes(run.lifecycle) || !['RUNNING', 'WAITING'].includes(node.status) || busy} onUpdate={card => { cardReadEpoch.current++; setCards(current => current.map(entry => entry.card.cardId === card.cardId ? { ...entry, card } : entry)); }} onSettled={refresh} />} />
      </NodeCard>;
    })}</div>
  </section>;
}

function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState('');
  const [error, setError] = useState('');
  const initial = useRef<Promise<Conversation[]> | null>(null);
  useEffect(() => {
    let active = true;
    initial.current ??= productApi.conversations().then(async ({ items }) => items.length ? items : [await productApi.createConversation()]);
    void initial.current.then(items => { if (active) { setConversations(items); setConversationId(items[0].id); } }).catch(() => { if (active) setError('会话读取失败，请刷新页面'); });
    return () => { active = false; };
  }, []);
  return <div className="chat-layout">
    <aside className="conversation-list"><div className="panel-heading"><h2>会话</h2><button aria-label="新建会话" onClick={async () => {
      try { const item = await productApi.createConversation(); setConversations(items => [item, ...items]); setConversationId(item.id); }
      catch { setError('新建会话失败'); }
    }}>＋</button></div>{error ? <p role="alert">{error}</p> : null}{conversations.map(item => <button key={item.id} className={item.id === conversationId ? 'selected' : ''} onClick={() => setConversationId(item.id)}>{item.title}<small>{new Date(item.updatedAt).toLocaleDateString()}</small></button>)}</aside>
    {conversationId ? <ChatConversation key={conversationId} conversationId={conversationId} /> : null}
  </div>;
}

function ChatConversation({ conversationId }: { conversationId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [unassignedCards, setUnassignedCards] = useState<ChatCard[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const sending = useRef(false);
  const epoch = useRef(0);
  const operationGeneration = useRef(0);
  const actionUpdatedCards = useRef(new Map<string, ChatCard>());
  const activeCardActions = useRef(new Set<string>());
  const [activeCardActionCount, setActiveCardActionCount] = useState(0);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const [runId, setRunId] = useState('');
  const load = useCallback(async () => {
    if (sending.current || activeCardActions.current.size) return;
    const current = ++epoch.current;
    const operation = operationGeneration.current;
    try {
      const result = await productApi.messages(conversationId);
      if (current === epoch.current && operation === operationGeneration.current
        && !activeCardActions.current.size) {
        setMessages(result.items);
        setUnassignedCards(result.unassignedCards);
        setLoaded(true);
        setHistoryError('');
      }
    } catch { if (current === epoch.current) { setLoaded(false); setHistoryError('历史读取失败，请刷新页面查看已保存状态；不要重复发送原消息。'); } }
  }, [conversationId]);
  useEffect(() => { void load(); }, [historyRefreshKey, load]);
  useEffect(() => () => { epoch.current++; controller.current?.abort(); }, []);
  const pending = messages.some(message => message.delivery === 'running' || message.delivery === 'unconfirmed');
  const cardNeedsRefresh = messages.some(message => [
    ...(message.parts ?? []).flatMap(part => part.type === 'application' && part.card ? [part.card] : []),
    ...(message.legacyCards ?? []),
  ].some(card => card.status === 'EXECUTING' || card.status === 'WAITING_ACTION'))
    || unassignedCards.some(card => card.status === 'EXECUTING' || card.status === 'WAITING_ACTION');
  useEffect(() => {
    if (busy || activeCardActionCount || (!pending && !cardNeedsRefresh)) return;
    const timer = setInterval(() => { void load(); }, 5000);
    return () => clearInterval(timer);
  }, [activeCardActionCount, busy, cardNeedsRefresh, pending, load]);
  const updateCard = useCallback((updated: ChatCard) => {
    operationGeneration.current++;
    epoch.current++;
    actionUpdatedCards.current.set(updated.cardId, updated);
    const replace = (card: ChatCard) => card.cardId === updated.cardId ? updated : card;
    setMessages(items => items.map(message => ({
      ...message,
      ...(message.parts ? {
        parts: message.parts.map(part => part.type === 'application' && part.cardId === updated.cardId
          ? { ...part, card: updated }
          : part),
      } : {}),
      ...(message.legacyCards ? { legacyCards: message.legacyCards.map(replace) } : {}),
    })));
    setUnassignedCards(cards => cards.map(replace));
  }, []);
  const setCardActionState = useCallback((cardId: string, active: boolean) => {
    const actions = activeCardActions.current;
    const changed = active ? !actions.has(cardId) : actions.has(cardId);
    if (!changed) return;
    if (active) actions.add(cardId); else actions.delete(cardId);
    operationGeneration.current++;
    epoch.current++;
    setActiveCardActionCount(actions.size);
    if (!active) setHistoryRefreshKey(value => value + 1);
  }, []);
  const send = useCallback(async (rawText: string) => {
    const text = rawText.trim();
    if (!text || sending.current || pending || !loaded) return;
    sending.current = true;
    epoch.current++; // In-flight history reads cannot overwrite live deltas.
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError('');
    try {
      await productApi.sendMessage(conversationId, text, event => {
        if (abort.signal.aborted) return;
        setMessages(items => {
          let next = items;
          if (event.type === 'turn_started') {
            const createdAt = new Date().toISOString();
            next = items.filter(item => item.id !== event.inputMessageId && item.id !== event.messageId).concat([
              { id: event.inputMessageId, role: 'user', text, createdAt },
              applyChatStreamEvent(
                { id: event.messageId, role: 'assistant', text: '', delivery: 'running', createdAt },
                event,
              ),
            ]);
          }
          return next.map(item => {
            if (item.id !== event.messageId) return item;
            if (event.type === 'done') {
              return preserveUpdatedCards(
                messageFromContent(item.id, 'assistant', event.content, item.createdAt),
                actionUpdatedCards.current,
              );
            }
            return preserveUpdatedCards(applyChatStreamEvent(item, event), actionUpdatedCards.current);
          });
        });
        if (event.type === 'error') setError('本轮未成功完成，请查看保存的状态；不会自动重试。');
      }, abort.signal);
    } catch { if (!abort.signal.aborted) { setLoaded(false); setError('连接中断或发送状态未确认。请刷新页面查看已保存状态，不要重复发送原消息。'); } }
    finally {
      sending.current = false;
      if (!abort.signal.aborted) { await load(); setBusy(false); }
    }
  }, [conversationId, load, loaded, pending]);
  const renderMessageExtras = useCallback((message: Message) => <>
    {message.event?.type === 'workflow_confirm' && (!message.delivery || message.delivery === 'completed') ? <section className="workflow-confirm"><strong>确认运行工作流 {message.event.title}？</strong><p>工作流仅在你明确确认后启动。</p><button className="primary" onClick={async () => {
      try { const result = await productApi.startRun(message.event!.type === 'workflow_confirm' ? message.event!.workflowKey : '', '来自对话的工作请求'); await productApi.attachRun(conversationId, result.runId); setRunId(result.runId); }
      catch { setError('工作流启动状态未确认，请查看工作流列表。'); }
    }}>运行工作流</button><button className="secondary" onClick={() => setMessages(items => items.map(item => item.id === message.id ? { ...item, event: undefined } : item))}>取消</button></section> : null}
    {message.event?.type === 'interaction_required' ? <RunDetail runId={message.event.runId} /> : null}
  </>, [conversationId]);
  return <section className="chat-main"><header className="chat-header"><div><h1>数字员工对话</h1><p>描述目标，数字员工会调用已发布能力并展示交互卡片</p></div></header>
    <AssistantThread
      messages={messages}
      unassignedCards={unassignedCards}
      isRunning={busy || pending}
      isSendDisabled={!loaded || pending}
      error={historyError || error}
      onSend={send}
      onCardUpdate={updateCard}
      onCardActionStateChange={setCardActionState}
      onComposerError={setError}
      renderMessageExtras={renderMessageExtras}
      threadTail={runId ? <RunDetail runId={runId} /> : null}
    />
  </section>;
}

function WorkflowCenter({ onSchedule }: { onSchedule: (workflowKey: string) => void }) {
  const [tab, setTab] = useState<'catalog' | 'runs'>('catalog');
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [selected, setSelected] = useState('');
  const [inputs, setInputs] = useState<Record<string, string>>({});
  useEffect(() => { void Promise.all([productApi.workflows(), productApi.runs()]).then(([catalog, mine]) => { setWorkflows(catalog.items); setRuns(mine.items); }); }, []);
  if (selected) return <RunDetail runId={selected} onBack={() => setSelected('')} />;
  return <section><div className="page-title"><h1>工作流中心</h1><p>选择工作流立即运行，或查看我的运行记录。</p></div><div className="tabs" role="tablist"><button role="tab" aria-selected={tab === 'catalog'} onClick={() => setTab('catalog')}>可执行工作流</button><button role="tab" aria-selected={tab === 'runs'} onClick={() => setTab('runs')}>我的运行</button></div>{tab === 'catalog' ? <div className="catalog-grid">{workflows.map((workflow) => <article className="workflow-catalog-card" key={workflow.key}><span className="card-icon">◇</span><h2>{workflow.name}</h2><p>{workflow.description}</p><label htmlFor={`input-${workflow.key}`}>执行输入</label><textarea id={`input-${workflow.key}`} placeholder={workflow.inputHint} value={inputs[workflow.key] ?? ''} onChange={(event) => setInputs((value) => ({ ...value, [workflow.key]: event.target.value }))} /><div><button className="primary" onClick={async () => setSelected((await productApi.startRun(workflow.key, inputs[workflow.key] ?? '')).runId)}>立即运行</button><button className="secondary" onClick={() => onSchedule(workflow.key)}>设置定时</button></div></article>)}</div> : <div className="run-list">{runs.map((run) => <button key={run.id} onClick={() => setSelected(run.id)}><div><strong>{run.title}</strong><p>{run.input}</p></div><span className={`status ${run.status.toLowerCase()}`}>{runLabels[run.status] ?? run.status}</span></button>)}</div>}</section>;
}

function SchedulePage({ initialWorkflow }: { initialWorkflow: string }) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [items, setItems] = useState<Schedule[]>([]);
  const [workflowKey, setWorkflowKey] = useState(initialWorkflow);
  const [input, setInput] = useState('');
  const [expression, setExpression] = useState('0 9 * * *');
  const [timezone, setTimezone] = useState('Asia/Shanghai');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => setItems((await productApi.schedules()).items), []);
  useEffect(() => {
    let active = true;
    void Promise.all([productApi.workflows(), productApi.schedules()]).then(([catalog, schedules]) => {
      if (!active) return;
      setWorkflows(catalog.items); setItems(schedules.items);
      setWorkflowKey((value) => value || catalog.items[0]?.key || '');
    }).catch(() => { if (active) setError('定时任务加载失败，请刷新页面重试。'); });
    return () => { active = false; };
  }, []);
  const workflowNames = useMemo(() => Object.fromEntries(workflows.map((item) => [item.key, item.name])), [workflows]);
  const mutate = async (operation: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true); setError('');
    try { await operation(); await load(); }
    catch (reason) { setError(apiErrorMessage(reason, '定时任务操作失败，请核对 Cron 表达式和时区。')); }
    finally { setBusy(false); }
  };
  return <section>
    <div className="page-title"><h1>定时管理</h1><p>按 Cron 表达式和指定时区自动执行工作流。</p></div>
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    <section className="schedule-form card"><h2>创建定时任务</h2>
      <form onSubmit={(event) => {
        event.preventDefault();
        if (expression.trim().split(/\s+/).length !== 5) { setError('Cron 需要五个字段：分 时 日 月 周。'); return; }
        void mutate(async () => {
          await productApi.createSchedule({ workflowKey, input, ruleType: 'cron', ruleJson: { expression: expression.trim() }, timezone: timezone.trim() });
          setInput('');
        });
      }}>
        <label htmlFor="schedule-workflow">工作流</label>
        <select id="schedule-workflow" required value={workflowKey} onChange={(event) => setWorkflowKey(event.target.value)}>{workflows.map((item) => <option value={item.key} key={item.key}>{item.name}</option>)}</select>
        <label htmlFor="schedule-cron">Cron 表达式</label>
        <input id="schedule-cron" required value={expression} onChange={(event) => setExpression(event.target.value)} aria-describedby="cron-help" />
        <small id="cron-help">分 时 日 月 周。例如 0 9 * * * 表示每天 09:00；*/15 * * * * 表示每 15 分钟。</small>
        <label htmlFor="schedule-timezone">时区</label>
        <input id="schedule-timezone" required value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Shanghai" />
        <label htmlFor="schedule-input">执行输入</label>
        <textarea id="schedule-input" value={input} onChange={(event) => setInput(event.target.value)} required placeholder="输入工作流执行内容" />
        <button className="primary" disabled={busy || !workflowKey}>{busy ? '正在保存…' : '创建定时任务'}</button>
      </form>
    </section>
    <div className="schedule-list">{items.length ? items.map((item) => <article className="card" key={item.id}>
      <div><h2>{workflowNames[item.workflowKey] ?? item.workflowName}</h2><p>{item.input}</p><small>{item.cadence} · 下次运行 {item.nextRunAt ? new Date(item.nextRunAt).toLocaleString() : '暂无'}</small></div>
      <label className="switch"><input role="switch" type="checkbox" disabled={busy} checked={item.enabled} onChange={(event) => { void mutate(() => productApi.toggleSchedule(item.id, event.target.checked)); }} /><span>{item.enabled ? '已启用' : '已停用'}</span></label>
      <button className="quiet danger" disabled={busy} onClick={() => { void mutate(() => productApi.deleteSchedule(item.id)); }}>删除</button>
    </article>) : <div className="empty-card">暂无定时任务</div>}</div>
  </section>;
}

function NotificationPage({ items, refresh, onRun }: { items: Notification[]; refresh: () => Promise<void>; onRun: (id: string) => void }) {
  return <section><div className="page-title"><h1>通知中心</h1><p>跟踪等待确认、完成与系统事件。</p></div><div className="notification-list">{items.map((item) => <article className={`notification-item card ${item.read ? 'read' : ''}`} key={item.id}><span className={`notification-type ${item.type.toLowerCase()}`}>{notificationLabels[item.type] ?? item.type}</span><button className="notification-link" onClick={() => item.relatedId && onRun(item.relatedId)}><strong>{item.title}</strong><small>{new Date(item.createdAt).toLocaleString()}</small></button>{!item.read ? <button className="secondary" onClick={async () => { await productApi.readNotification(item.id); await refresh(); }}>标记已读</button> : <span className="read-label">已读</span>}</article>)}</div></section>;
}

function Product() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [page, setPage] = useState<Page>('chat');
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [scheduleWorkflow, setScheduleWorkflow] = useState('');
  const [notificationRun, setNotificationRun] = useState('');
  const refreshNotifications = useCallback(async () => setNotifications((await productApi.notifications()).items), []);
  useEffect(() => { void productApi.session().then(setSession).catch(() => setSession(null)).finally(() => setChecking(false)); }, []);
  useEffect(() => { if (session) void refreshNotifications(); }, [session, refreshNotifications]);
  const unread = useMemo(() => notifications.filter((item) => !item.read).length, [notifications]);
  if (checking) return <div className="loading-screen">正在加载 A2Flow…</div>;
  if (!session) return <Login onSession={setSession} />;
  return <Shell session={session} page={page} unread={unread} onPage={(next) => { setNotificationRun(''); setPage(next); }} onLogout={async () => { await productApi.logout(); setPage('chat'); setSession(null); }}>
    {notificationRun ? <RunDetail runId={notificationRun} onBack={() => setNotificationRun('')} /> : page === 'memory' ? <MemorySettingsPage key={session.userId} /> : page === 'chat' ? <ChatPage /> : page === 'workflows' ? <WorkflowCenter onSchedule={(key) => { setScheduleWorkflow(key); setPage('schedules'); }} /> : page === 'schedules' ? <SchedulePage initialWorkflow={scheduleWorkflow} /> : <NotificationPage items={notifications} refresh={refreshNotifications} onRun={(id) => setNotificationRun(id)} />}
  </Shell>;
}

export function App() {
  return fixtureMode ? <FixturePreview /> : <Product />;
}
