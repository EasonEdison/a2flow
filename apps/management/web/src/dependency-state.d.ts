import type { DependencyGraph } from './contracts';

export interface DependencyViewState {
  identity: string;
  requestId: number;
  loading: boolean;
  graph: DependencyGraph | null;
  error: string | null;
  stale: boolean;
  staleReason: string | null;
}

export function beginDependencyLoad(previous: DependencyViewState | null, identity: string): DependencyViewState;
export function settleDependencyLoad(
  state: DependencyViewState | null,
  identity: string,
  requestId: number,
  graph: DependencyGraph | null,
  error: string | null,
  staleReason?: string | null,
): DependencyViewState | null;
export function staleDependencyState(
  state: DependencyViewState | null,
  reason: string,
): DependencyViewState | null;
