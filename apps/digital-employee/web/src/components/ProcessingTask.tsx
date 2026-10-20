import { useEffect, useState } from 'react';
import { apiErrorMessage, productApi, type ProcessingSelection, type ProcessingTask } from '../productApi';
import { MarkdownContent } from './MarkdownContent';
import { processingStatus, taskState, stateGuidance, operationPresentation } from '../processingPresentation';
import { displayTime } from './RunHistory';

export function ProcessingChip({ selection, onRemove }: { selection: ProcessingSelection; onRemove: () => void }) {
  return <div className="processing-composer" role="status"><div><strong>本次处理：{selection.label}</strong><small>发送要求后关联处理结果；补参提交会继续同一处理任务。</small></div><button className="quiet" onClick={onRemove} aria-label="移除本次处理目标">移除</button></div>;
}

export function ProcessingTaskPanel({ taskId, onContinue, onUpdated, onOpenConversation }: { taskId: string; onContinue: (task: ProcessingTask) => void; onUpdated: () => void; onOpenConversation: (task: ProcessingTask) => void }) {
  const [task, setTask] = useState<ProcessingTask | null>(null);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveUnconfirmed, setSaveUnconfirmed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let loading = false;
    const load = async () => {
      if (loading || document.hidden) return;
      loading = true;
      try { const result = await productApi.processingTask(taskId, abort.signal); if (!abort.signal.aborted) { setTask(result); setError(''); setSaveUnconfirmed(false); } }
      catch (error) { if (!abort.signal.aborted) setError(apiErrorMessage(error, '处理记录读取失败，请重新读取')); }
      finally { loading = false; }
    };
    void load();
    const timer = setInterval(() => void load(), 5000);
    document.addEventListener('visibilitychange', load);
    return () => { abort.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', load); };
  }, [taskId, revision]);
  if (!task) return <div role="status">{error || '正在读取处理记录…'}{error ? <button className="secondary" onClick={() => setRevision(value => value + 1)}>重新读取</button> : null}</div>;
  const state = taskState(task);
  const canContinue = ['OPEN', 'RESULT_RECORDED', 'INTERRUPTED'].includes(state);
  const returned = task.operations.filter(operation => operation.status === 'RETURNED').length;
  const canResolve = state === 'RESULT_RECORDED' && ['completed', 'waiting_action'].includes(task.deliveryStatus || '') && task.operations.length > 0 && task.operations.every(operation => operation.status === 'RETURNED');
  return <section className="processing-detail">
    <div className="processing-heading"><span className={`status processing-state ${state.toLowerCase()}`}>{processingStatus[state] || '状态待核实'}</span><small>更新于 {displayTime(task.updatedAt)}</small></div>
    <h3 className="processing-title">处理进展与结果</h3>
    <p className="processing-guidance" role="status">{stateGuidance[state] || '请查看原会话核实当前进度。'}</p>
    <details className="processing-objective"><summary>查看本次处理要求</summary><p>{task.objective}</p></details>
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    <div className="processing-result-heading"><h4>执行结果</h4><span>{returned} / {task.operations.length} 项已返回</span></div>
    <ol className="processing-operations">{task.operations.map(operation => {
      const result = operationPresentation(operation);
      return <li key={operation.operationId} className={`processing-operation ${operation.status.toLowerCase()}`}>
        <div className="processing-operation-title"><strong>{result.name}</strong><span>{processingStatus[operation.status] || '状态待核实'}</span></div>
        <small>{operation.finishedAt ? '完成于 ' + displayTime(operation.finishedAt) : operation.createdAt ? '开始于 ' + displayTime(operation.createdAt) : '时间未记录'}</small>
        {result.title ? <p className="processing-result-title">{result.title}</p> : null}
        {result.audience ? <p className="processing-result-audience">目标读者：{result.audience}</p> : null}
        {result.id ? <dl className="processing-identifiers"><dt>{result.idLabel}</dt><dd>{result.id}</dd>{result.revision != null ? <><dt>版本</dt><dd>{result.revision}</dd></> : null}</dl> : null}
        {result.markdown ? <details className="processing-content"><summary>查看内容</summary><div className="processing-markdown"><MarkdownContent markdown={result.markdown} /></div></details> : null}
        {operation.status !== 'RETURNED' ? <p className="processing-guidance">{stateGuidance[operation.status] || '请等待已发起的操作返回。'}</p> : null}
        <details className="processing-technical"><summary>技术详情</summary><p>业务能力：{operation.abilityKey}</p>{operation.errorCode ? <p>错误：{operation.errorCode}</p> : null}<pre>{JSON.stringify(operation.result ?? { status: operation.status }, null, 2)}</pre></details>
      </li>;
    })}</ol>
    {!task.operations.length ? <p className="muted">业务操作尚未开始，补参内容和对话进展可在原会话查看。</p> : null}
    <div className="activity-actions"><button className="secondary" onClick={() => onOpenConversation(task)}>打开原会话</button></div>
    {task.resolvedAt ? <div className="processing-resolution"><strong>人工确认 · {displayTime(task.resolvedAt)}</strong><p>{task.resolutionSummary}</p></div> : <>
      <div className="activity-actions">{canContinue ? <button className="secondary" onClick={() => onContinue(task)}>继续处理此异常</button> : null}{canResolve ? <button className="quiet" onClick={() => setConfirming(value => !value)}>确认本次任务完成</button> : null}</div>
      {confirming && canResolve ? <form className="processing-confirm" onSubmit={async event => {
        event.preventDefault(); if (!summary.trim() || saving || saveUnconfirmed) return; setSaving(true); setError('');
        try { const updated = await productApi.resolveProcessingTask(taskId, summary.trim()); setTask(updated); setConfirming(false); setRevision(value => value + 1); onUpdated(); }
        catch (error) { setSaveUnconfirmed(true); setError(apiErrorMessage(error, '保存状态未确认，请重新读取记录，不要重复提交')); }
        finally { setSaving(false); }
      }}><label htmlFor="processing-resolution">请记录本次任务完成了什么，还有什么未完成</label><textarea id="processing-resolution" required maxLength={1200} value={summary} onChange={event => setSummary(event.target.value)} placeholder="例如：已建立复核记录，业务复核仍待人工完成。" /><p>确认只结束本次处理任务，并保存你的说明。它不会修改原工作流、代替业务复核或自动关闭原异常。</p><button className="primary" disabled={saving || saveUnconfirmed || !summary.trim()}>{saving ? '正在保存…' : '保存确认说明'}</button></form> : null}
    </>}
  </section>;
}
