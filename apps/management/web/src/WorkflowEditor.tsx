import { appendRow, isEditableRecord, moveRow, removeRow, updateRow, workflowTopologyWarning } from './form-editor-state';
import { Field, MalformedValue, ReferencePicker, RowActions, Section, useRowKeys, type FormProps } from './EditorControls';
import type { WorkflowDraftDocument } from './asset-drafts';

export function WorkflowEditor({ document, disabled, onChange, references }: FormProps<WorkflowDraftDocument>) {
  const nodes = document.nodes;
  const warning = workflowTopologyWarning(document);
  const rowKeys = useRowKeys(Array.isArray(nodes) ? nodes.length : 0);
  return <div className="asset-form">
    {warning ? <div className="notice warning"><strong>当前拓扑不可发布</strong><span>{warning}</span></div> : null}
    <Section title="Workflow"><Field label="Definition key" value={document.definitionKey} disabled={disabled} readOnly /><Field label="Topology（只读，不会自动转换）" value={document.topology} disabled={disabled} readOnly /></Section>
    <Section title="Nodes">
      {Array.isArray(nodes) ? nodes.map((row: unknown, index) => isEditableRecord(row) ? <div className="form-row compact" key={rowKeys.keys[index]}>
        <Field label="Node ID" value={row.nodeId} disabled={disabled} onChange={(value) => onChange(updateRow(document, ['nodes'], index, 'nodeId', value))} />
        <ReferencePicker label="Skill key" value={row.skillKey} kind="SKILL" disabled={disabled} references={references} onChange={(value) => onChange(updateRow(document, ['nodes'], index, 'skillKey', value))} />
        <RowActions index={index} length={nodes.length} disabled={disabled} onMove={(direction) => { rowKeys.move(index, direction); onChange(moveRow(document, ['nodes'], index, direction)); }} onRemove={() => { rowKeys.remove(index); onChange(removeRow(document, ['nodes'], index)); }} />
      </div> : <MalformedValue key={rowKeys.keys[index]} label={`nodes[${index}]`} value={row} />) : <p className="field-feedback error">nodes 不是数组。</p>}
      <button className="secondary-button add-row" type="button" disabled={disabled || !Array.isArray(nodes)} onClick={() => onChange(appendRow(document, ['nodes'], { nodeId: '', skillKey: '' }))}>添加节点</button>
    </Section>
    <Section title="顺序预览"><ol className="sequence-preview">{Array.isArray(nodes) ? nodes.map((node: unknown, index) => <li key={rowKeys.keys[index]}><strong>{isEditableRecord(node) ? String(node.nodeId ?? '') : ''}</strong><span>{isEditableRecord(node) ? String(node.skillKey ?? '') : ''}</span></li>) : null}</ol></Section>
  </div>;
}
