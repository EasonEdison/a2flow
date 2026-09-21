import { appendRow, isEditableRecord, moveRow, removeRow, updateRow } from './form-editor-state';
import { EnumSelect, Field, JsonField, MalformedValue, RowActions, Section, useRowKeys, type FormProps } from './EditorControls';
import type { AbilityDraftDocument } from './asset-drafts';

export function AbilityEditor({ document, disabled, onChange, pendingFields, onPendingChange, onApplyPending, onDiscardPending, getPendingConflict }: FormProps<AbilityDraftDocument>) {
  const bindings = document.inputBindings;
  const credentials = document.credentialRequirements;
  const bindingKeys = useRowKeys(Array.isArray(bindings) ? bindings.length : 0);
  const credentialKeys = useRowKeys(Array.isArray(credentials) ? credentials.length : 0);
  return <div className="asset-form">
    <Section title="Identity 与适配">
      <Field label="Ability key" value={document.abilityKey} disabled={disabled} readOnly />
      <Field label="Adapter operation reference" value={document.adapterOperationRef} disabled={disabled} onChange={(value) => onChange({ ...document, adapterOperationRef: value })} />
      <Field label="Default success policy reference" value={document.defaultSuccessPolicyRef} disabled={disabled} onChange={(value) => onChange({ ...document, defaultSuccessPolicyRef: value })} />
    </Section>
    <Section title="Input bindings">
      {Array.isArray(bindings) ? bindings.map((row: unknown, index) => isEditableRecord(row) ? <div className="form-row" key={bindingKeys.keys[index]}>
        <Field label="Target path" value={row.targetPath} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['inputBindings'], index, 'targetPath', value))} />
        <EnumSelect label="Source" value={row.source} options={['MODEL_ARGUMENT', 'TRUSTED_CONTEXT']} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['inputBindings'], index, 'source', value))} />
        <Field label="Source path" value={row.sourcePath} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['inputBindings'], index, 'sourcePath', value))} />
        <RowActions index={index} length={bindings.length} disabled={disabled} onMove={(direction) => { bindingKeys.move(index, direction); onChange(moveRow(document, ['inputBindings'], index, direction)); }} onRemove={() => { bindingKeys.remove(index); onChange(removeRow(document, ['inputBindings'], index)); }} />
      </div> : <MalformedValue key={bindingKeys.keys[index]} label={`inputBindings[${index}]`} value={row} />) : <p className="field-feedback error">inputBindings 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(bindings)} onClick={() => onChange(appendRow(document, ['inputBindings'], { targetPath: '', source: 'MODEL_ARGUMENT', sourcePath: '' }))}>添加 binding</button>
    </Section>
    <Section title="Credential slot declarations">
      {Array.isArray(credentials) ? credentials.map((row: unknown, index) => isEditableRecord(row) ? <div className="form-row compact" key={credentialKeys.keys[index]}>
        <Field label="Slot ID（不填写真实凭据）" value={row.slotId} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['credentialRequirements'], index, 'slotId', value))} />
        {typeof row.required === 'boolean' || row.required === undefined ? <label className="checkbox-field"><input type="checkbox" checked={row.required === true} disabled={disabled} onChange={(event) => onChange(updateRow(document, ['credentialRequirements'], index, 'required', event.target.checked))} />必需</label> : <MalformedValue label={`credentialRequirements[${index}].required`} value={row.required} />}
        <RowActions index={index} length={credentials.length} disabled={disabled} onMove={(direction) => { credentialKeys.move(index, direction); onChange(moveRow(document, ['credentialRequirements'], index, direction)); }} onRemove={() => { credentialKeys.remove(index); onChange(removeRow(document, ['credentialRequirements'], index)); }} />
      </div> : <MalformedValue key={credentialKeys.keys[index]} label={`credentialRequirements[${index}]`} value={row} />) : <p className="field-feedback error">credentialRequirements 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(credentials)} onClick={() => onChange(appendRow(document, ['credentialRequirements'], { slotId: '', required: true }))}>添加 credential slot</button>
    </Section>
    {([
      ['Model argument schema', ['modelArgumentSchema'], 'object'],
      ['Resolved input schema', ['resolvedInputSchema'], 'object'],
      ['Output schema', ['outputSchema'], 'object'],
      ['Result interpretation policies', ['resultInterpretationPolicies'], 'array'],
    ] as const).map(([label, path, expected]) => <JsonField key={label} label={label} document={document} path={[...path]} expected={expected} disabled={disabled} pendingFields={pendingFields} onPendingChange={onPendingChange} onApply={onApplyPending} onDiscard={onDiscardPending} getConflict={getPendingConflict} />)}
  </div>;
}
