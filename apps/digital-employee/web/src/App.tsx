import { createUuidV4 } from './secureUuid.mjs';
import { PersonalWorkflowCard, PersonalWorkflowSteps } from './components/PersonalWorkflowCard';
import type { PersonalWorkflow } from './personalWorkflow';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Icon } from './components/Icon';
import { ActivityDialog, WorkActivitySidebar, useWorkActivities } from './components/WorkActivity';
import { chatDraftKey, readChatDraft, saveChatDraft } from './chatDraft';
import { ProcessingChip, ProcessingTaskPanel } from './components/ProcessingTask';
import type { ProcessingSelection, ProcessingTask, RunReference, WorkActivity } from './productApi';
import { RunHistory, runDisplayName, displayTime } from './components/RunHistory';
import { NodeCard } from './components/NodeCard';
import { WorkflowTimeline } from './components/WorkflowTimeline';
import { WorkflowApplications } from './components/WorkflowApplications';
import { productProgress } from './api/client';
import { useProgress } from './hooks/useProgress';
import { MemorySettingsPage } from './components/MemorySettingsPage';
import { AssistantThread } from './components/AssistantThread';
import './chat.css';
import { TemporaryDraftOwner } from './temporaryDraft';
import { FixturePreview } from './FixturePreview';
import { applyChatStreamEvent, preserveUpdatedCards } from './assistantChat';
import { apiErrorMessage, messageFromContent, productApi, type ChatCard, type Conversation, type Message, type Notification, type RunItem, type Schedule, type Session, type Workflow } from './productApi';
import { ScheduleEditor, ScheduleHistory, scheduleRunLabel, scheduleTime } from './ScheduleDetails';
import type { WorkflowCard } from './productApi';
import type { InteractiveCard, RunView } from './presentation';

const fixtureMode = new URLSearchParams(location.search).get('preview') === 'fixture';
type WorkflowTab = 'personal' | 'preset' | 'runs';
type Page = 'chat' | 'workflows' | 'schedules' | 'notifications' | 'memory';
const runLabels: Record<string, string> = { RUNNING: '运行中', WAITING: '等待确认', SUCCEEDED: '已完成', STOPPED: '已停止', FAILED: '失败', SUBMITTED: '已提交', PENDING: '准备中', SKIPPED: '已跳过', UNKNOWN: '待核对' };
const notificationLabels: Record<string, string> = { WAITING: '等待确认', COMPLETED: '完成', STOPPED: '停止', FAILED: '失败', SYSTEM: '系统', waiting: '等待确认', finished: '完成', stopped: '停止', failed: '失败', system: '系统' };

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
    <header className="mobile-app-header">
      <button className="mobile-menu" aria-label={mobileOpen ? '关闭导航' : '打开导航'} aria-expanded={mobileOpen} aria-controls="product-navigation" onClick={() => setMobileOpen(value => !value)}><Icon name={mobileOpen ? 'close' : 'menu'} /></button>
      <button className="top-brand" aria-label="A2Flow 对话工作台" onClick={() => navigate('chat')}><strong>A2</strong>Flow</button>
      <button className="notification-button" aria-label={`通知中心，${unread} 条未读`} onClick={() => navigate('notifications')}><Icon name="bell" />{unread ? <span>{unread}</span> : null}</button>
    </header>
    <aside id="product-navigation" className={`app-rail ${mobileOpen ? 'open' : ''}`} aria-label="主导航">
      <button className="rail-brand" aria-label="A2Flow 对话工作台" onClick={() => navigate('chat')}><strong>A2</strong><span>Flow</span></button>
      <nav className="rail-links" aria-label="应用">
        <button className={page === 'chat' ? 'active' : ''} aria-label="对话工作台" aria-current={page === 'chat' ? 'page' : undefined} onClick={() => navigate('chat')}><Icon name="chat" /><span>对话</span></button>
        <button className={page === 'workflows' ? 'active' : ''} aria-label="工作流中心" aria-current={page === 'workflows' ? 'page' : undefined} onClick={() => navigate('workflows')}><Icon name="workflow" /><span>工作流</span></button>
        <button className={page === 'schedules' ? 'active' : ''} aria-label="定时管理" aria-current={page === 'schedules' ? 'page' : undefined} onClick={() => navigate('schedules')}><Icon name="clock" /><span>定时任务</span></button>
        <button className={page === 'notifications' ? 'active' : ''} aria-label={`通知中心，${unread} 条未读`} aria-current={page === 'notifications' ? 'page' : undefined} onClick={() => navigate('notifications')}><Icon name="bell" /><span>通知</span>{unread ? <span className="rail-count">{unread}</span> : null}</button>
        <button className={page === 'memory' ? 'active' : ''} aria-label="设置 · 个人记忆" aria-current={page === 'memory' ? 'page' : undefined} onClick={() => navigate('memory')}><Icon name="settings" /><span>设置</span></button>
      </nav>
      <div className="rail-account"><Icon name="user" /><span>{session.username}</span><small>{session.role === 'ADMIN' ? '管理员' : '成员'}</small><button aria-label="退出登录" onClick={onLogout}><Icon name="logout" size={18} /><span>退出</span></button></div>
    </aside>
    <section className="product-content">{children}</section>
  </div>;
}

