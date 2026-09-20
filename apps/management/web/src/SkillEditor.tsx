import { useEffect, useRef, useState } from 'react';
import { isEditableRecord, skillFrontmatterMismatch, updatePath } from './form-editor-state';
import { Field, MalformedValue, Section, type FormProps } from './EditorControls';
import { SkillBindingWorkbench } from './SkillBindingWorkbench';
import { MarkdownPreview } from './MarkdownPreview';
import {
  acceptsAsyncTarget, activateAsyncLifecycle, applyPendingText, asyncTarget, checkPackage, createResource, createTextResource,
  inspectResourceVerified, mediaTypeForPath, pathIssue, pendingText, resourceIdentity,
  resourceIdentityIssue,
} from './skill-resource-state';
import { StringRows } from './StringRows';

function nextHandle(path: string, resources: unknown[]) {
  const base = path.toLowerCase().replace(/[^a-z0-9._:-]+/g, '-').replace(/^-+|-+$/g, '') || 'resource';
  const used = new Set(resources.filter(isEditableRecord).map((item) => item.handleId));
  let value = base;
  let suffix = 2;
  while (used.has(value)) value = `${base}-${suffix++}`;
  return value;
}

function ResourceWorkbench({ document, disabled, assetId, revision, pendingResources, onPendingResourcesChange, onChange }: FormProps) {
  const resources = document.resources;
  const list = Array.isArray(resources) ? resources : null;
  const [selected, setSelected] = useState<string | null>(null);
  const [inspection, setInspection] = useState<{ key: string; value: Awaited<ReturnType<typeof inspectResourceVerified>> } | null>(null);
  const [newPath, setNewPath] = useState('');
  const newPathRef = useRef(newPath);
  newPathRef.current = newPath;
  const [error, setError] = useState<string | null>(null);
  const operationSequence = useRef(0);
  const inspectionSequence = useRef(0);
  const mounted = useRef(false);
  const selectIdentity = (item: unknown, index: number) => {
    const base = resourceIdentity(item, index);
    return list && resourceIdentityIssue(item, list) ? `${base}:duplicate:${index}` : base;
  };
  const current = list?.find((item, index) => selectIdentity(item, index) === selected);
  const currentIndex = list?.findIndex((item, index) => selectIdentity(item, index) === selected) ?? -1;
  const identity = current ? resourceIdentity(current, currentIndex) : null;
  const inspectionKey = identity ? `${assetId}\n${revision}\n${identity}\n${current ? JSON.stringify(current) : ''}` : '';
  const identityIssue = current && list ? resourceIdentityIssue(current, list) : null;
  const currentCanonical = current ? JSON.stringify(current) : null;
  const pending = identity ? pendingResources[identity] : undefined;
  const local = list ? checkPackage(list) : null;
  const live = useRef({ document, disabled, assetId, revision, pendingResources, onPendingResourcesChange, onChange });
  live.current = { document, disabled, assetId, revision, pendingResources, onPendingResourcesChange, onChange };

  useEffect(() => activateAsyncLifecycle(mounted, operationSequence, inspectionSequence), []);

  useEffect(() => {
    if (!list?.length) { setSelected(null); return; }
    if (!list.some((item, index) => selectIdentity(item, index) === selected)) setSelected(selectIdentity(list[0], 0));
  }, [resources, selected]);

  useEffect(() => {
    const snapshot = current;
    const sequence = ++inspectionSequence.current;
    const target = identity ? asyncTarget(assetId, revision, identity, sequence) : '';
    setInspection(snapshot ? { key: inspectionKey, value: { status: 'verifying', reason: 'VERIFYING_DIGEST' } } : null);
    if (!snapshot || !identity) return;
    let active = true;
    void inspectResourceVerified(snapshot).then((result) => {
      const state = live.current;
      const latest = asyncTarget(state.assetId, state.revision, identity, inspectionSequence.current);
      if (active && mounted.current && acceptsAsyncTarget(target, latest)) setInspection({ key: inspectionKey, value: result });
    });
    return () => { active = false; };
  }, [assetId, revision, identity, currentCanonical]);

  const currentInspection = inspection?.key === inspectionKey ? inspection.value : current ? { status: 'verifying' as const, reason: 'VERIFYING_DIGEST' } : null;

  if (!list) return <Section title="资源"><MalformedValue label="resources" value={resources} /></Section>;

  async function applyText() {
    if (!current || !pending || !identity || identityIssue || disabled || currentInspection?.status !== 'editable') return;
    const sequence = ++operationSequence.current;
    const target = asyncTarget(assetId, revision, identity, sequence);
    const canonicalSnapshot = JSON.stringify(current);
    const documentSnapshot = JSON.stringify(document);
    const pendingSnapshot = JSON.stringify(pending);
    let result: Awaited<ReturnType<typeof applyPendingText>>;
    try {
      result = await applyPendingText(current, pending);
    } catch (reason) {
      const state = live.current;
      const latestPending = state.pendingResources[identity];
      const fresh = mounted.current && !state.disabled
        && acceptsAsyncTarget(target, asyncTarget(state.assetId, state.revision, identity, operationSequence.current))
        && JSON.stringify(state.document) === documentSnapshot
        && JSON.stringify(latestPending) === pendingSnapshot;
      if (fresh) setError(reason instanceof Error ? reason.message : 'SHA256_DIGEST_FAILED');
      return;
    }
    const state = live.current;
    const latestPending = state.pendingResources[identity];
    const fresh = mounted.current && !state.disabled
      && acceptsAsyncTarget(target, asyncTarget(state.assetId, state.revision, identity, operationSequence.current))
      && JSON.stringify(state.document) === documentSnapshot
      && JSON.stringify(latestPending) === pendingSnapshot;
    if (!fresh) return;
    if (result.error) { setError(result.error); return; }
    const currentResources = Array.isArray(state.document.resources) ? state.document.resources : [];
    const matches = currentResources.map((item, index) => ({ item, index })).filter(({ item, index }) => resourceIdentity(item, index) === identity);
    if (matches.length !== 1 || JSON.stringify(matches[0].item) !== canonicalSnapshot) return;
    const nextResources = currentResources.slice();
    nextResources[matches[0].index] = result.resource;
    const nextPending = { ...state.pendingResources };
    delete nextPending[identity];
    state.onChange(updatePath(state.document, ['resources'], nextResources));
    state.onPendingResourcesChange(nextPending);
    setError(null);
  }

  async function addText() {
    const sequence = ++operationSequence.current;
    const target = asyncTarget(assetId, revision, 'new-text', sequence);
    const documentSnapshot = JSON.stringify(document);
    const path = newPath.trim();
    try {
      const resource = await createTextResource({ handleId: nextHandle(path, list!), logicalPath: path, mediaType: mediaTypeForPath(path) ?? 'text/plain', text: '', resources: list! });
      const state = live.current;
      if (!mounted.current || state.disabled || newPathRef.current.trim() !== path
        || !acceptsAsyncTarget(target, asyncTarget(state.assetId, state.revision, 'new-text', operationSequence.current))
        || JSON.stringify(state.document) !== documentSnapshot) return;
      const currentResources = Array.isArray(state.document.resources) ? state.document.resources : [];
      state.onChange(updatePath(state.document, ['resources'], [...currentResources, resource]));
      setSelected(resourceIdentity(resource));
      setNewPath('');
      setError(null);
    } catch (reason) {
      const state = live.current;
      if (mounted.current && acceptsAsyncTarget(target, asyncTarget(state.assetId, state.revision, 'new-text', operationSequence.current))) {
        setError(reason instanceof Error ? reason.message : 'INVALID_RESOURCE');
      }
    }
  }

  async function upload(file: File) {
    const sequence = ++operationSequence.current;
    const target = asyncTarget(assetId, revision, 'new-upload', sequence);
    const documentSnapshot = JSON.stringify(document);
    setError(null);
    try {
      const mediaType = mediaTypeForPath(file.name, file.type);
      if (!mediaType) throw new Error('UNSUPPORTED_FILE_TYPE');
      if (file.size > 4 * 1024 * 1024) throw new Error('ENTRY_BYTES_LIMIT_EXCEEDED');
      const bytes = new Uint8Array(await file.arrayBuffer());
      let state = live.current;
      if (!mounted.current || state.disabled
        || !acceptsAsyncTarget(target, asyncTarget(state.assetId, state.revision, 'new-upload', operationSequence.current))
        || JSON.stringify(state.document) !== documentSnapshot) return;
      const currentResources = Array.isArray(state.document.resources) ? state.document.resources : [];
      const resource = await createResource({ handleId: nextHandle(file.name, currentResources), logicalPath: file.name, mediaType, bytes, resources: currentResources });
      state = live.current;
      if (!mounted.current || state.disabled
        || !acceptsAsyncTarget(target, asyncTarget(state.assetId, state.revision, 'new-upload', operationSequence.current))
        || JSON.stringify(state.document) !== documentSnapshot) return;
      const latestResources = Array.isArray(state.document.resources) ? state.document.resources : [];
      state.onChange(updatePath(state.document, ['resources'], [...latestResources, resource]));
      setSelected(resourceIdentity(resource));
    } catch (reason) {
      const state = live.current;
      if (mounted.current && acceptsAsyncTarget(target, asyncTarget(state.assetId, state.revision, 'new-upload', operationSequence.current))) {
        setError(reason instanceof Error ? reason.message : 'INVALID_RESOURCE');
      }
    }
  }

  function remove() {
    if (currentIndex < 0 || !identity || identityIssue || !window.confirm('确认移除该资源？此操作只修改本地草稿，保存前不会生效。')) return;
    operationSequence.current += 1;
    const next = { ...pendingResources };
    delete next[identity];
    onPendingResourcesChange(next);
    onChange(updatePath(document, ['resources'], list!.filter((_, index) => index !== currentIndex)));
    setSelected(null);
  }

  const conflict = Boolean(pending && current && pending.base !== JSON.stringify(current));
  return <Section title="资源工作台">
    <div className="resource-workbench">
      <nav className="resource-tree" aria-label="资源导航">
        {list.map((resource, index) => {
          const itemIdentity = selectIdentity(resource, index);
          const label = isEditableRecord(resource) && typeof resource.logicalPath === 'string' ? resource.logicalPath : `异常资源 ${index + 1}`;
          return <button type="button" disabled={disabled} className={itemIdentity === selected ? 'selected' : ''} key={itemIdentity}
            onClick={() => setSelected(itemIdentity)}>{label}{pendingResources[itemIdentity] ? <i>待应用</i> : null}</button>;
        })}
        {!list.length ? <span>暂无附加资源</span> : null}
      </nav>
      <div className="resource-detail">
        {current ? <>
          <dl><div><dt>路径</dt><dd>{String(isEditableRecord(current) ? current.logicalPath ?? '—' : '—')}</dd></div>
            <div><dt>媒体类型</dt><dd>{String(isEditableRecord(current) ? current.mediaType ?? '—' : '—')}</dd></div>
            <div><dt>字节</dt><dd>{String(isEditableRecord(current) ? current.byteSize ?? '—' : '—')}</dd></div>
            <div><dt>摘要</dt><dd>{String(isEditableRecord(current) ? current.contentDigest ?? '—' : '—')}</dd></div></dl>
          {identityIssue ? <div className="notice error"><strong>资源身份冲突</strong><span>{identityIssue}；重复 handleId 无法安全定位，当前项只读，请在完整 JSON 模式显式修复或移除冲突。</span></div> : null}
          {currentInspection?.status === 'verifying' ? <div className="notice warning"><strong>正在验证资源摘要</strong><span>摘要验证完成前不可编辑或应用。</span></div> : null}
          {!identityIssue && currentInspection?.status === 'editable' ? <label className="form-field resource-text"><span>UTF-8 文本</span><textarea aria-label="资源文本"
            disabled={disabled || conflict} value={pending?.text ?? currentInspection.text}
            onChange={(event) => identity && onPendingResourcesChange({ ...pendingResources, [identity]: pendingText(current, event.target.value) })} /></label> : null}
          {!identityIssue && currentInspection?.status === 'readonly' ? <div className="notice warning"><strong>二进制资源只读</strong><span>摘要已验证；原始 base64 与证据保持不变，不会尝试替换字符解码。</span></div> : null}
          {!identityIssue && currentInspection?.status === 'repair' ? <div className="notice error"><strong>资源需要显式修复</strong><span>{currentInspection.reason}；打开不会静默改写原值，请在完整 JSON 模式修复或移除。</span></div> : null}
          {pending ? <div className={conflict ? 'field-feedback error' : 'field-feedback'}><span>{conflict ? 'canonical 资源已改变；待应用文本已保留。' : '文本尚未应用到 canonical 草稿。'}</span><span className="field-actions">
            <button type="button" className="quiet-button" disabled={disabled || Boolean(identityIssue) || conflict || currentInspection?.status !== 'editable'} onClick={() => void applyText()}>应用资源文本</button>
            <button type="button" className="quiet-button" disabled={disabled} onClick={() => { if (!window.confirm('丢弃该资源尚未应用的文本？')) return; const next = { ...pendingResources }; delete next[identity!]; onPendingResourcesChange(next); }}>丢弃资源文本</button>
          </span></div> : null}
          <button type="button" className="warning-button" disabled={disabled || Boolean(identityIssue)} onClick={remove}>移除资源</button>
        </> : <p>选择资源查看内容与证据。</p>}
      </div>
    </div>
    <div className="resource-add"><label className="form-field"><span>新文本资源路径</span><input aria-label="新文本资源路径" value={newPath} disabled={disabled} onChange={(event) => setNewPath(event.target.value)} /></label>
      <button type="button" className="secondary-button" disabled={disabled || !newPath.trim() || Boolean(pathIssue(newPath.trim(), list))} onClick={() => void addText()}>添加文本资源</button>
      <label className="secondary-button file-button">上传单个文件<input aria-label="上传资源文件" type="file" disabled={disabled} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void upload(file); }} /></label></div>
    {error ? <div className="notice error">{error}</div> : null}
    <div className={local?.issues.length ? 'notice warning' : 'notice success'}><strong>本地包检查（部分预检）</strong>
      <span>{list.length}/127 个附加资源 · {local?.totalBytes ?? 0} 字节；还需后端 authoritative validation。</span>
      {local?.issues.length ? <ul>{local.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : <span>未发现本地可判定问题；这不是安全或可发布保证。</span>}</div>
  </Section>;
}

