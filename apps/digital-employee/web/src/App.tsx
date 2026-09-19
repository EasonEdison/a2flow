import { useCallback, useEffect, useMemo, useState } from 'react';

import { NodeCard } from './components/NodeCard';
import { MarkdownContent } from './components/MarkdownContent';
import { FixturePreview } from './FixturePreview';
import { apiErrorMessage, productApi, type Conversation, type Message, type Notification, type RunItem, type Schedule, type Session, type Workflow } from './productApi';
import type { InteractiveCard, RunView } from './presentation';

const fixtureMode = new URLSearchParams(location.search).get('preview') === 'fixture';
type Page = 'chat' | 'workflows' | 'schedules' | 'notifications';
const runLabels: Record<string, string> = { RUNNING: '运行中', WAITING: '等待确认', SUCCEEDED: '已完成', STOPPED: '已停止', FAILED: '失败' };
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
    </aside>
    <section className="product-content">{children}</section>
  </div>;
}

function RunDetail({ runId, onBack }: { runId: string; onBack?: () => void }) {
  const [run, setRun] = useState<RunView | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => setRun(await productApi.run(runId)), [runId]);
  useEffect(() => { void refresh(); }, [refresh]);
  if (!run) return <div className="loading">正在加载运行…</div>;
  return <section className="run-detail">
    <div className="section-heading">{onBack ? <button className="secondary" onClick={onBack}>返回</button> : null}<div><h2>{run.title}</h2><p>{run.requirement}</p></div><span className={`status ${run.lifecycle.toLowerCase()}`}>{runLabels[run.lifecycle] ?? run.lifecycle}</span>{['RUNNING', 'WAITING'].includes(run.lifecycle) ? <button className="quiet danger" onClick={async () => { if (!confirm('停止后无法恢复，确认停止？')) return; await productApi.stopRun(run.id); await refresh(); }}>停止运行</button> : null}</div>
    <div className="nodes">{run.nodes.map((node, index) => <NodeCard key={node.id} node={node} index={index} busy={busy} onHistory={refresh} onAction={async (card: InteractiveCard, value: string) => { setBusy(true); try { await productApi.runAction(run.id, card.interactionId, card.actionName, value, card.confirmed); await refresh(); } finally { setBusy(false); } }} />)}</div>
  </section>;
}