function RunDetail({ runId, onBack, metadata, onUpdated }: { runId: string; onBack?: () => void; metadata?: RunItem; onUpdated?: () => void }) {
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
    <div className="section-heading">{onBack ? <button className="secondary" onClick={onBack}>返回</button> : null}<div><h2>{metadata?.title || run.title}</h2><p>{run.requirement}</p>{metadata ? <p className="run-started">发起于 {displayTime(metadata.createdAt)} · 本地时间</p> : null}</div><span className={`status ${run.lifecycle.toLowerCase()}`}>{runLabels[run.lifecycle] ?? run.lifecycle}</span>{['RUNNING', 'WAITING'].includes(run.lifecycle) ? <button className="quiet danger" onClick={async () => { if (!confirm('停止后无法恢复，确认停止？')) return; await productApi.stopRun(run.id); await refresh(); onUpdated?.(); }}>停止运行</button> : null}</div>
    <details className="run-identifiers"><summary>运行标识</summary><p>运行记录：<code>{run.id}</code></p>{metadata ? <p>工作流：<code>{metadata.workflowKey}</code></p> : null}</details>
    <div className="nodes">{run.nodes.map((node, index) => {
      const entries = cards.filter(entry => entry.nodeId === node.id);
      const observedNode = { ...node, records: progress.records[node.id] ?? [], historyStatus: progress.historyStatus, ...(entries.length ? { card: undefined } : {}) };
      return <NodeCard key={node.id} node={observedNode} index={index} defaultResultOpen={index === run.nodes.length - 1 && node.status === 'SUCCEEDED'} busy={busy} onHistory={refresh} onAction={async (card: InteractiveCard, value: string) => { setBusy(true); try { await productApi.runAction(run.id, node.id, card.interactionId, card.actionName, value, card.confirmed, (view) => setRun(view)); await refresh(); onUpdated?.(); } finally { setBusy(false); } }}>
        {node.snapshotCardIds?.some(cardId => !entries.some(entry => entry.card.cardId === cardId))
          ? <p role="status">交互卡片尚未同步，请刷新页面重试。</p> : null}
        <WorkflowTimeline node={observedNode} entries={entries} renderCard={entry => <WorkflowApplications title={node.title} runId={run.id} entries={[entry]} disabled={!['RUNNING', 'WAITING'].includes(run.lifecycle) || !['RUNNING', 'WAITING'].includes(node.status) || busy} onUpdate={card => { cardReadEpoch.current++; setCards(current => current.map(entry => entry.card.cardId === card.cardId ? { ...entry, card } : entry)); }} onSettled={async () => { await refresh(); onUpdated?.(); }} />} />
      </NodeCard>;
    })}</div>
  </section>;
}