export function SkillEditor(props: FormProps) {
  const { document, disabled, onChange, references, onNavigateReference } = props;
  const [stage, setStage] = useState('overview');
  const stages = [
    ['overview', '基础信息'], ['abilities', '业务能力'],
    ['applications', '渲染组件'], ['resources', '指令与文件'],
  ];
  const mismatch = skillFrontmatterMismatch(document);
  const metadata = isEditableRecord(document.metadata) ? document.metadata : undefined;
  return <div className="asset-form">
    <nav className="skill-stage-tabs" aria-label="Skill 配置阶段">
      {stages.map(([key, label]) => <button type="button" key={key} aria-pressed={stage === key}
        className={stage === key ? 'active' : ''} onClick={() => setStage(key)}>{label}
        {key === 'abilities' && Array.isArray(document.abilityBindings) ? <span>{document.abilityBindings.length}</span> : null}
        {key === 'applications' && Array.isArray(document.applicationBindings) ? <span>{document.applicationBindings.length}</span> : null}
      </button>)}
    </nav>
    <div hidden={stage !== 'overview'}>
    {mismatch ? <div className="notice warning"><strong>metadata 与 frontmatter 需要核对</strong><span>{mismatch}</span></div> : null}
    <Section title="Skill 基础信息">
      {metadata || document.metadata === undefined ? <>
        <Field label="名称" value={metadata?.name} disabled={disabled} onChange={(value) => onChange(updatePath(document, ['metadata', 'name'], value))} />
        <Field label="描述" value={metadata?.description} disabled={disabled} multiline onChange={(value) => onChange(updatePath(document, ['metadata', 'description'], value))} />
      </> : <MalformedValue label="metadata" value={document.metadata} />}
    </Section>
    <StringRows label="所需工具" document={document} path={['requiredToolNames']} disabled={disabled} onChange={onChange} />
    <p className="skill-stage-hint">业务能力和展示应用在对应页签绑定；发布与版本历史仍使用资产详情的统一入口。</p>
    </div>
    <div hidden={stage !== 'abilities'}><SkillBindingWorkbench kind="ABILITY" document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigateReference} /></div>
    <div hidden={stage !== 'applications'}><SkillBindingWorkbench kind="APPLICATION" document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigateReference} /></div>
    <div hidden={stage !== 'resources'}>
    <Section title="Markdown 指令"><Field label="SKILL.md（不会自动改写 frontmatter）" value={document.skillMd} disabled={disabled} multiline onChange={(value) => onChange(updatePath(document, ['skillMd'], value))} />
      {typeof document.skillMd === 'string' ? <><MarkdownPreview markdown={document.skillMd} /><small>安全预览支持标题、段落、列表、代码与 GFM 子集；忽略 HTML、图片与链接导航，且不会执行 Skill。</small></> : null}</Section>
    <ResourceWorkbench {...props} />
    </div>
  </div>;
}
