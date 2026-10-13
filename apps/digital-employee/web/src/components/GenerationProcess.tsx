import { generationFailureDescription, generationStageLabels } from '../generationProgress';
import type { ChatToolCall } from '../productApi';

const elapsed = (milliseconds: number) => `${(milliseconds / 1000).toFixed(1)} 秒`;

export function GenerationProcess({ tool, active }: { tool: ChatToolCall; active: boolean }) {
  const progress = tool.generationProgress ?? [];
  const latest = progress.at(-1);
  const elapsedMs = latest?.elapsedMs ?? tool.durationMs;
  const failed = latest?.stage === 'failed' || tool.lifecycleStatus === 'raised' || tool.toolMessageStatus === 'error';
  const completed = !failed && latest?.stage === 'completed';
  const running = !failed && !completed && active && tool.lifecycleStatus === 'running';
  const label = failed ? '界面生成失败' : latest
    ? `${!running && !completed ? '最后记录：' : ''}${generationStageLabels[latest.stage]}`
    : running ? '等待生成进度' : '尚无已保存的生成进度';
  return <section className={`generation-process${failed ? ' failed' : ''}`} aria-label="界面生成进度">
    <div className="generation-process-summary" role="status">
      <strong>{label}</strong>
      {elapsedMs !== undefined ? <span>累计 {elapsed(elapsedMs)}</span> : null}
    </div>
    {failed ? <p>{generationFailureDescription(latest?.errorCode ?? tool.errorCode)}</p> : null}
    {!running && !failed && !completed
      ? <p>尚未收到界面生成完成记录。</p> : null}
    {progress.length ? <details>
      <summary>查看生成过程</summary>
      <ol>{progress.map((event, index) => <li key={`${event.stage}:${index}`}>
        <span>{generationStageLabels[event.stage]}</span><span>累计 {elapsed(event.elapsedMs)}</span>
      </li>)}</ol>
    </details> : null}
  </section>;
}