function ChatPage({ ownerId, onOpenWorkflows }: { ownerId: string; onOpenWorkflows: (tab: WorkflowTab) => void }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState('');
  const [incomingProcessing, setIncomingProcessing] = useState<{ conversationId: string; selection: ProcessingSelection } | undefined>();
  const [error, setError] = useState('');
  const initial = useRef<Promise<Conversation[]> | null>(null);
  const selectConversation = useCallback((id: string) => {
    setIncomingProcessing(undefined);
    setConversationId(id);
    try { sessionStorage.setItem(`a2flow:last-chat:${ownerId}`, id); } catch { /* Draft storage reports its own availability. */ }
  }, [ownerId]);
  useEffect(() => {
    let active = true;
    initial.current ??= productApi.conversations().then(async ({ items }) => items.length ? items : [await productApi.createConversation()]);
    void initial.current.then(items => { if (active) { setConversations(items); let saved = ''; try { saved = sessionStorage.getItem(`a2flow:last-chat:${ownerId}`) || ''; } catch { /* Use the newest conversation when no saved selection exists. */ } selectConversation(items.some(item => item.id === saved) ? saved : items[0].id); } }).catch(() => { if (active) setError('会话读取失败，请刷新页面'); });
    return () => { active = false; };
  }, []);
  return <div className="chat-layout">
    <aside className="conversation-list"><div className="panel-heading"><h2>会话</h2><button aria-label="新建会话" onClick={async () => {
      try { const item = await productApi.createConversation(); setConversations(items => [item, ...items]); selectConversation(item.id); }
      catch { setError('新建会话失败'); }
    }}><Icon name="plus" /><span>新建会话</span></button></div>{error ? <p role="alert">{error}</p> : null}{conversations.map(item => <button key={item.id} className={item.id === conversationId ? 'selected' : ''} onClick={() => selectConversation(item.id)}>{item.title}<small>{new Date(item.updatedAt).toLocaleDateString()}</small></button>)}</aside>
    {conversationId ? <ChatConversation key={`${ownerId}:${conversationId}`} ownerId={ownerId} conversationId={conversationId} onOpenWorkflows={onOpenWorkflows} incomingProcessing={incomingProcessing?.conversationId === conversationId ? incomingProcessing.selection : undefined} onProcessingSelected={() => setIncomingProcessing(undefined)} onOpenProcessingConversation={task => { setIncomingProcessing(undefined); selectConversation(String(task.conversationId)); }} onProcessingConversation={task => { selectConversation(String(task.conversationId)); setIncomingProcessing({ conversationId: String(task.conversationId), selection: { taskId: task.taskId, activityId: task.activityId, label: task.objective, requestId: createUuidV4() } }); }} /> : null}
  </div>;
}

