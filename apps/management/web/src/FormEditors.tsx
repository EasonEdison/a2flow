import type { ReactNode } from 'react';
import type { AssetKind, JsonObject } from './contracts';
import {
  appendRow, inspectDraftText, inspectPathEditability, isEditableRecord, jsonFieldConflict,
  moveRow, parseJsonField, removeRow, skillFrontmatterMismatch, updatePath, updateRow,
  workflowTopologyWarning,
} from './form-editor-state';

type Change = (document: JsonObject) => void;
type Path = string[];

function valueAt(document: any, path: Path): any {
  return path.reduce((value, key) => value?.[key], document);
}

function Field({ label, value, disabled, multiline = false, readOnly = false, onChange }: {
  label: string; value: unknown; disabled: boolean; multiline?: boolean; readOnly?: boolean;
  onChange?: (value: string) => void;
}) {
  const malformed = value !== undefined && typeof value !== 'string';
  const control = multiline ? (
    <textarea value={typeof value === 'string' ? value : ''} disabled={disabled || malformed} readOnly={readOnly}
      onChange={(event) => onChange?.(event.target.value)} />
  ) : (
    <input value={typeof value === 'string' ? value : ''} disabled={disabled || malformed} readOnly={readOnly}
      onChange={(event) => onChange?.(event.target.value)} />
  );
  return <label className="form-field"><span>{label}</span>{control}{malformed
    ? <small className="field-feedback error">当前值类型不受支持（{JSON.stringify(value)}），请在完整 JSON 模式修正。</small>
    : null}</label>;
}

function EnumSelect({ label, value, options, disabled, onChange }: {
  label: string; value: unknown; options: string[]; disabled: boolean; onChange: (value: string) => void;
}) {
  const current = typeof value === 'string' ? value : '';
  const supported = options.includes(current);
  return <label className="form-field"><span>{label}</span><select value={current} disabled={disabled || !supported}
    onChange={(event) => onChange(event.target.value)}>
    {!supported ? <option value={current}>不受支持：{current || JSON.stringify(value)}</option> : null}
    {options.map((option) => <option value={option} key={option}>{option}</option>)}
  </select>{!supported ? <small className="field-feedback error">当前值未被表单支持，请在完整 JSON 模式修正。</small> : null}</label>;
}

function MalformedValue({ label, value }: { label: string; value: unknown }) {
  return <div className="field-feedback error">{label} 的当前值类型不受支持（{JSON.stringify(value)}），已保留；请在完整 JSON 模式修正。</div>;
}

