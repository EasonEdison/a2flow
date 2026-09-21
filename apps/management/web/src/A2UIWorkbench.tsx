import { useEffect, useMemo, useState } from 'react';
import {
  A2UI_COMPONENT_TYPES,
  addComponent,
  analyzeSurface,
  createPreview,
  moveComponent,
  removeComponent,
  simulateAction,
  updateComponentProperty,
  validateSample,
  type SurfaceIssue,
} from './a2ui-workbench';
import { isEditableRecord, type PendingFields } from './form-editor-state';
import { JsonField, type PendingChange, type PendingConflict, type PendingDiscard, type PendingResolve } from './EditorControls';
import type { JsonObject } from './contracts';

export interface ApplicationPreviewState {
  sampleText: string;
  renderedSample: JsonObject | null;
  device: 'desktop' | 'narrow';
}

const DEFAULT_SAMPLE = JSON.stringify({
  prompt: '请选择一个选项',
  options: [{ label: '示例选项', value: 'sample' }],
  selection: 'sample',
}, null, 2);

function schemaPaths(schema: unknown): string[] {
  if (!isEditableRecord(schema) || !isEditableRecord(schema.properties)) return [];
  return Object.keys(schema.properties).map((key) => `/${key.replace(/~/g, '~0').replace(/\//g, '~1')}`);
}

function PreviewNode({ node, onAction }: { node: unknown; onAction: (id: string) => void }) {
  if (!isEditableRecord(node)) return null;
  const id = typeof node.id === 'string' ? node.id : '';
  if (node.component === 'Column') return <div className="a2ui-preview-column">{Array.isArray(node.children) ? node.children.map((child, index) => <PreviewNode key={`${id}-${index}`} node={child} onAction={onAction} />) : null}</div>;
  if (node.component === 'Text') return <p className="a2ui-preview-text">{typeof node.value === 'string' ? node.value : JSON.stringify(node.value)}</p>;
  if (node.component === 'ChoicePicker') return <div className="a2ui-preview-choices">{Array.isArray(node.options) ? node.options.map((option, index) => isEditableRecord(option) ? <label key={`${id}-${index}`}><input type="radio" name={`preview-${id}`} checked={option.value === node.value} readOnly /><span>{String(option.label ?? option.value ?? '')}</span></label> : <span key={`${id}-${index}`}>无效选项</span>) : <span>options 不是数组</span>}</div>;
  if (node.component === 'Button') return <button type="button" onClick={() => onAction(id)}>{String(node.label ?? 'Button')}</button>;
  return null;
}

function IssueList({ issues, onFocus }: { issues: SurfaceIssue[]; onFocus: (issue: SurfaceIssue) => void }) {
  const unique = [...new Map(issues.map((item) => [`${item.code}\u0000${item.path}\u0000${item.componentId ?? ''}\u0000${item.samplePath ?? ''}`, item])).values()];
  if (!unique.length) return null;
  return <div className="a2ui-issues notice warning"><strong>结构与绑定问题</strong><ul>{unique.map((item, index) => <li key={`${item.code}-${item.path}-${index}`}><button type="button" className="issue-link" onClick={() => onFocus(item)}>{item.code} · {item.path} · {item.message}</button></li>)}</ul></div>;
}

