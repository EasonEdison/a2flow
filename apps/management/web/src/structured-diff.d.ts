export type DiffKind = 'added' | 'removed' | 'changed' | 'type';
export interface DiffEntry {
  path: string;
  kind: DiffKind;
  before?: unknown;
  after?: unknown;
}
export function diffValues(before: unknown, after: unknown, path?: string): DiffEntry[];