function JsonField({ label, document, path, disabled, expected, onChange }: {
  label: string; document: JsonObject; path: Path; disabled: boolean; expected: 'object' | 'array'; onChange: Change;
}) {
  const value = valueAt(document, path);
  const editability = inspectPathEditability(document, path);
  const conflict = jsonFieldConflict(document, path);
  if (!editability.editable) {
    return <div className="form-field json-form-field"><span>{label}</span>
      <MalformedValue label={editability.blockedPath.join('.')} value={valueAt(document, editability.blockedPath)} />
    </div>;
  }
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  let error: string | null = null;
  if (typeof value === 'string') {
    const parsed = parseJsonField(value, expected);
    error = parsed.ok ? null : parsed.error;
  }
  function apply() {
    if (typeof value !== 'string') return;
    const parsed = parseJsonField(value, expected);
    if (parsed.ok) onChange(updatePath(document, path, parsed.value));
  }
  return (
    <div className="form-field json-form-field">
      <label><span>{label}</span><textarea spellCheck={false} value={text ?? ''} disabled={disabled || Boolean(conflict)}
        onChange={(event) => onChange(updatePath(document, path, event.target.value))} /></label>
      {conflict ? <div className="field-feedback error">{conflict}</div> : null}
      {typeof value === 'string' ? (
        <div className={error ? 'field-feedback error' : 'field-feedback'}>
          <span>{error ?? 'JSON 可应用。'}</span>
          <button type="button" className="quiet-button" disabled={disabled || Boolean(error) || Boolean(conflict)} onClick={apply}>应用 JSON</button>
        </div>
      ) : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset className="form-section"><legend>{title}</legend>{children}</fieldset>;
}

function RowActions({ index, length, disabled, onMove, onRemove }: {
  index: number; length: number; disabled: boolean; onMove: (direction: number) => void; onRemove: () => void;
}) {
  return <div className="row-actions">
    <button type="button" disabled={disabled || index === 0} onClick={() => onMove(-1)} aria-label="上移">↑</button>
    <button type="button" disabled={disabled || index === length - 1} onClick={() => onMove(1)} aria-label="下移">↓</button>
    <button type="button" disabled={disabled} onClick={onRemove}>移除</button>
  </div>;
}

function StringRows({ label, document, path, disabled, onChange }: {
  label: string; document: JsonObject; path: Path; disabled: boolean; onChange: Change;
}) {
  const rows = valueAt(document, path);
  return <Section title={label}>
    {Array.isArray(rows) ? rows.map((value, index) => (
      <div className="form-row compact" key={index}>
        <input aria-label={`${label} ${index + 1}`} value={typeof value === 'string' ? value : ''} disabled={disabled}
          onChange={(event) => {
            const next = rows.slice(); next[index] = event.target.value; onChange(updatePath(document, path, next));
          }} />
        <RowActions index={index} length={rows.length} disabled={disabled}
          onMove={(direction) => onChange(moveRow(document, path, index, direction))}
          onRemove={() => onChange(removeRow(document, path, index))} />
      </div>
    )) : <p className="field-feedback error">当前值不是数组，请在 JSON 模式修正。</p>}
    <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(rows)}
      onClick={() => onChange(appendRow(document, path, ''))}>添加一项</button>
  </Section>;
}

function SkillForm({ document, disabled, onChange }: FormProps) {
  const mismatch = skillFrontmatterMismatch(document);
  const resources = document.resources;
  return <div className="asset-form">
    {mismatch ? <div className="notice warning"><strong>metadata 与 frontmatter 需要核对</strong><span>{mismatch}</span></div> : null}
    <Section title="Metadata">
      {isEditableRecord(document.metadata) || document.metadata === undefined ? <>
        <Field label="名称" value={(document.metadata as any)?.name} disabled={disabled}
          onChange={(value) => onChange(updatePath(document, ['metadata', 'name'], value))} />
        <Field label="描述" value={(document.metadata as any)?.description} disabled={disabled} multiline
          onChange={(value) => onChange(updatePath(document, ['metadata', 'description'], value))} />
      </> : <MalformedValue label="metadata" value={document.metadata} />}
    </Section>
    <Section title="Markdown 指令">
      <Field label="SKILL.md（不会自动改写 frontmatter）" value={document.skillMd} disabled={disabled} multiline
        onChange={(value) => onChange(updatePath(document, ['skillMd'], value))} />
    </Section>
    <StringRows label="所需工具" document={document} path={['requiredToolNames']} disabled={disabled} onChange={onChange} />
    <StringRows label="Ability 绑定" document={document} path={['abilityBindings']} disabled={disabled} onChange={onChange} />
    <StringRows label="Application 绑定" document={document} path={['applicationBindings']} disabled={disabled} onChange={onChange} />
    <Section title="资源（只读）">
      <pre className="resource-summary">{JSON.stringify(resources, null, 2)}</pre>
      <small>资源内容、摘要和 base64 不能在表单模式修改。</small>
    </Section>
  </div>;
}

function AbilityForm({ document, disabled, onChange }: FormProps) {
  const bindings = document.inputBindings;
  const credentials = document.credentialRequirements;
  return <div className="asset-form">
    <Section title="Identity 与适配">
      <Field label="Ability key" value={document.abilityKey} disabled={disabled} readOnly />
      <Field label="Adapter operation reference" value={document.adapterOperationRef} disabled={disabled}
        onChange={(value) => onChange(updatePath(document, ['adapterOperationRef'], value))} />
      <Field label="Default success policy reference" value={document.defaultSuccessPolicyRef} disabled={disabled}
        onChange={(value) => onChange(updatePath(document, ['defaultSuccessPolicyRef'], value))} />
    </Section>
    <Section title="Input bindings">
      {Array.isArray(bindings) ? bindings.map((row: any, index) => isEditableRecord(row) ? <div className="form-row" key={index}>
        <Field label="Target path" value={row.targetPath} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['inputBindings'], index, 'targetPath', value))} />
        <EnumSelect label="Source" value={row.source} options={['MODEL_ARGUMENT', 'TRUSTED_CONTEXT']} disabled={disabled}
          onChange={(value) => onChange(updateRow(document, ['inputBindings'], index, 'source', value))} />
        <Field label="Source path" value={row.sourcePath} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['inputBindings'], index, 'sourcePath', value))} />
        <RowActions index={index} length={bindings.length} disabled={disabled} onMove={(direction) => onChange(moveRow(document, ['inputBindings'], index, direction))} onRemove={() => onChange(removeRow(document, ['inputBindings'], index))} />
      </div> : <MalformedValue key={index} label={`inputBindings[${index}]`} value={row} />) : <p className="field-feedback error">inputBindings 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(bindings)} onClick={() => onChange(appendRow(document, ['inputBindings'], { targetPath: '', source: 'MODEL_ARGUMENT', sourcePath: '' }))}>添加 binding</button>
    </Section>
    <Section title="Credential slot declarations">
      {Array.isArray(credentials) ? credentials.map((row: any, index) => isEditableRecord(row) ? <div className="form-row compact" key={index}>
        <Field label="Slot ID（不填写真实凭据）" value={row.slotId} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['credentialRequirements'], index, 'slotId', value))} />
        {typeof row.required === 'boolean' || row.required === undefined
          ? <label className="checkbox-field"><input type="checkbox" checked={row.required === true} disabled={disabled} onChange={(event) => onChange(updateRow(document, ['credentialRequirements'], index, 'required', event.target.checked))} />必需</label>
          : <MalformedValue label={`credentialRequirements[${index}].required`} value={row.required} />}
        <RowActions index={index} length={credentials.length} disabled={disabled} onMove={(direction) => onChange(moveRow(document, ['credentialRequirements'], index, direction))} onRemove={() => onChange(removeRow(document, ['credentialRequirements'], index))} />
      </div> : <MalformedValue key={index} label={`credentialRequirements[${index}]`} value={row} />) : <p className="field-feedback error">credentialRequirements 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(credentials)} onClick={() => onChange(appendRow(document, ['credentialRequirements'], { slotId: '', required: true }))}>添加 credential slot</button>
    </Section>
    <JsonField label="Model argument schema" document={document} path={['modelArgumentSchema']} expected="object" disabled={disabled} onChange={onChange} />
    <JsonField label="Resolved input schema" document={document} path={['resolvedInputSchema']} expected="object" disabled={disabled} onChange={onChange} />
    <JsonField label="Output schema" document={document} path={['outputSchema']} expected="object" disabled={disabled} onChange={onChange} />
    <JsonField label="Result interpretation policies" document={document} path={['resultInterpretationPolicies']} expected="array" disabled={disabled} onChange={onChange} />
  </div>;
}

