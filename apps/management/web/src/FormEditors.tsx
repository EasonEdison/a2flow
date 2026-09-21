import type { ApplicationPreviewState } from './A2UIWorkbench';
import type { AssetKind, JsonObject, PendingResourceEdits, ReferenceCatalog } from './contracts';
import { inspectDraftText, type PendingFields } from './form-editor-state';
import { type PendingChange, type PendingConflict, type PendingDiscard, type PendingResolve } from './EditorControls';
import { AbilityEditor } from './AbilityEditor';
import { ApplicationEditor } from './ApplicationEditor';
import { SkillEditor } from './SkillEditor';
import { WorkflowEditor } from './WorkflowEditor';
import { ComponentEditor } from './ComponentEditor';
import {
  parseAbilityDraft,
  parseApplicationDraft,
  parseComponentDraft,
  parseSkillDraft,
  parseWorkflowDraft,
  type DraftStructureIssue,
} from './asset-drafts';

function StructureIssue({ issue }: { issue: DraftStructureIssue }) {
  return <div className="notice warning"><strong>草稿结构无法由表单安全编辑</strong>
    <span><code>{issue.path}</code> · {issue.message}</span>
    <span>原始值仍保存在数据库中。请先重新加载；若问题仍存在，由后端修复该字段结构。</span>
  </div>;
}

export function FormEditor({ skillStage, kind, text, disabled, pendingFields, pendingResources, assetId, revision, references, onNavigateReference, previewState, onPreviewStateChange, onEdit, onPendingChange, onApplyPending, onDiscardPending, onPendingResourcesChange, getPendingConflict }: {
  skillStage?: string;
  kind: AssetKind; text: string; disabled: boolean; pendingFields: PendingFields; pendingResources: PendingResourceEdits; assetId: string; revision: number; references: ReferenceCatalog; onNavigateReference?: (kind: AssetKind, key: string) => void; previewState?: ApplicationPreviewState; onPreviewStateChange?: (state: ApplicationPreviewState) => void; onEdit: (text: string) => void;
  onPendingChange: PendingChange; onApplyPending: PendingResolve; onDiscardPending: PendingDiscard; onPendingResourcesChange: (pending: PendingResourceEdits) => void; getPendingConflict: PendingConflict;
}) {
  const inspected = inspectDraftText(text);
  if (!inspected.ok) return <div className="notice warning"><strong>无法打开表单</strong><span>{inspected.error}</span><span>草稿内容已保留，请重新加载后核对。</span></div>;
  const onChange = (document: JsonObject) => onEdit(JSON.stringify(document, null, 2));
  const props = { skillStage, disabled, onChange, pendingFields, pendingResources, assetId, revision, references, onNavigateReference, previewState, onPreviewStateChange, onPendingChange, onApplyPending, onDiscardPending, onPendingResourcesChange, getPendingConflict };
  if (kind === 'SKILL') {
    const parsed = parseSkillDraft(inspected.document);
    return parsed.ok ? <SkillEditor {...props} document={parsed.document} /> : <StructureIssue issue={parsed.issue} />;
  }
  if (kind === 'ABILITY') {
    const parsed = parseAbilityDraft(inspected.document);
    return parsed.ok ? <AbilityEditor {...props} document={parsed.document} /> : <StructureIssue issue={parsed.issue} />;
  }
  if (kind === 'APPLICATION') {
    const parsed = parseApplicationDraft(inspected.document);
    return parsed.ok ? <ApplicationEditor {...props} document={parsed.document} /> : <StructureIssue issue={parsed.issue} />;
  }
  if (kind === 'WORKFLOW') {
    const parsed = parseWorkflowDraft(inspected.document);
    return parsed.ok ? <WorkflowEditor {...props} document={parsed.document} /> : <StructureIssue issue={parsed.issue} />;
  }
  const parsed = parseComponentDraft(inspected.document);
  return parsed.ok ? <ComponentEditor {...props} document={parsed.document} /> : <StructureIssue issue={parsed.issue} />;
}
