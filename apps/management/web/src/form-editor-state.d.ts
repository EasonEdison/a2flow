export type DraftInspection =
  | { ok: true; text: string; document: Record<string, unknown> }
  | { ok: false; text: string; error: string };

export function inspectDraftText(text: string): DraftInspection;
export function isEditableRecord(value: unknown): value is Record<string, unknown>;
export function inspectPathEditability(document: any, path: string[]):
  | { editable: true }
  | { editable: false; blockedPath: string[] };
export function jsonFieldConflict(document: any, path: string[]): string | null;
export function hasPendingJsonField(document: any): boolean;
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
