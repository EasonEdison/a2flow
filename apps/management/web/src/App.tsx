import { useEffect, useMemo, useRef, useState } from 'react';
import { initialApplicationPreviewState, type ApplicationPreviewState } from './A2UIWorkbench';
import { ManagementApiError, managementApi } from './api';
import { DiffView } from './DiffView';
import { diffValues } from './structured-diff';
import { filterAssets } from './asset-filter';
import { FormEditor } from './FormEditors';
import {
  applyPendingField, createPendingFieldState, discardPendingField, editPendingField, inspectDraftText,
  pendingFieldConflict, reconcilePendingFields, type PendingFields,
} from './form-editor-state';
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
  type ReferenceCatalog,
  type RetainedVersion,
  type ValidationReport,
} from './contracts';

type Buffers = Record<string, DraftBuffer>;
type PendingBuffers = Record<string, PendingFields>;
type PreviewBuffers = Record<string, ApplicationPreviewState>;

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
  query,
  onQueryChange,
  selectedKey,
  buffers,
  loading,
  error,
  onSelect,
  onCreate,
  canAuthor,
  disabled,
}: {
  kind: AssetKind;
  assets: AssetSummary[];
  query: string;
  onQueryChange: (query: string) => void;
  selectedKey: string | null;
  buffers: Buffers;
  loading: boolean;
  error: string | null;
  onSelect: (key: string) => void;
  onCreate: () => void;
  canAuthor: boolean;
  disabled: boolean;
}) {
  const filteredAssets = useMemo(() => filterAssets(assets, query), [assets, query]);
  const hasQuery = query.trim().length > 0;

  return (
    <section className="asset-rail" aria-label={KIND_COPY[kind].label + ' 列表'}>
      <header className="rail-header">
        <div>
          <p className="section-label">资产目录</p>
          <h1>{KIND_COPY[kind].label}</h1>
        </div>
        <div className="rail-actions"><span className="count" aria-label={`匹配 ${filteredAssets.length} 项，共 ${assets.length} 项`}>
          {filteredAssets.length}/{assets.length}
        </span>{canAuthor ? <button type="button" className="secondary-button" disabled={disabled} onClick={onCreate}>新建</button> : null}</div>
      </header>
      <p className="guidance">{KIND_COPY[kind].guidance}</p>
      <div className="asset-search">
        <label htmlFor="asset-search">搜索当前资产类型</label>
        <div className="asset-search-control">
          <input
            id="asset-search"
            type="search"
            value={query}
            disabled={disabled}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="按名称或标识符搜索"
          />
          <button type="button" disabled={disabled || !query} onClick={() => onQueryChange('')}>
            清除
          </button>
        </div>
        <span className="search-count" aria-live="polite">匹配 {filteredAssets.length} 项，共 {assets.length} 项</span>
      </div>
      {loading ? <div className="rail-state">正在加载列表…</div> : null}
      {error ? <div className="rail-state error">{error}</div> : null}
      {!loading && !error && assets.length === 0 ? (
        <div className="rail-state">当前环境没有已发布资产。</div>
      ) : null}
      {!loading && !error && assets.length > 0 && hasQuery && filteredAssets.length === 0 ? (
        <div className="rail-state no-match">没有匹配的资产，请调整搜索条件。</div>
      ) : null}
      <div className="asset-items">
        {filteredAssets.map((asset) => {
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
                {asset.draftOnly ? '仅草稿' : asset.versionId ?? key}
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

function CreateDialog({ kind, busy, error, onCancel, onCreate }: {
  kind: AssetKind; busy: boolean; error: string | null; onCancel: () => void;
  onCreate: (key: string) => void;
}) {
  const [key, setKey] = useState('');
  return <div className="dialog-backdrop"><section className="create-dialog" role="dialog" aria-modal="true" aria-label={`新建 ${kind}`}>
    <p className="section-label">Draft only</p><h2>新建 {KIND_COPY[kind].label}</h2>
    <label className="form-field"><span>不可变 Key</span><input autoFocus value={key} maxLength={256} disabled={busy}
      onChange={(event) => setKey(event.target.value)} /></label>
    <p>将创建未发布草稿；模板中的执行与引用字段保持未配置。</p>
    {error ? <div className="notice error">{error}</div> : null}
    <div className="dialog-actions"><button type="button" className="quiet-button" disabled={busy} onClick={onCancel}>取消</button>
      <button type="button" className="primary-button" disabled={busy || !key} onClick={() => onCreate(key)}>{busy ? '正在创建…' : '创建草稿'}</button></div>
  </section></div>;
}

function ComparisonPanel({ kind, keyName, history, buffer, pendingCount }: {
  kind: AssetKind; keyName: string; history: PublicationHistory; buffer?: DraftBuffer; pendingCount: number;
}) {
  const firstVersion = history.versions[0]?.versionId ?? '';
  const secondVersion = history.versions[1]?.versionId ?? firstVersion;
  const [left, setLeft] = useState(firstVersion);
  const [right, setRight] = useState(buffer ? 'DRAFT' : secondVersion);
  const [documents, setDocuments] = useState<Record<string, RetainedVersion>>({});
  const [canonicalDraft, setCanonicalDraft] = useState<JsonObject | undefined>();
  const [draftError, setDraftError] = useState<string | null>(null);
  const [versionError, setVersionError] = useState<string | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [versionLoading, setVersionLoading] = useState(false);
  const [requestEpoch, setRequestEpoch] = useState(0);
  const [comparedText, setComparedText] = useState<string | null>(null);
  const compareController = useRef<AbortController | null>(null);
  const compareEpoch = useRef(0);
  const bufferText = buffer?.text;
  const comparisonStale = canonicalDraft !== undefined && comparedText !== bufferText;
  useEffect(() => {
    const nextFirst = history.versions[0]?.versionId ?? '';
    const nextSecond = history.versions[1]?.versionId ?? nextFirst;
    compareController.current?.abort();
    compareEpoch.current += 1;
    setLeft(nextFirst);
    setRight(buffer ? 'DRAFT' : nextSecond);
    setDocuments({});
    setCanonicalDraft(undefined);
    setComparedText(null);
    setDraftLoading(false);
    setDraftError(null);
    setVersionError(null);
    setRequestEpoch((current) => current + 1);
    return () => compareController.current?.abort();
  }, [kind, keyName, history, Boolean(buffer)]);
  useEffect(() => {
    const versions = [...new Set([left, right].filter((value) => value && value !== 'DRAFT'))];
    if (!versions.length) return;
    const controller = new AbortController();
    const epoch = requestEpoch;
    setVersionLoading(true);
    setVersionError(null);
    Promise.all(versions.map((version) => managementApi.version(kind, keyName, version, controller.signal)))
      .then((values) => {
        if (!controller.signal.aborted && epoch === requestEpoch) {
          setDocuments(Object.fromEntries(values.map((value) => [value.versionId, value])));
        }
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setVersionError(errorText(reason)); })
      .finally(() => { if (!controller.signal.aborted) setVersionLoading(false); });
    return () => controller.abort();
  }, [kind, keyName, left, right, requestEpoch]);
  async function compareDraft() {
    const snapshot = buffer?.text;
    if (snapshot === undefined) {
      compareController.current?.abort();
      compareEpoch.current += 1;
      setCanonicalDraft(undefined);
      setComparedText(null);
      setDraftLoading(false);
      setDraftError('没有可比较的草稿。');
      return;
    }
    const inspected = inspectDraftText(snapshot);
    if (!inspected.ok) {
      compareController.current?.abort();
      compareEpoch.current += 1;
      setCanonicalDraft(undefined);
      setComparedText(null);
      setDraftLoading(false);
      setDraftError(inspected.error);
      return;
    }
    compareController.current?.abort();
    const controller = new AbortController();
    const epoch = compareEpoch.current + 1;
    compareEpoch.current = epoch;
    compareController.current = controller;
    setDraftLoading(true);
    setDraftError(null);
    try {
      const document = await managementApi.comparisonDocument(
        kind, keyName, inspected.document, controller.signal);
      if (!controller.signal.aborted && epoch === compareEpoch.current) {
        setCanonicalDraft(document);
        setComparedText(snapshot);
      }
    } catch (reason) {
      if (!controller.signal.aborted && epoch === compareEpoch.current) {
        setCanonicalDraft(undefined);
        setComparedText(null);
        setDraftError(errorText(reason));
      }
    } finally {
      if (!controller.signal.aborted && epoch === compareEpoch.current) {
        setDraftLoading(false);
        compareController.current = null;
      }
    }
  }
  function selectRetainedSide(side: 'left' | 'right', value: string) {
    compareController.current?.abort();
    compareEpoch.current += 1;
    setDraftLoading(false);
    setDraftError(null);
    if (side === 'left') setLeft(value);
    else {
      setRight(value);
      setCanonicalDraft(undefined);
      setComparedText(null);
    }
  }
  if (!history.versions.length) return <section className="history-panel"><h3>版本比较</h3><p>该资产尚无已发布版本，无法比较。</p></section>;
  const value = (side: string) => side === 'DRAFT' ? canonicalDraft : documents[side]?.document;
  const leftValue = value(left); const rightValue = value(right);
  const loading = draftLoading || versionLoading;
  const error = draftError ?? versionError;
  return <section className="history-panel"><div className="history-heading"><div><p className="section-label">Read-only comparison</p><h3>版本比较</h3></div></div>
    <div className="compare-controls"><select aria-label="比较左侧" value={left} onChange={(event) => selectRetainedSide('left', event.target.value)}>{history.versions.map((version) => <option key={version.versionId}>{version.versionId}</option>)}</select>
      <select aria-label="比较右侧" value={right} onChange={(event) => selectRetainedSide('right', event.target.value)}>{buffer ? <option value="DRAFT">当前 canonical 草稿</option> : null}{history.versions.map((version) => <option key={version.versionId}>{version.versionId}</option>)}</select>
      {buffer && right === 'DRAFT' ? <button type="button" className="secondary-button" disabled={draftLoading} onClick={() => void compareDraft()}>{comparisonStale ? '刷新过时比较' : canonicalDraft ? '更新草稿比较' : '比较当前草稿'}</button> : null}</div>
    {right === 'DRAFT' && canonicalDraft === undefined && !draftError ? <p>点击“比较当前草稿”读取当前 canonical 草稿；尚未应用的字段 JSON 不会包含。</p> : null}
    {right === 'DRAFT' && comparisonStale ? <p className="notice warning">比较内容已过时，请显式刷新后再查看当前 canonical 草稿。</p> : null}
    {pendingCount ? <p className="notice warning">{pendingCount} 个尚未应用的字段 JSON 不包含在 canonical 草稿比较中。</p> : null}
    {loading ? <p>正在读取比较内容…</p> : null}{error ? <div className="notice error">{error}</div> : null}
    {!loading && !error && leftValue !== undefined && rightValue !== undefined ? <DiffView entries={diffValues(leftValue, rightValue)} leftLabel={left} rightLabel={right === 'DRAFT' ? comparisonStale ? '过时 canonical 草稿快照' : '当前 canonical 草稿' : right} /> : null}
  </section>;
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

const ISSUE_FIELD_LABELS: Record<string, string> = {
  '/metadata/name': '名称',
  '/metadata/description': '描述',
  '/modelArgumentSchema': 'Model argument schema',
  '/resolvedInputSchema': 'Resolved input schema',
  '/outputSchema': 'Output schema',
  '/definition/surfaceTemplate': 'Surface template',
  '/definition/surfaceTemplate/inputSchema': 'Parameter schema',
  '/definition/renderPolicy/interactionMode': 'Mode',
  '/topology': 'Topology（只读，不会自动转换）',
};

function focusValidationPath(path?: string) {
  const label = path ? ISSUE_FIELD_LABELS[path] : undefined;
  if (!label) return;
  const control = document.querySelector<HTMLElement>(`[aria-label="${CSS.escape(label)}"]`)
    ?? [...document.querySelectorAll<HTMLLabelElement>('label')].find((item) => item.textContent?.includes(label))?.querySelector<HTMLElement>('input, textarea, select');
  control?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  control?.focus();
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
              {ISSUE_FIELD_LABELS[issue.path ?? ''] ? <button type="button" className="issue-link" onClick={() => focusValidationPath(issue.path)}>
                {issue.code}{issue.path ? ' · ' + issue.path : ''}{issue.message ? ' · ' + issue.message : ''}
              </button> : <span>{issue.code}{issue.path ? ' · ' + issue.path : ''}{issue.message ? ' · ' + issue.message : ''}</span>}
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
  pendingFields,
  previewState,
  references,
  onEdit,
  onPendingChange,
  onApplyPending,
  onDiscardPending,
  onPreviewStateChange,
  getPendingConflict,
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
  pendingFields: PendingFields;
  previewState: ApplicationPreviewState;
  references: ReferenceCatalog;
  onEdit: (value: string) => void;
  onPendingChange: (path: string[], text: string, expected: 'object' | 'array', baseValue: unknown) => void;
  onApplyPending: (path: string[], expected: 'object' | 'array') => void;
  onDiscardPending: (path: string[]) => void;
  onPreviewStateChange: (state: ApplicationPreviewState) => void;
  getPendingConflict: (path: string[]) => string | null;
  onSave: () => void;
  onReload: () => void;
  onValidate: () => void;
  onPrepare: (versionId: string, channel: string, users: string[]) => Promise<void>;
  onPublish: () => void;
  onTargetChange: () => void;
}) {
  const [mode, setMode] = useState<'FORM' | 'JSON'>('FORM');
  if (!buffer) return <div className="workspace-state">正在加载草稿…</div>;
  const inspection = inspectDraftText(buffer.text);
  const invalidDraft = !inspection.ok;
  const pendingJsonField = Object.keys(pendingFields).length > 0;
  return (
    <div className="author-workspace">
      <section className="editor-panel">
        <div className="editor-heading">
          <div>
            <p className="section-label">管理草稿编辑器</p>
            <h2>{kind} · {keyName}</h2>
          </div>
          <div className="editor-heading-actions">
            <div className="mode-switch" role="group" aria-label="编辑模式">
              <button type="button" className={mode === 'FORM' ? 'active' : ''} disabled={actionBusy || invalidDraft}
                onClick={() => setMode('FORM')}>表单</button>
              <button type="button" className={mode === 'JSON' ? 'active' : ''} disabled={actionBusy}
                onClick={() => setMode('JSON')}>完整 JSON</button>
            </div>
            <span className={buffer.dirty ? 'edit-state dirty' : 'edit-state'}>
              {buffer.dirty ? '未保存' : '已同步'}
            </span>
          </div>
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
        {invalidDraft ? <div className="notice warning invalid-json"><strong>完整 JSON 当前无效</strong><span>{inspection.error}</span><span>内容不会被重置；修正前不能保存、验证或发布，也不能进入表单模式。</span></div> : null}
        {pendingJsonField ? <div className="notice warning invalid-json"><strong>存在尚未应用的字段 JSON</strong><span>canonical 草稿尚未改变。请在表单中明确应用或丢弃；切换资产或模式不会清除字段文本。</span></div> : null}
        {mode === 'JSON' || invalidDraft ? (
          <textarea
            className="json-editor"
            aria-label="结构化草稿 JSON"
            spellCheck={false}
            value={buffer.text}
            disabled={actionBusy}
            onChange={(event) => onEdit(event.target.value)}
          />
        ) : <FormEditor kind={kind} text={buffer.text} disabled={actionBusy} pendingFields={pendingFields} references={references} previewState={previewState} onPreviewStateChange={onPreviewStateChange} onEdit={onEdit}
          onPendingChange={onPendingChange} onApplyPending={onApplyPending} onDiscardPending={onDiscardPending}
          getPendingConflict={getPendingConflict} />}
        <div className="editor-footer">
          <span>修订 #{buffer.revision} · {buffer.updatedBy}</span>
          <div>
            <button className="quiet-button" type="button" disabled={actionBusy || buffer.dirty || invalidDraft || pendingJsonField} onClick={onValidate}>
              验证已保存草稿
            </button>
            <button className="primary-button" type="button" disabled={actionBusy || !buffer.dirty || invalidDraft || pendingJsonField} onClick={onSave}>
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
        disabled={buffer.dirty || actionBusy || invalidDraft || pendingJsonField || validation?.valid !== true}
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
  const [searchQuery, setSearchQuery] = useState('');
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<JsonObject | null>(null);
  const [assetLoading, setAssetLoading] = useState(false);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [buffers, setBuffers] = useState<Buffers>({});
  const [pendingBuffers, setPendingBuffers] = useState<PendingBuffers>({});
  const [previewBuffers, setPreviewBuffers] = useState<PreviewBuffers>({});
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [plan, setPlan] = useState<PublicationPlan | null>(null);
  const [history, setHistory] = useState<PublicationHistory | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [references, setReferences] = useState<ReferenceCatalog>({ loading: false, errors: {}, assets: {}, histories: {} });
  const [referenceRefresh, setReferenceRefresh] = useState(0);

  useEffect(() => {
    const dirty = Object.values(buffers).some((item) => item.dirty)
      || Object.values(pendingBuffers).some((item) => Object.keys(item).length > 0);
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [buffers, pendingBuffers]);

  useEffect(() => {
    if (!session?.canAuthor) return;
    const controller = new AbortController();
    setReferences((current) => ({ ...current, loading: true }));
    const kinds: AssetKind[] = ['SKILL', 'ABILITY', 'APPLICATION'];
    Promise.all(kinds.map(async (referenceKind) => {
      try { return [referenceKind, await managementApi.list(referenceKind, controller.signal)] as const; }
      catch (error) { return [referenceKind, error] as const; }
    })).then(async (results) => {
      if (controller.signal.aborted) return;
      const nextAssets: ReferenceCatalog['assets'] = {};
      const errors: ReferenceCatalog['errors'] = {};
      for (const [referenceKind, value] of results) {
        if (Array.isArray(value)) nextAssets[referenceKind] = value.filter((item) => !item.draftOnly);
        else errors[referenceKind] = errorText(value);
      }
      const historyEntries = await Promise.all((nextAssets.ABILITY ?? []).map(async (item): Promise<[string, PublicationHistory | Error]> => {
        const key = assetKeyOf(item);
        try { return [`ABILITY:${key}`, await managementApi.history('ABILITY', key, controller.signal)]; }
        catch (error) { return [`ABILITY:${key}`, error instanceof Error ? error : new Error(errorText(error))]; }
      }));
      const histories: Record<string, PublicationHistory> = {};
      for (const [catalogKey, value] of historyEntries) {
        if (value instanceof Error) errors[catalogKey] = errorText(value);
        else histories[catalogKey] = value;
      }
      if (!controller.signal.aborted) setReferences({
        loading: false, errors, assets: nextAssets, histories,
        retry: () => setReferenceRefresh((current) => current + 1),
      });
    });
    return () => controller.abort();
  }, [session, referenceRefresh]);

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

  const selectedSummary = useMemo(
    () => assets.find((asset) => assetKeyOf(asset) === selectedKey) ?? null,
    [assets, selectedKey],
  );

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
    const detailRequest = selectedSummary?.draftOnly
      ? Promise.resolve(null)
      : managementApi.detail(kind, selectedKey, controller.signal);
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
  }, [session, kind, selectedKey, selectedSummary?.draftOnly]);

  const activeBufferId = kind && selectedKey ? bufferId(kind, selectedKey) : null;
  const buffer = activeBufferId ? buffers[activeBufferId] : undefined;
  const pendingFields = activeBufferId ? pendingBuffers[activeBufferId] ?? createPendingFieldState() : createPendingFieldState();
  const previewState = activeBufferId ? previewBuffers[activeBufferId] ?? initialApplicationPreviewState() : initialApplicationPreviewState();

  async function createDraft(keyName: string) {
    if (!kind) return;
    setActionBusy(true);
    setCreateError(null);
    try {
      const created = await managementApi.createDraft(kind, keyName);
      const summary: AssetSummary = { kind, key: keyName, draftOnly: true, draftRevision: created.revision };
      setAssets((current) => [...current.filter((item) => assetKeyOf(item) !== keyName), summary]
        .sort((left, right) => assetKeyOf(left).localeCompare(assetKeyOf(right))));
      setBuffers((current) => ({ ...current, [bufferId(kind, keyName)]: createDraftBuffer(created) }));
      setSelectedKey(keyName);
      setCreateOpen(false);
    } catch (error) {
      setCreateError(errorText(error));
    } finally {
      setActionBusy(false);
    }
  }

  function changeKind(next: AssetKind) {
    if (!shouldChangeKind(kind, next)) return;
    setKind(next);
    setSearchQuery('');
    setSelectedKey(null);
    setHistory(null);
    setDetail(null);
    setAssets([]);
  }

  function editDraft(value: string) {
    if (!activeBufferId || !buffer) return;
    const nextInspection = inspectDraftText(value);
    if (nextInspection.ok) {
      setPendingBuffers((current) => ({
        ...current,
        [activeBufferId]: reconcilePendingFields(current[activeBufferId] ?? {}, nextInspection.document),
      }));
    }
    setBuffers((current) => ({
      ...current,
      [activeBufferId]: { ...current[activeBufferId], text: value, dirty: true },
    }));
    setValidation(null);
    setPlan(null);
    setActionMessage(null);
    setSuccessMessage(null);
  }

  function changePendingField(path: string[], text: string, expected: 'object' | 'array', baseValue: unknown) {
    if (!activeBufferId) return;
    setPendingBuffers((current) => ({
      ...current,
      [activeBufferId]: editPendingField(current[activeBufferId] ?? {}, path, text, expected, baseValue),
    }));
    setValidation(null);
    setPlan(null);
  }

  function applyPending(path: string[], expected: 'object' | 'array') {
    if (!activeBufferId || !buffer) return;
    const inspection = inspectDraftText(buffer.text);
    if (!inspection.ok) return;
    const result = applyPendingField(inspection.document, pendingFields, path, expected);
    setPendingBuffers((current) => ({ ...current, [activeBufferId]: result.pending }));
    if (result.applied) editDraft(JSON.stringify(result.document, null, 2));
  }

  function discardPending(path: string[]) {
    if (!activeBufferId || !buffer) return;
    const inspection = inspectDraftText(buffer.text);
    if (!inspection.ok || !window.confirm('丢弃该字段尚未应用的文本并恢复 canonical 值？')) return;
    const result = discardPendingField(inspection.document, pendingFields, path);
    setPendingBuffers((current) => ({ ...current, [activeBufferId]: result.pending }));
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
    const pendingCount = Object.keys(pendingFields).length;
    if (!window.confirm(`重新加载会丢弃当前未保存内容${pendingCount ? `和 ${pendingCount} 个尚未应用的字段编辑` : ''}。确定继续吗？`)) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const latest = await managementApi.draft(kind, selectedKey);
      setBuffers((current) => ({
        ...current,
        [activeBufferId]: createDraftBuffer(latest),
      }));
      setPendingBuffers((current) => ({ ...current, [activeBufferId]: createPendingFieldState() }));
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
        setReferenceRefresh((current) => current + 1);
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
        setReferenceRefresh((current) => current + 1);
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
          query={searchQuery}
          onQueryChange={setSearchQuery}
          selectedKey={selectedKey}
          buffers={buffers}
          loading={listLoading}
          error={listError}
          onSelect={setSelectedKey}
          onCreate={() => { setCreateError(null); setCreateOpen(true); }}
          canAuthor={session.canAuthor}
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
                <span className="published-status">{selectedSummary?.draftOnly ? '仅草稿' : '已发布版本'}</span>
                <span className={session.canAuthor ? 'role-status admin' : 'role-status'}>
                  {session.canAuthor ? '可编辑草稿' : '只读'}
                </span>
              </div>
            </header>
            {assetLoading ? <div className="workspace-state">正在读取资产…</div> : null}
            {assetError ? <div className="notice error">{assetError}</div> : null}
            {!assetLoading && !assetError && (detail || selectedSummary?.draftOnly) ? (
              <>
                {detail ? <JsonBlock value={detail} label="当前已发布详情" /> : <section className="readonly-panel"><strong>仅草稿</strong><p>尚无已发布版本；不会显示虚构版本或历史。</p></section>}
                {history ? <HistoryPanel history={history} canAuthor={session.canAuthor && history.versions.length > 0} busy={actionBusy}
                  onRefresh={() => void refreshPublishedState()} onRollback={rollbackVersion} /> : null}
                {history ? <ComparisonPanel key={`${kind}:${selectedKey}`} kind={kind} keyName={selectedKey} history={history} buffer={session.canAuthor ? buffer : undefined} pendingCount={Object.keys(pendingFields).length} /> : null}
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
                    pendingFields={pendingFields}
                    previewState={previewState}
                    references={references}
                    onEdit={editDraft}
                    onPendingChange={changePendingField}
                    onApplyPending={applyPending}
                    onDiscardPending={discardPending}
                    onPreviewStateChange={(state) => { if (activeBufferId) setPreviewBuffers((current) => ({ ...current, [activeBufferId]: state })); }}
                    getPendingConflict={(path) => pendingFieldConflict(pendingFields, path)}
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
      {createOpen && kind ? <CreateDialog kind={kind} busy={actionBusy} error={createError}
        onCancel={() => setCreateOpen(false)} onCreate={(keyName) => void createDraft(keyName)} /> : null}
    </div>
  );
}

export default App;
