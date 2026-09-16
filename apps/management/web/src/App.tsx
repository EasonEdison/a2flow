import { useEffect, useMemo, useState } from 'react';
import { ManagementApiError, managementApi } from './api';
import {
  publicationConfirmation, rollbackConfirmation, rollbackTarget,
  settleSaveBuffer, shouldChangeKind,
} from './draft-state';
import {
  KIND_COPY,
  assetKeyOf,
  bufferId,
  createDraftBuffer,
  type AssetKind,
  type AssetSummary,
  type DraftBuffer,
  type JsonObject,
  type ManagementSession,
  type PublicationHistory,
  type PublicationPlan,
  type ValidationReport,
} from './contracts';

type Buffers = Record<string, DraftBuffer>;

function errorText(error: unknown): string {
  if (error instanceof ManagementApiError) {
    if (error.code === 'DRAFT_REVISION_CONFLICT') {
      return '草稿已被其他会话更新。你的未保存内容仍保留在编辑器中，请比对后再处理。';
    }
    if (error.code === 'ADMIN_REQUIRED') return '当前会话没有管理员写权限。';
    if (error.code === 'STALE_SERVING_SELECTION') {
      return '服务选择已更新。请刷新版本历史并重新检查；不会自动重试。';
    }
    return error.code + ' · HTTP ' + error.status;
  }
  if (error instanceof SyntaxError) return '草稿不是有效 JSON，请修正语法后重试。';
  return error instanceof Error ? error.message : 'UNKNOWN_ERROR';
}

function Logo() {
  return (
    <div className="logo" aria-label="A2Flow">
      <span className="logo-mark">A2</span>
      <span>Flow</span>
    </div>
  );
}

function KindNav({
  kinds,
  active,
  onChange,
  disabled,
}: {
  kinds: AssetKind[];
  active: AssetKind | null;
  onChange: (kind: AssetKind) => void;
  disabled: boolean;
}) {
  return (
    <nav className="kind-nav" aria-label="资产类型">
      {kinds.map((kind) => (
        <button
          className={kind === active ? 'kind-link active' : 'kind-link'}
          disabled={disabled}
          key={kind}
          onClick={() => onChange(kind)}
          type="button"
        >
          <span>{KIND_COPY[kind].short}</span>
          {KIND_COPY[kind].label}
        </button>
      ))}
    </nav>
  );
}

function ShellSidebar({
  session,
  activeKind,
  onKindChange,
  disabled,
}: {
  session: ManagementSession;
  activeKind: AssetKind | null;
  onKindChange: (kind: AssetKind) => void;
  disabled: boolean;
}) {
  return (
    <aside className="shell-sidebar">
      <Logo />
      <KindNav kinds={session.registeredKinds} active={activeKind} onChange={onKindChange} disabled={disabled} />
      <div className="session-card">
        <div className="avatar" aria-hidden="true">{session.userId.slice(0, 2).toUpperCase()}</div>
        <div>
          <strong>{session.userId}</strong>
          <span>{session.environment} · {session.canAuthor ? '管理员' : '只读用户'}</span>
        </div>
      </div>
    </aside>
  );
}