function ApplicationForm({ document, disabled, onChange }: FormProps) {
  const definition = document.definition as any;
  const actions = definition?.actionPolicies;
  const dependencies = document.dependencies;
  const mode = definition?.renderPolicy?.interactionMode;
  return <div className="asset-form">
    {isEditableRecord(definition) ? <>
    <Section title="Identity">
      <Field label="Application key" value={(definition.asset as any)?.applicationKey} disabled={disabled} readOnly />
      <Field label="Protocol profile" value={(definition.asset as any)?.protocolProfileRef} disabled={disabled} readOnly />
      <Field label="Component catalog" value={(definition.asset as any)?.componentCatalogRef} disabled={disabled} readOnly />
    </Section>
    <Section title="Interaction mode">
      {isEditableRecord(definition.renderPolicy) || definition.renderPolicy === undefined
        ? <EnumSelect label="Mode" value={mode} options={['DISPLAY_ONLY', 'INTERACTIVE']} disabled={disabled}
          onChange={(value) => onChange(updatePath(document, ['definition', 'renderPolicy', 'interactionMode'], value))} />
        : <MalformedValue label="definition.renderPolicy" value={definition.renderPolicy} />}
      <p className="field-feedback">更改 mode 不会删除 Actions、组件或改写固定策略。请依据下方警告在 JSON 模式明确调整。</p>
      {(mode === 'DISPLAY_ONLY' && Array.isArray(actions) && actions.length > 0) || (mode === 'INTERACTIVE' && Array.isArray(actions) && actions.length === 0)
        ? <div className="notice warning">当前 interactionMode 与 Action 数量不一致；后端验证会拒绝，表单不会自动修复。</div> : null}
    </Section>
    <JsonField label="Parameter schema" document={document} path={['definition', 'surfaceTemplate', 'inputSchema']} expected="object" disabled={disabled} onChange={onChange} />
    <Section title="Action policies">
      {Array.isArray(actions) ? actions.map((row: any, index) => isEditableRecord(row) ? <div className="form-row action-row" key={index}>
        {['actionName', 'sourceComponentId', 'abilityReleaseRef', 'successPolicyRef'].map((field) => <Field key={field} label={field} value={row[field]} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['definition', 'actionPolicies'], index, field, value))} />)}
        {typeof row.completeInteractionOnSuccess === 'boolean' || row.completeInteractionOnSuccess === undefined
          ? <label className="checkbox-field"><input type="checkbox" checked={row.completeInteractionOnSuccess === true} disabled={disabled} onChange={(event) => onChange(updateRow(document, ['definition', 'actionPolicies'], index, 'completeInteractionOnSuccess', event.target.checked))} />completeInteractionOnSuccess</label>
          : <MalformedValue label={`actionPolicies[${index}].completeInteractionOnSuccess`} value={row.completeInteractionOnSuccess} />}
        <div className="fixed-policy">固定安全策略：controlRequestDedupeOnly={String(row.controlRequestDedupeOnly)} · businessIdempotencyOwner={String(row.businessIdempotencyOwner)}</div>
        <RowActions index={index} length={actions.length} disabled={disabled} onMove={(direction) => onChange(moveRow(document, ['definition', 'actionPolicies'], index, direction))} onRemove={() => onChange(removeRow(document, ['definition', 'actionPolicies'], index))} />
      </div> : <MalformedValue key={index} label={`actionPolicies[${index}]`} value={row} />) : <p className="field-feedback error">actionPolicies 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(actions)} onClick={() => onChange(appendRow(document, ['definition', 'actionPolicies'], { actionName: '', sourceComponentId: '', abilityReleaseRef: '', successPolicyRef: '', completeInteractionOnSuccess: true, controlRequestDedupeOnly: true, businessIdempotencyOwner: 'CALLED_API_BACKEND' }))}>添加 Action</button>
    </Section>
    <Section title="Dependencies">
      {Array.isArray(dependencies) ? dependencies.map((row: any, index) => isEditableRecord(row) ? <div className="form-row compact" key={index}>
        <EnumSelect label="Kind" value={row.kind} options={['ABILITY', 'COMPONENT']} disabled={disabled}
          onChange={(value) => onChange(updateRow(document, ['dependencies'], index, 'kind', value))} />
        <Field label="Key" value={row.key} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['dependencies'], index, 'key', value))} />
        <RowActions index={index} length={dependencies.length} disabled={disabled} onMove={(direction) => onChange(moveRow(document, ['dependencies'], index, direction))} onRemove={() => onChange(removeRow(document, ['dependencies'], index))} />
      </div> : <MalformedValue key={index} label={`dependencies[${index}]`} value={row} />) : <p className="field-feedback error">dependencies 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(dependencies)} onClick={() => onChange(appendRow(document, ['dependencies'], { kind: 'ABILITY', key: '' }))}>添加依赖</button>
    </Section>
    <JsonField label="Surface template" document={document} path={['definition', 'surfaceTemplate']} expected="object" disabled={disabled} onChange={onChange} />
    <Section title="固定策略（只读）"><pre className="resource-summary">{JSON.stringify({ interactionPolicy: definition?.interactionPolicy, versionAdmissionPolicy: definition?.versionAdmissionPolicy, retryPolicy: definition?.retryPolicy, finalizerPolicy: definition?.finalizerPolicy }, null, 2)}</pre></Section>
    </> : <MalformedValue label="definition" value={definition} />}
  </div>;
}