function PropertyPanel({ document, component, index, paths, disabled, pendingFields, onUpdate, onPendingChange, onApplyPending, onDiscardPending, getPendingConflict }: {
  document: JsonObject; component: JsonObject; index: number; paths: string[]; disabled: boolean; pendingFields: PendingFields;
  onUpdate: (path: string[], value: unknown) => void;
  onPendingChange: PendingChange; onApplyPending: PendingResolve; onDiscardPending: PendingDiscard; getPendingConflict: PendingConflict;
}) {
  const type = component.component;
  const bindingControl = (label: string, field: string) => {
    const value = component[field];
    const editable = isEditableRecord(value) && typeof value.path === 'string';
    return <label className="form-field"><span>{label}</span><input aria-label={label} list={`schema-paths-${index}`} value={editable ? String(value.path) : ''} disabled={disabled || !editable} onChange={(event) => onUpdate([field, 'path'], event.target.value)} />{!editable ? <small className="field-feedback error">当前值类型不受支持（{JSON.stringify(value)}），原值已保留；请重新加载草稿后核对。</small> : null}</label>;
  };
  const event = isEditableRecord(component.action) && isEditableRecord(component.action.event) ? component.action.event : null;
  const actionEditable = Boolean(event && typeof event.name === 'string');
  return <section className="a2ui-property-panel" aria-label="组件属性">
    <div><p className="section-label">Properties</p><h4>{String(component.id)} · {String(type)}</h4></div>
    <label className="form-field"><span>Component ID（只读）</span><input value={String(component.id ?? '')} readOnly /></label>
    {type === 'Column' ? <JsonField label="Children IDs" document={document} path={['definition', 'surfaceTemplate', 'components', String(index), 'children']} expected="array" disabled={disabled} pendingFields={pendingFields} onPendingChange={onPendingChange} onApply={onApplyPending} onDiscard={onDiscardPending} getConflict={getPendingConflict} /> : null}
    {type === 'Text' ? bindingControl('Text binding path', 'text') : null}
    {type === 'ChoicePicker' ? <>{bindingControl('Options binding path', 'options')}{bindingControl('Value binding path', 'value')}<label className="form-field"><span>Variant（合同固定）</span><input value={String(component.variant ?? '')} readOnly /></label></> : null}
    {type === 'Button' ? <><label className="form-field"><span>Button label</span><input aria-label="Button label" value={typeof component.label === 'string' ? component.label : ''} disabled={disabled || typeof component.label !== 'string'} onChange={(event) => onUpdate(['label'], event.target.value)} />{typeof component.label !== 'string' ? <small className="field-feedback error">当前值类型不受支持（{JSON.stringify(component.label)}），原值已保留；请重新加载草稿后核对。</small> : null}</label><label className="form-field"><span>Event name</span><input aria-label="Event name" value={actionEditable ? event?.name as string : ''} disabled={disabled || !actionEditable} onChange={(event) => onUpdate(['action', 'event', 'name'], event.target.value)} />{!actionEditable ? <small className="field-feedback error">action/event 结构不受支持，原值已保留；请重新加载草稿后核对。</small> : null}</label></> : null}
    <datalist id={`schema-paths-${index}`}>{paths.map((path) => <option value={path} key={path} />)}</datalist>
    <p className="field-feedback">仅编辑当前表单支持的合同字段；其他字段保持原样。异常结构由服务端校验与修复流程处理。</p>
  </section>;
}

