import type { ApplicationPreviewState } from './A2UIWorkbench';
import type { AssetKind, JsonObject, ReferenceCatalog } from './contracts';
import { inspectDraftText, type PendingFields } from './form-editor-state';
import { type PendingChange, type PendingConflict, type PendingDiscard, type PendingResolve } from './EditorControls';
import { AbilityEditor } from './AbilityEditor';
import { ApplicationEditor } from './ApplicationEditor';
import { SkillEditor } from './SkillEditor';
import { WorkflowEditor } from './WorkflowEditor';

export function FormEditor({ kind, text, disabled, pendingFields, references, previewState, onPreviewStateChange, onEdit, onPendingChange, onApplyPending, onDiscardPending, getPendingConflict }: {
  kind: AssetKind; text: string; disabled: boolean; pendingFields: PendingFields; references: ReferenceCatalog; previewState?: ApplicationPreviewState; onPreviewStateChange?: (state: ApplicationPreviewState) => void; onEdit: (text: string) => void;
  onPendingChange: PendingChange; onApplyPending: PendingResolve; onDiscardPending: PendingDiscard; getPendingConflict: PendingConflict;
}) {
  const inspected = inspectDraftText(text);
  if (!inspected.ok) return <div className="notice warning"><strong>无法打开表单模式</strong><span>{inspected.error}</span><span>原始 JSON 已保留，请切回 JSON 模式修正。</span></div>;
  const onChange = (document: JsonObject) => onEdit(JSON.stringify(document, null, 2));
  const props = { document: inspected.document, disabled, onChange, pendingFields, references, previewState, onPreviewStateChange, onPendingChange, onApplyPending, onDiscardPending, getPendingConflict };
  if (kind === 'SKILL') return <SkillEditor {...props} />;
  if (kind === 'ABILITY') return <AbilityEditor {...props} />;
  if (kind === 'APPLICATION') return <ApplicationEditor {...props} />;
  return <WorkflowEditor {...props} />;
}
