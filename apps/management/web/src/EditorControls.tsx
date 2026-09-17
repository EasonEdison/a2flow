import { useRef, type ReactNode } from 'react';
import type { JsonObject } from './contracts';
import {
  inspectPathEditability, isEditableRecord, parseJsonField, type PendingFields,
} from './form-editor-state';

export type Change = (document: JsonObject) => void;
export type Path = string[];
export type PendingChange = (path: Path, text: string, expected: 'object' | 'array', baseValue: unknown) => void;
export type PendingResolve = (path: Path, expected: 'object' | 'array') => void;
export type PendingDiscard = (path: Path) => void;
export type PendingConflict = (path: Path) => string | null;
export type FormProps = {
  document: JsonObject;
  disabled: boolean;
  onChange: Change;
  pendingFields: PendingFields;
  onPendingChange: PendingChange;
  onApplyPending: PendingResolve;
  onDiscardPending: PendingDiscard;
  getPendingConflict: PendingConflict;
};

let nextRowId = 1;

export function useRowKeys(length: number) {
  const keys = useRef<string[]>([]);
  while (keys.current.length < length) keys.current.push(`row-${nextRowId++}`);
  if (keys.current.length > length) keys.current.length = length;
  return {
    keys: keys.current,
    move(index: number, direction: number) {
      const target = index + direction;
      [keys.current[index], keys.current[target]] = [keys.current[target], keys.current[index]];
    },
    remove(index: number) { keys.current.splice(index, 1); },
  };
}

export function valueAt(document: unknown, path: Path): unknown {
  return path.reduce<unknown>((value, key) => isEditableRecord(value) ? value[key] : undefined, document);
}

export function Field({ label, value, disabled, multiline = false, readOnly = false, onChange }: {
  label: string; value: unknown; disabled: boolean; multiline?: boolean; readOnly?: boolean;
  onChange?: (value: string) => void;
}) {
  const malformed = value !== undefined && typeof value !== 'string';
  const control = multiline ? (
    <textarea aria-label={label} value={typeof value === 'string' ? value : ''} disabled={disabled || malformed} readOnly={readOnly}
      onChange={(event) => onChange?.(event.target.value)} />
  ) : (
    <input aria-label={label} value={typeof value === 'string' ? value : ''} disabled={disabled || malformed} readOnly={readOnly}
      onChange={(event) => onChange?.(event.target.value)} />
  );
  return <label className="form-field"><span>{label}</span>{control}{malformed
    ? <small className="field-feedback error">当前值类型不受支持（{JSON.stringify(value)}），请在完整 JSON 模式修正。</small>
    : null}</label>;
}

export function EnumSelect({ label, value, options, disabled, onChange }: {
  label: string; value: unknown; options: string[]; disabled: boolean; onChange: (value: string) => void;
}) {
  const current = typeof value === 'string' ? value : '';
  const supported = options.includes(current);
  return <label className="form-field"><span>{label}</span><select aria-label={label} value={current} disabled={disabled || !supported}
    onChange={(event) => onChange(event.target.value)}>
    {!supported ? <option value={current}>不受支持：{current || JSON.stringify(value)}</option> : null}
    {options.map((option) => <option value={option} key={option}>{option}</option>)}
  </select>{!supported ? <small className="field-feedback error">当前值未被表单支持，请在完整 JSON 模式修正。</small> : null}</label>;
}

export function MalformedValue({ label, value }: { label: string; value: unknown }) {
  return <div className="field-feedback error">{label} 的当前值类型不受支持（{JSON.stringify(value)}），已保留；请在完整 JSON 模式修正。</div>;
}

export function JsonField({ label, document, path, disabled, expected, pendingFields, onPendingChange, onApply, onDiscard, getConflict }: {
  label: string; document: JsonObject; path: Path; disabled: boolean; expected: 'object' | 'array';
  pendingFields: PendingFields; onPendingChange: PendingChange; onApply: PendingResolve; onDiscard: PendingDiscard;
  getConflict: PendingConflict;
}) {
  const value = valueAt(document, path);
  const editability = inspectPathEditability(document, path);
  const pending = pendingFields[path.join('.')];
  const conflict = getConflict(path);
  if (!editability.editable && !pending) {
    return <div className="form-field json-form-field"><span>{label}</span>
      <MalformedValue label={editability.blockedPath.join('.')} value={valueAt(document, editability.blockedPath)} />
    </div>;
  }
  const text = pending?.text ?? JSON.stringify(value, null, 2);
  const parsed = parseJsonField(text ?? '', expected);
  const error = pending ? (pending.error ?? (parsed.ok ? null : parsed.error)) : null;
  return <div className="form-field json-form-field">
    <label><span>{label}</span><textarea aria-label={label} spellCheck={false} value={text ?? ''} disabled={disabled || Boolean(conflict) || !editability.editable}
      onChange={(event) => onPendingChange(path, event.target.value, expected, value)} /></label>
    {!editability.editable ? <MalformedValue label={editability.blockedPath.join('.')} value={valueAt(document, editability.blockedPath)} /> : null}
    {conflict ? <div className="field-feedback error">{conflict}</div> : null}
    {pending ? <div className={error || pending.conflict ? 'field-feedback error' : 'field-feedback'}>
      <span>{pending.conflict ? 'canonical 字段已改变；恢复原值后可应用，或明确丢弃字段文本。' : error ?? 'JSON 可应用；canonical 草稿尚未改变。'}</span>
      <span className="field-actions">
        <button type="button" className="quiet-button" disabled={disabled || Boolean(error) || Boolean(conflict) || pending.conflict || !editability.editable} onClick={() => onApply(path, expected)}>应用 JSON</button>
        <button type="button" className="quiet-button" disabled={disabled} onClick={() => onDiscard(path)}>丢弃字段编辑</button>
      </span>
    </div> : null}
  </div>;
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset className="form-section"><legend>{title}</legend>{children}</fieldset>;
}

export function RowActions({ index, length, disabled, onMove, onRemove }: {
  index: number; length: number; disabled: boolean; onMove: (direction: number) => void; onRemove: () => void;
}) {
  return <div className="row-actions">
    <button type="button" disabled={disabled || index === 0} onClick={() => onMove(-1)} aria-label="上移">↑</button>
    <button type="button" disabled={disabled || index === length - 1} onClick={() => onMove(1)} aria-label="下移">↓</button>
    <button type="button" disabled={disabled} onClick={onRemove}>移除</button>
  </div>;
}