function AssetList({
  kind,
  assets,
  selectedKey,
  buffers,
  loading,
  error,
  onSelect,
  disabled,
}: {
  kind: AssetKind;
  assets: AssetSummary[];
  selectedKey: string | null;
  buffers: Buffers;
  loading: boolean;
  error: string | null;
  onSelect: (key: string) => void;
  disabled: boolean;
}) {
  return (
    <section className="asset-rail" aria-label={KIND_COPY[kind].label + ' 列表'}>
      <header className="rail-header">
        <div>
          <p className="section-label">资产目录</p>
          <h1>{KIND_COPY[kind].label}</h1>
        </div>
        <span className="count">{assets.length}</span>
      </header>
      <p className="guidance">{KIND_COPY[kind].guidance}</p>
      {loading ? <div className="rail-state">正在加载列表…</div> : null}
      {error ? <div className="rail-state error">{error}</div> : null}
      {!loading && !error && assets.length === 0 ? (
        <div className="rail-state">当前环境没有已发布资产。</div>
      ) : null}
      <div className="asset-items">
        {assets.map((asset) => {
          const key = assetKeyOf(asset);
          const dirty = buffers[bufferId(kind, key)]?.dirty;
          return (
            <button
              type="button"
              className={selectedKey === key ? 'asset-row selected' : 'asset-row'}
              disabled={disabled}
              key={key}
              onClick={() => onSelect(key)}
            >
              <span className="asset-key">{asset.name ?? key}</span>
              <span className="asset-meta">
                {asset.versionId ?? key}
                {dirty ? <i title="有未保存修改">未保存</i> : null}
              </span>
              {asset.description ? <span className="asset-description">{asset.description}</span> : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function JsonBlock({ value, label }: { value: unknown; label: string }) {
  return (
    <section className="json-card">
      <header>
        <h3>{label}</h3>
      </header>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

function ValidationView({ report }: { report: ValidationReport }) {
  return (
    <section className={report.valid ? 'notice success' : 'notice warning'} aria-live="polite">
      <strong>{report.valid ? '草稿验证通过' : '草稿未通过验证'}</strong>
      {report.valid ? (
        <span>后端已生成规范化候选，可继续准备发布候选。</span>
      ) : (
        <ul>
          {report.issues.map((issue, index) => (
            <li key={issue.code + index}>
              {issue.code}{issue.path ? ' · ' + issue.path : ''}{issue.message ? ' · ' + issue.message : ''}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CandidateView({
  plan, history, busy, onPublish,
}: {
  plan: PublicationPlan;
  history: PublicationHistory;
  busy: boolean;
  onPublish: () => void;
}) {
  const users = plan.target.grayUserIds.length ? plan.target.grayUserIds.join(', ') : '无';
  return (
    <section className="candidate-panel" aria-live="polite">
      <div className="candidate-title">
        <div>
          <p className="section-label">Publication candidate</p>
          <h3>候选已准备，但尚未发布</h3>
        </div>
        <span>NOT PUBLISHED</span>
      </div>
      <p>环境 {plan.target.environment} · 通道 {plan.target.channel} · 版本 {plan.target.versionId} · 灰度用户 {users}</p>
      {plan.target.channel === 'STABLE' ? <p className="candidate-warning">切换 STABLE 会清除当前灰度。</p> : null}
      <div className="candidate-action">
        <small>CAS：{history.servingDigest}</small>
        <button className="primary-button" type="button" disabled={busy} onClick={onPublish}>
          确认并显式发布
        </button>
      </div>
      <details>
        <summary>查看候选 JSON</summary>
        <pre>{JSON.stringify(plan.candidate, null, 2)}</pre>
      </details>
    </section>
  );
}

function HistoryPanel({
  history, canAuthor, busy, onRefresh, onRollback,
}: {
  history: PublicationHistory;
  canAuthor: boolean;
  busy: boolean;
  onRefresh: () => void;
  onRollback: (versionId: string) => void;
}) {
  return (
    <section className="history-panel">
      <div className="history-heading">
        <div><p className="section-label">Retained versions</p><h3>保留版本</h3></div>
        <button className="quiet-button" type="button" disabled={busy} onClick={onRefresh}>刷新历史</button>
      </div>
      <p className="serving-summary">当前选择：{JSON.stringify(history.serving)}</p>
      <div className="version-list">
        {history.versions.map((version) => (
          <div className="version-row" key={version.versionId}>
            <div><strong>{version.versionId}</strong><small>{version.contentDigest}</small></div>
            {canAuthor ? (
              <button className="secondary-button" type="button" disabled={busy}
                onClick={() => onRollback(version.versionId)}>回滚配置到此版本</button>
            ) : null}
          </div>
        ))}
      </div>
      <small>按版本标识列出保留记录；当前 current/stable/gray 选择以上方状态为准。回滚只改配置，不补偿业务。</small>
    </section>
  );
}

function PublicationControls({
  session,
  revision,
  disabled,
  onPrepare,
  onTargetChange,
}: {
  session: ManagementSession;
  revision: number;
  disabled: boolean;
  onPrepare: (versionId: string, channel: string, grayUserIds: string[]) => Promise<void>;
  onTargetChange: () => void;
}) {
  const [versionId, setVersionId] = useState('');
  const [channel, setChannel] = useState(session.environment === 'PRT' ? 'CURRENT' : 'STABLE');
  const [grayUsers, setGrayUsers] = useState('');
  const [working, setWorking] = useState(false);

  async function submit() {
    setWorking(true);
    try {
      const users = channel === 'GRAY'
        ? grayUsers.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)
        : [];
      await onPrepare(versionId.trim(), channel, users);
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="publication-controls">
      <div>
        <label htmlFor="version-id">候选版本标识</label>
        <input
          id="version-id"
          value={versionId}
          disabled={disabled || working}
          maxLength={256}
          onChange={(event) => { setVersionId(event.target.value); onTargetChange(); }}
          placeholder="例如 0.2.0-rc.1"
        />
      </div>
      {session.environment === 'ONLINE' ? (
        <div>
          <label htmlFor="release-channel">目标通道</label>
          <select id="release-channel" disabled={disabled || working} value={channel} onChange={(event) => { setChannel(event.target.value); onTargetChange(); }}>
            <option value="STABLE">STABLE</option>
            <option value="GRAY">GRAY</option>
          </select>
        </div>
      ) : null}
      {channel === 'GRAY' ? (
        <div className="gray-users">
          <label htmlFor="gray-users">灰度用户 ID</label>
          <textarea
            id="gray-users"
            value={grayUsers}
            disabled={disabled || working}
            onChange={(event) => { setGrayUsers(event.target.value); onTargetChange(); }}
            placeholder="每行一个用户 ID"
          />
        </div>
      ) : null}
      <button
        className="secondary-button"
        type="button"
        disabled={disabled || working || !versionId.trim()}
        onClick={submit}
      >
        {working ? '正在准备…' : '准备未发布候选'}
      </button>
      <small>草稿修订 #{revision} · 只生成候选，不执行发布</small>
    </section>
  );
}

function AuthorWorkspace({
  session,
  kind,
  keyName,
  buffer,
  validation,
  plan,
  history,
  actionMessage,
  successMessage,
  actionBusy,
  onEdit,
  onSave,
  onReload,
  onValidate,
  onPrepare,
  onPublish,
  onTargetChange,
}: {
  session: ManagementSession;
  kind: AssetKind;
  keyName: string;
  buffer: DraftBuffer | undefined;
  validation: ValidationReport | null;
  plan: PublicationPlan | null;
  history: PublicationHistory;
  actionMessage: string | null;
  successMessage: string | null;
  actionBusy: boolean;
  onEdit: (value: string) => void;
  onSave: () => void;
  onReload: () => void;
  onValidate: () => void;
  onPrepare: (versionId: string, channel: string, users: string[]) => Promise<void>;
  onPublish: () => void;
  onTargetChange: () => void;
}) {
  if (!buffer) return <div className="workspace-state">正在加载草稿…</div>;
  return (
    <div className="author-workspace">
      <section className="editor-panel">
        <div className="editor-heading">
          <div>
            <p className="section-label">结构化草稿 JSON</p>
            <h2>{kind} · {keyName}</h2>
          </div>
          <span className={buffer.dirty ? 'edit-state dirty' : 'edit-state'}>
            {buffer.dirty ? '未保存' : '已同步'}
          </span>
        </div>
        {buffer.conflict ? (
          <div className="notice warning">
            <strong>修订冲突</strong>
            <span>编辑内容已保留。请先复制需要保留的内容；重新加载会在确认后丢弃当前编辑。</span>
            <button className="warning-button" type="button" disabled={actionBusy} onClick={onReload}>
              重新加载最新草稿
            </button>
          </div>
        ) : null}
        <textarea
          className="json-editor"
          aria-label="结构化草稿 JSON"
          spellCheck={false}
          value={buffer.text}
          disabled={actionBusy}
          onChange={(event) => onEdit(event.target.value)}
        />
        <div className="editor-footer">
          <span>修订 #{buffer.revision} · {buffer.updatedBy}</span>
          <div>
            <button className="quiet-button" type="button" disabled={actionBusy || buffer.dirty} onClick={onValidate}>
              验证已保存草稿
            </button>
            <button className="primary-button" type="button" disabled={actionBusy || !buffer.dirty} onClick={onSave}>
              {actionBusy ? '处理中…' : '保存草稿'}
            </button>
          </div>
        </div>
      </section>
      {actionMessage ? <div className="notice error">{actionMessage}</div> : null}
      {successMessage ? <div className="notice success">{successMessage}</div> : null}
      {validation ? <ValidationView report={validation} /> : null}
      <PublicationControls
        session={session}
        revision={buffer.revision}
        disabled={buffer.dirty || actionBusy || validation?.valid !== true}
        onPrepare={onPrepare}
        onTargetChange={onTargetChange}
      />
      {plan ? <CandidateView plan={plan} history={history} busy={actionBusy} onPublish={onPublish} /> : null}
    </div>
  );
}

function App() {
  const [session, setSession] = useState<ManagementSession | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [kind, setKind] = useState<AssetKind | null>(null);
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<JsonObject | null>(null);
  const [assetLoading, setAssetLoading] = useState(false);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [buffers, setBuffers] = useState<Buffers>({});
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [plan, setPlan] = useState<PublicationPlan | null>(null);
  const [history, setHistory] = useState<PublicationHistory | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    managementApi.session(controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setSession(value);
      setKind(value.registeredKinds[0] ?? null);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setSessionError(errorText(error));
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!kind) return;
    const controller = new AbortController();
    setListLoading(true);
    setListError(null);
    managementApi.list(kind, controller.signal).then((items) => {
      if (controller.signal.aborted) return;
      setAssets(items);
      setSelectedKey((current) => {
        if (current && items.some((item) => assetKeyOf(item) === current)) return current;
        return items[0] ? assetKeyOf(items[0]) : null;
      });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        setAssets([]);
        setSelectedKey(null);
        setListError(errorText(error));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setListLoading(false);
    });
    return () => controller.abort();
  }, [kind]);

  useEffect(() => {
    if (!session || !kind || !selectedKey) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    const currentBufferId = bufferId(kind, selectedKey);
    setAssetLoading(true);
    setAssetError(null);
    setValidation(null);
    setPlan(null);
    setHistory(null);
    setSuccessMessage(null);
    setActionMessage(null);
    const detailRequest = managementApi.detail(kind, selectedKey, controller.signal);
    const draftRequest = session.canAuthor
      ? managementApi.draft(kind, selectedKey, controller.signal)
      : Promise.resolve(null);
    const historyRequest = managementApi.history(kind, selectedKey, controller.signal);
    Promise.all([detailRequest, draftRequest, historyRequest]).then(([nextDetail, draft, nextHistory]) => {
      if (controller.signal.aborted) return;
      setDetail(nextDetail);
      setHistory(nextHistory);
      if (draft) {
        setBuffers((current) => current[currentBufferId]
          ? current
          : { ...current, [currentBufferId]: createDraftBuffer(draft) });
      }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setAssetError(errorText(error));
    }).finally(() => {
      if (!controller.signal.aborted) setAssetLoading(false);
    });
    return () => controller.abort();
  }, [session, kind, selectedKey]);

  const activeBufferId = kind && selectedKey ? bufferId(kind, selectedKey) : null;
  const buffer = activeBufferId ? buffers[activeBufferId] : undefined;
  const selectedSummary = useMemo(
    () => assets.find((asset) => assetKeyOf(asset) === selectedKey) ?? null,
    [assets, selectedKey],
  );

  function changeKind(next: AssetKind) {
    if (!shouldChangeKind(kind, next)) return;
    setKind(next);
    setSelectedKey(null);
    setAssets([]);
  }

  function editDraft(value: string) {
    if (!activeBufferId) return;
    setBuffers((current) => ({
      ...current,
      [activeBufferId]: { ...current[activeBufferId], text: value, dirty: true, conflict: false },
    }));
    setValidation(null);
    setPlan(null);
    setActionMessage(null);
    setSuccessMessage(null);
  }

  async function saveDraft() {
    if (!kind || !selectedKey || !activeBufferId || !buffer) return;
    const submittedText = buffer.text;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const document = JSON.parse(buffer.text) as JsonObject;
      if (!document || Array.isArray(document) || typeof document !== 'object') {
        throw new SyntaxError('DRAFT_MUST_BE_OBJECT');
      }
      const saved = await managementApi.saveDraft(kind, selectedKey, buffer.revision, document);
      setBuffers((current) => ({
        ...current,
        [activeBufferId]: settleSaveBuffer(current[activeBufferId], submittedText, saved),
      }));
      setValidation(null);
      setPlan(null);
    } catch (error) {
      const conflict = error instanceof ManagementApiError && error.code === 'DRAFT_REVISION_CONFLICT';
      if (conflict) {
        setBuffers((current) => ({
          ...current,
          [activeBufferId]: { ...current[activeBufferId], conflict: true },
        }));
      }
      setActionMessage(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  async function reloadDraft() {
    if (!kind || !selectedKey || !activeBufferId) return;
    if (!window.confirm('重新加载会丢弃当前未保存内容。确定继续吗？')) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const latest = await managementApi.draft(kind, selectedKey);
      setBuffers((current) => ({
        ...current,
        [activeBufferId]: createDraftBuffer(latest),
      }));
      setValidation(null);
      setPlan(null);
    } catch (error) {
      setActionMessage(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  async function validateDraft() {
    if (!kind || !selectedKey) return;
    setActionBusy(true);
    setActionMessage(null);
    setPlan(null);
    try {
      setValidation(await managementApi.validate(kind, selectedKey));
    } catch (error) {
      setActionMessage(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  async function refreshPublishedState() {
    if (!kind || !selectedKey) return;
    setActionBusy(true);
    setActionMessage(null);
    setSuccessMessage(null);
    try {
      const [nextHistory, nextDetail, nextAssets] = await Promise.all([
        managementApi.history(kind, selectedKey), managementApi.detail(kind, selectedKey),
        managementApi.list(kind),
      ]);
      setHistory(nextHistory);
      setDetail(nextDetail);
      setAssets(nextAssets);
      setPlan(null);
    } catch (error) {
      setActionMessage(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  async function publishPrepared() {
    if (!kind || !selectedKey || !plan || !history) return;
    if (!window.confirm(publicationConfirmation(plan.target))) return;
    setActionBusy(true);
    setActionMessage(null);
    setSuccessMessage(null);
    try {
      await managementApi.publish(kind, selectedKey, plan, history.servingDigest);
      setPlan(null);
      setSuccessMessage('发布完成：已写入不可变版本并更新服务选择。');
      try {
        const [nextHistory, nextDetail, nextAssets] = await Promise.all([
          managementApi.history(kind, selectedKey), managementApi.detail(kind, selectedKey),
          managementApi.list(kind),
        ]);
        setHistory(nextHistory);
        setDetail(nextDetail);
        setAssets(nextAssets);
      } catch (refreshError) {
        setActionMessage('发布已成功，但刷新失败：' + errorText(refreshError));
      }
    } catch (error) {
      setActionMessage(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  async function rollbackVersion(versionId: string) {
    if (!session || !kind || !selectedKey || !history) return;
    const target = rollbackTarget(session.environment, versionId);
    if (!window.confirm(rollbackConfirmation(target))) return;
    setActionBusy(true);
    setActionMessage(null);
    setSuccessMessage(null);
    try {
      await managementApi.rollback(kind, selectedKey, target, history.servingDigest);
      setPlan(null);
      setSuccessMessage('配置回滚完成；未撤销或补偿任何业务操作。');
      try {
        const [nextHistory, nextDetail, nextAssets] = await Promise.all([
          managementApi.history(kind, selectedKey), managementApi.detail(kind, selectedKey),
          managementApi.list(kind),
        ]);
        setHistory(nextHistory);
        setDetail(nextDetail);
        setAssets(nextAssets);
      } catch (refreshError) {
        setActionMessage('回滚已成功，但刷新失败：' + errorText(refreshError));
      }
    } catch (error) {
      setActionMessage(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  async function prepareCandidate(versionId: string, channel: string, grayUserIds: string[]) {
    if (!session || !kind || !selectedKey || !buffer) return;
    setActionBusy(true);
    setActionMessage(null);
    setSuccessMessage(null);
    setPlan(null);
    try {
      const nextPlan = await managementApi.prepare(kind, selectedKey, buffer.revision, {
        environment: session.environment,
        versionId,
        channel,
        grayUserIds,
      });
      setPlan(nextPlan);
    } catch (error) {
      setActionMessage(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  if (sessionError) {
    return <main className="boot-state"><Logo /><h1>无法进入管理台</h1><p>{sessionError}</p></main>;
  }
  if (!session) {
    return <main className="boot-state"><Logo /><p>正在读取可信会话…</p></main>;
  }

  return (
    <div className="app-shell">
      <ShellSidebar
        session={session}
        activeKind={kind}
        onKindChange={changeKind}
        disabled={actionBusy}
      />
      {kind ? (
        <AssetList
          kind={kind}
          assets={assets}
          selectedKey={selectedKey}
          buffers={buffers}
          loading={listLoading}
          error={listError}
          onSelect={setSelectedKey}
          disabled={actionBusy}
        />
      ) : null}
      <main className="content">
        {!selectedKey || !kind ? (
          <div className="empty-content">
            <h2>选择一个资产</h2>
            <p>从左侧目录打开已发布版本与管理草稿。</p>
          </div>
        ) : (
          <>
            <header className="content-header">
              <div>
                <p className="section-label">{KIND_COPY[kind].label} · {session.environment}</p>
                <h1>{selectedSummary?.name ?? selectedKey}</h1>
                <p>{selectedKey}</p>
              </div>
              <div className="header-status">
                <span className="published-status">已发布版本</span>
                <span className={session.canAuthor ? 'role-status admin' : 'role-status'}>
                  {session.canAuthor ? '可编辑草稿' : '只读'}
                </span>
              </div>
            </header>
            {assetLoading ? <div className="workspace-state">正在读取资产…</div> : null}
            {assetError ? <div className="notice error">{assetError}</div> : null}
            {!assetLoading && !assetError && detail ? (
              <>
                <JsonBlock value={detail} label="当前已发布详情" />
                {history ? <HistoryPanel history={history} canAuthor={session.canAuthor} busy={actionBusy}
                  onRefresh={() => void refreshPublishedState()} onRollback={rollbackVersion} /> : null}
                {session.canAuthor && history ? (
                  <AuthorWorkspace
                    session={session}
                    kind={kind}
                    keyName={selectedKey}
                    buffer={buffer}
                    validation={validation}
                    plan={plan}
                    history={history}
                    actionMessage={actionMessage}
                    successMessage={successMessage}
                    actionBusy={actionBusy}
                    onEdit={editDraft}
                    onSave={saveDraft}
                    onReload={reloadDraft}
                    onValidate={validateDraft}
                    onPrepare={prepareCandidate}
                    onPublish={publishPrepared}
                    onTargetChange={() => { setPlan(null); setSuccessMessage(null); }}
                  />
                ) : (
                  <section className="readonly-panel">
                    <strong>当前会话为只读</strong>
                    <p>你可以浏览已发布资产，但不能读取、保存或验证管理草稿。</p>
                  </section>
                )}
              </>
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}

export default App;
