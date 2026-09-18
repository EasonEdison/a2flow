export interface SurfaceIssue {
  code: string;
  path: string;
  message: string;
  componentId?: string;
  samplePath?: string;
}

export interface SurfaceNode {
  index: number;
  id: string | null;
  component: string | null;
  children: unknown[];
  supported: boolean;
  path: string;
}

export interface SurfaceAnalysis { nodes: SurfaceNode[]; issues: SurfaceIssue[] }
export interface SampleValidation { valid: boolean; issues: SurfaceIssue[] }
export interface PreviewResult { ok: boolean; issues: SurfaceIssue[]; root?: Record<string, unknown> | null }

export function analyzeSurface(surface: unknown): SurfaceAnalysis;
export function updateComponentProperty<T>(surface: T, index: number, path: string[], value: unknown): T;
export function moveComponent<T>(surface: T, index: number, direction: -1 | 1): T;
export function removeComponent<T>(surface: T, index: number): T;
export function addComponent<T>(surface: T, component: string): T;
export function validateSample(surface: unknown, sample: unknown): SampleValidation;
export function createPreview(surface: unknown, sample: unknown): PreviewResult;
export function simulateAction(surface: unknown, componentId: string, sample: unknown): Record<string, unknown> | null;
export const A2UI_COMPONENT_TYPES: readonly string[];
