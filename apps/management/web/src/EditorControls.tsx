import { useRef, type ReactNode } from 'react';
import type { ApplicationPreviewState } from './A2UIWorkbench';
import type { AssetKind, JsonObject, PendingResourceEdits, ReferenceCatalog } from './contracts';
import {
  inspectPathEditability, isEditableRecord, parseJsonField, type PendingFields,
} from './form-editor-state';

export type Change = (document: JsonObject) => void;
export type Path = string[];
export type PendingChange = (path: Path, text: string, expected: 'object' | 'array', baseValue: unknown) => void;
export type PendingResolve = (path: Path, expected: 'object' | 'array') => void;
export type PendingDiscard = (path: Path) => void;
export type PendingConflict = (path: Path) => string | null;
export type FormProps<TDocument extends JsonObject = JsonObject> = {
  skillStage?: string;
  document: TDocument;
  disabled: boolean;
  onChange: Change;
  pendingFields: PendingFields;
  onPendingChange: PendingChange;
  onApplyPending: PendingResolve;
  onDiscardPending: PendingDiscard;
  getPendingConflict: PendingConflict;
  references?: ReferenceCatalog;
  onNavigateReference?: (kind: AssetKind, key: string) => void;
  previewState?: ApplicationPreviewState;
  onPreviewStateChange?: (state: ApplicationPreviewState) => void;
  assetId: string;
  revision: number;
  pendingResources: PendingResourceEdits;
  onPendingResourcesChange: (pending: PendingResourceEdits) => void;
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
    ? <small className="field-feedback error">当前值类型不受支持（{JSON.stringify(value)}），请重新加载草稿；若问题仍存在，由后端修复该字段结构。</small>
    : null}</label>;
}

export function ReferencePicker({ label, value, kind, disabled, references, onChange }: {
  label: string; value: unknown; kind: AssetKind; disabled: boolean;
  references?: ReferenceCatalog; onChange: (value: string) => void;
}) {
  if (typeof value !== 'string') {
    return <label className="form-field"><span>{label}</span><select aria-label={label} value="" disabled><option value="">类型错误</option></select>
      <small className="field-feedback error">当前值类型不受支持（{JSON.stringify(value)}），原值已保留；请重新加载草稿后核对。</small></label>;
  }
  const current = value;
  const options = references?.assets[kind] ?? [];
  const values = options.map((item) => item.key ?? item.skillKey).filter((item): item is string => Boolean(item));
  const known = values.includes(current);
  return <label className="form-field"><span>{label}</span><select aria-label={label} value={current}
    disabled={disabled || references?.loading} onChange={(event) => onChange(event.target.value)}>
    <option value="">请选择已发布 {kind}</option>
    {current && !known ? <option value={current}>当前不可用：{current}</option> : null}
    {values.map((item) => <option value={item} key={item}>{item}</option>)}
  </select>
  {references?.loading ? <small className="field-feedback">正在加载引用…</small> : null}
  {references?.errors[kind] ? <small className="field-feedback error">引用加载失败：{references.errors[kind]}</small> : null}
  {!references?.loading && !references?.errors[kind] && values.length === 0 ? <small className="field-feedback">没有可用的已发布引用。</small> : null}
  {current && !known ? <small className="field-feedback error">当前引用不可用，原值已保留。</small> : null}</label>;
}

export function ReleaseReferencePicker({ label, value, disabled, references, onChange }: {
  label: string; value: unknown; disabled: boolean; references?: ReferenceCatalog; onChange: (value: string) => void;
}) {
  if (typeof value !== 'string') {
    return <div className="form-field"><span>{label}</span><div className="reference-pair">
      <select aria-label={`${label} key`} value="" disabled><option value="">类型错误</option></select>
      <select aria-label={`${label} version`} value="" disabled><option value="">类型错误</option></select>
    </div><small className="field-feedback error">当前值类型不受支持（{JSON.stringify(value)}），原值已保留；请重新加载草稿后核对。</small></div>;
  }
  const current = value;
  const [key = '', version = ''] = current.split('@');
  const abilities = references?.assets.ABILITY ?? [];
  const keys = abilities.map((item) => item.key).filter((item): item is string => Boolean(item));
  const versions = references?.histories[`ABILITY:${key}`]?.versions ?? [];
  const historyError = references?.errors[`ABILITY:${key}`];
  return <div className="form-field"><span>{label}</span><div className="reference-pair">
    <select aria-label={`${label} key`} value={key} disabled={disabled || references?.loading}
      onChange={(event) => onChange(event.target.value ? `${event.target.value}@` : '')}>
      <option value="">选择 Ability</option>
      {key && !keys.includes(key) ? <option value={key}>当前不可用：{key}</option> : null}
      {keys.map((item) => <option value={item} key={item}>{item}</option>)}
    </select>
    <select aria-label={`${label} version`} value={version} disabled={disabled || !key || Boolean(historyError)}
      onChange={(event) => onChange(`${key}@${event.target.value}`)}>
      <option value="">选择保留版本</option>
      {version && !versions.some((item) => item.versionId === version) ? <option value={version}>当前不可用：{version}</option> : null}
      {versions.map((item) => <option value={item.versionId} key={item.versionId}>{item.versionId}</option>)}
    </select>
  </div>{historyError ? <small className="field-feedback error">版本历史加载失败：{historyError} <button type="button" className="quiet-button" onClick={references?.retry}>重试</button></small> : null}
  {current && (!keys.includes(key) || (!historyError && !versions.some((item) => item.versionId === version)))
    ? <small className="field-feedback error">当前 release 引用不可用，原值已保留。</small> : null}</div>;
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
  </select>{!supported ? <small className="field-feedback error">当前值未被表单支持，请重新加载草稿后核对。</small> : null}</label>;
}

export function MalformedValue({ label, value }: { label: string; value: unknown }) {
  return <div className="field-feedback error">{label} 的当前值类型不受支持（{JSON.stringify(value)}），已保留；请重新加载草稿后核对。</div>;
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