function WorkflowForm({ document, disabled, onChange }: FormProps) {
  const nodes = document.nodes;
  const warning = workflowTopologyWarning(document);
  return <div className="asset-form">
    {warning ? <div className="notice warning"><strong>当前拓扑不可发布</strong><span>{warning}</span></div> : null}
    <Section title="Workflow">
      <Field label="Definition key" value={document.definitionKey} disabled={disabled} readOnly />
      <Field label="Topology（只读，不会自动转换）" value={document.topology} disabled={disabled} readOnly />
    </Section>
    <Section title="Nodes">
      {Array.isArray(nodes) ? nodes.map((row: any, index) => isEditableRecord(row) ? <div className="form-row compact" key={index}>
        <Field label="Node ID" value={row.nodeId} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['nodes'], index, 'nodeId', value))} />
        <Field label="Skill key" value={row.skillKey} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['nodes'], index, 'skillKey', value))} />
        <RowActions index={index} length={nodes.length} disabled={disabled} onMove={(direction) => onChange(moveRow(document, ['nodes'], index, direction))} onRemove={() => onChange(removeRow(document, ['nodes'], index))} />
      </div> : <MalformedValue key={index} label={`nodes[${index}]`} value={row} />) : <p className="field-feedback error">nodes 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(nodes)} onClick={() => onChange(appendRow(document, ['nodes'], { nodeId: '', skillKey: '' }))}>添加节点</button>
    </Section>
    <Section title="顺序预览"><ol className="sequence-preview">{Array.isArray(nodes) ? nodes.map((node: any, index) => <li key={index}><strong>{String(node?.nodeId ?? '')}</strong><span>{String(node?.skillKey ?? '')}</span></li>) : null}</ol></Section>
  </div>;
}

type FormProps = { document: JsonObject; disabled: boolean; onChange: Change };

export function FormEditor({ kind, text, disabled, onEdit }: {
  kind: AssetKind; text: string; disabled: boolean; onEdit: (text: string) => void;
}) {
  const inspected = inspectDraftText(text);
  if (!inspected.ok) return <div className="notice warning"><strong>无法打开表单模式</strong><span>{inspected.error}</span><span>原始 JSON 已保留，请切回 JSON 模式修正。</span></div>;
  const onChange = (document: JsonObject) => onEdit(JSON.stringify(document, null, 2));
  if (kind === 'SKILL') return <SkillForm document={inspected.document} disabled={disabled} onChange={onChange} />;
  if (kind === 'ABILITY') return <AbilityForm document={inspected.document} disabled={disabled} onChange={onChange} />;
  if (kind === 'APPLICATION') return <ApplicationForm document={inspected.document} disabled={disabled} onChange={onChange} />;
  return <WorkflowForm document={inspected.document} disabled={disabled} onChange={onChange} />;
}
