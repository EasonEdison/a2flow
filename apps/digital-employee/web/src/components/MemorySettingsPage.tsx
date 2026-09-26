import { useEffect, useRef, useState } from 'react';
import { apiErrorMessage, productApi, type ApiError, type MemorySettings } from '../productApi';
import { createUuidV4 } from '../secureUuid.mjs';
import './MemorySettingsPage.css';

const lengthOf = (text: string) => Array.from(text).length;

export function MemorySettingsPage() {
  const [saved, setSaved] = useState<MemorySettings | null>(null);
  const [draft, setDraft] = useState<MemorySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const alive = useRef(false);
  const submitting = useRef(false);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setNotice('');
    void productApi.memory(controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setSaved(value);
      setDraft(value);
      setBlocked(false);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) {
        setBlocked(true);
        setError(apiErrorMessage(failure, '读取失败，请重新读取；不会使用本地副本代替服务器记忆'));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [reload]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const total = draft?.entries.reduce((sum, entry) => sum + lengthOf(entry.text), 0) ?? 0;
  const invalid = draft?.entries.some((entry) => !entry.text.trim() || lengthOf(entry.text) > 1000) || total > 8000;
  const disabled = loading || saving || blocked;

  const save = async () => {
    if (!draft || disabled || !dirty || invalid || submitting.current) return;
    submitting.current = true;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const value = await productApi.saveMemory(draft);
      if (!alive.current) return;
      setSaved(value);
      setDraft(value);
      setNotice('已保存。后续模型调用会读取当前设置。');
    } catch (failure) {
      if (!alive.current) return;
      // A lost response may follow a successful write; reread rather than replay.
      setBlocked(true);
      setError((failure as ApiError)?.code === 'MEMORY_REVISION_CONFLICT'
        ? apiErrorMessage(failure)
        : `${apiErrorMessage(failure, '保存未确认')}。请重新读取服务器状态后再编辑。`);
    } finally {
      submitting.current = false;
      if (alive.current) setSaving(false);
    }
  };

  return <section className="memory-settings" aria-labelledby="memory-heading">
    <div className="page-title"><h1 id="memory-heading">个人记忆</h1><p>设置 · 让数字员工了解你的长期偏好</p></div>
    <div className="memory-explanation card">
      <h2>由你管理，按需使用</h2>
      <p>只保存你在这里明确填写的偏好。对话和工作流共享当前账号、当前环境下的记忆；不会自动提炼聊天、记录工具结果或保存任务进度。</p>
      <p>关闭后，后续模型调用不再读取记忆。删除或关闭不会删除聊天历史，也无法撤回已经进入模型请求的内容。工作流只读取偏好，不会写回记忆。</p>
    </div>
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    {notice ? <p className="memory-notice" role="status">{notice}</p> : null}
    {loading ? <p role="status">正在读取个人记忆…</p> : null}
    {!loading && !draft ? <button className="secondary" onClick={() => setReload((value) => value + 1)}>重新读取</button> : null}
    {draft ? <form className="card memory-form" onSubmit={(event) => { event.preventDefault(); void save(); }} aria-busy={loading || saving}>
      <fieldset disabled={disabled}>
        <legend>记忆设置</legend>
        <div className="memory-toggle">
          <label className="switch"><input type="checkbox" role="switch" aria-label="启用个人记忆" checked={draft.enabled} onChange={(event) => { setDraft({ ...draft, enabled: event.target.checked }); setNotice(''); }} /><span>启用个人记忆</span></label>
          <span className="memory-saved-state">服务器状态：{saved?.enabled ? '已开启' : '已关闭'}</span>
        </div>
        <p className="memory-hint">开关、编辑和删除均在点击“保存更改”后生效。关闭时仍可查看、整理或删除已保存的条目。</p>
        <div className="memory-entries">
          {draft.entries.length ? draft.entries.map((entry, index) => <div className="memory-entry" key={entry.id}>
            <div className="memory-entry-heading"><label htmlFor={`memory-${entry.id}`}>偏好 {index + 1}</label><button type="button" className="quiet danger" aria-label={`删除偏好 ${index + 1}`} onClick={() => { setDraft({ ...draft, entries: draft.entries.filter((item) => item.id !== entry.id) }); setNotice(''); }}>删除</button></div>
            <textarea id={`memory-${entry.id}`} rows={3} value={entry.text} placeholder="例如：回答尽量简洁，优先给出结论。请勿填写密码或敏感凭据。" aria-describedby={`memory-count-${entry.id}`} aria-invalid={!entry.text.trim() || lengthOf(entry.text) > 1000} onChange={(event) => { setDraft({ ...draft, entries: draft.entries.map((item) => item.id === entry.id ? { ...item, text: event.target.value } : item) }); setNotice(''); }} />
            <small id={`memory-count-${entry.id}`}>{lengthOf(entry.text)} / 1000 字{!entry.text.trim() ? ' · 请填写内容或删除空条目' : ''}</small>
          </div>) : <p className="empty-card">还没有记忆。添加一条你希望数字员工长期参考的偏好。</p>}
        </div>
        <div className="memory-add"><button type="button" className="secondary" disabled={draft.entries.length >= 20} onClick={() => { setDraft({ ...draft, entries: [...draft.entries, { id: createUuidV4(), text: '' }] }); setNotice(''); }}>添加偏好</button><span>{draft.entries.length} / 20 条 · {total} / 8000 字</span></div>
      </fieldset>
      {invalid ? <p className="inline-error">每条需填写 1–1000 字，全部条目合计不超过 8000 字。</p> : null}
      <div className="memory-actions">
        <button className="primary" type="submit" disabled={disabled || !dirty || Boolean(invalid)}>{saving ? '正在保存…' : '保存更改'}</button>
        <button className="secondary" type="button" disabled={loading || saving} onClick={() => {
          if (dirty && !confirm('重新读取会丢弃本页尚未保存的更改，继续吗？')) return;
          setReload((value) => value + 1);
        }}>重新读取</button>
        {dirty ? <span role="status">有尚未保存的更改</span> : null}
      </div>
    </form> : null}
  </section>;
}
