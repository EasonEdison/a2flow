export type ResourceInspection =
  | { status: 'editable'; text: string; pendingDigestCheck?: boolean }
  | { status: 'verifying' | 'repair'; reason: string }
  | { status: 'readonly'; reason: string; integrity?: 'verified' };

export type PendingResourceText = { identity: string; base: string; text: string };

export function resourceIdentity(resource: unknown, index?: number): string;
export function resourceIdentityIssue(resource: unknown, resources: unknown[]): string | null;
export function pathIssue(path: unknown, resources?: unknown[], current?: unknown): string | null;
export function inspectResource(resource: unknown, allowInstruction?: boolean): ResourceInspection;
export function inspectResourceVerified(resource: unknown, allowInstruction?: boolean): Promise<ResourceInspection>;
export function pendingText(resource: unknown, text: string): PendingResourceText;
export function applyPendingText(resource: unknown, pending: PendingResourceText): Promise<{ resource?: Record<string, unknown>; error?: string }>;
export function mediaTypeForPath(path: string, browserType?: string): string | null;
export function createResource(input: { handleId: string; logicalPath: string; mediaType: string; bytes: Uint8Array; resources?: unknown[] }): Promise<Record<string, unknown>>;
export function createTextResource(input: { handleId: string; logicalPath: string; mediaType?: string; text: string; resources?: unknown[] }): Promise<Record<string, unknown>>;
export const MANAGEMENT_BODY_LIMIT: number;
export function saveBodyIssue(document: unknown): string | null;
export function checkPackage(resources: unknown): { issues: string[]; entries: number; totalBytes: number };
export function activateAsyncLifecycle(
  mounted: { current: boolean },
  operationSequence: { current: number },
  inspectionSequence: { current: number },
): () => void;
export function asyncTarget(assetId: string, revision: number, identity: string, sequence: number): string;
export function acceptsAsyncTarget(expected: string, current: string): boolean;
