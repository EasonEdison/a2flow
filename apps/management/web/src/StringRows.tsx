import type { JsonObject } from './contracts';
import { appendRow, moveRow, removeRow, updatePath } from './form-editor-state';
import { RowActions, Section, useRowKeys, valueAt, type Change, type Path } from './EditorControls';

export function StringRows({ label, document, path, disabled, onChange }: {
  label: string; document: JsonObject; path: Path; disabled: boolean; onChange: Change;
}) {
  const rows = valueAt(document, path);
  const rowKeys = useRowKeys(Array.isArray(rows) ? rows.length : 0);
  return <Section title={label}>
    {Array.isArray(rows) ? rows.map((value, index) => <div className="form-row compact" key={rowKeys.keys[index]}>
      {typeof value === 'string' ? <input aria-label={`${label} ${index + 1}`} value={value} disabled={disabled}
        onChange={(event) => {
          const next = rows.slice(); next[index] = event.target.value; onChange(updatePath(document, path, next));
        }} /> : <div className="malformed-row" role="status" aria-label={`${label} ${index + 1} 类型错误`}>
        <strong>{typeof value === 'object' ? (value === null ? 'null' : Array.isArray(value) ? 'array' : 'object') : typeof value}</strong>
        <code>{JSON.stringify(value)}</code>
        <span>原值已保留。请在完整 JSON 修复，或明确移除此项。</span>
      </div>}
      <RowActions index={index} length={rows.length} disabled={disabled || typeof value !== 'string'}
        onMove={(direction) => { rowKeys.move(index, direction); onChange(moveRow(document, path, index, direction)); }}
        onRemove={() => { rowKeys.remove(index); onChange(removeRow(document, path, index)); }} />
      {typeof value !== 'string' ? <button type="button" className="warning-button" disabled={disabled}
        onClick={() => window.confirm(`确认移除 ${label} 第 ${index + 1} 项的原始值？`) && (rowKeys.remove(index), onChange(removeRow(document, path, index)))}>确认移除异常项</button> : null}
    </div>) : <p className="field-feedback error">当前值不是数组，请在 JSON 模式修正。</p>}
    <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(rows)}
      onClick={() => onChange(appendRow(document, path, ''))}>添加一项</button>
  </Section>;
}