function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState('');
  const [runId, setRunId] = useState('');
  const loadMessages = useCallback(async (id: string) => { setMessages((await productApi.messages(id)).items); }, []);
  useEffect(() => { void productApi.conversations().then(async ({ items }) => { let list = items; if (!list.length) list = [await productApi.createConversation()]; setConversations(list); setConversationId(list[0].id); }); }, []);
  useEffect(() => { if (conversationId) void loadMessages(conversationId); }, [conversationId, loadMessages]);
  const send = async () => { const text = input.trim(); if (!text || !conversationId) return; setInput(''); setMessages((items) => [...items, { id: `local-${Date.now()}`, role: 'user', text, createdAt: new Date().toISOString() }]); setStreaming(''); const event = await productApi.sendMessage(conversationId, text, (delta) => setStreaming((value) => value + delta)); const assistant: Message = { id: `assistant-${Date.now()}`, role: 'assistant', text: streaming || '我找到了合适的工作流，请确认后运行。', createdAt: new Date().toISOString(), event }; setMessages((items) => [...items, assistant]); setStreaming(''); };
  return <div className="chat-layout">
    <aside className="conversation-list"><div className="panel-heading"><h2>会话</h2><button aria-label="新建会话" onClick={async () => { const item = await productApi.createConversation(); setConversations((items) => [item, ...items]); setConversationId(item.id); }}>＋</button></div>{conversations.map((item) => <button key={item.id} className={item.id === conversationId ? 'selected' : ''} onClick={() => setConversationId(item.id)}>{item.title}<small>{new Date(item.updatedAt).toLocaleDateString()}</small></button>)}</aside>
    <section className="chat-main"><header><h1>数字员工对话</h1><p>描述目标，确认后启动工作流</p></header><div className="message-flow">{messages.map((message) => <article className={`message ${message.role}`} key={message.id}><span>{message.role === 'user' ? '你' : 'AI'}</span><div><MarkdownContent markdown={message.text} />{message.event?.type === 'workflow_confirm' ? <section className="workflow-confirm"><strong>确认运行工作流 {message.event.title}？</strong><p>工作流仅在你明确确认后启动。</p><div><button className="primary" onClick={async () => { const result = await productApi.startRun(message.event!.type === 'workflow_confirm' ? message.event!.workflowKey : '', input || '来自对话的工作请求'); setRunId(result.runId); }}>运行工作流</button><button className="secondary" onClick={(event) => { event.currentTarget.closest('.workflow-confirm')?.remove(); }}>取消</button></div></section> : null}{message.event?.type === 'interaction_required' ? <RunDetail runId={message.event.runId} /> : null}</div></article>)}{streaming ? <article className="message assistant"><span>AI</span><div><MarkdownContent markdown={streaming} /></div></article> : null}{runId ? <article className="message assistant"><span>AI</span><div><p>工作流已启动，正在等待你的确认。</p><RunDetail runId={runId} /></div></article> : null}</div><form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send(); }}><textarea aria-label="消息" placeholder="输入消息，描述你想完成的工作" value={input} onChange={(event) => setInput(event.target.value)} /><button className="primary">发送</button></form></section>
  </div>;
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
  const [cadenceType, setCadenceType] = useState('daily');
  const [interval, setInterval] = useState('30');
  const load = useCallback(async () => setItems((await productApi.schedules()).items), []);
  useEffect(() => { void Promise.all([productApi.workflows(), productApi.schedules()]).then(([catalog, schedules]) => { setWorkflows(catalog.items); setItems(schedules.items); setWorkflowKey((value) => value || catalog.items[0]?.key || ''); }); }, []);
  const cadence = cadenceType === 'minutes' ? `每 ${interval} 分钟` : cadenceType === 'daily' ? '每天 09:00' : cadenceType === 'weekly' ? '每周一 09:00' : '一次性执行';
  return <section><div className="page-title"><h1>定时管理</h1><p>为工作流设置周期或一次性自动执行。</p></div><section className="schedule-form card"><h2>创建定时任务</h2><form onSubmit={async (event) => { event.preventDefault(); await productApi.createSchedule({ workflowKey, input, cadence }); setInput(''); await load(); }}><label htmlFor="schedule-workflow">工作流</label><select id="schedule-workflow" value={workflowKey} onChange={(event) => setWorkflowKey(event.target.value)}>{workflows.map((item) => <option value={item.key} key={item.key}>{item.name}</option>)}</select><label htmlFor="cadence">执行周期</label><select id="cadence" value={cadenceType} onChange={(event) => setCadenceType(event.target.value)}><option value="minutes">每 N 分钟</option><option value="daily">每天</option><option value="weekly">每周</option><option value="once">一次性</option></select>{cadenceType === 'minutes' ? <><label htmlFor="interval">分钟间隔</label><input id="interval" type="number" min="5" value={interval} onChange={(event) => setInterval(event.target.value)} /></> : null}<label htmlFor="schedule-input">执行输入</label><textarea id="schedule-input" value={input} onChange={(event) => setInput(event.target.value)} required placeholder="输入工作流执行内容" /><button className="primary">创建定时任务</button></form></section><div className="schedule-list">{items.length ? items.map((item) => <article className="card" key={item.id}><div><h2>{item.workflowName}</h2><p>{item.input}</p><small>{item.cadence} · 下次运行 {new Date(item.nextRunAt).toLocaleString()}</small></div><label className="switch"><input role="switch" type="checkbox" checked={item.enabled} onChange={async (event) => { await productApi.toggleSchedule(item.id, event.target.checked); await load(); }} /><span>{item.enabled ? '已启用' : '已停用'}</span></label><button className="quiet danger" onClick={async () => { await productApi.deleteSchedule(item.id); await load(); }}>删除</button></article>) : <div className="empty-card">暂无定时任务</div>}</div></section>;
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
    {notificationRun ? <RunDetail runId={notificationRun} onBack={() => setNotificationRun('')} /> : page === 'chat' ? <ChatPage /> : page === 'workflows' ? <WorkflowCenter onSchedule={(key) => { setScheduleWorkflow(key); setPage('schedules'); }} /> : page === 'schedules' ? <SchedulePage initialWorkflow={scheduleWorkflow} /> : <NotificationPage items={notifications} refresh={refreshNotifications} onRun={(id) => setNotificationRun(id)} />}
  </Shell>;
}

export function App() {
  return fixtureMode ? <FixturePreview /> : <Product />;
}