function ChatConversation({ ownerId, conversationId, onOpenWorkflows, incomingProcessing, onProcessingSelected, onProcessingConversation, onOpenProcessingConversation }: { ownerId: string; conversationId: string; onOpenWorkflows: (tab: WorkflowTab) => void; incomingProcessing?: ProcessingSelection; onProcessingSelected: () => void; onProcessingConversation: (task: ProcessingTask) => void; onOpenProcessingConversation: (task: ProcessingTask) => void }) {
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
  const workflowStartInFlight = useRef(false);
  const [startingWorkflow, setStartingWorkflow] = useState(false);
  const [workflowStartUnconfirmed, setWorkflowStartUnconfirmed] = useState(false);
  const draftKey = chatDraftKey(ownerId, conversationId);
  const initialDraft = useRef(readChatDraft(draftKey));
  const [processing, setProcessing] = useState<ProcessingSelection | undefined>(initialDraft.current.processing);
  const [selectedTaskId, setSelectedTaskId] = useState('');
  useEffect(() => { if (incomingProcessing) { setProcessing(incomingProcessing); onProcessingSelected(); } }, [incomingProcessing, onProcessingSelected]);
  const [draftText, setDraftText] = useState(initialDraft.current.text);
  const [runReferences, setRunReferences] = useState<RunReference[]>(initialDraft.current.references);
  const [draftStorageError, setDraftStorageError] = useState('');
  const [compactActivity, setCompactActivity] = useState(() => !matchMedia('(min-width: 1400px)').matches);
  const [activityOpen, setActivityOpen] = useState(() => matchMedia('(min-width: 1400px)').matches);
  const [selectedActivity, setSelectedActivity] = useState<WorkActivity | null>(null);
  const [activityReadError, setActivityReadError] = useState('');
  const [readingActivity, setReadingActivity] = useState(false);
  const activityReadEpoch = useRef(0);
  const activityTrigger = useRef<HTMLButtonElement>(null);
  const activities = useWorkActivities(activityOpen && !selectedActivity);
  useEffect(() => {
    const media = matchMedia('(min-width: 1400px)');
    const resize = () => setCompactActivity(!media.matches);
    media.addEventListener('change', resize);
    return () => media.removeEventListener('change', resize);
  }, []);
  useEffect(() => {
    setDraftStorageError(saveChatDraft(draftKey, draftText, runReferences, processing) ? '' : '浏览器暂时无法保存草稿，请在刷新前复制输入内容。');
  }, [draftKey, draftText, runReferences, processing]);
  const addRunReference = (item: WorkActivity) => {
    if (runReferences.some(reference => reference.activityId === item.activityId)) return;
    if (new Set([...runReferences.map(reference => reference.activityId), ...(processing?.target?.activityId || processing?.activityId ? [processing.target?.activityId || processing.activityId!] : []), item.activityId]).size > 3) { setError('一次最多引用 3 次运行，请先移除一个引用。'); return; }
    setError('');
    setRunReferences(current => [...current, { activityId: item.activityId, workflowName: item.workflowName, createdAt: item.createdAt }]);
    if (compactActivity) setActivityOpen(false);
  };
  const openRunReference = useCallback(async (id: string) => {
    const epoch = ++activityReadEpoch.current;
    setReadingActivity(true); setActivityReadError('');
    try {
      const item = await productApi.workActivity(id);
      if (epoch === activityReadEpoch.current) setSelectedActivity(item);
    } catch (error) { if (epoch === activityReadEpoch.current) setActivityReadError(apiErrorMessage(error, '运行详情读取失败，请重新打开。')); }
    finally { if (epoch === activityReadEpoch.current) setReadingActivity(false); }
  }, []);

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
    if (!text || sending.current || pending || !loaded || activeCardActions.current.size) return;
    sending.current = true;
    epoch.current++; // In-flight history reads cannot overwrite live deltas.
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError('');
    const sentReferences = runReferences;
    const sentProcessing = processing;
    let accepted = false;
    try {
      await productApi.sendMessage(conversationId, text, event => {
        if (abort.signal.aborted) return;
        if (event.type === 'turn_started' && !accepted) { accepted = true; setProcessing(current => current?.requestId === sentProcessing?.requestId ? undefined : current); setDraftText(current => current.trim() === text ? '' : current); setRunReferences(current => current.filter(reference => !sentReferences.some(sent => sent.activityId === reference.activityId))); }
        setMessages(items => {
          let next = items;
          if (event.type === 'turn_started') {
            const createdAt = new Date().toISOString();
            next = items.filter(item => item.id !== event.inputMessageId && item.id !== event.messageId).concat([
              { id: event.inputMessageId, role: 'user', text, createdAt, runReferences: sentReferences, processingTaskId: event.processingTaskId },
              applyChatStreamEvent(
                { id: event.messageId, role: 'assistant', text: '', delivery: 'running', createdAt, processingTaskId: event.processingTaskId },
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
      }, abort.signal, sentReferences.map(({ activityId }) => ({ activityId })), sentProcessing);
    } catch { if (!abort.signal.aborted) { setLoaded(false); setError('连接中断或发送状态未确认。请刷新页面查看已保存状态，不要重复发送原消息。'); } }
    finally {
      sending.current = false;
      if (!abort.signal.aborted) { await load(); setBusy(false); }
    }
  }, [conversationId, load, loaded, pending, runReferences, processing]);
  const runPersonalWorkflow = async (workflow: PersonalWorkflow, requirement: string) => {
    if (workflowStartInFlight.current || workflowStartUnconfirmed || busy || pending || !loaded || activeCardActions.current.size) return;
    workflowStartInFlight.current = true;
    setStartingWorkflow(true); setError('');
    let startedRunId = '';
    try {
      const result = await productApi.startRun(workflow.definitionKey, requirement, 'chat');
      startedRunId = result.runId;
      setRunId(result.runId);
      await productApi.attachRun(conversationId, result.runId);
      setHistoryRefreshKey(value => value + 1);
    } catch {
      if (startedRunId) setError('运行已创建，但未能关联到当前对话。请查看下方运行或运行历史，不要重复启动。');
      else {
        setWorkflowStartUnconfirmed(true);
        setError('工作流启动状态未确认，请查看运行历史；不会自动重试，请勿重复启动。');
      }
    } finally { workflowStartInFlight.current = false; setStartingWorkflow(false); }
  };
  const renderMessageExtras = useCallback((message: Message) => <>
    {message.processingTaskId ? <button className="secondary processing-message-link" onClick={() => setSelectedTaskId(message.processingTaskId!)}>查看本次处理记录</button> : null}
    {message.event?.type === 'workflow_confirm' && (!message.delivery || message.delivery === 'completed') ? <section className="workflow-confirm"><strong>确认运行工作流 {message.event.title}？</strong><p>工作流仅在你明确确认后启动。</p><button className="primary" onClick={async () => {
      try { const result = await productApi.startRun(message.event!.type === 'workflow_confirm' ? message.event!.workflowKey : '', '来自对话的工作请求', 'chat'); await productApi.attachRun(conversationId, result.runId); setRunId(result.runId); }
      catch { setError('工作流启动状态未确认，请查看工作流列表。'); }
    }}>运行工作流</button><button className="secondary" onClick={() => setMessages(items => items.map(item => item.id === message.id ? { ...item, event: undefined } : item))}>取消</button></section> : null}
    {message.event?.type === 'interaction_required' ? <RunDetail runId={message.event.runId} /> : null}
  </>, [conversationId]);
  const activitySidebar = <WorkActivitySidebar {...activities} onClose={() => { setActivityOpen(false); activityTrigger.current?.focus(); }} onOpen={setSelectedActivity} onReference={addRunReference} onProcessingTask={task => setSelectedTaskId(task.taskId)} onProcess={(item, attentionId, title) => {
    if (new Set([...runReferences.map(reference => reference.activityId), item.activityId]).size > 3) { setError('处理目标也占用运行引用名额，请先移除一个引用。'); return; }
    setProcessing({ target: { activityId: item.activityId, attentionId }, label: title, requestId: createUuidV4() });
    setSelectedActivity(null); setError(''); if (compactActivity) setActivityOpen(false);
  }} />;
  return <div className={`chat-workspace ${activityOpen && !compactActivity ? 'with-activity' : ''}`}><section className="chat-main"><header className="chat-header"><div><h1>对话</h1><p>描述目标，在这里查看结果并完成确认</p></div><button ref={activityTrigger} className="secondary activity-toggle" aria-expanded={activityOpen} onClick={() => setActivityOpen(value => !value)}><Icon name="workflow" size={17} />工作动态{activities.attentionCount ? <span>{activities.attentionCount}</span> : null}</button></header>
    <AssistantThread
      processingComposer={processing ? <ProcessingChip selection={processing} onRemove={() => setProcessing(undefined)} /> : null}
      draftText={draftText}
      onDraftTextChange={setDraftText}
      runReferences={runReferences}
      onRemoveReference={id => { setRunReferences(current => current.filter(reference => reference.activityId !== id)); setError(''); }}
      onOpenReference={id => void openRunReference(id)}
      messages={messages}
      unassignedCards={unassignedCards}
      isRunning={busy || pending}
      isSendDisabled={!loaded || pending || activeCardActionCount > 0 || startingWorkflow}
      error={historyError || error || draftStorageError || activityReadError || (readingActivity ? '正在读取运行详情…' : '')}
      onSend={send}
      onCardUpdate={updateCard}
      onCardActionStateChange={setCardActionState}
      onComposerError={setError}
      renderMessageExtras={renderMessageExtras}
      renderPersonalWorkflow={workflow => <PersonalWorkflowCard workflow={workflow}
        disabled={!loaded || busy || pending || activeCardActionCount > 0 || startingWorkflow || workflowStartUnconfirmed}
        onRun={runPersonalWorkflow} onOpenWorkflows={() => onOpenWorkflows('personal')} />}
      threadTail={<>{workflowStartUnconfirmed ? <button className="secondary" onClick={() => onOpenWorkflows('runs')}>查看运行历史</button> : null}{runId && !messages.some(message => message.event?.type === 'interaction_required' && message.event.runId === runId) ? <RunDetail runId={runId} /> : null}</>}
    />
  </section>
    {activityOpen && !compactActivity ? activitySidebar : null}
    {activityOpen && compactActivity && !selectedActivity && !selectedTaskId ? <ActivityDialog title="工作动态" onClose={() => setActivityOpen(false)}>{activitySidebar}</ActivityDialog> : null}
    {selectedTaskId ? <ActivityDialog title="异常处理记录" onClose={() => { setSelectedTaskId(''); activities.refresh(); }}><ProcessingTaskPanel key={selectedTaskId} taskId={selectedTaskId} onOpenConversation={task => { setSelectedTaskId(''); onOpenProcessingConversation(task); }} onUpdated={activities.refresh} onContinue={task => { setSelectedTaskId(''); onProcessingConversation(task); }} /></ActivityDialog> : null}
    {selectedActivity ? <ActivityDialog title="工作详情" onClose={() => { setSelectedActivity(null); activities.refresh(); }}>
      <div className="activity-detail-actions"><button className="secondary" onClick={() => { addRunReference(selectedActivity); setSelectedActivity(null); }}>在对话中继续</button><p>引用结果后，发送你的问题继续分析。</p></div>
      {selectedActivity.runId ? <RunDetail key={selectedActivity.controlRequestId} runId={selectedActivity.controlRequestId} metadata={{ id: selectedActivity.controlRequestId, workflowKey: selectedActivity.workflowKey, title: selectedActivity.workflowName, status: selectedActivity.runStatus, input: '', createdAt: selectedActivity.createdAt }} onUpdated={activities.refresh} /> : <p role="status">运行尚未关联执行实例，当前状态：{selectedActivity.runStatus}。请关闭详情后刷新工作动态查看。</p>}
    </ActivityDialog> : null}
  </div>;
}

function WorkflowCenter({ onSchedule, initialTab }: { onSchedule: (workflowKey: string) => void; initialTab: WorkflowTab }) {
  const [tab, setTab] = useState<WorkflowTab>(initialTab);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [selected, setSelected] = useState('');
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [starting, setStarting] = useState('');
  const [startError, setStartError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(true);
  const startInFlight = useRef(false);
  const startRun = async (workflow: Workflow) => {
    if (startInFlight.current) return;
    startInFlight.current = true; setStarting(workflow.key); setStartError('');
    try {
      const result = await productApi.startRun(workflow.key, inputs[workflow.key] ?? workflow.personal?.defaultRequirement ?? '');
      setSelected(result.runId);
    } catch {
      setStartError('工作流启动状态未确认，请查看运行历史；未自动重试，请勿重复启动。');
    } finally { startInFlight.current = false; setStarting(''); }
  };
  const viewRunsAfterStart = async () => {
    setTab('runs');
    try { setRuns((await productApi.runs()).items); }
    catch { setStartError('运行记录暂未同步，请刷新页面查看；请勿重复启动同一工作流。'); }
  };
  useEffect(() => {
    let active = true;
    void Promise.all([productApi.workflows(), productApi.runs()]).then(([catalog, mine]) => {
      if (active) { setWorkflows(catalog.items); setRuns(mine.items); }
    }).catch(() => { if (active) setLoadError('工作流或运行历史读取失败，请刷新页面重试。'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  if (selected) {
    const record = runs.find(run => run.id === selected);
    return <RunDetail runId={selected} metadata={record ? { ...record, title: runDisplayName(record, workflows) } : undefined} onBack={() => setSelected('')} />;
  }
  const visible = workflows.filter(workflow => workflow.source === (tab === 'personal' ? 'PERSONAL' : 'PRESET'));
  return <section>
    <div className="page-title"><h1>工作流中心</h1><p>运行工作流，查看每一次执行的进展与结果。</p></div>
    {startError ? <div><p className="inline-error" role="alert">{startError}</p><button className="secondary" onClick={() => void viewRunsAfterStart()}>查看运行历史</button></div> : null}
    {loadError ? <p className="inline-error" role="alert">{loadError}</p> : null}
    <div className="tabs" role="tablist" aria-label="工作流分类">
      {([['personal', '我的工作流'], ['preset', '预制工作流'], ['runs', '运行历史']] as const).map(([value, label]) =>
        <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{label}</button>)}
    </div>
    {loading ? <p role="status">正在读取工作流与运行历史…</p> : tab !== 'runs' ? <>
      {!visible.length && !loadError ? <p className="muted">{tab === 'personal' ? '还没有我的工作流。在对话中点击“创建工作流”，或直接描述你的创建需求。' : '当前没有可执行的预制工作流。'}</p> : null}
      <div className="catalog-grid">{visible.map(workflow => <article className="workflow-catalog-card" key={workflow.key}>
        <span className="card-icon"><Icon name="workflow" /></span><h2>{workflow.name}</h2>
        {workflow.description ? <p>{workflow.description}</p> : null}
        {workflow.personal ? <PersonalWorkflowSteps workflow={workflow.personal} /> : null}
        <label htmlFor={`input-${workflow.key}`}>本次运行要求</label>
        <textarea id={`input-${workflow.key}`} placeholder={workflow.inputHint} maxLength={2000}
          value={inputs[workflow.key] ?? workflow.personal?.defaultRequirement ?? ''}
          onChange={event => setInputs(value => ({ ...value, [workflow.key]: event.target.value }))} />
        <div><button className="primary" disabled={Boolean(starting) || (workflow.source === 'PERSONAL' && !(inputs[workflow.key] ?? workflow.personal?.defaultRequirement ?? '').trim())} onClick={() => void startRun(workflow)}>{starting === workflow.key ? '正在启动…' : '立即运行'}</button>
          {workflow.source === 'PRESET' ? <button className="secondary" onClick={() => onSchedule(workflow.key)}>设置定时</button> : null}</div>
      </article>)}</div>
    </> : <RunHistory runs={runs} workflows={workflows} onOpen={setSelected} hasError={Boolean(loadError)} />}

  </section>;
}

function SchedulePage({ initialWorkflow }: { initialWorkflow: string }) {
  const [creating, setCreating] = useState(Boolean(initialWorkflow));
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState('');
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
      const presets = catalog.items.filter(workflow => workflow.source === 'PRESET');
      setWorkflows(presets); setItems(schedules.items);
      setWorkflowKey(value => presets.some(workflow => workflow.key === value) ? value : presets[0]?.key || '');
    }).catch(() => { if (active) setError('定时任务加载失败，请刷新页面重试。'); })
      .finally(() => { if (active) setLoading(false); });
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
  if (selectedRun) return <RunDetail runId={selectedRun} onBack={() => { setSelectedRun(''); void load().catch(() => setError('定时任务加载失败。')); }} />;
  return <section>
    <div className="page-title page-title-actions"><div><h1>定时任务</h1><p>安排自动执行，掌握每次运行。</p></div><button className="primary icon-button" aria-expanded={creating} aria-controls="schedule-create" onClick={() => setCreating(value => !value)}><Icon name="plus" />{creating ? '收起表单' : '新建任务'}</button></div>
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    {creating ? <section id="schedule-create" className="schedule-form card"><h2>新建定时任务</h2>
      <form onSubmit={(event) => {
        event.preventDefault();
        if (expression.trim().split(/\s+/).length !== 5) { setError('Cron 需要五个字段：分 时 日 月 周。'); return; }
        void mutate(async () => {
          await productApi.createSchedule({ workflowKey, input, ruleType: 'cron', ruleJson: { expression: expression.trim() }, timezone: timezone.trim() });
          setInput(''); setCreating(false);
        });
      }}>
        <div className="form-field"><label htmlFor="schedule-workflow">工作流</label>
        <select id="schedule-workflow" required value={workflowKey} onChange={(event) => setWorkflowKey(event.target.value)}>{workflows.map((item) => <option value={item.key} key={item.key}>{item.name}</option>)}</select></div>
        <div className="form-field"><label htmlFor="schedule-cron">Cron 表达式</label>
        <input id="schedule-cron" required value={expression} onChange={(event) => setExpression(event.target.value)} aria-describedby="cron-help" />
        <small id="cron-help">分 时 日 月 周。例如 0 9 * * * 表示每天 09:00；*/15 * * * * 表示每 15 分钟。</small></div>
        <div className="form-field"><label htmlFor="schedule-timezone">时区</label>
        <input id="schedule-timezone" required value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Shanghai" /></div>
        <div className="form-field form-field-wide"><label htmlFor="schedule-input">执行要求</label>
        <textarea id="schedule-input" value={input} onChange={(event) => setInput(event.target.value)} required placeholder="输入工作流执行内容" /></div>
        <div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={() => setCreating(false)}>取消</button><button className="primary" disabled={busy || !workflowKey}>{busy ? '正在保存…' : '创建定时任务'}</button></div>
      </form>
    </section> : null}
    {loading ? <p role="status">正在读取定时任务…</p> : null}
    <div className="schedule-list">{items.length ? items.map((item) => <article className="card schedule-card" key={item.id}>
      <div className="schedule-overview"><h2>{workflowNames[item.workflowKey] || (item.workflowName !== item.workflowKey ? item.workflowName : '工作流暂不可用')} <small className="schedule-task-id">任务 #{item.id}</small></h2><p className="schedule-snapshot">{item.input}</p><div className="schedule-facts"><div><span>执行规则 / 时区</span><strong>{item.expression || item.cadence}</strong><small>{item.timezone}</small></div><div><span>下次执行</span><strong>{item.enabled ? scheduleTime(item.nextRunAt, item.timezone) : '已停用'}</strong></div><div><span>最近触发</span><strong>{scheduleTime(item.lastRunAt, item.timezone)}</strong></div></div>
        <p className="schedule-latest">最近结果：{item.latestRun ? scheduleRunLabel(item.latestRun) : '尚未触发'} {item.latestRun?.runId ? <button className="quiet" onClick={() => setSelectedRun(item.latestRun!.controlId)}>查看最近运行</button> : null}</p>
      </div>
      <div className="schedule-actions"><label className="switch"><input role="switch" type="checkbox" disabled={busy || editing !== null} checked={item.enabled} onChange={(event) => { void mutate(() => productApi.toggleSchedule(item.id, event.target.checked)); }} /><span>{item.enabled ? '已启用' : '已停用'}</span></label>
      <button className="secondary" disabled={busy || editing !== null} onClick={() => setEditing(item.id)}>编辑</button>
      <button className="secondary" disabled={editing !== null} onClick={() => setHistory(history === item.id ? null : item.id)}>{history === item.id ? '收起记录' : '运行记录'}</button>
      <button className="quiet danger" disabled={busy || editing !== null} onClick={() => { void mutate(() => productApi.deleteSchedule(item.id)); }}>删除</button></div>
      {editing === item.id ? <ScheduleEditor key={item.id} item={item} onCancel={() => setEditing(null)} onSave={async () => { await load(); setEditing(null); }} /> : null}
      {history === item.id ? <ScheduleHistory key={item.id} item={item} onRun={setSelectedRun} /> : null}
    </article>) : !loading && !error ? <div className="empty-card"><Icon name="clock" size={32} /><h2>还没有定时任务</h2><p>为预制工作流安排执行时间，运行记录会保存在这里。</p><button className="primary" onClick={() => setCreating(true)}>新建任务</button></div> : null}</div>
  </section>;
}

function NotificationPage({ items, refresh, onRun }: { items: Notification[]; refresh: () => Promise<void>; onRun: (id: string) => void }) {
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [error, setError] = useState('');
  const visible = items.filter(item => !onlyUnread || !item.read);
  return <section><div className="page-title"><h1>通知中心</h1><p>查看需要你确认的事项，以及工作流的最新结果。</p></div>
    <div className="list-toolbar"><label className="switch"><input type="checkbox" checked={onlyUnread} onChange={event => setOnlyUnread(event.target.checked)} />只看未读</label><span className="muted">{visible.length} 条通知</span></div>
    {error ? <p role="alert" className="inline-error">{error}</p> : null}
    <div className="notification-list">{visible.length ? visible.map(item => <article className={`notification-item card ${item.read ? 'read' : ''}`} key={item.id}>
      <span className={`notification-type ${item.type.toLowerCase()}`}>{notificationLabels[item.type] ?? item.type}</span>
      <div className="notification-copy"><strong>{item.title}</strong><time dateTime={item.createdAt}>{displayTime(item.createdAt)}</time></div>
      {item.relatedId ? <button className="quiet" onClick={() => onRun(item.relatedId!)}>查看运行</button> : null}
      {!item.read ? <button className="secondary" onClick={async () => { try { await productApi.readNotification(item.id); await refresh(); setError(''); } catch (reason) { setError(apiErrorMessage(reason, '标记结果未确认，请重新读取通知。')); } }}>标记已读</button> : <span className="read-label">已读</span>}
    </article>) : <div className="empty-card"><Icon name="bell" size={32} /><h2>{onlyUnread ? '没有未读通知' : '暂无通知'}</h2><p>工作流的执行进展与待办事项会显示在这里。</p></div>}</div></section>;
}

function Product() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [page, setPage] = useState<Page>('chat');
  const [workflowTab, setWorkflowTab] = useState<WorkflowTab>('personal');
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [scheduleWorkflow, setScheduleWorkflow] = useState('');
  const [notificationRun, setNotificationRun] = useState('');
  const refreshNotifications = useCallback(async () => setNotifications((await productApi.notifications()).items), []);
  useEffect(() => { void productApi.session().then(setSession).catch(() => setSession(null)).finally(() => setChecking(false)); }, []);
  useEffect(() => { if (session) void refreshNotifications(); }, [session, refreshNotifications]);
  const unread = useMemo(() => notifications.filter((item) => !item.read).length, [notifications]);
  if (checking) return <div className="loading-screen">正在加载 A2Flow…</div>;
  if (!session) return <Login onSession={setSession} />;
  return <TemporaryDraftOwner.Provider value={session.userId}><Shell session={session} page={page} unread={unread} onPage={(next) => { setNotificationRun(''); setPage(next); }} onLogout={async () => { await productApi.logout(); setPage('chat'); setSession(null); }}>
    {notificationRun ? <RunDetail runId={notificationRun} onBack={() => setNotificationRun('')} /> : page === 'memory' ? <MemorySettingsPage key={session.userId} /> : page === 'chat' ? <ChatPage ownerId={session.userId} onOpenWorkflows={tab => { setWorkflowTab(tab); setPage('workflows'); }} /> : page === 'workflows' ? <WorkflowCenter initialTab={workflowTab} onSchedule={(key) => { setScheduleWorkflow(key); setPage('schedules'); }} /> : page === 'schedules' ? <SchedulePage initialWorkflow={scheduleWorkflow} /> : <NotificationPage items={notifications} refresh={refreshNotifications} onRun={(id) => setNotificationRun(id)} />}
  </Shell></TemporaryDraftOwner.Provider>;
}

export function App() {
  return fixtureMode ? <FixturePreview /> : <Product />;
}
