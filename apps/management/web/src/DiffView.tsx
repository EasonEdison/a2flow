import type { DiffEntry } from './structured-diff';

function valueText(value: unknown) {
  return value === undefined ? '—' : JSON.stringify(value);
}

export function DiffView({ entries, leftLabel, rightLabel }: {
  entries: DiffEntry[];
  leftLabel: string;
  rightLabel: string;
}) {
  return <section className="diff-view" aria-label="版本差异">
    <header><strong>{leftLabel}</strong><span>对比</span><strong>{rightLabel}</strong></header>
    {entries.length === 0 ? <p className="diff-empty">没有差异。</p> : <div className="diff-rows">
      {entries.map((entry, index) => <div className={`diff-row ${entry.kind}`} key={`${entry.path}:${index}`}>
        <code>{entry.path}</code><span>{entry.kind}</span>
        <pre>{valueText(entry.before)}</pre><pre>{valueText(entry.after)}</pre>
      </div>)}
    </div>}
  </section>;
}
