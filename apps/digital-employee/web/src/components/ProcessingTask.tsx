import { useEffect, useState } from 'react';
import { apiErrorMessage, productApi, type ProcessingSelection, type ProcessingTask } from '../productApi';
import { displayTime } from './RunHistory';

export const processingStatus: Record<string, string> = { OPEN: '处理中', WAITING_INPUT: '等待补充', RESULT_RECORDED: '已有执行回执，待确认', FAILED: '执行失败', UNKNOWN: '结果不确定', RESOLVED: '人工已确认处理', RUNNING: '执行中', RETURNED: '已返回执行结果' };

export function ProcessingChip({ selection, onRemove }: { selection: ProcessingSelection; onRemove: () => void }) {
  return <div className="processing-composer" role="status"><div><strong>本次处理：{selection.label}</strong><small>发送要求后关联处理结果；补参提交会继续同一处理任务。</small></div><button className="quiet" onClick={onRemove} aria-label="移除本次处理目标">移除</button></div>;
}

export function ProcessingTaskPanel({ taskId, onContinue, onUpdated, onOpenConversation }: { taskId: string; onContinue: (task: ProcessingTask) => void; onUpdated: () => void; onOpenConversation: (task: ProcessingTask) => void }) {
  const [task, setTask] = useState<ProcessingTask | null>(null);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let loading = false;
    const load = async () => {
      if (loading || document.hidden) return;
      loading = true;
      try { const result = await productApi.processingTask(taskId, abort.signal); if (!abort.signal.aborted) { setTask(result); setError(''); } }
      catch (error) { if (!abort.signal.aborted) setError(apiErrorMessage(error, '处理记录读取失败，请重新读取')); }
      finally { loading = false; }
    };
    void load();
    const timer = setInterval(() => void load(), 5000);
    document.addEventListener('visibilitychange', load);
    return () => { abort.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', load); };
  }, [taskId, revision]);
  if (!task) return <div role="status">{error || '正在读取处理记录…'}{error ? <button className="secondary" onClick={() => setRevision(value => value + 1)}>重新读取</button> : null}</div>;
  const canContinue = ['OPEN', 'RESULT_RECORDED'].includes(task.status);
  const canResolve = task.status === 'RESULT_RECORDED' && task.operations.length > 0 && task.operations.every(operation => operation.status === 'RETURNED');
  return <section className="processing-detail">
    <div className="processing-heading"><span className={`status ${task.status.toLowerCase()}`}>{processingStatus[task.status] || task.status}</span><small>更新于 {displayTime(task.updatedAt)}</small></div>
    <h3>{task.objective}</h3>
    <p className="muted">以下来自保存的执行回执。收到返回结果不代表异常已解决；表单提交也不代表业务处理完成。</p>
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    <ol className="processing-operations">{task.operations.map(operation => <li key={operation.operationId}>
      <div><strong>{operation.abilityKey}</strong><span>{processingStatus[operation.status] || operation.status}</span></div>
      <small>{operation.createdAt ? displayTime(operation.createdAt) : '时间未记录'}</small>
      {operation.errorCode ? <p>错误：{operation.errorCode}</p> : null}
      {operation.result != null ? <details><summary>查看保存的结果</summary><pre>{JSON.stringify(operation.result, null, 2)}</pre></details> : null}
    </li>)}</ol>
    {!task.operations.length ? <p className="muted">尚无业务执行回执。</p> : null}
    <div className="activity-actions"><button className="secondary" onClick={() => onOpenConversation(task)}>打开原会话</button></div>
    {task.resolvedAt ? <div className="processing-resolution"><strong>人工确认 · {displayTime(task.resolvedAt)}</strong><p>{task.resolutionSummary}</p></div> : <>
      <div className="activity-actions">{canContinue ? <button className="secondary" onClick={() => onContinue(task)}>继续处理此异常</button> : null}{canResolve ? <button className="quiet" onClick={() => setConfirming(value => !value)}>确认已处理</button> : null}</div>
      {!canContinue ? <p className="muted">{task.status === 'WAITING_INPUT' ? '请在原会话提交待填写表单，提交后自动继续。' : '当前结果不可继续执行，请先核对已保存的执行记录。系统不会自动重试。'}</p> : null}
      {confirming && canResolve ? <form className="processing-confirm" onSubmit={async event => {
        event.preventDefault(); if (!summary.trim() || saving) return; setSaving(true); setError('');
        try { await productApi.resolveProcessingTask(taskId, summary.trim()); setConfirming(false); setRevision(value => value + 1); onUpdated(); }
        catch (error) { setError(apiErrorMessage(error, '保存状态未确认，请重新读取记录，不要重复提交')); }
        finally { setSaving(false); }
      }}><label htmlFor="processing-resolution">请明确记录实际处理结论</label><textarea id="processing-resolution" required maxLength={1200} value={summary} onChange={event => setSummary(event.target.value)} placeholder="例如：已建立复核记录，业务复核仍待人工完成。" /><p>这是你的人工确认，将保留确认时间和说明，不改变原工作流。</p><button className="primary" disabled={saving || !summary.trim()}>{saving ? '正在保存…' : '保存处理结论'}</button></form> : null}
    </>}
  </section>;
}
