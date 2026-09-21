import { useEffect, useState } from 'react';
import { A2UIWorkbench } from './A2UIWorkbench';
import { managementApi } from './api';
import { inspectPublishedComponentCatalog } from './component-catalog-state';
import { appendRow, isEditableRecord, moveRow, removeRow, updatePath, updateRow } from './form-editor-state';
import { EnumSelect, Field, JsonField, MalformedValue, ReferencePicker, ReleaseReferencePicker, RowActions, Section, useRowKeys, type FormProps } from './EditorControls';
import type { ApplicationDraftDocument } from './asset-drafts';

export function ApplicationEditor({ document, disabled, onChange, pendingFields, references, previewState, onPreviewStateChange, onPendingChange, onApplyPending, onDiscardPending, getPendingConflict }: FormProps<ApplicationDraftDocument>) {
  const definition = document.definition;
  const actions = isEditableRecord(definition) ? definition.actionPolicies : undefined;
  const dependencies = document.dependencies;
  const renderPolicy = isEditableRecord(definition) && isEditableRecord(definition.renderPolicy) ? definition.renderPolicy : undefined;
  const mode = renderPolicy?.interactionMode;
  const asset = isEditableRecord(definition) && isEditableRecord(definition.asset) ? definition.asset : undefined;
  const componentCatalogRef = typeof asset?.componentCatalogRef === 'string' ? asset.componentCatalogRef : '';
  const protocolProfileRef = typeof asset?.protocolProfileRef === 'string' ? asset.protocolProfileRef : '';
  const [catalog, setCatalog] = useState<{ key: string; loading: boolean; error: string | null; members: string[] }>({ key: '', loading: false, error: '未选择已发布组件目录。', members: [] });
  useEffect(() => {
    if (!componentCatalogRef) {
      setCatalog({ key: '', loading: false, error: '未选择已发布组件目录。', members: [] });
      return;
    }
    const controller = new AbortController();
    setCatalog({ key: componentCatalogRef, loading: true, error: null, members: [] });
    managementApi.detail('COMPONENT', componentCatalogRef, controller.signal).then((detail) => {
      if (controller.signal.aborted) return;
      const inspected = inspectPublishedComponentCatalog(detail, componentCatalogRef);
      if (!inspected.ok) {
        setCatalog({ key: componentCatalogRef, loading: false, error: inspected.error, members: [] });
      } else if (protocolProfileRef && inspected.protocolProfileRef !== protocolProfileRef) {
        setCatalog({ key: componentCatalogRef, loading: false, error: `目录协议 ${inspected.protocolProfileRef} 与 Application 协议 ${protocolProfileRef} 不匹配。`, members: [] });
      } else {
        setCatalog({ key: componentCatalogRef, loading: false, error: null, members: inspected.components });
      }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setCatalog({ key: componentCatalogRef, loading: false, error: error instanceof Error ? error.message : '组件目录加载失败。', members: [] });
    });
    return () => controller.abort();
  }, [componentCatalogRef, protocolProfileRef]);
  const actionKeys = useRowKeys(Array.isArray(actions) ? actions.length : 0);
  const dependencyKeys = useRowKeys(Array.isArray(dependencies) ? dependencies.length : 0);
  return <div className="asset-form">
    {isEditableRecord(definition) ? <>
      <Section title="Identity"><Field label="Application key" value={asset?.applicationKey} disabled={disabled} readOnly /><Field label="Protocol profile" value={asset?.protocolProfileRef} disabled={disabled} readOnly /><Field label="Component catalog" value={asset?.componentCatalogRef} disabled={disabled} readOnly /></Section>
      <Section title="Interaction mode">
        {isEditableRecord(definition.renderPolicy) || definition.renderPolicy === undefined ? <EnumSelect label="Mode" value={mode} options={['DISPLAY_ONLY', 'INTERACTIVE']} disabled={disabled} onChange={(value) => onChange(updatePath(document, ['definition', 'renderPolicy', 'interactionMode'], value))} /> : <MalformedValue label="definition.renderPolicy" value={definition.renderPolicy} />}
        <p className="field-feedback">更改 mode 不会删除 Actions、组件或改写固定策略。请依据下方警告在对应表单区域明确调整。</p>
        {(mode === 'DISPLAY_ONLY' && Array.isArray(actions) && actions.length > 0) || (mode === 'INTERACTIVE' && Array.isArray(actions) && actions.length === 0) ? <div className="notice warning">当前 interactionMode 与 Action 数量不一致；后端验证会拒绝，表单不会自动修复。</div> : null}
      </Section>
      <JsonField label="Parameter schema" document={document} path={['definition', 'surfaceTemplate', 'inputSchema']} expected="object" disabled={disabled} pendingFields={pendingFields} onPendingChange={onPendingChange} onApply={onApplyPending} onDiscard={onDiscardPending} getConflict={getPendingConflict} />
      {isEditableRecord(definition.surfaceTemplate) && previewState && onPreviewStateChange ? <A2UIWorkbench document={document} surface={definition.surfaceTemplate} disabled={disabled} previewState={previewState} componentCatalog={catalog} pendingFields={pendingFields} onPreviewStateChange={onPreviewStateChange} onChange={onChange} onPendingChange={onPendingChange} onApplyPending={onApplyPending} onDiscardPending={onDiscardPending} getPendingConflict={getPendingConflict} /> : <div className="notice warning">Surface template 结构不可用；已保留原值，请重新加载草稿后核对。</div>}
      <Section title="Action policies">
        {Array.isArray(actions) ? actions.map((row: unknown, index) => isEditableRecord(row) ? <div className="form-row action-row" key={actionKeys.keys[index]}>
          {['actionName', 'sourceComponentId', 'successPolicyRef'].map((field) => <Field key={field} label={field} value={row[field]} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['definition', 'actionPolicies'], index, field, value))} />)}
          <ReleaseReferencePicker label="abilityReleaseRef" value={row.abilityReleaseRef} disabled={disabled} references={references} onChange={(value) => onChange(updateRow(document, ['definition', 'actionPolicies'], index, 'abilityReleaseRef', value))} />
          {typeof row.completeInteractionOnSuccess === 'boolean' || row.completeInteractionOnSuccess === undefined ? <label className="checkbox-field"><input type="checkbox" checked={row.completeInteractionOnSuccess === true} disabled={disabled} onChange={(event) => onChange(updateRow(document, ['definition', 'actionPolicies'], index, 'completeInteractionOnSuccess', event.target.checked))} />completeInteractionOnSuccess</label> : <MalformedValue label={`actionPolicies[${index}].completeInteractionOnSuccess`} value={row.completeInteractionOnSuccess} />}
          <div className="fixed-policy">固定安全策略：controlRequestDedupeOnly={String(row.controlRequestDedupeOnly)} · businessIdempotencyOwner={String(row.businessIdempotencyOwner)}</div>
          <RowActions index={index} length={actions.length} disabled={disabled} onMove={(direction) => { actionKeys.move(index, direction); onChange(moveRow(document, ['definition', 'actionPolicies'], index, direction)); }} onRemove={() => { actionKeys.remove(index); onChange(removeRow(document, ['definition', 'actionPolicies'], index)); }} />
        </div> : <MalformedValue key={actionKeys.keys[index]} label={`actionPolicies[${index}]`} value={row} />) : <p className="field-feedback error">actionPolicies 不是数组。</p>}
        <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(actions)} onClick={() => onChange(appendRow(document, ['definition', 'actionPolicies'], { actionName: '', sourceComponentId: '', abilityReleaseRef: '', successPolicyRef: '', completeInteractionOnSuccess: true, controlRequestDedupeOnly: true, businessIdempotencyOwner: 'CALLED_API_BACKEND' }))}>添加 Action</button>
      </Section>
      <Section title="Dependencies">
        {Array.isArray(dependencies) ? dependencies.map((row: unknown, index) => isEditableRecord(row) ? <div className="form-row compact" key={dependencyKeys.keys[index]}><EnumSelect label="Kind" value={row.kind} options={['ABILITY', 'COMPONENT']} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['dependencies'], index, 'kind', value))} />{row.kind === 'ABILITY' ? <ReferencePicker label="Key" value={row.key} kind="ABILITY" disabled={disabled} references={references} onChange={(value) => onChange(updateRow(document, ['dependencies'], index, 'key', value))} /> : <Field label="Key" value={row.key} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['dependencies'], index, 'key', value))} />}<RowActions index={index} length={dependencies.length} disabled={disabled} onMove={(direction) => { dependencyKeys.move(index, direction); onChange(moveRow(document, ['dependencies'], index, direction)); }} onRemove={() => { dependencyKeys.remove(index); onChange(removeRow(document, ['dependencies'], index)); }} /></div> : <MalformedValue key={dependencyKeys.keys[index]} label={`dependencies[${index}]`} value={row} />) : <p className="field-feedback error">dependencies 不是数组。</p>}
        <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(dependencies)} onClick={() => onChange(appendRow(document, ['dependencies'], { kind: 'ABILITY', key: '' }))}>添加依赖</button>
      </Section>
      <JsonField label="Surface template" document={document} path={['definition', 'surfaceTemplate']} expected="object" disabled={disabled} pendingFields={pendingFields} onPendingChange={onPendingChange} onApply={onApplyPending} onDiscard={onDiscardPending} getConflict={getPendingConflict} />
      <Section title="固定策略（只读）"><pre className="resource-summary">{JSON.stringify({ interactionPolicy: definition.interactionPolicy, versionAdmissionPolicy: definition.versionAdmissionPolicy, retryPolicy: definition.retryPolicy, finalizerPolicy: definition.finalizerPolicy }, null, 2)}</pre></Section>
    </> : <>
      <MalformedValue label="definition" value={definition} />
      {pendingFields['definition.surfaceTemplate.inputSchema'] ? <JsonField label="Parameter schema" document={document} path={['definition', 'surfaceTemplate', 'inputSchema']} expected="object" disabled={disabled} pendingFields={pendingFields} onPendingChange={onPendingChange} onApply={onApplyPending} onDiscard={onDiscardPending} getConflict={getPendingConflict} /> : null}
      {pendingFields['definition.surfaceTemplate'] ? <JsonField label="Surface template" document={document} path={['definition', 'surfaceTemplate']} expected="object" disabled={disabled} pendingFields={pendingFields} onPendingChange={onPendingChange} onApply={onApplyPending} onDiscard={onDiscardPending} getConflict={getPendingConflict} /> : null}
    </>}
  </div>;
}