export function A2UIWorkbench({ document, surface, disabled, previewState, componentCatalog, pendingFields, onPreviewStateChange, onChange, onPendingChange, onApplyPending, onDiscardPending, getPendingConflict }: {
  document: JsonObject;
  surface: JsonObject;
  disabled: boolean;
  previewState: ApplicationPreviewState;
  componentCatalog: { key: string; loading: boolean; error: string | null; members: string[] };
  pendingFields: PendingFields;
  onPreviewStateChange: (state: ApplicationPreviewState) => void;
  onChange: (document: JsonObject) => void;
  onPendingChange: PendingChange;
  onApplyPending: PendingResolve;
  onDiscardPending: PendingDiscard;
  getPendingConflict: PendingConflict;
}) {
  const analysis = useMemo(() => analyzeSurface(surface), [surface]);
  const paths = useMemo(() => schemaPaths(surface.inputSchema), [surface.inputSchema]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const supportedCatalogMembers = useMemo(() => componentCatalog.members.filter((name) => A2UI_COMPONENT_TYPES.includes(name)), [componentCatalog.members]);
  const unsupportedCatalogMembers = useMemo(() => componentCatalog.members.filter((name) => !A2UI_COMPONENT_TYPES.includes(name)), [componentCatalog.members]);
  const [componentToAdd, setComponentToAdd] = useState('');
  useEffect(() => {
    setComponentToAdd((current) => supportedCatalogMembers.includes(current) ? current : supportedCatalogMembers[0] ?? '');
  }, [supportedCatalogMembers]);
  const [previewIssues, setPreviewIssues] = useState<SurfaceIssue[]>([]);
  const [simulatedEvent, setSimulatedEvent] = useState<Record<string, unknown> | null>(null);
  const selected = Array.isArray(surface.components) && isEditableRecord(surface.components[selectedIndex]) ? surface.components[selectedIndex] : null;
  const rendered = previewState.renderedSample ? createPreview(surface, previewState.renderedSample) : null;
  const renderedIssues = rendered && !rendered.ok ? rendered.issues : [];
  const actionPolicies = isEditableRecord(document.definition) && Array.isArray(document.definition.actionPolicies) ? document.definition.actionPolicies : [];
  const policyIssues: SurfaceIssue[] = actionPolicies.flatMap((policy, index) => {
    if (!isEditableRecord(policy) || typeof policy.sourceComponentId !== 'string') return [];
    return analysis.nodes.some((node) => node.id === policy.sourceComponentId) ? [] : [{ code: 'DANGLING_ACTION_SOURCE', path: `/actionPolicies/${index}/sourceComponentId`, message: `Action source ${policy.sourceComponentId} 不存在。`, componentId: policy.sourceComponentId }];
  });
  function replaceSurface(next: JsonObject) {
    onChange({ ...document, definition: { ...(document.definition as JsonObject), surfaceTemplate: next } });
  }
  function focusIssue(item: SurfaceIssue) {
    if (item.componentId) {
      const index = analysis.nodes.find((node) => node.id === item.componentId)?.index;
      if (index !== undefined) setSelectedIndex(index);
    }
    if (item.samplePath) documentQuery<HTMLInputElement | HTMLTextAreaElement>('Preview sample JSON')?.focus();
  }
  function updatePreview() {
    setSimulatedEvent(null);
    try {
      const value = JSON.parse(previewState.sampleText);
      if (!isEditableRecord(value)) throw new Error('示例输入必须是 JSON 对象。');
      const validation = validateSample(surface, value);
      setPreviewIssues(validation.issues);
      onPreviewStateChange({ ...previewState, renderedSample: validation.valid ? value : null });
    } catch (error) {
      setPreviewIssues([{ code: 'INVALID_SAMPLE_JSON', path: '/', samplePath: '/', message: error instanceof Error ? error.message : '示例 JSON 无效。' }]);
      onPreviewStateChange({ ...previewState, renderedSample: null });
    }
  }
  function simulate(componentId: string) {
    if (!previewState.renderedSample) return;
    setSimulatedEvent(simulateAction(surface, componentId, previewState.renderedSample));
  }
  return <section className="a2ui-workbench" aria-label="A2UI authoring workbench">
    <header className="a2ui-workbench-heading"><div><p className="section-label">Local safe workbench</p><h3>A2UI 组件与预览</h3></div><span>SIMULATED / LOCAL</span></header>
    {componentCatalog.loading ? <div className="notice warning"><strong>正在读取已发布组件目录</strong><span>{componentCatalog.key}；加载完成前不能新增组件。</span></div> : null}
    {componentCatalog.error ? <div className="notice error"><strong>组件目录不可用，已失败关闭新增入口</strong><span>{componentCatalog.error}</span></div> : null}
    {!componentCatalog.loading && !componentCatalog.error && supportedCatalogMembers.length === 0 ? <div className="notice warning"><strong>当前已发布目录没有可用组件</strong><span>请先在组件中心修改草稿，经验证并显式发布新版本。</span></div> : null}
    {unsupportedCatalogMembers.length ? <div className="notice error"><strong>目录含有当前宿主未实现的成员</strong><span>{unsupportedCatalogMembers.join(', ')} 不会出现在新增列表中。</span></div> : null}
    <IssueList issues={[...analysis.issues, ...policyIssues, ...previewIssues, ...renderedIssues]} onFocus={focusIssue} />
    <div className="a2ui-author-grid">
      <section className="a2ui-component-tree" aria-label="组件层级">
        <div className="a2ui-panel-title"><strong>组件层级与数组顺序</strong><select aria-label="新增组件类型" value={componentToAdd} disabled={disabled || componentCatalog.loading || Boolean(componentCatalog.error) || supportedCatalogMembers.length === 0} onChange={(event) => setComponentToAdd(event.target.value)}>{supportedCatalogMembers.map((type) => <option key={type}>{type}</option>)}</select><button type="button" className="secondary-button" disabled={disabled || componentCatalog.loading || Boolean(componentCatalog.error) || !componentToAdd || !Array.isArray(surface.components) || surface.components.length >= 128} onClick={() => replaceSurface(addComponent(surface, componentToAdd))}>添加</button></div>
        <ol>{analysis.nodes.map((node) => <li key={`${node.index}-${String(node.id)}`} className={selectedIndex === node.index ? 'selected' : ''}><button type="button" onClick={() => setSelectedIndex(node.index)}>{String(node.id ?? '(invalid id)')} · {String(node.component ?? '(invalid type)')}</button><small>{node.path}{node.children.length ? ` → ${node.children.join(', ')}` : ''}</small><div className="row-actions"><button type="button" aria-label={`上移组件 ${String(node.id)}`} disabled={disabled || node.index === 0} onClick={() => { replaceSurface(moveComponent(surface, node.index, -1)); setSelectedIndex(Math.max(0, node.index - 1)); }}>上移</button><button type="button" aria-label={`下移组件 ${String(node.id)}`} disabled={disabled || node.index === analysis.nodes.length - 1} onClick={() => { replaceSurface(moveComponent(surface, node.index, 1)); setSelectedIndex(Math.min(analysis.nodes.length - 1, node.index + 1)); }}>下移</button><button type="button" aria-label={`移除组件 ${String(node.id)}`} disabled={disabled} onClick={() => { replaceSurface(removeComponent(surface, node.index)); setSelectedIndex(0); }}>移除</button></div></li>)}</ol>
      </section>
      {selected ? <PropertyPanel document={document} component={selected} index={selectedIndex} paths={paths} disabled={disabled} pendingFields={pendingFields} onUpdate={(path, value) => replaceSurface(updateComponentProperty(surface, selectedIndex, path, value))} onPendingChange={onPendingChange} onApplyPending={onApplyPending} onDiscardPending={onDiscardPending} getPendingConflict={getPendingConflict} /> : <section className="a2ui-property-panel"><p>选择可编辑组件；异常行保持只读，请重新加载草稿或由后端修复字段结构。</p></section>}
    </div>
    <section className="a2ui-preview-panel">
      <div className="a2ui-preview-controls"><div><strong>安全本地预览</strong><small>不执行 Action、不发请求、不导航、不渲染 HTML 或外部图片。</small></div><div className="mode-switch"><button type="button" className={previewState.device === 'desktop' ? 'active' : ''} onClick={() => onPreviewStateChange({ ...previewState, device: 'desktop' })}>桌面</button><button type="button" className={previewState.device === 'narrow' ? 'active' : ''} onClick={() => onPreviewStateChange({ ...previewState, device: 'narrow' })}>窄屏</button></div></div>
      <div className="a2ui-preview-grid"><label className="form-field"><span>Preview sample JSON</span><textarea aria-label="Preview sample JSON" spellCheck={false} value={previewState.sampleText} onChange={(event) => onPreviewStateChange({ ...previewState, sampleText: event.target.value })} /><button type="button" className="secondary-button" onClick={updatePreview}>更新本地预览</button></label><div className={`a2ui-preview-frame ${previewState.device}`} aria-label="本地模拟预览">{rendered?.ok && rendered.root ? <PreviewNode node={rendered.root} onAction={simulate} /> : <p>输入有效示例并显式更新后显示预览。</p>}</div></div>
      {simulatedEvent ? <div className="simulated-event"><strong>仅模拟事件记录</strong><pre>{JSON.stringify(simulatedEvent, null, 2)}</pre><span>未执行 Ability、业务请求或工作流完成。</span></div> : null}
    </section>
  </section>;
}

function documentQuery<T extends HTMLElement>(label: string): T | null {
  return window.document.querySelector<T>(`[aria-label="${CSS.escape(label)}"]`);
}

export function initialApplicationPreviewState(): ApplicationPreviewState {
  return { sampleText: DEFAULT_SAMPLE, renderedSample: null, device: 'desktop' };
}
