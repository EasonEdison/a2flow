import { useEffect, useState } from 'react';
import { managementApi } from './api';
import type { ManagedDraft, PendingResourceEdits } from './contracts';
import { inspectResourceVerified, mediaTypeForPath, type ResourceInspection } from './skill-resource-state';

export interface SkillWorkspaceEntry {
  handleId: string;
  logicalPath: string;
  mediaType: string;
  byteSize: number;
  contentDigest: string;
  base64: string;
}
export interface SkillWorkspace {
  baseDraftRevision: number;
  workspaceRevision: number;
  entries: SkillWorkspaceEntry[];
  dirty: boolean;
}

function encodeText(text: string) {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function FileTree({ entries, selected, locked, onSelect }: {
  entries: SkillWorkspaceEntry[]; selected: string; locked: boolean; onSelect: (path: string) => void;
}) {
  function branch(prefix: string) {
    const children = new Map<string, boolean>();
    for (const entry of entries) {
      if (!entry.logicalPath.startsWith(prefix)) continue;
      const rest = entry.logicalPath.slice(prefix.length);
      const [name, ...tail] = rest.split('/');
      children.set(name, tail.length > 0);
    }
    return <ul>{[...children].sort(([a, dirA], [b, dirB]) => Number(dirB) - Number(dirA) || a.localeCompare(b)).map(([name, directory]) => {
      const path = prefix + name;
      return <li key={path}>{directory
        ? <details open><summary>{name}</summary>{branch(path + '/')}</details>
        : <button type="button" className={selected === path ? 'selected' : ''} aria-current={selected === path ? 'true' : undefined}
          disabled={locked && selected !== path} onClick={() => onSelect(path)}>{name}</button>}</li>;
    })}</ul>;
  }
  return <nav className="skill-files-tree" aria-label="项目文件">{branch('')}</nav>;
}

export function SkillFileWorkspace({ assetKey, revision, environment, disabled, draftDirty, pending, onPending, onCommitted, onBlocked }: {
  assetKey: string; revision: number; environment: string; disabled: boolean; draftDirty: boolean;
  pending: PendingResourceEdits; onPending: (edits: PendingResourceEdits) => void;
  onCommitted: (draft: ManagedDraft) => void;
  onBlocked: (blocked: boolean) => void;
}) {
  const [workspace, setWorkspace] = useState<SkillWorkspace | null>(null);
  const [selected, setSelected] = useState('SKILL.md');
  const [editing, setEditing] = useState(false);
  const [inspection, setInspection] = useState<ResourceInspection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [newPath, setNewPath] = useState('');
  const [refresh, setRefresh] = useState(0);
  const file = workspace?.entries.find((entry) => entry.logicalPath === selected);
  const pendingKey = `workspace:${selected}`;
  const edit = pending[pendingKey];
  const fileChanged = Boolean(edit);
  const text = edit?.text ?? (inspection?.status === 'editable' ? inspection.text : '');
  const locked = disabled || busy;
  const conflict = workspace !== null && workspace.baseDraftRevision !== revision;

  useEffect(() => { onBlocked(!workspace || workspace.dirty || busy); }, [workspace, busy, onBlocked]);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    void managementApi.skillWorkspace(assetKey, controller.signal).then(setWorkspace).catch((reason) => {
      if (!controller.signal.aborted) setError(String(reason.message ?? reason));
    });
    return () => controller.abort();
  }, [assetKey, revision, refresh]);

  useEffect(() => {
    let active = true;
    setInspection(null);
    if (file) void inspectResourceVerified(file, true).then((result) => { if (active) setInspection(result); });
    return () => { active = false; };
  }, [file]);

  useEffect(() => {
    if (!Object.keys(pending).length) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [pending]);

  function discardEdit() {
    const next = { ...pending };
    delete next[pendingKey];
    onPending(next);
    setEditing(false);
  }

  async function saveFile() {
    if (!workspace || !file || !edit || locked || draftDirty) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const next = await managementApi.saveSkillFile(assetKey, workspace.workspaceRevision, selected, file.mediaType, encodeText(edit.text));
      setWorkspace(next); discardEdit();
      setMessage('文件已保存到数据库。保存当前工作区后，才会更新待发布草稿；运行中的 Skill 不受影响。');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  async function commit() {
    if (!workspace || locked || Object.keys(pending).length || draftDirty || conflict) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await managementApi.commitSkillWorkspace(assetKey, workspace.workspaceRevision, revision);
      setWorkspace(result.workspace); onCommitted(result.draft);
      setMessage('当前工作区已保存为草稿。校验并发布后，use_skill 才会读取新版本。');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  async function addFile() {
    if (!workspace || locked || editing || fileChanged || draftDirty || !newPath.trim()) return;
    setBusy(true); setError(null);
    const path = newPath.trim();
    try {
      if (workspace.entries.some((entry) => entry.logicalPath === path)) throw new Error('文件已存在，请从文件树选择后编辑。');
      const media = path.endsWith('.py') ? 'text/x-python' : path.endsWith('.md') ? 'text/markdown' : 'text/plain';
      const next = await managementApi.saveSkillFile(assetKey, workspace.workspaceRevision, path, media, '');
      setWorkspace(next); setSelected(path); setNewPath(''); setEditing(true);
      setMessage('空文件已存入数据库工作区，尚未提交到待发布草稿。');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  async function uploadFile(upload: File) {
    if (!workspace || locked || editing || fileChanged || draftDirty) return;
    const path = newPath.trim() || upload.name;
    if (workspace.entries.some((entry) => entry.logicalPath === path)) {
      setError('文件已存在，请从文件树选择后编辑。'); return;
    }
    setBusy(true); setError(null);
    try {
      if (upload.size > 700 * 1024) throw new Error('文件过大：当前 HTTP 请求上限为 1 MiB，单文件上传限制为 700 KiB。');
      const media = path.endsWith('.py') ? 'text/x-python' : mediaTypeForPath(path, upload.type);
      if (!media) throw new Error('不支持此文件类型。');
      const bytes = new Uint8Array(await upload.arrayBuffer());
      let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
      const next = await managementApi.saveSkillFile(assetKey, workspace.workspaceRevision, path, media, btoa(binary));
      setWorkspace(next); setSelected(path); setNewPath('');
      setMessage('文件已上传到数据库工作区，尚未提交到待发布草稿。');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  async function deleteFile() {
    if (!workspace || locked || editing || fileChanged || draftDirty || selected === 'SKILL.md') return;
    if (!window.confirm(`从编辑工作区移除 ${selected}？已发布版本不受影响。`)) return;
    setBusy(true); setError(null);
    try {
      setWorkspace(await managementApi.deleteSkillFile(assetKey, workspace.workspaceRevision, selected));
      setSelected('SKILL.md'); setMessage('文件已从编辑工作区移除。保存工作区并发布后才影响运行时。');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  return <div className="skill-file-workspace">
    <div className="skill-workspace-meta">
      <div><span>工作区</span><strong>{assetKey}</strong></div>
      <div><span>工作区视图</span><strong>{environment} 编辑态</strong></div>
      <div><span>草稿修订</span><strong>{revision}</strong></div>
      <div><span>文件数</span><strong>{workspace?.entries.length ?? '—'} 个</strong></div>
      <div><span>工作区修订</span><strong>{workspace?.workspaceRevision ?? '—'}</strong></div>
      <div><span>变更状态</span><strong>{workspace?.dirty ? '文件已保存 · 待保存工作区' : '与草稿同步'}</strong></div>
    </div>
    {error ? <div role="alert" className="notice error">{error}<button type="button" disabled={locked} onClick={() => setRefresh((value) => value + 1)}>重新读取工作区</button></div> : null}
    {message ? <div role="status" className="notice success">{message}</div> : null}
    {conflict ? <div className="notice warning">草稿已经变化，文件工作区已保留。当前不能覆盖保存，请核对草稿与工作区修订。</div> : null}
    <div className="skill-files-layout">
      <section className="skill-files-browser"><h3>项目文件</h3>
        {workspace ? <FileTree entries={workspace.entries} selected={selected} locked={locked || editing || fileChanged}
          onSelect={(path) => { setSelected(path); setEditing(false); setMessage(null); }} /> : <p>正在读取数据库工作区…</p>}
        <div className="skill-file-create"><label>新文件路径<input value={newPath} disabled={locked || editing || fileChanged} placeholder="scripts/example.py"
          onChange={(event) => setNewPath(event.target.value)} /></label>
          <button type="button" disabled={locked || editing || fileChanged || draftDirty || !workspace || !newPath.trim()} onClick={() => void addFile()}>新建文件</button></div>
      </section>
      <section className="skill-file-content"><header><div><h3>{selected}</h3><small>{file?.mediaType} · {file?.byteSize ?? 0} bytes</small></div>
        <div className="skill-file-actions">
          <button type="button" disabled={locked || draftDirty || editing || Boolean(edit) || inspection?.status !== 'editable'} onClick={() => setEditing(true)}>编辑</button>
          <button type="button" disabled={locked || (!editing && !edit)} onClick={() => { if (fileChanged && !window.confirm('放弃当前文件尚未保存的修改？')) return; discardEdit(); }}>取消</button>
          <button type="button" disabled={locked || draftDirty || !fileChanged || edit?.base !== JSON.stringify(file)} onClick={() => void saveFile()}>保存文件</button>
          {selected !== 'SKILL.md' ? <button type="button" disabled={locked || draftDirty || editing || fileChanged} onClick={() => void deleteFile()}>移除文件</button> : null}
          <button type="button" className="primary-button" disabled={locked || !workspace?.dirty || Object.keys(pending).length > 0 || draftDirty || conflict} onClick={() => void commit()}>保存当前工作区</button>
        </div></header>
        {inspection?.status === 'editable' ? <div className="skill-source-editor">
          <pre aria-hidden="true" className="skill-line-numbers">{text.split('\n').map((_, i) => i + 1).join('\n')}</pre>
          <textarea aria-label={`文件内容 ${selected}`} spellCheck={false} readOnly={!editing || locked} value={text}
            onChange={(event) => onPending({ ...pending, [pendingKey]: { identity: pendingKey, base: JSON.stringify(file), text: event.target.value } })} />
        </div> : <p className="skill-file-status">{inspection?.status === 'readonly' ? '二进制文件：内容已保留，当前只读。' : inspection?.status === 'repair' ? `文件校验失败：${inspection.reason}` : '正在校验文件内容…'}</p>}
        <footer>{editing || fileChanged ? '编辑中：保存或取消后才能切换文件。' : '只读模式 · 点击「编辑」后修改'}<small>{file?.contentDigest}</small></footer>
      </section>
      <aside className="skill-file-help"><h3>上传文件</h3><label className="secondary-button file-button">选择单个文件<input type="file" aria-label="上传工作区文件" disabled={locked || editing || fileChanged || draftDirty || !workspace}
        onChange={(event) => { const upload = event.target.files?.[0]; event.target.value = ''; if (upload) void uploadFile(upload); }} /></label><p>使用左侧新文件路径；未填写时使用文件名。ZIP 整包导入暂未提供。</p>
        <h3>文件保护</h3><p>默认只读，点击编辑后才允许修改当前文件。</p><p>切换文件前必须保存或取消未保存改动。</p><p>保存文件只写数据库工作区；保存当前工作区后更新待发布草稿。发布是独立操作。</p><p>SKILL.md、scripts 和 references 从同一份数据库文件结构恢复，目录不是服务器上的编辑路径。</p>
        {draftDirty ? <p className="notice warning">其他页签还有未保存的草稿修改，请先保存，再提交文件工作区。</p> : null}
      </aside>
    </div>
  </div>;
}
