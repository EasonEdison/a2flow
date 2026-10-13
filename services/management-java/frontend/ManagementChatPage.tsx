import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Alert, Button, Input } from 'antd';
import { PlusOutlined, ReloadOutlined, SendOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { managementChatApi, ManagementChatError, newManagementChatRequestId, type AgentAsset, type AgentConversation, type AgentEvent, type AgentHistory, type AgentTurn } from './managementChatApi';
import './managementChat.less';

const errorLabels: Record<string, string> = {
  INVALID_MANAGEMENT_AGENT_REQUEST: '发送内容无效，请检查后重新发送。',
  ACCOUNT_AUTHENTICATION_REQUIRED: '登录已过期，请通过管理台登录入口重新登录。',
  PERMISSION_DENIED: '当前账号无权执行此操作，请联系管理员。',
  ADMIN_REQUIRED: '当前账号无权执行此操作，请联系管理员。',
  ACCOUNT_ORIGIN_REQUIRED: '请求来源验证未通过，请重新打开管理台。',
  CLIENT_IDENTITY_FIELDS_NOT_ALLOWED: '请求未通过身份验证，请刷新页面后重试。',
  CONVERSATION_NOT_FOUND: '未找到可访问的会话，请重新选择会话。',
  CONVERSATION_BUSY: '这段会话仍在执行，已保存的进度会继续同步。',
  REQUEST_ID_CONFLICT: '请求标识冲突，未重复执行，请读取已保存的状态。',
  TURN_LIMIT_REACHED: '本会话已达到轮数上限，请新建会话。',
  MANAGEMENT_AGENT_ROUTE_NOT_FOUND: '对话创建服务尚不可用。',
};
const failureText = (code: string) => errorLabels[code] ?? '本轮未能完成，请查看已保存的处理结果；未自动重试。';
const statusLabels = { RUNNING: '正在执行', COMPLETED: '本轮已完成', FAILED: '执行失败', UNKNOWN: '结果待确认' };
const asText = (value: unknown) => typeof value === 'string' ? value : '';

const toolLabels: Record<string, string> = {
  SKILL_FACTORY_CONFIG: '读取创建配置', SKILL_LIST: '查找 Skill', SKILL_DETAIL: '读取 Skill',
  WORKSPACE_CREATE: '创建 Skill 草稿', SKILL_UPDATE: '更新 Skill 信息', WORKSPACE_TREE: '读取文件列表',
  WORKSPACE_FILE_CONTENT: '读取草稿文件', WORKSPACE_FILE_SAVE: '保存草稿文件', WORKSPACE_SAVE: '保存 Skill 草稿',
  WORKSPACE_DIFF: '查看草稿变更', SKILL_COMPONENT_CANDIDATE_LIST: '查找可用组件', SKILL_CAPABILITY_CANDIDATE_LIST: '查找可用业务能力',
  SKILL_BINDINGS_REPLACE: '保存 Skill 依赖', RUNTIME_VALIDATE: '校验 Skill',
  CAPABILITY_LIST: '查找业务能力', CAPABILITY_PUBLISHED_LIST: '读取已发布能力', CAPABILITY_DRAFT_DETAIL: '读取能力草稿',
  CAPABILITY_DRAFT_CREATE: '创建能力草稿', CAPABILITY_DRAFT_SAVE: '保存能力草稿', CAPABILITY_VALIDATE: '校验业务能力',
  COMPONENT_LIST: '查找组件', COMPONENT_DETAIL: '读取组件', COMPONENT_REGISTER: '注册组件', COMPONENT_UPDATE: '更新组件',
  A2UI_CATALOG_LIST: '读取组件目录', A2UI_CATALOG_DETAIL: '读取目录定义', A2UI_CATALOG_COMPONENT_LIST: '查找目录组件',
  A2UI_CATALOG_COMPONENT_DETAIL: '读取组件定义', A2UI_APPLICATION_LIST: '查找 A2UI Application',
  A2UI_APPLICATION_DETAIL: '读取 A2UI Application', A2UI_APPLICATION_BLUEPRINT_LIST: '读取可用应用模板',
  A2UI_APPLICATION_CREATE: '创建 A2UI Application', A2UI_APPLICATION_UPDATE: '更新 A2UI Application',
  A2UI_APPLICATION_ACTION_SCAN: '校验应用动作', WORKFLOW_LIST: '查找 Workflow', WORKFLOW_DETAIL: '读取 Workflow',
  WORKFLOW_CREATE: '创建 Workflow 草稿', WORKFLOW_BASIC_INFO_UPDATE: '更新 Workflow 信息',
  WORKFLOW_DRAFT_DETAIL: '读取流程草稿', WORKFLOW_SKILL_CANDIDATES: '查找可用 Skill',
  WORKFLOW_DRAFT_UPDATE: '保存流程草稿', WORKFLOW_COMPILED_PLAN_PREVIEW: '校验流程计划',
  RELEASE_OVERVIEW: '读取发布状态', RELEASE_CHANGE_CREATE: '创建发布变更', RELEASE_DIFF: '读取发布变更',
  RELEASE_PREPROD_DEPLOY: '发布到 PRT', RELEASE_DEPLOYMENT_DETAIL: '读取发布结果',
};

function ProcessEvents({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const tools = new Map<string, { started?: AgentEvent; completed?: AgentEvent }>();
  for (const event of events) {
    if (event.type !== 'TOOL_STARTED' && event.type !== 'TOOL_COMPLETED') continue;
    const id = asText(event.payload.toolCallId);
    if (!id) continue;
    const current = tools.get(id) ?? {};
    tools.set(id, { ...current, [event.type === 'TOOL_STARTED' ? 'started' : 'completed']: event });
  }
  if (!tools.size) return null;
  return <details className="management-chat-process"><summary>处理过程 · {tools.size} 次工具调用</summary>
    <ol>{Array.from(tools.entries()).map(([id, tool]) => {
      const event = tool.completed ?? tool.started!;
      const status = asText(tool.completed?.payload.status);
      return <li key={id}><span>{toolLabels[asText(event.payload.name)] ?? asText(event.payload.name)}</span><span>{tool.completed ? status === 'UNKNOWN' ? '结果待确认' : status === 'FAILED' || status === 'REJECTED' ? '未完成' : status === 'NOT_FOUND' ? '未找到回执' : '已返回' : running ? '执行中' : '未收到结果'}</span>
        <details><summary>查看步骤信息</summary><dl><dt>工具</dt><dd>{asText(event.payload.name)}</dd><dt>请求标识</dt><dd>{asText(event.payload.requestId)}</dd></dl></details>
      </li>;
    })}</ol>
  </details>;
}

const assetLabels: Record<string, string> = { SKILL: 'Skill', CAPABILITY_ACTION: '业务能力', COMPONENT: '组件', A2UI_APPLICATION: 'A2UI Application', ORCHESTRATION_CONFIG: 'Workflow' };
function assetLink(asset: AgentAsset): string | undefined {
  const detail = asset.detail;
  if (!detail) return;
  if (asset.assetType === 'SKILL' && detail.skillCode) return `/management/detail?skillCode=${encodeURIComponent(detail.skillCode)}`;
  if (asset.assetType === 'CAPABILITY_ACTION' && detail.draftId) return `/management/capabilities/edit?draftId=${encodeURIComponent(detail.draftId)}`;
  if (asset.assetType === 'COMPONENT' && detail.id) return `/management/components/detail?id=${encodeURIComponent(detail.id)}`;
  if (asset.assetType === 'A2UI_APPLICATION' && detail.id) return `/management/components/a2ui-applications/edit?id=${encodeURIComponent(detail.id)}`;
  if (asset.assetType === 'ORCHESTRATION_CONFIG' && detail.workflowCode) return `/management/workflows/${encodeURIComponent(detail.workflowCode)}`;
}
function AssetResults({ events }: { events: AgentEvent[] }) {
  const assets = new Map<string, AgentAsset>();
  for (const event of events) for (const asset of event.assets) {
    const key = `${asset.assetType}:${asset.assetKey}`;
    const previous = assets.get(key);
    // Identity metadata may be omitted by release results; publication always follows the latest fact.
    const detail = Object.fromEntries(Object.entries(asset.detail ?? {}).filter(([, value]) => Boolean(value)));
    assets.set(key, { ...asset, displayName: asset.displayName || previous?.displayName, detail: { ...previous?.detail, ...detail } });
  }
  if (!assets.size) return null;
  return <section className="management-chat-assets" aria-label="已保存的资产结果">{Array.from(assets.entries()).map(([key, asset]) => {
    const href = assetLink(asset);
    const publication = asset.publication;
    return <article key={key} className="management-chat-asset">
      <div><span className="management-chat-muted">{assetLabels[asset.assetType] ?? '管理资产'}</span><h3>{asset.displayName || asset.assetKey}</h3></div>
      {href ? <Link to={href}>查看详情</Link> : null}
      {publication ? <div className="management-chat-publication"><strong>{publication.status === 'EFFECTIVE' ? 'PRT 已生效' : 'PRT 发布记录'}</strong>{publication.version ? <span>版本 {publication.version}</span> : null}{publication.status !== 'EFFECTIVE' ? <span>状态：{publication.status}</span> : null}</div> : null}
      <details><summary>查看结果标识</summary><dl><dt>资产标识</dt><dd>{asset.assetKey}</dd>{publication?.deploymentId ? <><dt>发布记录</dt><dd>{publication.deploymentId}</dd></> : null}{publication?.sourceId ? <><dt>来源记录</dt><dd>{publication.sourceId}</dd></> : null}{publication?.digest ? <><dt>内容摘要</dt><dd>{publication.digest}</dd></> : null}</dl></details>
    </article>;
  })}</section>;
}

function Turn({ turn, events }: { turn: AgentTurn; events: AgentEvent[] }) {
  const text = turn.finalText || asText(events.filter(event => event.type === 'ASSISTANT_MESSAGE').at(-1)?.payload.text);
  return <article className="management-chat-turn">
    <div className="management-chat-user">{turn.message}</div>
    <div className="management-chat-answer">
      <p className={`management-chat-status status-${turn.status.toLowerCase()}`} role={turn.status === 'RUNNING' ? 'status' : undefined}>{statusLabels[turn.status]}</p>
      <ProcessEvents events={events} running={turn.status === 'RUNNING'} />
      <AssetResults events={events} />
      {text ? <div className="management-chat-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div> : null}
      {turn.status === 'FAILED' ? <Alert type="error" showIcon message={failureText(turn.errorCode)} /> : null}
      {turn.status === 'UNKNOWN' ? <Alert type="warning" showIcon message="上一轮结果尚未确认，已保存的操作不会自动重放。" description="可继续查询已保存的状态；新消息不会重新执行未确认的变更。" /> : null}
    </div>
  </article>;
}

export default function ManagementChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selected = searchParams.get('conversationId') ?? '';
  const selectedRef = useRef(selected); selectedRef.current = selected;
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [nextPageToken, setNextPageToken] = useState('');
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState('');
  const [history, setHistory] = useState<AgentHistory | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [readError, setReadError] = useState('');
  const [sendError, setSendError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const pendingRequests = useRef(new Map<string, string>());
  const createRequest = useRef('');
  const submitting = useRef(false);
  const viewport = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);

  const choose = useCallback((id: string) => {
    setSearchParams({ conversationId: id });
    setDraft(''); setSendError(''); followLatest.current = true;
  }, [setSearchParams]);

  const loadConversations = useCallback(async (pageToken?: string) => {
    setListBusy(true);
    try {
      const result = await managementChatApi.list(pageToken);
      setConversations(previous => pageToken ? Array.from(new Map([...previous, ...result.items].map(item => [item.id, item])).values()) : result.items);
      setNextPageToken(result.nextPageToken); setListError('');
    } catch { setListError('会话列表读取失败，请重新读取。'); }
    finally { setListBusy(false); }
  }, []);
  useEffect(() => { void loadConversations(); }, [loadConversations]);

  useEffect(() => {
    setHistory(null); setEvents([]); setReadError('');
    if (!selected) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cursor = 0;
    const saved = new Map<number, AgentEvent>();
    const read = async () => {
      try {
        const value = await managementChatApi.read(selected, cursor, controller.signal);
        if (controller.signal.aborted) return;
        if (value.conversation.id !== selected || value.nextEventSeq < cursor) throw new ManagementChatError('RESPONSE_INVALID');
        for (const event of value.events) saved.set(event.sequence, event);
        cursor = value.nextEventSeq;
        const pending = pendingRequests.current.get(selected);
        if (pending && value.turns.some(turn => turn.requestId === pending)) {
          pendingRequests.current.delete(selected); setSendError(''); setDraft('');
        }
        setHistory(value); setEvents([...saved.values()].sort((a, b) => a.sequence - b.sequence)); setReadError('');
        setConversations(previous => [value.conversation, ...previous.filter(item => item.id !== selected)]);
        if (value.hasMore || value.turns.some(turn => turn.status === 'RUNNING') || pendingRequests.current.has(selected)) {
          timer = setTimeout(() => void read(), value.hasMore ? 0 : 1500);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const rejected = error instanceof ManagementChatError && error.rejected;
          setReadError(rejected ? failureText(error.code) : '状态暂未同步，请重新读取；读取状态不会重新执行操作。');
          if (!rejected) timer = setTimeout(() => void read(), 3000);
        }
      }
    };
    void read();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [selected, refresh]);

  useEffect(() => {
    if (followLatest.current && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [history, events]);

  const createConversation = async () => {
    createRequest.current ||= newManagementChatRequestId();
    const value = await managementChatApi.create(createRequest.current);
    createRequest.current = '';
    setConversations(previous => [value, ...previous.filter(item => item.id !== value.id)]);
    return value;
  };
  const newConversation = async () => {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setSendError('');
    try { choose((await createConversation()).id); }
    catch (error) { setSendError(error instanceof ManagementChatError && error.rejected ? failureText(error.code) : '新会话创建状态未确认，请重新读取会话列表。'); }
    finally { submitting.current = false; setBusy(false); }
  };
  const ready = !selected || Boolean(history?.canSend && history.conversation.id === selected && !readError && !pendingRequests.current.has(selected));
  const send = async () => {
    const message = draft.trim();
    if (!message || !ready || submitting.current) return;
    submitting.current = true; setBusy(true); setSendError('');
    let id = selected;
    try {
      if (!id) { id = (await createConversation()).id; setSearchParams({ conversationId: id }); }
      const requestId = newManagementChatRequestId();
      pendingRequests.current.set(id, requestId);
      const result = await managementChatApi.send(id, requestId, message);
      if (result.conversationId !== id || result.requestId !== requestId) throw new ManagementChatError('RESPONSE_INVALID');
      if (!selectedRef.current || selectedRef.current === id) setDraft('');
      followLatest.current = true;
    } catch (error) {
      if (error instanceof ManagementChatError && error.rejected) {
        pendingRequests.current.delete(id); setSendError(failureText(error.code));
      } else {
        setSendError(id ? '发送结果尚未确认，正在读取已保存的状态；未自动重发。' : '新会话创建状态未确认，请重新读取会话列表。');
      }
    } finally {
      if (id && (!selectedRef.current || selectedRef.current === id)) setRefresh(value => value + 1);
      submitting.current = false; setBusy(false);
    }
  };

  return <section className="management-global-chat">
    <header className="management-chat-heading"><div><h1>对话创建</h1><p>描述一次需求，由助手创建管理资产并发布到 PRT。执行和发布结果以保存记录为准。</p></div><Button icon={<ReloadOutlined />} onClick={() => { void loadConversations(); setRefresh(value => value + 1); }}>读取最新状态</Button></header>
    <div className="management-chat-layout">
      <aside className="management-chat-conversations" aria-label="创建会话">
        <div className="management-chat-list-heading"><h2>会话</h2><Button icon={<PlusOutlined />} disabled={busy} onClick={() => void newConversation()}>新建</Button></div>
        {listError ? <Alert type="warning" message={listError} /> : null}
        {conversations.map(item => <button key={item.id} className={item.id === selected ? 'is-selected' : ''} aria-current={item.id === selected ? 'page' : undefined} disabled={busy} onClick={() => choose(item.id)}><strong>{item.title || '未命名会话'}</strong><small>{new Date(item.updatedAt).toLocaleString()}</small></button>)}
        {!conversations.length && !listBusy ? <p className="management-chat-muted">发送需求后会保存为会话。</p> : null}
        {nextPageToken ? <Button type="link" loading={listBusy} onClick={() => void loadConversations(nextPageToken)}>更多会话</Button> : null}
      </aside>
      <div className="management-chat-main">
        <div className="management-chat-messages" ref={viewport} onScroll={event => { const el = event.currentTarget; followLatest.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}>
          {selected && !history ? <p role="status">正在读取已保存的对话…</p> : null}
          {!selected || history?.turns.length === 0 ? <div className="management-chat-empty"><h2>从你的需求开始</h2><p>说明要创建什么、用于什么场景，以及已有的资产或接口信息。</p><p>支持 Skill、业务能力、组件、A2UI Application 和 Workflow，已有手工编辑入口保持可用。</p></div> : null}
          {history?.turns.map(turn => <Turn key={turn.turnId} turn={turn} events={events.filter(event => event.turnId === turn.turnId)} />)}
        </div>
        <div className="management-chat-footer">
          {readError ? <Alert type="warning" showIcon message={readError} /> : null}
          {sendError ? <Alert type="error" showIcon message={sendError} /> : null}
          {history?.mutationsBlocked ? <p className="management-chat-muted">有操作结果待确认：可以继续查询已保存状态，创建和发布操作暂不可重复执行。</p> : null}
          <form onSubmit={event => { event.preventDefault(); void send(); }}>
            <label className="management-chat-input-label" htmlFor="management-chat-message">创建需求</label>
            <Input.TextArea id="management-chat-message" value={draft} onChange={event => setDraft(event.target.value)} placeholder="描述你的需求、目标资产及已有信息" autoSize={{ minRows: 2, maxRows: 6 }} disabled={busy || !ready} />
            <div className="management-chat-compose-actions"><span>{busy ? '正在发送…' : history && !history.canSend ? '当前会话仍在执行，请等待保存结果。' : '默认创建并发布到 PRT'}</span><Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={busy} disabled={!draft.trim() || !ready}>发送需求</Button></div>
          </form>
        </div>
      </div>
    </div>
  </section>;
}
