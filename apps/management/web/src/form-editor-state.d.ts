export type DraftInspection =
  | { ok: true; text: string; document: Record<string, unknown> }
  | { ok: false; text: string; error: string };

export function inspectDraftText(text: string): DraftInspection;
export function isEditableRecord(value: unknown): value is Record<string, unknown>;
export function inspectPathEditability(document: any, path: string[]):
  | { editable: true }
  | { editable: false; blockedPath: string[] };
export function jsonFieldConflict(document: any, path: string[]): string | null;
export type PendingField = {
  path: string[];
  text: string;
  expected: 'object' | 'array' | null;
  error: string | null;
  conflict: boolean;
  hasBase: boolean;
  baseValue?: unknown;
};
export type PendingFields = Record<string, PendingField>;

export function createPendingFieldState(): PendingFields;
export function editPendingField(pending: PendingFields, path: string[], text: string, expected?: 'object' | 'array', baseValue?: unknown): PendingFields;
export function pendingFieldConflict(pending: PendingFields, path: string[]): string | null;
export function applyPendingField(document: Record<string, unknown>, pending: PendingFields, path: string[], expected: 'object' | 'array'): { applied: boolean; document: Record<string, unknown>; pending: PendingFields };
export function discardPendingField(document: Record<string, unknown>, pending: PendingFields, path: string[]): { document: Record<string, unknown>; pending: PendingFields };
export function reconcilePendingFields(pending: PendingFields, document: Record<string, unknown>, previousDocument?: Record<string, unknown>): PendingFields;
export function parseJsonField(text: string, expected: 'object' | 'array'):
  | { ok: true; text: string; value: Record<string, unknown> | unknown[] }
  | { ok: false; text: string; error: string };
export function updatePath(document: any, path: string[], value: unknown): any;
export function updateRow(document: any, path: string[], index: number, field: string, value: unknown): any;
export function appendRow(document: any, path: string[], row: unknown): any;
export function removeRow(document: any, path: string[], index: number): any;
export function moveRow(document: any, path: string[], index: number, direction: number): any;
export function skillFrontmatterMismatch(document: any): string | null;
export function workflowTopologyWarning(document: any): string | null;
